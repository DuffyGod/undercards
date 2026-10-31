"""Reuse V5 forks; distinguish legal knowledge from continuation targets."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import argparse,gzip,hashlib,json,random,time
import numpy as np
from .knowledge import Knowledge,vector,STATE_DIM
from .memory_model import MemoryNetwork,encode,head_features
from .network import Network
from .policies import LearnedPolicy,ReferencePolicy
from .catalog import Spec,Effect,semantic_key
from .profiles import base_deck,opponents,training_pool
from .training import dump,commit,decode
from .counterfactual_research import PrefixController,PrefixAgent,run,sample_inputs,DelayedSweepPolicy
from .relational_research import ValueRecorder,value_metrics,phase_metrics,paired_value_gain,small_result
from .relations import state_features
from .statistics import interval

SOURCE=Path('artifacts/card_eval/v5')
BASELINE=SOURCE/'primary-value.npz'
ARMS=('plain_mixed','known_mixed','plain_current','known_current')


def prepare(folder):
    if folder.exists() and set(p.name for p in folder.iterdir())!={'METHOD.md'}:raise ValueError('Preserve experiment')
    files=sorted(SOURCE.glob('*-forks-*.jsonl.gz'))+sorted(SOURCE.glob('*-rollins-*.jsonl.gz'))
    folder.mkdir(parents=True,exist_ok=True)
    dump(folder/'design.json',dict(source_commit=commit(),baseline=str(BASELINE),
        source_files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        data='Reuse V5 training/diagnostic worlds and public prefixes. New V5 continuation only; reuse existing V4/race outcomes, add missing V5 baseline action with all necessary continuations. Not new independent openings.',
        arms=ARMS,primary='known_current',l2=.01,iterations=160,margins=[0.,.05,.1],
        selection='Primary arm fixed before data. Choose its margin by mean development win only, ties larger margin. Other arms .05 diagnostics; no final arm reselection.',
        development_seeds=list(range(1750000,1750016)),final_seeds=list(range(1810000,1810064)),
        value_train_seeds=list(range(1060000,1060384)),value_dev_seeds=list(range(1160000,1160096)),value_final_seeds=list(range(1830000,1830096)),
        source_train_seeds=list(range(1040000,1040384)),source_diagnostic_seeds=list(range(1140000,1140096)),
        information='Owner initial deck multiset and actually played cards on both sides only. No opponent unseen descriptors, hand, order or seed in model inputs. Summaries are not a belief state.',
        acceptance='Every final context paired95%lower above V5 and race/board/guard; no unresolved slots. No final tuning.',
        decision_seconds=.25,value_l2=.01,value_baselines=['same actor, old74 public features','same actor, five HP/board/deck differences'],
        final_cases=[c[0] for c in cases(True)],limitations=['One training seed','Old roll-in state distribution reused','New actor still differs from frozen continuation','Known/seen bag is not sufficient history','Supported rules unchanged']))


def read_rows(path):
    with gzip.open(path,'rt',encoding='utf-8') as stream:
        for line in stream:yield json.loads(line)


def augmented_episodes(stage):
    for path in sorted(SOURCE.glob(f'{stage}-rollins-*.jsonl.gz')):
        metadata=None;records=[];knowledge=None
        for row in read_rows(path):
            if row['record_type']=='input':
                metadata=row;records=[];knowledge=Knowledge(row['decks'])
            elif row['record_type']=='decision':
                row=deepcopy(row);actor=row['observation']['player'];row['observation'].update(knowledge.fields(actor));records.append(row)
                action=row['selection']['action']
                if action[0]=='play':
                    source=next(h for h in row['observation']['hand'] if h['uid']==action[1]);knowledge.observe_play(actor,source)
            else:yield metadata,records


def collect(folder,stage):
    if (folder/f'{stage}-collection.json').exists() or list(folder.glob(f'{stage}-targets-*.jsonl.gz')):raise ValueError('Preserve targets')
    d=json.loads((folder/'design.json').read_text())
    for name,digest in d['source_files'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:raise ValueError('Frozen reusable input changed')
    current=Network.load(BASELINE)[0];old=Network.load('artifacts/card_eval/v4/primary-value.npz')[0]
    forks={}
    for path in sorted(SOURCE.glob(f'{stage}-forks-*.jsonl.gz')):
        for row in read_rows(path):forks.setdefault(row['seed'],[]).append(row)
    status=dict(source_commit=commit(),stage=stage,episodes=0,forks=0,new_branches=0,unresolved=0,prefix_matches=0);started=time.monotonic()
    sink=None
    try:
        for episode,(meta,records) in enumerate(augmented_episodes(stage)):
            if episode%32==0:
                if sink:sink.close()
                sink=gzip.open(folder/f'{stage}-targets-{episode:04}.jsonl.gz','wt',encoding='utf-8')
            decks=tuple(tuple(decode(s) for s in deck) for deck in meta['decks'])
            for source in forks[meta['seed']]:
                row=records[source['decision']];obs=row['observation'];actions=list(map(tuple,row['legal_actions']))
                anchor=LearnedPolicy(current).choose(obs,actions)['action_index'];indices=sorted(set(source['sampled_action_indices'])|{anchor})
                results=[dict(b,continuation='old' if b['continuation']=='baseline' else 'race') for b in source['branches']]
                for index in indices:
                    names=['current']+(['old','race'] if index not in source['sampled_action_indices'] else [])
                    for name in names:
                        a=LearnedPolicy(current if name=='current' else old) if name!='race' else ReferencePolicy('race')
                        controller=PrefixController(records,source['decision'],actions[index],(a,ReferencePolicy(meta['opponent'])))
                        r=run(decks,meta['seed'],(PrefixAgent(controller),PrefixAgent(controller)),meta['seat'],meta['souls'])
                        if not controller.checked and not r['unfinished']:raise ValueError('Intervention not reached')
                        status['new_branches']+=1;status['unresolved']+=r['unfinished'];status['prefix_matches']+=controller.checked
                        results.append(dict(action_index=index,continuation=name,won=r['won'],lost=r['lost'],unfinished=r['unfinished'],error=r.get('error')))
                out=dict(seed=meta['seed'],decision=source['decision'],observation=obs,legal_actions=actions,indices=indices,
                    baseline_action=anchor,branches=results,source_old_indices=source['sampled_action_indices'])
                sink.write(json.dumps(out,separators=(',',':'))+'\n');status['forks']+=1
            status['episodes']+=1
            if (episode+1)%32==0:
                status['elapsed_seconds']=time.monotonic()-started;dump(folder/f'{stage}-progress.json',status);print(json.dumps(status),flush=True)
    finally:
        if sink:sink.close()
    dump(folder/f'{stage}-collection.json',status)


def data(folder,stage,arm):
    known=arm.startswith('known');current=arm.endswith('current');output=[]
    for path in sorted(folder.glob(f'{stage}-targets-*.jsonl.gz')):
        for row in read_rows(path):
            if any(b['unfinished'] for b in row['branches']):continue
            s,a=encode(row['observation'],list(map(tuple,row['legal_actions'])),known);indices=row['indices'];targets=[]
            for index in indices:
                names=('current',) if current else ('old','race')
                bs=[b for b in row['branches'] if b['action_index']==index and b['continuation'] in names]
                if len(bs)!=len(names):raise ValueError('Missing action target, do not impute')
                targets.append(np.mean([float(b['won']) for b in bs]))
            output.append((head_features(s,a)[indices],np.asarray(targets),row))
    return output


def fit(folder):
    if (folder/'fit.json').exists():raise ValueError('Preserve fit')
    d=json.loads((folder/'design.json').read_text());reports={}
    for arm in ARMS:
        values=data(folder,'train',arm);net=MemoryNetwork(Network.load(BASELINE)[0],use_memory=arm.startswith('known'))
        report=net.fit_advantage([(x,y) for x,y,_ in values],d['l2'],d['iterations'])
        net.save(folder/(arm+'.npz'),dict(source_commit=commit(),fit=report,validation=dict(qualified=False),arm=arm,value_unfitted=True))
        reports[arm]=dict(fit=report,contrast_groups=int(sum(np.ptp(y)>0 for _,y,_ in values)),fingerprint=net.fingerprint)
        print(json.dumps(dict(arm=arm,**reports[arm])),flush=True)
        dump(folder/'fit-progress.json',reports)
    dump(folder/'fit.json',dict(source_commit=commit(),arms=reports))


class SwitchingPolicy:
    name='public_hp_switch_race_guard'
    def choose(self,obs,actions):return ReferencePolicy('guard' if obs['hp']<obs['enemy_hp'] else 'race').choose(obs,actions)


def cases(final=False):
    own=base_deck();opp=opponents()
    standard=[('pressure',own,opp['pressure'],('INTEGRITY','INTEGRITY'),'race'),
              ('defense',own,opp['defense'],('INTEGRITY','KINDNESS'),'race'),
              ('refill',own,opp['refill'],('KINDNESS','INTEGRITY'),'race')]
    if not final:return standard+[('known_role_failure',opp['pressure'],opp['refill'],('KINDNESS','INTEGRITY'),'guard'),
                                 ('role_defense',opp['defense'],opp['pressure'],('INTEGRITY','KINDNESS'),'board')]
    param=Spec('unseen_4G_6_11_taunt',4,6,11,(('taunt',1),),())
    combo=Spec('unseen_haste_armor',5,5,6,(('haste',1),('armor',1)),())
    pool={semantic_key(s) for s in training_pool()}
    if semantic_key(param) in pool or semantic_key(combo) in pool:raise ValueError('Final semantics overlap pool')
    a=list(own);a[:3]=[param]*3;b=list(own);b[:3]=[combo]*3
    sweep=Spec('synthetic_sweeper',5,0,5,(),(Effect('play','damage','all_enemy',3),));counter=list(opp['defense']);counter[:3]=[sweep]*3
    return standard+[('new_parameters',tuple(a),opp['pressure'],('INTEGRITY','INTEGRITY'),'race'),
        ('new_composition',tuple(b),opp['pressure'],('INTEGRITY','INTEGRITY'),'race'),
        ('new_structure',opp['defense'],opp['refill'],('KINDNESS','KINDNESS'),'race'),
        ('known_delayed_sweep',own,tuple(counter),('INTEGRITY','KINDNESS'),'delayed'),
        ('unseen_switching',own,opp['pressure'],('INTEGRITY','KINDNESS'),'switching')]


def opponent(name):return DelayedSweepPolicy() if name=='delayed' else SwitchingPolicy() if name=='switching' else ReferencePolicy(name)


def development(folder):
    if (folder/'selection.json').exists():raise ValueError('Preserve selection')
    d=json.loads((folder/'design.json').read_text());items=[(arm,.05) for arm in ARMS]+[(d['primary'],m) for m in d['margins'] if m!=.05];output=[]
    with gzip.open(folder/'development-games.jsonl.gz','wt',encoding='utf-8') as sink:
        for arm,margin in items:
            net=Network.load(folder/(arm+'.npz'))[0];net.margin=margin;wins=[]
            for group,a,b,souls,style in cases():
                for seed in d['development_seeds']:
                    r=run((a,b),seed,(LearnedPolicy(net),opponent(style)),seed%2,souls)
                    wins.append(0 if r['unfinished'] else float(r['won']));sink.write(json.dumps(dict(arm=arm,margin=margin,group=group,seed=seed,result=small_result(r)),separators=(',',':'))+'\n')
            output.append(dict(arm=arm,margin=margin,mean_win_lower=float(np.mean(wins))));print(json.dumps(output[-1]),flush=True)
    chosen=max((r for r in output if r['arm']==d['primary']),key=lambda r:(r['mean_win_lower'],r['margin']))
    net=Network.load(folder/(d['primary']+'.npz'))[0];net.margin=chosen['margin']
    net.save(folder/'selected-actor.npz',dict(source_commit=commit(),validation=dict(qualified=False),value_unfitted=True))
    dump(folder/'selection.json',dict(source_commit=commit(),primary=d['primary'],selected_margin=net.margin,candidates=output,actor_fingerprint=net.actor_fingerprint,selection=d['selection']))


def diagnostic(folder):
    if (folder/'diagnostic.json').exists():raise ValueError('Preserve diagnostic')
    selection=json.loads((folder/'selection.json').read_text());output={}
    for arm in ARMS:
        net=Network.load(folder/('selected-actor.npz' if arm==selection['primary'] else arm+'.npz'))[0]
        values=data(folder,'diagnostic',arm);errors=[];zero=[];bounds={};missing=0;changed=0
        for x,y,row in values:
            prediction=x@net.advantage;errors.append(float(np.mean(((prediction-prediction.mean())-(y-y.mean()))**2)));zero.append(float(np.mean((y-y.mean())**2)))
            actions=list(map(tuple,row['legal_actions']));chosen=LearnedPolicy(net).choose(row['observation'],actions)['action_index'];base=row['baseline_action'];changed+=chosen!=base
            current={b['action_index']:float(b['won']) for b in row['branches'] if b['continuation']=='current'}
            if chosen in current:lo=hi=current[chosen]-current[base]
            else:lo,hi=-current[base],1-current[base];missing+=1
            bounds.setdefault(row['seed'],[]).append((lo,hi))
        clustered=[np.mean(v,axis=0) for v in bounds.values()]
        output[arm]=dict(groups=len(values),centered_mse=float(np.mean(errors)),zero_mse=float(np.mean(zero)),changed=changed,unmeasured_choices=missing,
            common_v5_continuation_gain=interval(*np.asarray(clustered).T),scope='Actual all-legal choice; unmeasured actions retain 0/1 return bounds. Cluster by old source opening; no new independent openings.')
    dump(folder/'diagnostic.json',dict(source_commit=commit(),arms=output,selection_used=False))


class MemoryValueRecorder(ValueRecorder):
    def record(self,obs,actions,selected):
        super().record(obs,actions,selected)
        if obs['player']==0:self.states[-1]=np.r_[state_features(obs),vector(obs)]


def value_data(folder,net,stage,seeds):
    rng=random.Random(20261031060+{'train':0,'dev':1,'final':2}[stage]);output=[]
    for start in range(0,len(seeds),64):
        with gzip.open(folder/f'value-{stage}-{start:04}.jsonl.gz','wt',encoding='utf-8') as sink:
            for i,seed in enumerate(seeds[start:start+64],start):
                decks,souls,roles=sample_inputs(rng);style=('race','board','guard')[i%3]
                rec=MemoryValueRecorder(sink,seed,dict(seed=seed,decks=[[asdict(s) for s in deck] for deck in decks],souls=souls,roles=roles,seat=i%2,opponent=style,actor_fingerprint=net.actor_fingerprint))
                r=run(decks,seed,(LearnedPolicy(net),ReferencePolicy(style)),i%2,souls,rec)
                output.append(dict(seed=seed,states=rec.states,terminal=not r['unfinished'],won=r['won']))
    return output


def value(folder):
    if (folder/'value.json').exists() or list(folder.glob('value-*.jsonl.gz')):raise ValueError('Preserve value')
    d=json.loads((folder/'design.json').read_text());net=Network.load(folder/'selected-actor.npz')[0];train=value_data(folder,net,'train',d['value_train_seeds'])
    xs=[];ys=[];weights=[]
    for e in train:
        if not e['terminal']:continue
        xs.extend(e['states']);ys.extend([float(e['won'])]*len(e['states']));weights.extend([1/len(e['states'])]*len(e['states']))
    xs=np.asarray(xs);before=net.actor_fingerprint;report=net.fit_value(xs,ys,weights,l2=d['value_l2']);assert before==net.actor_fingerprint
    net.save(folder/'primary-value.npz',dict(source_commit=commit(),validation=dict(qualified=False),value_target='Own frozen actor under declared structured decks and equal race/board/guard.'))
    others={};fit_reports={}
    for name,x in [('old74',xs[:,:74]),('five',np.c_[np.ones(len(xs)),xs[:,1]-xs[:,2],xs[:,26]-xs[:,39],xs[:,27]-xs[:,40],xs[:,8]-xs[:,9]])]:
        other=Network.load(folder/'selected-actor.npz')[0];fit_reports[name]=other.fit_value(x,ys,weights,l2=d['value_l2']);coef=other.critic.copy();other.critic=np.zeros(STATE_DIM)
        if name=='old74':other.critic[:74]=coef
        else:
            other.critic[0]=coef[0]
            for w,(pos,neg) in zip(coef[1:],((1,2),(26,39),(27,40),(8,9))):other.critic[pos]=w;other.critic[neg]=-w
        other.save(folder/('value-'+name+'.npz'),dict(source_commit=commit(),validation=dict(qualified=False),purpose='Same actor value information ablation.'));others[name]=other
    prior=float(np.mean([float(e['won']) for e in train if e['terminal']]));dev=value_data(folder,net,'dev',d['value_dev_seeds'])
    dump(folder/'value.json',dict(source_commit=commit(),fit=report,baseline_fits=fit_reports,actor_unchanged=True,actor_fingerprint=before,train_episodes=len(train),train_decisions=len(xs),train_prior=prior,development=value_metrics(net,dev,prior),baselines={n:dict(metrics=value_metrics(m,dev,prior),gain=paired_value_gain(net,m,dev)) for n,m in others.items()}))


def final(folder):
    if (folder/'final.json').exists() or (folder/'final-games.jsonl.gz').exists():raise ValueError('Final used once')
    d=json.loads((folder/'design.json').read_text());net=Network.load(folder/'primary-value.npz')[0];base=Network.load(BASELINE)[0];inputs=cases(True)
    dump(folder/'final-plan.json',dict(source_commit=commit(),primary_fingerprint=net.fingerprint,actor_fingerprint=net.actor_fingerprint,seeds=d['final_seeds'],cases=[dict(group=g,decks=[[asdict(s) for s in deck] for deck in (a,b)],souls=s,opponent=p) for g,a,b,s,p in inputs]))
    names=['primary','v5','race','board','guard'];groups=[];failures=[];started=time.monotonic()
    with gzip.open(folder/'final-games.jsonl.gz','wt',encoding='utf-8') as sink:
        for group,a,b,souls,style in inputs:
            scores={n:[] for n in names};times={n:[] for n in names}
            for seed in d['final_seeds']:
                seats={n:[] for n in names}
                for seat in (0,1):
                    for name in names:
                        agent=LearnedPolicy(net if name=='primary' else base) if name in ('primary','v5') else ReferencePolicy(name)
                        r=run((a,b),seed,(agent,opponent(style)),seat,souls);sink.write(json.dumps(dict(group=group,seed=seed,seat=seat,policy=name,result=small_result(r)),separators=(',',':'))+'\n')
                        seats[name].append(None if r['unfinished'] else float(r['won']));times[name].extend(r['decision_seconds'][0])
                        if r['unfinished']:failures.append(dict(group=group,seed=seed,seat=seat,policy=name,error=r.get('error')))
                for name in names:scores[name].append((np.mean([0 if x is None else x for x in seats[name]]),np.mean([1 if x is None else x for x in seats[name]])))
            lo,hi=np.asarray(scores['primary']).T;comparisons=[]
            for name in names:
                a0,b0=np.asarray(scores[name]).T;comparisons.append(dict(policy=name,win=interval(a0,b0),primary_gain=interval(lo-b0,hi-a0)))
            groups.append(dict(group=group,policies=comparisons,timings={n:dict(decisions=len(t),p95=float(np.quantile(t,.95)),maximum=max(t)) for n,t in times.items()}));print(json.dumps(dict(group=group,wins={r['policy']:r['win']['completion_range'] for r in comparisons})),flush=True)
    prior=json.loads((folder/'value.json').read_text())['train_prior'];val=value_data(folder,net,'final',d['value_final_seeds']);others={n:Network.load(folder/('value-'+n+'.npz'))[0] for n in ('old74','five')}
    qualified=not failures and all(c['primary_gain']['low']>0 for g in groups for c in g['policies'] if c['policy']!='primary')
    result=dict(status='complete',source_commit=commit(),qualified=qualified,groups=groups,failures=failures,primary_fingerprint=net.fingerprint,value_final=value_metrics(net,val,prior),value_phases=phase_metrics(net,val,prior),value_baselines={n:dict(metrics=value_metrics(m,val,prior),gain=paired_value_gain(net,m,val)) for n,m in others.items()},no_final_selection=True,elapsed_seconds=time.monotonic()-started)
    dump(folder/'final.json',result);dump(folder/'validation.json',dict(qualified=qualified,status='qualified' if qualified else 'not_qualified',frozen_policy=net.fingerprint,default_model_replaced=False,source='final.json'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','collect','fit','development','diagnostic','value','final']);p.add_argument('--output',type=Path,required=True);p.add_argument('--stage',choices=['train','diagnostic']);args=p.parse_args()
    if args.mode=='collect':collect(args.output,args.stage)
    else:globals()[args.mode](args.output)
