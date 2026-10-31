"""V8: equal-capacity entity/aggregate continuation critics and new finals."""
from collections import Counter,defaultdict
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import argparse,gzip,hashlib,json,random,time
import numpy as np
from .entity_value import EntityValueNetwork,entity_state,GLOBAL
from .network import Network
from ._proof_first_v2 import PublicPlanner,PublicGame,UnknownDraw
from .policies import LearnedPolicy,ReferencePolicy
from .catalog import Spec,Effect,resolve,semantic_key,deck
from .profiles import base_deck,opponents,training_pool
from .planner_research import rows,PlannerRecorder
from .memory_research import opponent,read_rows
from .counterfactual_research import collect,run
from .relational_research import small_result
from .statistics import interval
from .training import dump,commit

SOURCE=Path('artifacts/card_eval/v6');BASE=Path('artifacts/card_eval/v5/primary-value.npz');LINEAR=Path('artifacts/card_eval/v7/afterstate-value.npz')


def cases(final=False):
    own=base_deck();opp=opponents();standard=[('pressure',own,opp['pressure'],('INTEGRITY','INTEGRITY'),'race'),
        ('defense',own,opp['defense'],('INTEGRITY','KINDNESS'),'race'),('refill',own,opp['refill'],('KINDNESS','INTEGRITY'),'race')]
    if not final:return standard+[('role_failure',opp['pressure'],opp['refill'],('KINDNESS','INTEGRITY'),'guard'),('role_defense',opp['defense'],opp['pressure'],('INTEGRITY','KINDNESS'),'board')]
    param=Spec('unseen_6G_3_11_haste',6,3,11,(('haste',1),),())
    combo=Spec('unseen_haste_taunt_growth',5,4,7,(('haste',1),('taunt',1)),(Effect('start','buff','self',1,1),))
    if any(semantic_key(s) in {semantic_key(p) for p in training_pool()} for s in (param,combo)):raise ValueError('Overlapping heldout semantics')
    a=list(own);a[:3]=[param]*3;b=list(own);b[:3]=[combo]*3
    ma=tuple(resolve('Charles') if s.name=='Scarf Mouse' else resolve('Ice Cap') if s.name=='Bloody Tree' else s for s in opp['refill'])
    mb=tuple(resolve('Bench') if s.name=='Scarf Mouse' else resolve('Froggit') if s.name=='Charles' else s for s in opp['defense'])
    deck(list(ma));deck(list(mb))
    sweep=Spec('synthetic_sweeper',5,0,5,(),(Effect('play','damage','all_enemy',3),));counter=list(opp['defense']);counter[:3]=[sweep]*3
    return standard+[('new_parameters',tuple(a),opp['pressure'],('INTEGRITY','INTEGRITY'),'race'),
        ('new_composition',tuple(b),opp['pressure'],('INTEGRITY','INTEGRITY'),'race'),
        ('new_mixed_decks',ma,mb,('KINDNESS','KINDNESS'),'race'),
        ('known_delayed_sweep',own,tuple(counter),('INTEGRITY','KINDNESS'),'delayed'),
        ('unseen_value_planner_opponent',own,opp['pressure'],('INTEGRITY','KINDNESS'),'linear_planner')]


