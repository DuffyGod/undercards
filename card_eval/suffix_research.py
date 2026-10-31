"""V11: 2x2 own-future-order targets and regret-weighted action policies.

Reused roots are intervention starting points, not new independent openings.
Their original future labels remain references, not resampled targets. Fresh
roots use an online stopping rule and fully crossed opponent/seat allocation.
"""
from collections import Counter,defaultdict
from dataclasses import asdict
from copy import deepcopy
from pathlib import Path
import argparse,gzip,hashlib,json,random,time
import numpy as np
from .suffix_sampling import OnlineForkRecorder,continuation,stable
from .regret_model import RegretNetwork
from .network import Network
from .policies import LearnedPolicy,ReferencePolicy
from .action_value import encode
from .counterfactual_research import sample_inputs,run,value_data
from .memory_research import read_rows,opponent
from .relational_research import small_result,value_metrics,paired_value_gain
from .statistics import interval
from .training import dump,commit,decode
from .catalog import Spec,Effect,semantic_key
from .profiles import base_deck,opponents,training_pool

BASE=Path('artifacts/card_eval/v5/primary-value.npz')
SOURCE=Path('artifacts/card_eval/v10')
ARMS=('regret_mean','regret_single','centered_mean','centered_single')


def cases(final=False):
    own=base_deck();others=opponents()
    standard=[('pressure',own,others['pressure'],('INTEGRITY','INTEGRITY'),'race'),
              ('defense',own,others['defense'],('INTEGRITY','KINDNESS'),'race'),
              ('refill',own,others['refill'],('KINDNESS','INTEGRITY'),'race')]
    if not final:
        return standard+[('role_pressure',others['pressure'],others['refill'],('KINDNESS','INTEGRITY'),'guard'),
                         ('role_defense',others['defense'],others['pressure'],('INTEGRITY','KINDNESS'),'board')]
    a=list(own);b=list(own)
    param=Spec('v11_heldout_haste',5,6,9,(('haste',1),),())
    combo=Spec('v11_heldout_taunt_draw_endheal',5,4,7,(('taunt',1),),
        (Effect('play','draw','owner',1),Effect('end','heal','owner',2)))
    if any(semantic_key(s) in {semantic_key(t) for t in training_pool()} for s in (param,combo)):raise ValueError('Heldout overlap')
    a[:3]=[param]*3;b[:3]=[combo]*3
    sweep=Spec('v11_sweeper',5,0,5,(),(Effect('play','damage','all_enemy',3),));counter=list(others['defense']);counter[:3]=[sweep]*3
    return standard+[('new_parameters',tuple(a),others['pressure'],('INTEGRITY','INTEGRITY'),'race'),
        ('new_composition',tuple(b),others['pressure'],('INTEGRITY','INTEGRITY'),'race'),
        ('new_mixed_decks',others['defense'],others['refill'],('KINDNESS','KINDNESS'),'switching'),
        ('delayed_sweep',own,tuple(counter),('INTEGRITY','KINDNESS'),'delayed'),
        ('heldout_learned_opponent',own,others['pressure'],('INTEGRITY','KINDNESS'),'learned')]


