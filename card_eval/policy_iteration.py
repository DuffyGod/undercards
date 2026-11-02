"""V13: paired current-policy vs frozen-policy continuation targets.

Round0 reuses actor-matched V12 training trajectories, not its retired finals.
Round1 uses the new policy's stopping-time roots; the two target arms share
every observation/action/world, initialization and optimizer budget.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import argparse, gzip, hashlib, json, random, time
import numpy as np
from .action_value import encode
from .counterfactual_research import PrefixController, PrefixAgent, sample_inputs, run
from .memory_research import opponent
from .network import Network
from .policies import LearnedPolicy, lethal
from .regret_model import RegretNetwork
from .relational_research import small_result
from .statistics import interval
from .suffix_research import cases, BehaviorRecorder
from .suffix_sampling import OnlineForkRecorder
from .training import dump, commit, decode

BASE = Path('artifacts/card_eval/v5/primary-value.npz')
INITIAL = Path('artifacts/card_eval/v12/primary-value.npz')
DONOR = Path('artifacts/card_eval/v12')


def prepare(folder):
    if folder.exists(): raise ValueError('Preserve experiment')
    folder.mkdir(parents=True)
    inputs = [BASE, INITIAL, DONOR/'value-train-0000.jsonl.gz', DONOR/'value-dev-0000.jsonl.gz']
    dump(folder/'design.json', dict(schema=1, source_commit=commit(), rng_seed=2026110213, primary='updated',
        input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        donor_train_seeds=list(range(3640000,3640064)), donor_diagnostic_seeds=list(range(3650000,3650016)),
        train_seeds=list(range(4110000,4110064)), diagnostic_seeds=list(range(4120000,4120016)),
        development_seeds=list(range(4130000,4130012)), final_seeds=list(range(4330000,4330032)),
        value_train_seeds=list(range(4140000,4140192)), value_dev_seeds=list(range(4150000,4150048)),
        value_final_seeds=list(range(4350000,4350096)),
        rounds=2, hidden=8, objective='regret', baseline_weight=.05, l2=.001, epochs=64,
        lr=.0015, batch=32, checkpoints=[16,32,64], max_actions=6,
        roots='Same preassigned-turn stopping rule in each round: first multi-action non-attack-lethal decision from random target2..5 until5, and target6..12 until12; no fallback/outcome selection.',
        actions='End, V5 anchor, actual roll-in action; one per kind then random remainder, capped6. Unmeasured legal actions remain missing; full legal deployment remains possible.',
        round0='First64 V12 value-train and first16 value-dev trajectories by seed, regardless of result; actor-matched V12 router. Source replay not a new opening. Label action then frozen V12 continuation; reuse actual chosen cell.',
        round1='Fresh round0 actor roll-in. At the SAME roots/actions/worlds label both current round0 continuation and frozen V12 continuation. Reuse current selected-action terminal. No hidden resampling or private input.',
        fitting='Round0 from fixed random initialization; round1 updated and frozen arms both warm-start the exact round0 weights, identical batches/epochs. Only continuation labels differ. No old target mixing or post-result model selection.',
        selection='Fixed epoch64 in both rounds/arms; diagnostic curves report only. Never select a mode/epoch/threshold with development or final.',
        development_gate='Updated point score strictly exceeds both V5 and V12 over5 contexts, paired95% lower gain vsV5>=-.05, at least1% semantic activation vsV5, no primary unknown; otherwise no large final/own critic. Never select frozen control.',
        acceptance='Conditional433/435 final after freezing actor and own critic. Positive paired95% lower vsV5,V12,frozen in every context and no primary unknown; default remains unchanged until broad evidence.',
        decision_seconds=.25, previous_final_files_read=[],
        limits='Two finite approximate policy-improvement rounds, not a LOLS theorem or converged POMDP solution. Public555 representation is still lossy; hidden worlds only generate offline terminal costs. Single training seed, fixed opponent mixture, no full beliefs/adaptive best response.'))


def design(folder):
    d=json.loads((folder/'design.json').read_text())
    for path,digest in d['input_sha256'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest: raise ValueError('Frozen input changed')
    return d


def read_rows(path):
    with gzip.open(path,'rt') as stream:
        for line in stream: yield json.loads(line)


def donor_episodes(stage,seeds):
    path=DONOR/('value-train-0000.jsonl.gz' if stage=='train' else 'value-dev-0000.jsonl.gz')
    wanted=set(seeds); rows=[]
    for row in read_rows(path):
        if row['record_type']=='decision': rows.append(row)
        else:
            meta=row['metadata']
            if meta['seed'] in wanted:
                yield dict(meta,record_type='input',source_file=str(path)),rows,row['result']
            rows=[]
    if rows: raise ValueError('Missing donor outcome boundary')


def root_turns(seed,rng_seed):
    rng=random.Random(rng_seed+seed)
    return rng.randrange(2,6),rng.randrange(6,13)


def stopping_indices(rows,turns):
    found={}
    for j,row in enumerate(rows):
        o=row['observation']; actions=list(map(tuple,row['legal_actions']))
        if o['player']!=0 or len(actions)<2 or lethal(o)[0]: continue
        for window,(start,stop) in enumerate(zip(turns,(5,12))):
            if window not in found and start<=o['turn']<=stop: found[window]=j
    return sorted(found.values())


def action_indices(row,base,rng,limit=6):
    obs=row['observation']; actions=list(map(tuple,row['legal_actions']))
    anchor=LearnedPolicy(base).choose(obs,actions)['action_index']; chosen=row['selection']['action_index']
    ids={0,anchor,chosen}
    for kind in ('play','attack'):
        options=[j for j,a in enumerate(actions) if a[0]==kind]
        if options: ids.add(rng.choice(options))
    rest=[j for j in range(len(actions)) if j not in ids]; rng.shuffle(rest)
    ids.update(rest[:max(0,limit-len(ids))])
    return sorted(ids),anchor


def collect(folder,phase,stage):
    d=design(folder); name=f'p{phase}-{stage}'; output=folder/name
    if (folder/f'{name}-collection.json').exists(): raise ValueError('Preserve completed collection')
    output.mkdir(exist_ok=True); started=time.monotonic(); initial=Network.load(INITIAL)[0]; base=Network.load(BASE)[0]
    current=initial if phase==0 else Network.load(folder/'phase0-selected.npz')[0]
    targets={'initial':initial} if phase==0 else {'updated':current,'frozen':initial}
    if phase==0:
        episodes=donor_episodes(stage,d['donor_'+stage+'_seeds'])
    else:
        rng=random.Random(d['rng_seed']+(stage=='diagnostic')); inputs=[]
        for i,seed in enumerate(d[stage+'_seeds']):
            decks,souls,roles=sample_inputs(rng)
            inputs.append(dict(record_type='input',seed=seed,decks=[[asdict(s) for s in deck] for deck in decks],
                souls=souls,roles=roles,seat=(i//4)%2,opponent=('race','board','guard','delayed')[i%4],
                actor_fingerprint=current.actor_fingerprint))
        episodes=((m,None,None) for m in inputs)
    for i,(meta,rows,result) in enumerate(episodes):
        path=output/f'episode-{i:04}.jsonl.gz'
        if path.exists(): continue
        pending=path.with_suffix('.pending')
        if pending.exists(): raise ValueError('Preserve partial attempt before resuming')
        assert meta['actor_fingerprint']==current.actor_fingerprint
        turns=root_turns(meta['seed'],d['rng_seed']); decks=tuple(tuple(map(decode,ds)) for ds in meta['decks'])
        with gzip.open(pending,'wt') as sink:
            sink.write(json.dumps(dict(meta,turn_targets=turns,rollin_reused=phase==0))+'\n')
            if rows is None:
                rec=OnlineForkRecorder(sink,meta['seed'],turns)
                result=run(decks,meta['seed'],(LearnedPolicy(current),opponent(meta['opponent'])),meta['seat'],meta['souls'],rec)
                rows=rec.rows; forks=sorted(rec.forks.values())
            else: forks=stopping_indices(rows,turns)
            sink.write(json.dumps(dict(record_type='root_selection',forks=forks,rollin_unknown=result['unfinished']))+'\n')
            rng=random.Random(d['rng_seed']+meta['seed']+phase*997)
            for fork in forks:
                row=rows[fork]; actions=list(map(tuple,row['legal_actions'])); ids,anchor=action_indices(row,base,rng,d['max_actions']); cells=[]
                for target,net in targets.items():
                    for index in ids:
                        reused=net.actor_fingerprint==current.actor_fingerprint and index==row['selection']['action_index']
                        if reused: outcome=small_result(result); checked=True
                        else:
                            control=PrefixController(rows,fork,actions[index],(LearnedPolicy(net),opponent(meta['opponent'])))
                            outcome=run(decks,meta['seed'],(PrefixAgent(control),PrefixAgent(control)),meta['seat'],meta['souls'])
                            checked=control.checked
                            if not checked and not outcome['unfinished']: raise ValueError('Branch never reached intervention')
                        cells.append(dict(target=target,continuation_actor=net.actor_fingerprint,action_index=index,
                            reused=reused,prefix_checked=checked,result=small_result(outcome)))
                sink.write(json.dumps(dict(record_type='root',seed=meta['seed'],decision=fork,observation=row['observation'],
                    legal_actions=actions,sampled_actions=ids,anchor=anchor,rollin_choice=row['selection']['action_index'],cells=cells),separators=(',',':'))+'\n')
        pending.rename(path)
        if i%8==7: print(json.dumps(dict(stage=name,completed_openings=i+1)),flush=True)
    dump(folder/f'{name}-collection.json',dict(collection_summary(output),source_commit=commit(),elapsed_seconds=time.monotonic()-started))


def collection_summary(output):
    counts=Counter(); coverage=Counter(); changed=0; paired=0
    for path in sorted(output.glob('episode-*.jsonl.gz')):
        records=list(read_rows(path)); meta=records[0]; counts['openings']+=1; coverage[meta['opponent'],meta['seat']]+=1
        for r in records:
            if r['record_type']=='root_selection':
                counts['rollin_unknown']+=r['rollin_unknown']; counts['absent_roots']+=2-len(r['forks'])
            if r['record_type']!='root': continue
            counts['roots']+=1
            for c in r['cells']:
                counts['cells']+=1; counts['new_branches']+=not c['reused']; counts['reused_cells']+=c['reused']; counts['unknown_cells']+=c['result']['unfinished']
            if {c['target'] for c in r['cells']}=={'updated','frozen'}:
                for index in r['sampled_actions']:
                    cs=[c for c in r['cells'] if c['action_index']==index]
                    if any(c['result']['unfinished'] for c in cs): continue
                    paired+=1; changed+=cs[0]['result']['won']!=cs[1]['result']['won']
    return dict(counts=dict(counts),opponent_seat_coverage={str(k):v for k,v in coverage.items()},
        paired_known_action_targets=paired,changed_targets=changed,
        inference='Changed labels are paired realized worlds; new branches and reused terminal cells are not independent openings.')


def dataset(folder,phase,stage,target):
    roots=[]
    for p in sorted((folder/f'p{phase}-{stage}').glob('episode-*.jsonl.gz')):
        roots.extend(r for r in read_rows(p) if r['record_type']=='root')
    eligible=[]; excluded=0
    for r in roots:
        available={c['target']:sum(not x['result']['unfinished'] for x in r['cells'] if x['target']==c['target']) for c in r['cells']}
        if not all(available.values()): excluded+=1; continue  # Same root eligibility in paired arms.
        x=encode(r['observation'],list(map(tuple,r['legal_actions'])))[1][0]; y=np.full(len(x),np.nan)
        for cell in r['cells']:
            if cell['target']==target and not cell['result']['unfinished']: y[cell['action_index']]=int(cell['result']['won'])
        eligible.append((r,x,y))
    n=Counter(r['seed'] for r,_,_ in eligible); xs=[];ys=[];groups=[];anchors={};weights={};seeds={}; raw=[]
    for group,(r,x,y) in enumerate(eligible):
        anchors[group]=len(xs)+r['anchor']; weights[group]=1/n[r['seed']]; seeds[group]=r['seed']
        xs.extend(x);ys.extend(y);groups.extend([group]*len(x));raw.append(r)
    return dict(x=np.array(xs),y=np.array(ys),groups=np.array(groups),anchors=anchors,weights=weights,seeds=seeds,raw=raw,excluded_roots=excluded)


def target_metrics(net,ds):
    z=net.action_scores(np.zeros(74),(ds['x'],None)); byseed=defaultdict(list); regrets=[]; measured=changes=0
    for group,anchor in ds['anchors'].items():
        ix=np.where(ds['groups']==group)[0]; known=ix[np.isfinite(ds['y'][ix])]
        choice=ix[int(z[ix].argmax())]; sampled=known[int(z[known].argmax())]
        regrets.append(float(ds['y'][known].max()-ds['y'][sampled])); measured+=np.isfinite(ds['y'][choice])
        changes+=not np.array_equal(ds['x'][choice],ds['x'][anchor])
        a=ds['y'][choice]; b=ds['y'][anchor]
        alo,ahi=(0.,1.) if not np.isfinite(a) else (a,a); blo,bhi=(0.,1.) if not np.isfinite(b) else (b,b)
        byseed[ds['seeds'][group]].append((0.,0.) if choice==anchor else (alo-bhi,ahi-blo))
    w=np.array(list(ds['weights'].values())); w/=w.sum(); bounds=np.array([np.mean(v,axis=0) for v in byseed.values()])
    return dict(sampled_action_regret=float(w@np.array(regrets)),roots=len(regrets),full_choices_measured=int(measured),
        full_semantic_changes=int(changes),full_choice_vs_v5_anchor=interval(*bounds.T),excluded_roots=ds['excluded_roots'],
        limitation='Full greedy choice may be unmeasured. Completion bounds retain those actions; sampled regret is conditional on measured actions only.')


def fit(folder,phase):
    d=design(folder)
    if (folder/f'phase{phase}-fit.json').exists(): raise ValueError('Preserve fit')
    targets=('initial',) if phase==0 else ('updated','frozen'); report={}
    for target in targets:
        train=dataset(folder,phase,'train',target); diagnostic=dataset(folder,phase,'diagnostic',target)
        net=(RegretNetwork(Network.load(BASE)[0],seed=d['rng_seed'],hidden=d['hidden'],baseline_weight=d['baseline_weight'])
             if phase==0 else Network.load(folder/'phase0-selected.npz')[0])
        net.target_description=f'One action then {target} continuation, phase{phase}, original-world offline terminal costs; not calibratedQ'
        warm=net.actor_fingerprint; rng=np.random.default_rng(d['rng_seed']); m={k:np.zeros_like(p) for k,p in net.p.items()};v=deepcopy(m);step=0;curve=[]
        idx={g:np.where(train['groups']==g)[0] for g in train['anchors']};total=sum(train['weights'].values());ng=len(idx)
        for epoch in range(1,d['epochs']+1):
            order=rng.permutation(ng)
            for start in range(0,ng,d['batch']):
                selected=order[start:start+d['batch']];ix=np.concatenate([idx[g] for g in selected]);reverse={j:i for i,j in enumerate(ix)}
                weights={int(g):float(train['weights'][g]/total*ng/len(selected)) for g in selected}
                anchors={int(g):reverse[train['anchors'][g]] for g in selected}
                _,grad=net.loss_grad(train['x'][ix],train['y'][ix],train['groups'][ix],anchors,weights,d['l2']);step+=1
                norm=np.sqrt(sum(np.sum(g*g) for g in grad.values()));scale=min(1.,5/max(norm,1e-12))
                for k,g in grad.items():
                    g=g*scale;m[k]=.9*m[k]+.1*g;v[k]=.999*v[k]+.001*g*g
                    net.p[k]-=d['lr']*(m[k]/(1-.9**step))/(np.sqrt(v[k]/(1-.999**step))+1e-8)
            if epoch in d['checkpoints']:
                curve.append(dict(epoch=epoch,train=target_metrics(net,train),diagnostic=target_metrics(net,diagnostic)))
                net.save(folder/f'phase{phase}-{target}-epoch-{epoch:03}.npz',dict(source_commit=commit(),validation=dict(qualified=False),value_unfitted=True,epoch=epoch))
        name='phase0-selected.npz' if phase==0 else f'{target}-selected.npz'
        net.save(folder/name,dict(source_commit=commit(),validation=dict(qualified=False),value_unfitted=True,epoch=d['epochs'],selection=d['selection']))
        report[target]=dict(warm_start_actor=warm,actor_fingerprint=net.actor_fingerprint,parameters=net.parameters,
            optimizer_steps=step,training_roots=ng,epochs=d['epochs'],curve=curve)
    if phase==1:
        common=dataset(folder,1,'diagnostic','updated')
        report['common_current_target_diagnostic']={name:target_metrics(Network.load(folder/file)[0],common)
            for name,file in (('updated','updated-selected.npz'),('frozen','frozen-selected.npz'),('phase0','phase0-selected.npz'))}
    dump(folder/f'phase{phase}-fit.json',dict(source_commit=commit(),selection=d['selection'],arms=report))


def development(folder):
    if (folder/'development.json').exists(): raise ValueError('Preserve development')
    d=design(folder);base=Network.load(BASE)[0]
    models={n:Network.load(folder/f'{n}-selected.npz')[0] for n in ('updated','frozen','phase0')}
    models.update(v12=Network.load(INITIAL)[0],v5=base);results=[];behavior=defaultdict(Counter)
    with gzip.open(folder/'development-decisions.jsonl.gz','wt') as decisions,gzip.open(folder/'development-games.jsonl.gz','wt') as games:
        for group,a,b,souls,style in cases():
            for seed in d['development_seeds']:
                for seat in (0,1):
                    for name,net in models.items():
                        meta=dict(group=group,seed=seed,seat=seat,policy=name);rec=BehaviorRecorder(decisions,meta,LearnedPolicy(base))
                        result=run((a,b),seed,(LearnedPolicy(net),opponent(style)),seat,souls,rec)
                        games.write(json.dumps(dict(meta,result=small_result(result)))+'\n');results.append(dict(meta,result=result))
                        behavior[name].update(decisions=rec.decisions,changed=rec.changed,raw_changed=rec.raw_changed,unknown=result['unfinished'])
            print(json.dumps(dict(group=group,completed_slots=len(results))),flush=True)
    perseed={}
    for name in models:
        clusters=[[r['result'] for r in results if r['policy']==name and r['seed']==seed] for seed in d['development_seeds']]
        perseed[name]=(np.array([np.mean([0 if r['unfinished'] else int(r['won']) for r in rs]) for rs in clusters]),
                       np.array([np.mean([1 if r['unfinished'] else int(r['won']) for r in rs]) for rs in clusters]))
    lo,hi=perseed['updated'];metrics={n:dict(win=interval(a,b),primary_gain=interval(lo-b,hi-a),behavior=dict(behavior[n])) for n,(a,b) in perseed.items()}
    activation=behavior['updated']['changed']/max(1,behavior['updated']['decisions'])
    proceed=bool(lo.mean()>max(perseed['v5'][1].mean(),perseed['v12'][1].mean()) and metrics['v5']['primary_gain']['low']>=-.05 and activation>=.01 and not behavior['updated']['unknown'])
    dump(folder/'development.json',dict(source_commit=commit(),primary='updated',metrics=metrics,activation=activation,proceed_to_final=proceed,gate=d['development_gate'],no_reselection=True))
    if not proceed:
        dump(folder/'validation.json',dict(qualified=False,status='development_rejected',frozen_policy=models['updated'].fingerprint,default_model_replaced=False))
        dump(folder/'final-status.json',dict(status='not_executed',qualified=False,final_seeds_unread=True,value_final_unread=True,own_value_fitted=False,reason='Fixed development gate failed'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','collect','fit','development']);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--phase',type=int,choices=[0,1]);p.add_argument('--stage',choices=['train','diagnostic']);args=p.parse_args()
    if args.mode=='collect':collect(args.output,args.phase,args.stage)
    elif args.mode=='fit':fit(args.output,args.phase)
    else:globals()[args.mode](args.output)