def prepare(folder):
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/'design.json').exists():raise ValueError('Preserve experiment')
    files=sorted(SOURCE.glob('*-targets-*.jsonl.gz'))
    dump(folder/'design.json',dict(source_commit=commit(),baseline=str(BASE),linear_control=str(LINEAR),rng_seed=2026103108,
        source_files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        primary='entity',arms={a:EntityValueNetwork(variant=a).parameters for a in ('entity','aggregate')},train='Identical V6 current-V5 terminal labels and deterministic public successors. Equal source-opening weights. Frozen V5 actor.',
        representation='Shared nonlinear16-dimensional card/unit encoder, separate hand/own/enemy sums,16hidden value head. Joint trigger/op/scope/count/amount/health tensor. Public board position retained; hand order excluded. Aggregate74MLP hidden123 is capacity control.',
        optimizer='Adam, unbiased globally episode-weighted minibatch gradient',epochs=64,epoch_candidates=[8,16,32,64],batch=256,lr=.0015,l2=.001,
        selection='Each predeclared arm selects epoch by reused diagnostic opening-weighted NLL, ties earlier. Primary arm fixed. Only primary margin selected on new development lower win; ties larger. No final model/arm selection.',
        margins=[.05,.1,.2],development_seeds=list(range(2150000,2150008)),final_seeds=list(range(2250000,2250032)),
        diagnostic_seeds=list(range(2230000,2230096)),max_actions=6,continuations=['baseline'],
        planner=dict(nodes=48,depth=3,width=4,seconds=.12),decision_seconds=.25,
        final_policies=['entity','aggregate','linear','v5','race','board','guard'],final_cases=[g for g,*_ in cases(True)],
        acceptance='Every final context primary paired95%lower above V5 and race/board/guard, no unresolved. Entity must also beat capacity control for representation attribution; report all intervals.',
        value_target='V5 continuation, not planner-policy V or Q*. Fresh2230000 data used only after selection.',
        limits=['Single training initialization','Old V4/race roll-in distribution reused','Partial observation without learned belief','Entity pooling finite-dimensional, not sufficient state guarantee','Heldout planner opponent is fixed, not an adaptive best response','Simulator mechanisms remain limited'],
        retired_final_starts=[1210000,1310000,1330000,1610000,1630000,1810000,1830000,2030000,2050000]))


def prepare_extended(folder):
    prepare(folder);p=folder/'design.json';d=json.loads(p.read_text());files=sorted(BASE.parent.glob('value-train-*.jsonl.gz'))+sorted(BASE.parent.glob('value-dev-*.jsonl.gz'))
    d.update(stage='V9_coverage_revision',include_on_policy=True,rng_seed=2026103109,
        development_seeds=list(range(2170000,2170008)),final_seeds=list(range(2350000,2350032)),diagnostic_seeds=list(range(2330000,2330096)),
        coverage_reason='V8 actual training had no turns>12 and no empty own deck; preserve V8 before-final attempt and reuse matching frozen-V5 full train/dev episodes. No old final imported.',
        train='Equal original-opening weights over384 paired-fork openings and384 complete on-policyV5 training openings. Same actor/targets for both arms; no new old-game replay.')
    d['source_files'].update({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files});dump(p,d)


def on_policy(stage):
    expected_actor=Network.load(BASE)[0].actor_fingerprint
    for path in sorted(BASE.parent.glob(f'value-{stage}-*.jsonl.gz')):
        observations=[]
        for row in read_rows(path):
            if row['record_type']=='decision':
                if row['observation']['player']==0:observations.append(row['observation'])
            elif row['record_type']=='outcome':
                meta=row['metadata'];result=row['result']
                if meta['actor_fingerprint']!=expected_actor:raise ValueError('Full-trajectory continuation actor mismatch')
                yield dict(seed=meta['seed'],observations=observations,unfinished=result['unfinished'],won=result['won']);observations=[]
        if observations:raise ValueError('Unfinished serialized full-trajectory episode; never synthesize label')


