"""V10 matched action objectives and policy-specific continuation values.

Retired final sets are never inputs. Existing V6 V5-continuation interventions
are reused; new interventions start from V5 roll-ins. No hidden-world online
search, no label imputation, and no final reselection.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import argparse, gzip, hashlib, json, random, time
import numpy as np
from .action_value import ActionValueNetwork, INPUT
from .network import Network
from .catalog import Spec, Effect, deck, semantic_key
from .profiles import base_deck, opponents, training_pool
from .policies import LearnedPolicy, ReferencePolicy, lethal
from .public_planner import PublicPlanner
from .counterfactual_research import sample_inputs, PrefixController, PrefixAgent, RollinRecorder, run, value_data
from .memory_research import read_rows, opponent
from .relational_research import small_result, value_metrics, paired_value_gain, phase_metrics
from .relational_model import RelationalNetwork
from .statistics import interval
from .training import dump, commit

BASE = Path('artifacts/card_eval/v5/primary-value.npz')
SOURCE = Path('artifacts/card_eval/v6')
ARMS = ('centered', 'pointwise')


def prepare(folder):
    if folder.exists():
        raise ValueError('Preserve experiment; select a new directory')
    folder.mkdir(parents=True)
    files = sorted(SOURCE.glob('train-targets-*.jsonl.gz')) + sorted(SOURCE.glob('diagnostic-targets-*.jsonl.gz')) + [BASE]
    d = dict(source_commit=commit(), baseline=str(BASE), rng_seed=2026103110, primary='centered',
        source_files={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        train_seeds=list(range(2670000, 2670128)), diagnostic_seeds=list(range(2680000, 2680032)),
        development_seeds=list(range(2690000, 2690012)), final_seeds=list(range(2870000, 2870032)),
        value_train_seeds=list(range(2700000, 2700192)), value_dev_seeds=list(range(2710000, 2710048)),
        value_final_seeds=list(range(2890000, 2890096)),
        forks_per_episode=2, max_actions=6, arms=ARMS, hidden=32, epochs=96, epoch_candidates=[16, 32, 64, 96],
        lr=.0015, l2=.001, batch_forks=64, margins=[0., .05, .1, .2], decision_seconds=.25,
        data='Reuse V6 current-V5 continuation branches only. Add128 training/32 diagnostic V5-on-policy openings, two stratum-sampled forks; old and new observations retain original provenance. No old game replay.',
        collection='Each fresh opening uses fixed V5 roll-in and one action then V5 continuation, equal race/board/guard/delayed opponents. Prefixes asserted equal. Sample end, V5 choice, kinds and remaining actions at most6. Future/private state never observed by the model.',
        objectives=dict(centered='2*episode-weighted squared centered sigmoid action-value residuals, all groups including flat outcomes',
                        pointwise='Episode-weighted binary cross entropy of sigmoid action values. Identical inputs, initialization, architecture, epoch/update budget and l2.'),
        representation='74 state summaries +50 legal known/seen summaries +81 public action relations +source/target current stats and ordered effect slots8. Hand slot removed from learned head; frozen V5 fallback retains original behavior. Missing knowledge/unknown op/overflow raises, never truncates.',
        selection='Each arm selects epoch by its own predeclared diagnostic objective excluding l2. Each arm selects margin using only fresh development lower win; ties larger. Primary arm fixed, never replace it after seeing results. Centered values not calibrated Q.',
        value_target='After centered actor frozen, fit74-feature logistic critic on192 fresh complete own-policy training trajectories; fixed l2=.01, compare same-data5parameter and inherited V5 critic on new96 final. Actor fingerprint unchanged. No critic-driven action/planning this round.',
        final_policies=['centered', 'pointwise', 'v5', 'v9_planner', 'guard'],
        acceptance='Zero unresolved and primary paired95%lower gain>0 against V5, matched pointwise, V9 planner and guard in every8 context. Report8context Bonferroni sensitivity. No final selection/default promotion.',
        final_cases=[c[0] for c in cases(True)],
        limits=['One training initialization; intervals exclude training variance', 'V5 rollout Q target is not the new greedy policy Q or Q*',
                'Ordered action source/target is not a sufficient whole-observation or belief representation',
                'Eight effect slots explicit model capacity, no arbitrary-length guarantee', 'Fixed opponent pool and heldout planner are not learned best responses',
                'Rule coverage unchanged; no real-server certification'],
        retired_final_starts=[1210000,1310000,1330000,1610000,1630000,1810000,1830000,2030000,2050000,2330000,2350000])
    dump(folder/'design.json', d)


def cases(final=False):
    own=base_deck(); other=opponents()
    standard=[('pressure',own,other['pressure'],('INTEGRITY','INTEGRITY'),'race'),
              ('defense',own,other['defense'],('INTEGRITY','KINDNESS'),'race'),
              ('refill',own,other['refill'],('KINDNESS','INTEGRITY'),'race')]
    if not final:
        return standard + [('role_failure',other['pressure'],other['refill'],('KINDNESS','INTEGRITY'),'guard'),
                           ('role_defense',other['defense'],other['pressure'],('INTEGRITY','KINDNESS'),'board')]
    param=Spec('v10_heldout_4G_7_10_armor',4,7,10,(('armor',1),),())
    combo=Spec('v10_heldout_haste_play_draw_end_growth',5,4,6,(('haste',1),),
               (Effect('play','draw','owner',1),Effect('end','buff','self',1,1)))
    if any(semantic_key(s) in {semantic_key(p) for p in training_pool()} for s in (param,combo)):
        raise ValueError('Heldout semantic overlap')
    a=list(own); a[:3]=[param]*3; b=list(own); b[:3]=[combo]*3
    ma=tuple(next(x for x in other['defense'] if x.name=='Sad Dragon') if s.name=='Aaron' else s for s in other['refill'])
    # Validate copy limits using semantic identity, not names.
    deck(list(ma))
    sweep=Spec('v10_sweeper',5,0,5,(),(Effect('play','damage','all_enemy',3),))
    counter=list(other['defense']);counter[:3]=[sweep]*3
    return standard+[('new_parameters',tuple(a),other['pressure'],('INTEGRITY','INTEGRITY'),'race'),
        ('new_composition',tuple(b),other['pressure'],('INTEGRITY','INTEGRITY'),'race'),
        ('new_mixed_decks',ma,other['defense'],('KINDNESS','KINDNESS'),'switching'),
        ('known_delayed_sweep',own,tuple(counter),('INTEGRITY','KINDNESS'),'delayed'),
        ('heldout_value_planner',own,other['pressure'],('INTEGRITY','KINDNESS'),'planner')]


def collect(folder, stage):
    path=folder/f'{stage}-forks.jsonl.gz'
    if path.exists():raise ValueError('Preserve new intervention data')
    d=json.loads((folder/'design.json').read_text()); net=Network.load(BASE)[0]
    rng=random.Random(d['rng_seed']+(stage=='diagnostic')); status=Counter(); started=time.monotonic()
    with gzip.open(folder/f'{stage}-rollins.jsonl.gz','wt') as rollins, gzip.open(path,'wt') as sink:
        for i,seed in enumerate(d[stage+'_seeds']):
            decks,souls,roles=sample_inputs(rng); style=('race','board','guard','delayed')[i%4]
            rollins.write(json.dumps(dict(record_type='input',seed=seed,decks=[[asdict(s) for s in ds] for ds in decks],
                souls=souls,roles=roles,seat=i%2,opponent=style,actor_fingerprint=net.actor_fingerprint))+'\n')
            rec=RollinRecorder(rollins,seed); r=run(decks,seed,(LearnedPolicy(net),opponent(style)),i%2,souls,rec)
            status['episodes']+=1;status['unfinished_rollins']+=r['unfinished']
            eligible=[j for j,row in enumerate(rec.rows) if row['observation']['player']==0 and len(row['legal_actions'])>1 and not lethal(row['observation'])[0]]
            chosen=[]
            for lo,hi in ((2,5),(6,12)):
                choices=[j for j in eligible if lo<=rec.rows[j]['observation']['turn']<=hi and j not in chosen]
                if not choices:choices=[j for j in eligible if j not in chosen]
                if choices:chosen.append(rng.choice(choices))
            for fork in chosen:
                row=rec.rows[fork];obs=row['observation'];actions=list(map(tuple,row['legal_actions']))
                anchor=LearnedPolicy(net).choose(obs,actions)['action_index'];indices={0,anchor}
                for kind in ('play','attack'):
                    choices=[j for j,a in enumerate(actions) if a[0]==kind]
                    if choices:indices.add(rng.choice(choices))
                rest=[j for j in range(len(actions)) if j not in indices];rng.shuffle(rest)
                indices.update(rest[:max(0,d['max_actions']-len(indices))]);branches=[]
                for index in sorted(indices):
                    controller=PrefixController(rec.rows,fork,actions[index],(LearnedPolicy(net),opponent(style)))
                    b=run(decks,seed,(PrefixAgent(controller),PrefixAgent(controller)),i%2,souls)
                    if not controller.checked and not b['unfinished']:raise ValueError('Intervention prefix not reached')
                    status['branches']+=1;status['prefix_matches']+=controller.checked;status['unknown_branches']+=b['unfinished']
                    branches.append(dict(action_index=index,continuation='current',won=b['won'],unfinished=b['unfinished'],error=b.get('error')))
                sink.write(json.dumps(dict(seed=seed,decision=fork,observation=obs,legal_actions=actions,
                    baseline_action=anchor,branches=branches,provenance='fresh_V5_on_policy'),separators=(',',':'))+'\n')
                status['forks']+=1
            if (i+1)%32==0:
                report=dict(status,elapsed_seconds=time.monotonic()-started);dump(folder/f'{stage}-progress.json',report);print(json.dumps(report),flush=True)
    dump(folder/f'{stage}-collection.json',dict(status,elapsed_seconds=time.monotonic()-started,source_commit=commit()))


def raw_rows(folder,stage):
    oldstage='diagnostic' if stage=='diagnostic' else 'train'
    for path in sorted(SOURCE.glob(f'{oldstage}-targets-*.jsonl.gz')):
        for row in read_rows(path):yield dict(row,provenance=str(path))
    yield from read_rows(folder/f'{stage}-forks.jsonl.gz')


def cache(folder,stage):
    path=folder/f'action-{stage}.npz'
    if path.exists():return dict(np.load(path,allow_pickle=False))
    net=ActionValueNetwork(Network.load(BASE)[0]); groups=[]; counts=Counter()
    for row in raw_rows(folder,stage):
        bs=[b for b in row['branches'] if b['continuation']=='current']
        if not bs or any(b['unfinished'] for b in bs):counts['unknown_groups']+=1;continue
        ids=[b['action_index'] for b in bs]
        if len(ids)!=len(set(ids)) or row['baseline_action'] not in ids:raise ValueError('Missing/duplicate current anchor')
        _,(x,_)=net.encode(row['observation'],list(map(tuple,row['legal_actions'])))
        groups.append((row['seed'],x[ids],np.asarray([int(b['won']) for b in bs])))
        counts['fresh_groups' if row['provenance']=='fresh_V5_on_policy' else 'reused_groups']+=1
        counts['contrast_groups']+=bool(np.ptp(groups[-1][2]));counts['action_labels']+=len(bs)
    sizes=Counter(s for s,_,_ in groups);x=[];ys=[];gs=[];seeds=[];weights=[]
    for i,(seed,xx,y) in enumerate(groups):
        x.extend(xx);ys.extend(y);gs.extend([i]*len(y));seeds.extend([seed]*len(y));weights.extend([1/(sizes[seed]*len(y))]*len(y))
    data=dict(x=np.asarray(x,np.float32),y=np.asarray(ys),groups=np.asarray(gs),seeds=np.asarray(seeds),weights=np.asarray(weights))
    np.savez_compressed(path,**data)
    dump(folder/f'{stage}-input.json',dict(counts,openings=len(sizes),features=INPUT,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return data


def metrics(net,data):
    q=net.batch(data['x'])[0];w=data['weights']/data['weights'].sum();res=q-data['y'];center=res.copy()
    for g in np.unique(data['groups']):
        mask=data['groups']==g;center[mask]-=center[mask].mean()
    return dict(centered_mse=float(w@center**2),brier=float(w@res**2),
        nll=float(-w@(data['y']*np.log(np.clip(q,1e-10,1))+(1-data['y'])*np.log(np.clip(1-q,1e-10,1)))))


def fit(folder):
    if (folder/'fit.json').exists():raise ValueError('Preserve fit')
    d=json.loads((folder/'design.json').read_text())
    for path,digest in d['source_files'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Reusable source changed')
    train=cache(folder,'train');dev=cache(folder,'diagnostic');report={}
    unique=np.unique(train['groups']);indices={g:np.where(train['groups']==g)[0] for g in unique}
    for arm in ARMS:
        net=ActionValueNetwork(Network.load(BASE)[0],arm,d['rng_seed'],d['hidden']);rng=np.random.default_rng(d['rng_seed'])
        m={k:np.zeros_like(p) for k,p in net.p.items()};v=deepcopy(m);step=0;curve=[]
        for epoch in range(1,d['epochs']+1):
            order=rng.permutation(unique)
            for start in range(0,len(order),d['batch_forks']):
                ix=np.concatenate([indices[g] for g in order[start:start+d['batch_forks']]])
                _,grads=net.loss_grad(train['x'][ix],train['y'][ix],train['groups'][ix],train['weights'][ix],d['l2']);step+=1
                norm=np.sqrt(sum(np.sum(g*g) for g in grads.values()));scale=min(1.,5/max(norm,1e-12))
                for k,g in grads.items():
                    g=g*scale;m[k]=.9*m[k]+.1*g;v[k]=.999*v[k]+.001*g*g
                    net.p[k]-=d['lr']*(m[k]/(1-.9**step))/(np.sqrt(v[k]/(1-.999**step))+1e-8)
            if epoch in d['epoch_candidates']:
                result=dict(epoch=epoch,train=metrics(net,train),diagnostic=metrics(net,dev));curve.append(result)
                net.save(folder/f'{arm}-epoch-{epoch:03}.npz',dict(value_unfitted=True,validation=dict(qualified=False),source_commit=commit()))
                print(json.dumps(dict(arm=arm,**result)),flush=True)
        key='centered_mse' if arm=='centered' else 'nll';selected=min(curve,key=lambda r:(r['diagnostic'][key],r['epoch']))['epoch']
        chosen=Network.load(folder/f'{arm}-epoch-{selected:03}.npz')[0]
        chosen.save(folder/f'{arm}-action.npz',dict(value_unfitted=True,validation=dict(qualified=False),source_commit=commit()))
        report[arm]=dict(selected_epoch=selected,parameters=chosen.parameters,curve=curve,actor_fingerprint=chosen.actor_fingerprint)
    dump(folder/'fit.json',dict(arms=report,source_commit=commit()))


def development(folder):
    if (folder/'development.json').exists():raise ValueError('Preserve development')
    d=json.loads((folder/'design.json').read_text());output={}
    with gzip.open(folder/'development-games.jsonl.gz','wt') as sink:
        for arm in ARMS:
            net=Network.load(folder/f'{arm}-action.npz')[0];records=[]
            for margin in d['margins']:
                net.margin=margin;scores=[];unfinished=0
                for group,a,b,souls,style in cases():
                    for seed in d['development_seeds']:
                        r=run((a,b),seed,(LearnedPolicy(net),opponent(style)),seed%2,souls)
                        sink.write(json.dumps(dict(arm=arm,margin=margin,group=group,seed=seed,result=small_result(r)),separators=(',',':'))+'\n')
                        scores.append(0 if r['unfinished'] else int(r['won']));unfinished+=r['unfinished']
                records.append(dict(margin=margin,lower=float(np.mean(scores)),unfinished=unfinished,slots=len(scores)))
                print(json.dumps(dict(arm=arm,**records[-1])),flush=True)
            margin=max(records,key=lambda r:(r['lower'],r['margin']))['margin'];net.margin=margin
            net.save(folder/f'{arm}-selected.npz',dict(value_unfitted=True,validation=dict(qualified=False),source_commit=commit()))
            output[arm]=dict(records=records,selected_margin=margin,actor_fingerprint=net.actor_fingerprint)
    dump(folder/'development.json',dict(arms=output,source_commit=commit(),primary='centered',no_final_selection=True))


def value(folder):
    if (folder/'value.json').exists():raise ValueError('Preserve critic fit')
    d=json.loads((folder/'design.json').read_text());net=Network.load(folder/'centered-selected.npz')[0]
    train=value_data(folder,net,'train',d['value_train_seeds']);x=[];y=[];w=[]
    for e in train:
        if not e['terminal']:continue
        x.extend(e['states']);y.extend([int(e['won'])]*len(e['states']));w.extend([1/len(e['states'])]*len(e['states']))
    before=net.actor_fingerprint;fit=net.fit_value(x,y,w,l2=.01);prior=float(np.mean([e['won'] for e in train if e['terminal']]))
    net.save(folder/'primary-value.npz',dict(value_unfitted=False,validation=dict(qualified=False),source_commit=commit(),critic_actor_fingerprint=before,
        target='Frozen centered actor continuation under declared training opponent/deck distribution; not Q* or searched-policy V'))
    simple=RelationalNetwork();states=np.asarray(x)
    reduced=np.c_[np.ones(len(states)),states[:,1]-states[:,2],states[:,26]-states[:,39],states[:,27]-states[:,40],states[:,8]-states[:,9]]
    sf=simple.fit_value(reduced,y,w,l2=.01);beta=simple.critic.copy();simple.critic=np.zeros(74);simple.critic[0]=beta[0]
    for c,(pos,neg) in zip(beta[1:],((1,2),(26,39),(27,40),(8,9))):simple.critic[pos]=c;simple.critic[neg]=-c
    simple.save(folder/'value-simple.npz',dict(validation=dict(qualified=False),target_actor_fingerprint=before))
    dev=value_data(folder,net,'dev',d['value_dev_seeds'])
    dump(folder/'value.json',dict(source_commit=commit(),fit=fit,simple_fit=sf,train_prior=prior,actor_unchanged=net.actor_fingerprint==before,
        train_openings=len(train),train_unresolved=sum(not e['terminal'] for e in train),train_states=len(x),
        development=value_metrics(net,dev,prior),simple_development=value_metrics(simple,dev,prior),gain_vs_simple=paired_value_gain(net,simple,dev)))


def final(folder):
    if (folder/'final-games.jsonl.gz').exists():raise ValueError('Final is single use')
    d=json.loads((folder/'design.json').read_text());nets=dict(centered=Network.load(folder/'primary-value.npz')[0],
        pointwise=Network.load(folder/'pointwise-selected.npz')[0],v5=Network.load(BASE)[0],
        v9=Network.load('artifacts/card_eval/v9/entity-value.npz')[0])
    def agent(name):
        if name=='guard':return ReferencePolicy('guard')
        if name=='v9_planner':return PublicPlanner(nets['v9'],'value',.2,nodes=48,depth=3,width=4,seconds=.12)
        return LearnedPolicy(nets[name])
    def enemy(style):
        return PublicPlanner(Network.load('artifacts/card_eval/v7/afterstate-value.npz')[0],'value',.3,nodes=48,depth=3,width=4,seconds=.12) if style=='planner' else opponent(style)
    dump(folder/'final-plan.json',dict(source_commit=commit(),policies={n:getattr(agent(n),'fingerprint',getattr(agent(n),'network',None).fingerprint if hasattr(agent(n),'network') else n) for n in d['final_policies']},
        actor_fingerprint=nets['centered'].actor_fingerprint,seeds=d['final_seeds'],
        cases=[dict(group=g,decks=[[asdict(s) for s in ds] for ds in (a,b)],souls=ss,opponent=p) for g,a,b,ss,p in cases(True)]))
    groups=[];failures=[]
    with gzip.open(folder/'final-games.jsonl.gz','wt') as sink:
        for group,a,b,souls,style in cases(True):
            scores={n:[] for n in d['final_policies']};times={n:[] for n in scores}
            for seed in d['final_seeds']:
                seats={n:[] for n in scores}
                for seat in (0,1):
                    for name in scores:
                        r=run((a,b),seed,(agent(name),enemy(style)),seat,souls)
                        sink.write(json.dumps(dict(group=group,seed=seed,seat=seat,policy=name,result=small_result(r)),separators=(',',':'))+'\n')
                        seats[name].append(None if r['unfinished'] else int(r['won']));times[name].extend(r['decision_seconds'][0])
                        if r['unfinished']:failures.append(dict(group=group,seed=seed,seat=seat,policy=name,error=r.get('error')))
                for name in scores:
                    scores[name].append((np.mean([0 if r is None else r for r in seats[name]]),np.mean([1 if r is None else r for r in seats[name]])))
            lo,hi=np.asarray(scores['centered']).T;cs=[]
            for name in scores:
                a0,b0=np.asarray(scores[name]).T
                cs.append(dict(policy=name,win=interval(a0,b0),primary_gain=interval(lo-b0,hi-a0),family_gain=interval(lo-b0,hi-a0,alpha=.05/8)))
            groups.append(dict(group=group,policies=cs,timings={n:dict(decisions=len(t),p95=float(np.quantile(t,.95)) if t else None,maximum=max(t) if t else None) for n,t in times.items()}))
            dump(folder/'final-progress.json',dict(groups=groups,failures=failures))
            print(json.dumps(dict(group=group,wins={c['policy']:c['win']['completion_range'] for c in cs})),flush=True)
    qualified=not failures and all(c['primary_gain']['low']>0 for g in groups for c in g['policies'] if c['policy']!='centered')
    dump(folder/'final.json',dict(source_commit=commit(),qualified=qualified,groups=groups,failures=failures,no_final_selection=True))
    dump(folder/'validation.json',dict(qualified=qualified,status='qualified' if qualified else 'not_qualified',frozen_policy=nets['centered'].fingerprint,
        default_model_replaced=False,source='final.json'))
    val=value_data(folder,nets['centered'],'final',d['value_final_seeds']);simple=Network.load(folder/'value-simple.npz')[0]
    prior=json.loads((folder/'value.json').read_text())['train_prior']
    dump(folder/'value-final.json',dict(source_commit=commit(),actor_fingerprint=nets['centered'].actor_fingerprint,
        primary=value_metrics(nets['centered'],val,prior),simple=value_metrics(simple,val,prior),stale_v5=value_metrics(nets['v5'],val,prior),
        gain_vs_simple=paired_value_gain(nets['centered'],simple,val),gain_vs_stale_v5=paired_value_gain(nets['centered'],nets['v5'],val),
        phases=phase_metrics(nets['centered'],val,prior),no_final_selection=True))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','collect','fit','development','value','final']);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--stage',choices=['train','diagnostic']);a=p.parse_args()
    if a.mode=='collect':collect(a.output,a.stage)
    else:globals()[a.mode](a.output)