def prepare(folder):
    if folder.exists():raise ValueError('Preserve experiment')
    folder.mkdir(parents=True)
    files=[BASE]+[SOURCE/f'{s}-{kind}.jsonl.gz' for s in ('train','diagnostic') for kind in ('forks','rollins')]
    dump(folder/'design.json',dict(source_commit=commit(),rng_seed=2026103111,baseline=str(BASE),primary='regret_mean',arms=ARMS,
        source_files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        fresh_train_seeds=list(range(3110000,3110064)),fresh_diagnostic_seeds=list(range(3120000,3120016)),
        development_seeds=list(range(3130000,3130012)),final_seeds=list(range(3330000,3330032)),
        value_train_seeds=list(range(3140000,3140192)),value_dev_seeds=list(range(3150000,3150048)),value_final_seeds=list(range(3350000,3350096)),
        suffixes=dict(train=4,diagnostic=8),fit_suffixes=[1,2,3,4],single_suffix=1,audit_suffixes=[5,6,7,8],max_actions=6,
        target='Uniform intervention on own unseen future deck order at a fixed public root, then frozen V5 continuation. Opponent hidden hand/order and root remaining multisets held fixed. Not a full posterior belief or Q*.',
        old_roots='Reuse128 V10 train and32 diagnostic openings/prefixes/forks. Original labels are reference only, never replayed or mixed into target means: retrospective fork sampling can condition on later trajectory length.',
        fresh_roots='64/16 fresh V5 roll-ins. Preassign turn in2..5 and6..12; first eligible decision at/after that turn within the window, sampled online. Missing windows remain missing. Style=i%4 and seat=(i//4)%2 fully crossed.',
        capacity='Same ordered555 features/32hidden/17825 trainable action parameters in all4 arms; existing V5 actor only supplies training anchors and attack-lethal wrapper.',
        objectives='Regret: gap-weighted pairwise logistic on known sampled action means. Centered: probability-centered squared error. Both add baseline cross entropy on all legal actions, weight.05. Unmeasured outcomes remain masked NaN; baseline regularization is not a zero outcome label.',
        inference='Argmax shared learned logits, no posthoc probability margin; existing32-node attack-lethal proof unchanged. Not safe policy improvement.',
        epochs=96,epoch_candidates=[16,32,64,96],batch_forks=64,lr=.0015,l2=.0001,baseline_weight=.05,
        epoch_selection='Minimum opening-weighted sampled-action regret on diagnostic mean of suffix1..4; ties earlier. Same criterion for every arm. No arm/prior/margin selection.',
        development_gate='Primary lower completed score>=V5 upper score over5 contexts, paired95% lower gain>=-.10, at least1% actual Actor0 decisions differ fromV5, and no unresolved primary slot. Otherwise do not execute large final or refit own critic.',
        final_policies=['regret_mean','regret_single','centered_mean','v5','guard'],final_cases=[c[0] for c in cases(True)],decision_seconds=.25,
        acceptance='Every8 final context primary paired95%lower>0 against all4 controls, zero unknown. Report8context sensitivity. No final reselection, no default promotion.',
        retired_final_starts=[1210000,1310000,1330000,1610000,1630000,1810000,1830000,2030000,2050000,2330000,2350000,2870000,2890000],
        limits=['One training initialization','Old retrospective roots and fresh stopping-time roots are different declared cohorts','Only own future order integrated; no full opponent/history belief',
                'Same-root suffixes are not independent new worlds','Finite4-suffix target estimates','Policy target is V5 continuation, not learned actor Q','No learned opponent best response','Rules remain20 complete real cards and supported grammar']))
    old={}
    for arm in ('centered','pointwise'):
        n=Network.load(SOURCE/f'{arm}-selected.npz')[0];l1=float(abs(n.p['w']).sum())
        old[arm]=dict(output_l1=l1,universal_sigmoid_gap_upper=float(np.tanh(l1/2)),margin=n.margin,norms={k:float(np.linalg.norm(v)) for k,v in n.p.items()})
    dump(folder/'v10-output-diagnostic.json',dict(models=old,conclusion='The universal tanh/sigmoid bound does not prove the V10 head globally inactive; observed zero changes must not be extrapolated to every input.',no_final_used=True))


def old_episodes(stage):
    forks=defaultdict(list)
    for row in read_rows(SOURCE/f'{stage}-forks.jsonl.gz'):forks[row['seed']].append(row)
    meta=None;rows=[]
    for row in read_rows(SOURCE/f'{stage}-rollins.jsonl.gz'):
        if row['record_type']=='input':meta=row;rows=[]
        elif row['record_type']=='decision':rows.append(row)
        else:
            roots=[]
            for r in forks[meta['seed']]:
                bs=[b for b in r['branches'] if b['continuation']=='current']
                roots.append(dict(r,indices=sorted(b['action_index'] for b in bs),reference=bs))
            yield meta,rows,roots,'reused_retrospective'