def dataset(source,rollins=None):
    records=[];counts=Counter()
    for row in source:
        counts['forks']+=1;obs=row['observation'];actions=list(map(tuple,row['legal_actions']))
        labels={b['action_index']:b for b in row['branches'] if b['continuation'] in ('current','baseline')}
        base=labels.get(row['baseline_action'])
        if base is not None and not base['unfinished']:records.append((row['seed'],0,entity_state(obs).astype(np.float32),int(base['won'])))
        else:counts['unknown_root']+=1
        for index,b in labels.items():
            if b['unfinished']:counts['unknown_label']+=1;continue
            action=actions[index]
            if action[0]=='end':counts['end_boundary']+=1;continue
            try:child=PublicGame(obs).child(action)
            except UnknownDraw:counts['unknown_draw']+=1;continue
            terminal=child.terminal()
            if terminal is not None:
                counts['exact_terminal']+=1
                if terminal!=bool(b['won']):raise ValueError('Terminal replay disagrees with public rules')
                continue
            records.append((row['seed'],1,entity_state(child.observation()).astype(np.float32),int(b['won'])))
    for episode in rollins or ():
        counts['full_episodes']+=1
        if episode['unfinished']:counts['unknown_full_episode']+=1;continue
        records.extend((episode['seed'],2,entity_state(obs).astype(np.float32),int(episode['won'])) for obs in episode['observations'])
    seeds=np.array([r[0] for r in records]);sizes=Counter(seeds)
    output=dict(seeds=seeds,kinds=np.array([r[1] for r in records]),states=np.asarray([r[2] for r in records],dtype=np.float32),
        labels=np.array([r[3] for r in records]),weights=np.array([1/sizes[s] for s in seeds]))
    counts.update(states=len(records),roots=int(np.sum(output['kinds']==0)),after=int(np.sum(output['kinds']==1)),openings=len(sizes))
    if rollins is not None:counts.update(full_states=int(np.sum(output['kinds']==2)),past_turn12=int(np.sum(output['states'][:,5]*30>12.01)),empty_own_deck=int(np.sum(output['states'][:,8]==0)))
    return output,dict(counts)


def inputs(net,data):return data['states'] if isinstance(net,EntityValueNetwork) and net.variant=='entity' else data['states'][:,:GLOBAL]


def probabilities(net,data):
    x=inputs(net,data)
    if isinstance(net,EntityValueNetwork):
        z=np.concatenate([net.batch_forward(x[i:i+256])[0] for i in range(0,len(x),256)])
        return 1/(1+np.exp(-np.clip(z,-40,40)))
    return np.array([(net.predict_value(s)+1)/2 for s in x])


def score(net,data):
    p=probabilities(net,data);y=data['labels'];w=data['weights'];w=w/w.sum()
    return dict(brier=float(w@((p-y)**2)),nll=float(-w@(y*np.log(np.clip(p,1e-10,1))+(1-y)*np.log(np.clip(1-p,1e-10,1)))))