def fresh_episodes(folder,stage,d,net):
    with gzip.open(folder/f'{stage}-fresh-rollins.jsonl.gz','wt') as sink:
        for i,seed in enumerate(d[f'fresh_{stage}_seeds']):
            rng=random.Random(d['rng_seed']+seed);decks,souls,roles=sample_inputs(rng);style=('race','board','guard','delayed')[i%4];seat=(i//4)%2
            turns=(rng.randrange(2,6),rng.randrange(6,13));meta=dict(record_type='input',seed=seed,decks=[[asdict(s) for s in ds] for ds in decks],souls=souls,roles=roles,seat=seat,opponent=style,turn_targets=turns,actor_fingerprint=net.actor_fingerprint)
            sink.write(json.dumps(meta)+'\n');rec=OnlineForkRecorder(sink,seed,turns)
            result=run(decks,seed,(LearnedPolicy(net),opponent(style)),seat,souls,rec);roots=[]
            for fork in sorted(rec.forks.values()):
                row=rec.rows[fork];actions=list(map(tuple,row['legal_actions']));anchor=row['selection']['action_index'];ids={0,anchor}
                rr=random.Random(d['rng_seed']+seed*997+fork)
                for kind in ('play','attack'):
                    options=[j for j,a in enumerate(actions) if a[0]==kind]
                    if options:ids.add(rr.choice(options))
                rest=[j for j in range(len(actions)) if j not in ids];rr.shuffle(rest);ids.update(rest[:max(0,d['max_actions']-len(ids))])
                reference=[dict(action_index=anchor,won=result['won'],unfinished=result['unfinished'],source='already executed V5 roll-in; no replay')]
                roots.append(dict(seed=seed,decision=fork,observation=row['observation'],legal_actions=actions,baseline_action=anchor,indices=sorted(ids),reference=reference))
            yield meta,rec.rows,roots,'fresh_online_stopping_time'


def collect(folder,stage):
    if (folder/f'{stage}-targets.jsonl.gz').exists():raise ValueError('Preserve targets')
    d=json.loads((folder/'design.json').read_text())
    for name,digest in d['source_files'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:raise ValueError('Reusable input changed')
    net=Network.load(BASE)[0];counts=Counter();started=time.monotonic()
    def episodes():
        yield from old_episodes(stage)
        yield from fresh_episodes(folder,stage,d,net)
    with gzip.open(folder/f'{stage}-targets.jsonl.gz','wt') as sink:
        for meta,records,roots,origin in episodes():
            if meta['actor_fingerprint']!=net.actor_fingerprint:raise ValueError('Reused roll-in actor mismatch')
            counts[origin+'_openings']+=1;decks=tuple(tuple(decode(s) for s in ds) for ds in meta['decks'])
            for root in roots:
                bs=[];permutations={};known={}
                reference={tuple(root['legal_actions'][r['action_index']]):dict(won=r['won'],unfinished=r['unfinished'],error=r.get('error')) for r in root['reference']}
                for suffix in range(1,d['suffixes'][stage]+1):
                    suffix_seed=int(stable([d['rng_seed'],stage,meta['seed'],root['decision'],suffix]),16)
                    for index in root['indices']:
                        r,sampler,checked=continuation(decks,meta['seed'],(LearnedPolicy(net),opponent(meta['opponent'])),meta['seat'],meta['souls'],records,root['decision'],root['legal_actions'][index],suffix_seed,known,reference)
                        counts['continuations']+=1;counts['unknown_continuations']+=r['unfinished'];counts['prefix_matches']+=checked
                        counts['reused_identical_continuations']+=bool(sampler and sampler['reused_identical_continuation'])
                        if sampler is not None:
                            key=tuple(sampler['own_future_uids'])
                            if suffix in permutations and permutations[suffix]!=key:raise ValueError('Different hidden suffix for paired actions')
                            permutations[suffix]=key
                        bs.append(dict(action_index=index,suffix=suffix,won=r['won'],unfinished=r['unfinished'],error=r.get('error'),sampler_private=sampler))
                out={k:root[k] for k in ('seed','decision','observation','legal_actions','baseline_action','indices','reference')}
                out.update(origin=origin,branches=bs,unique_orders=len(set(permutations.values())),opponent=meta['opponent'],seat=meta['seat'])
                sink.write(json.dumps(out,separators=(',',':'))+'\n');sink.flush();counts['forks']+=1
            if sum(counts[k] for k in ('reused_retrospective_openings','fresh_online_stopping_time_openings'))%16==0:
                status=dict(counts,elapsed_seconds=time.monotonic()-started);dump(folder/f'{stage}-progress.json',status);print(json.dumps(status),flush=True)
    dump(folder/f'{stage}-collection.json',dict(counts,elapsed_seconds=time.monotonic()-started,source_commit=commit()))


def data(folder,stage):
    path=folder/f'{stage}-inputs.npz'
    if path.exists():return dict(np.load(path,allow_pickle=False))
    matrices=[];single=[];mean=[];seeds=[];anchors=[];groups=[];counts=Counter();origins=[]
    for row in read_rows(folder/f'{stage}-targets.jsonl.gz'):
        used=[b for b in row['branches'] if b['suffix']<=4]
        if any(b['unfinished'] for b in used):counts['unknown_groups_excluded']+=1;continue
        actions=list(map(tuple,row['legal_actions']));x=encode(row['observation'],actions)[1][0];g=len(anchors);n=len(x);one=np.full(n,np.nan);avg=one.copy()
        for index in row['indices']:
            bs=sorted((b for b in used if b['action_index']==index),key=lambda b:b['suffix'])
            if [b['suffix'] for b in bs]!=[1,2,3,4]:raise ValueError('Incomplete suffix target; never fill missing as zero')
            one[index]=int(bs[0]['won']);avg[index]=np.mean([int(b['won']) for b in bs])
        if not np.isfinite(avg[row['baseline_action']]):raise ValueError('Baseline target missing')
        anchors.append(sum(len(m) for m in matrices)+row['baseline_action']);matrices.append(x.astype(np.float32));single.extend(one);mean.extend(avg);groups.extend([g]*n);seeds.append(row['seed']);origins.append(int(row['origin']=='fresh_online_stopping_time'));counts['forks']+=1
    sizes=Counter(seeds);weights=np.array([1/sizes[s] for s in seeds])
    out=dict(x=np.concatenate(matrices),single=np.array(single),mean=np.array(mean),groups=np.array(groups),seeds=np.array(seeds),anchors=np.array(anchors),weights=weights,origins=np.array(origins))
    np.savez_compressed(path,**out);dump(folder/f'{stage}-inputs.json',dict(counts,openings=len(sizes),legal_action_rows=len(out['x']),measured_action_labels=int(np.isfinite(out['mean']).sum()),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return out


def policy_metrics(net,ds):
    z=net.batch(ds['x'])[1][2];regrets=[];changes=measured=0
    for g,anchor in enumerate(ds['anchors']):
        ix=np.where(ds['groups']==g)[0];known=ix[np.isfinite(ds['mean'][ix])];sampled=known[int(z[known].argmax())]
        regrets.append(float(ds['mean'][known].max()-ds['mean'][sampled]));best=ix[int(z[ix].argmax())]
        changes+=best!=anchor;measured+=np.isfinite(ds['mean'][best])
    w=ds['weights']/ds['weights'].sum()
    return dict(sampled_regret=float(w@np.asarray(regrets)),full_choice_changes=int(changes),full_choices_measured=int(measured),forks=len(regrets))


def fit(folder):
    if (folder/'fit.json').exists():raise ValueError('Preserve fit')
    d=json.loads((folder/'design.json').read_text());train=data(folder,'train');dev=data(folder,'diagnostic');report={}
    idx={g:np.where(train['groups']==g)[0] for g in range(len(train['anchors']))};total=train['weights'].sum();ng=len(idx)
    for arm in ARMS:
        objective,target=arm.split('_');net=RegretNetwork(Network.load(BASE)[0],objective,d['rng_seed'],baseline_weight=d['baseline_weight']);rng=np.random.default_rng(d['rng_seed'])
        m={k:np.zeros_like(p) for k,p in net.p.items()};v=deepcopy(m);step=0;curve=[]
        for epoch in range(1,d['epochs']+1):
            order=rng.permutation(ng)
            for start in range(0,ng,d['batch_forks']):
                selected=order[start:start+d['batch_forks']];ix=np.concatenate([idx[g] for g in selected]);reverse={j:i for i,j in enumerate(ix)}
                weights={int(g):float(train['weights'][g]/total*ng/len(selected)) for g in selected}
                anchors={int(g):reverse[train['anchors'][g]] for g in selected}
                _,grads=net.loss_grad(train['x'][ix],train['single' if target=='single' else 'mean'][ix],train['groups'][ix],anchors,weights,d['l2']);step+=1
                norm=np.sqrt(sum(np.sum(g*g) for g in grads.values()));scale=min(1.,5/max(norm,1e-12))
                for k,g in grads.items():
                    g=g*scale;m[k]=.9*m[k]+.1*g;v[k]=.999*v[k]+.001*g*g
                    net.p[k]-=d['lr']*(m[k]/(1-.9**step))/(np.sqrt(v[k]/(1-.999**step))+1e-8)
            if epoch in d['epoch_candidates']:
                metric=dict(epoch=epoch,train=policy_metrics(net,train),diagnostic=policy_metrics(net,dev));curve.append(metric)
                net.save(folder/f'{arm}-epoch-{epoch:03}.npz',dict(source_commit=commit(),validation=dict(qualified=False),value_unfitted=True,target=d['target']))
                print(json.dumps(dict(arm=arm,**metric)),flush=True)
        chosen=min(curve,key=lambda r:(r['diagnostic']['sampled_regret'],r['epoch']))['epoch'];selected=Network.load(folder/f'{arm}-epoch-{chosen:03}.npz')[0]
        selected.save(folder/f'{arm}-selected.npz',dict(source_commit=commit(),validation=dict(qualified=False),value_unfitted=True,target=d['target']))
        report[arm]=dict(selected_epoch=chosen,curve=curve,actor_fingerprint=selected.actor_fingerprint,parameters=selected.parameters)
    dump(folder/'fit.json',dict(source_commit=commit(),primary='regret_mean',arms=report))


class BehaviorRecorder:
    def __init__(self,sink,metadata,baseline):self.sink=sink;self.metadata=metadata;self.baseline=baseline;self.decisions=0;self.changed=0
    def record(self,obs,actions,selection):
        alt=self.baseline.choose(obs,actions) if obs['player']==0 else None
        if alt is not None:self.decisions+=1;self.changed+=tuple(selection['action'])!=tuple(alt['action'])
        self.sink.write(json.dumps(dict(record_type='decision',metadata=self.metadata,observation=obs,legal_actions=actions,selection=selection,baseline=alt),separators=(',',':'))+'\n')
    def finish(self,result):self.sink.write(json.dumps(dict(record_type='outcome',metadata=self.metadata,result=small_result(result)))+'\n')


def development(folder):
    if (folder/'development.json').exists():raise ValueError('Preserve development')
    d=json.loads((folder/'design.json').read_text());base=Network.load(BASE)[0];ms={a:Network.load(folder/f'{a}-selected.npz')[0] for a in ARMS};ms['v5']=base
    results=[];scores=defaultdict(list);behaviors=defaultdict(Counter)
    with gzip.open(folder/'development-decisions.jsonl.gz','wt') as decisions,gzip.open(folder/'development-games.jsonl.gz','wt') as sink:
        for group,a,b,souls,style in cases():
            for seed in d['development_seeds']:
                for seat in (0,1):
                    for name,net in ms.items():
                        meta=dict(group=group,seed=seed,seat=seat,policy=name);rec=BehaviorRecorder(decisions,meta,LearnedPolicy(base))
                        r=run((a,b),seed,(LearnedPolicy(net),opponent(style)),seat,souls,rec)
                        sink.write(json.dumps(dict(meta,result=small_result(r)))+'\n');results.append(dict(meta,unknown=r['unfinished'],won=r['won']))
                        scores[name].append((0 if r['unfinished'] else int(r['won']),1 if r['unfinished'] else int(r['won'])))
                        behaviors[name].update(decisions=rec.decisions,changed=rec.changed,unknown=r['unfinished'])
            print(json.dumps(dict(group=group,completed_slots=len(results))),flush=True)
    # Cluster all contexts and both seats by seed; raw completion bounds kept.
    metrics={};perseed={}
    for name in ms:
        lo=[];hi=[]
        for seed in d['development_seeds']:
            rs=[r for r in results if r['policy']==name and r['seed']==seed]
            lo.append(np.mean([0 if r['unknown'] else int(r['won']) for r in rs]));hi.append(np.mean([1 if r['unknown'] else int(r['won']) for r in rs]))
        perseed[name]=(np.array(lo),np.array(hi))
    a,b=perseed['regret_mean']
    for name,(lo,hi) in perseed.items():metrics[name]=dict(win=interval(lo,hi),primary_gain=interval(a-hi,b-lo),behavior=dict(behaviors[name]))
    ratio=behaviors['regret_mean']['changed']/max(1,behaviors['regret_mean']['decisions']);gain=metrics['v5']['primary_gain']
    proceed=bool(a.mean()>=perseed['v5'][1].mean() and gain['low']>=-.1 and ratio>=.01 and not behaviors['regret_mean']['unknown'])
    dump(folder/'development.json',dict(source_commit=commit(),primary='regret_mean',metrics=metrics,activation=ratio,proceed_to_final=proceed,gate=d['development_gate'],no_reselection=True))
    if not proceed:dump(folder/'final-status.json',dict(status='not_executed',reason='Predeclared development gate failed; do not spend a large final on an inactive/degraded policy',final_seeds_unread=True,value_final_unread=True,qualified=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','collect','fit','development']);p.add_argument('--output',type=Path,required=True);p.add_argument('--stage',choices=['train','diagnostic']);a=p.parse_args()
    if a.mode=='collect':collect(a.output,a.stage)
    else:globals()[a.mode](a.output)