def fit(folder):
    if (folder/'fit.json').exists():raise ValueError('Preserve fit')
    d=json.loads((folder/'design.json').read_text())
    for path,digest in d['source_files'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Source changed')
    train,counts=dataset(rows(SOURCE,'train'),on_policy('train') if d.get('include_on_policy') else None)
    dev,dc=dataset(rows(SOURCE,'diagnostic'),on_policy('dev') if d.get('include_on_policy') else None)
    np.savez_compressed(folder/'value-train.npz',**train);np.savez_compressed(folder/'value-development.npz',**dev)
    report={};base=Network.load(BASE)[0]
    for arm in ('entity','aggregate'):
        net=EntityValueNetwork(deepcopy(base),arm,d['rng_seed']);rng=np.random.default_rng(d['rng_seed']);m={k:np.zeros_like(p) for k,p in net.p.items()};v=deepcopy(m);step=0;curve=[]
        x=inputs(net,train);n=len(x);w=train['weights'];wsum=w.sum()
        for epoch in range(1,d['epochs']+1):
            order=rng.permutation(n)
            for start in range(0,n,d['batch']):
                ix=order[start:start+d['batch']];step+=1
                _,grads=net.loss_grad(x[ix],train['labels'][ix],w[ix]/wsum*n/len(ix),d['l2'],normalize=False)
                norm=np.sqrt(sum(np.sum(g*g) for g in grads.values()));scale=min(1.,5/max(norm,1e-12))
                for k,g in grads.items():
                    g=g*scale;m[k]=.9*m[k]+.1*g;v[k]=.999*v[k]+.001*g*g
                    net.p[k]-=d['lr']*(m[k]/(1-.9**step))/(np.sqrt(v[k]/(1-.999**step))+1e-8)
            if epoch in d['epoch_candidates']:
                metrics=score(net,dev);curve.append(dict(epoch=epoch,train=score(net,train),development=metrics))
                net.save(folder/f'{arm}-epoch-{epoch:03}.npz',dict(source_commit=commit(),validation=dict(qualified=False),target=d['value_target'],epoch=epoch))
                print(json.dumps(dict(arm=arm,**curve[-1])),flush=True)
        selected=min(curve,key=lambda r:(r['development']['nll'],r['epoch']))['epoch']
        chosen=Network.load(folder/f'{arm}-epoch-{selected:03}.npz')[0]
        if chosen.actor_fingerprint!=base.actor_fingerprint:raise ValueError('Changed actor')
        chosen.save(folder/f'{arm}-value.npz',dict(source_commit=commit(),validation=dict(qualified=False),target=d['value_target'],selected_epoch=selected))
        report[arm]=dict(curve=curve,selected_epoch=selected,parameters=chosen.parameters,fingerprint=chosen.fingerprint,actor_fingerprint=chosen.actor_fingerprint)
    dump(folder/'fit.json',dict(source_commit=commit(),training=counts,development=dc,arms=report,no_final_selection=True))


def models(folder):return dict(entity=Network.load(folder/'entity-value.npz')[0],aggregate=Network.load(folder/'aggregate-value.npz')[0],linear=Network.load(LINEAR)[0],v5=Network.load(BASE)[0])


def agent(name,ms,d,margin):
    if name in ('entity','aggregate','linear'):return PublicPlanner(ms[name],'value',margin,**d['planner'])
    return LearnedPolicy(ms['v5']) if name=='v5' else ReferencePolicy(name)


def enemy(style,ms,d):return PublicPlanner(ms['linear'],'value',.3,**d['planner']) if style=='linear_planner' else opponent(style)


def development(folder):
    if (folder/'development.json').exists():raise ValueError('Preserve development')
    d=json.loads((folder/'design.json').read_text());ms=models(folder);result=[]
    with gzip.open(folder/'development-games.jsonl.gz','wt') as sink:
        for margin in d['margins']:
            lower=[];unknown=0
            for group,a,b,souls,style in cases():
                for seed in d['development_seeds']:
                    for seat in (0,1):
                        r=run((a,b),seed,(agent('entity',ms,d,margin),enemy(style,ms,d)),seat,souls)
                        sink.write(json.dumps(dict(group=group,seed=seed,seat=seat,margin=margin,result=small_result(r)),separators=(',',':'))+'\n')
                        unknown+=r['unfinished'];lower.append(0 if r['unfinished'] else float(r['won']))
            result.append(dict(margin=margin,lower=float(np.mean(lower)),unfinished=unknown,slots=len(lower)))
            dump(folder/'development-progress.json',result);print(json.dumps(result[-1]),flush=True)
    selected=max(result,key=lambda x:(x['lower'],x['margin']))['margin']
    dump(folder/'development.json',dict(source_commit=commit(),results=result,selected_margin=selected,
        frozen_policies={n:agent(n,ms,d,selected).fingerprint for n in ('entity','aggregate','linear')}))


def final(folder):
    if (folder/'final-games.jsonl.gz').exists():raise ValueError('Preserve final')
    d=json.loads((folder/'design.json').read_text());dev=json.loads((folder/'development.json').read_text());ms=models(folder);margin=dev['selected_margin'];names=d['final_policies'];groups=[];failures=[]
    dump(folder/'final-plan.json',dict(source_commit=commit(),frozen_policies=dev['frozen_policies'],margin=margin,seeds=d['final_seeds'],
        cases=[dict(group=g,decks=[[asdict(s) for s in ds] for ds in (a,b)],souls=ss,opponent=p) for g,a,b,ss,p in cases(True)]))
    with gzip.open(folder/'final-games.jsonl.gz','wt') as sink:
        for group,a,b,souls,style in cases(True):
            scores={n:[] for n in names};times={n:[] for n in names};events={n:Counter() for n in names}
            for seed in d['final_seeds']:
                seats={n:[] for n in names}
                for seat in (0,1):
                    for name in names:
                        rec=PlannerRecorder();r=run((a,b),seed,(agent(name,ms,d,margin),enemy(style,ms,d)),seat,souls,rec)
                        sink.write(json.dumps(dict(group=group,seed=seed,seat=seat,policy=name,result=small_result(r),planner=dict(rec.events)),separators=(',',':'))+'\n')
                        seats[name].append(None if r['unfinished'] else float(r['won']));events[name].update(rec.events);times[name].extend(r['decision_seconds'][0])
                        if r['unfinished']:failures.append(dict(group=group,seed=seed,seat=seat,policy=name,error=r.get('error')))
                for name in names:scores[name].append((np.mean([0 if s is None else s for s in seats[name]]),np.mean([1 if s is None else s for s in seats[name]])))
            lo,hi=np.asarray(scores['entity']).T;comparison=[]
            for name in names:
                a0,b0=np.asarray(scores[name]).T;comparison.append(dict(policy=name,win=interval(a0,b0),primary_gain=interval(lo-b0,hi-a0),family_gain=interval(lo-b0,hi-a0,alpha=.05/8)))
            groups.append(dict(group=group,policies=comparison,events={n:dict(e) for n,e in events.items()},timings={n:dict(p95=float(np.quantile(t,.95)) if t else None,maximum=max(t) if t else None,decisions=len(t)) for n,t in times.items()}))
            dump(folder/'final-progress.json',dict(groups=groups,failures=failures));print(json.dumps(dict(group=group,wins={c['policy']:c['win']['completion_range'] for c in comparison})),flush=True)
    qualified=not failures and all(c['primary_gain']['low']>0 for g in groups for c in g['policies'] if c['policy'] in ('v5','race','board','guard'))
    dump(folder/'final.json',dict(source_commit=commit(),qualified=qualified,groups=groups,failures=failures,no_final_selection=True))
    dump(folder/'validation.json',dict(qualified=False,status='not_qualified',frozen_policy=ms['entity'].fingerprint,
        reason='Checkpoint retains V5 actor; planner is separately qualified.',source='final.json'))
    dump(folder/'planner-validation.json',dict(qualified=qualified,status='qualified' if qualified else 'not_qualified',frozen_policy=dev['frozen_policies']['entity'],source='final.json'))


def final_value(folder):
    collect(folder,'diagnostic');data,counts=dataset(rows(folder,'diagnostic',reused=False));np.savez_compressed(folder/'value-final.npz',**data)
    ms=models(folder);output={}
    for kind in (0,1):
        ids=np.where(data['kinds']==kind)[0];seeds=sorted(set(data['seeds'][ids]));errors={}
        for name in ('entity','aggregate','linear'):
            p=probabilities(ms[name],data);error=(p-data['labels'])**2
            errors[name]={s:float(np.mean(error[ids[data['seeds'][ids]==s]])) for s in seeds}
        output['root' if kind==0 else 'after']=dict(states=len(ids),brier={n:interval([e[s] for s in seeds]) for n,e in errors.items()},
            entity_error_reduction={n:interval([errors[n][s]-errors['entity'][s] for s in seeds]) for n in ('aggregate','linear')})
    dump(folder/'final-value.json',dict(source_commit=commit(),counts=counts,metrics=output,no_selection=True))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','prepare-extended','fit','development','final','final-value']);p.add_argument('--output',required=True,type=Path);args=p.parse_args()
    {'prepare':prepare,'prepare-extended':prepare_extended,'fit':fit,'development':development,'final':final,'final-value':final_value}[args.mode](args.output)
