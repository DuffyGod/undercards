"""Explicitly post-hoc V13 diagnostic, with a new development seed set.

It cannot replace the rejected primary or unlock its reserved finals.
The negative control disables terminal cost loss, not unknown outcome masks.
"""
from collections import Counter,defaultdict
from copy import deepcopy
from pathlib import Path
import argparse,gzip,json,time
import numpy as np
from .policy_iteration import design,dataset,BASE,read_rows
from .network import Network
from .policies import LearnedPolicy
from .memory_research import opponent
from .suffix_research import cases,BehaviorRecorder
from .counterfactual_research import run
from .relational_research import small_result
from .statistics import interval
from .training import dump,commit


def prepare(folder):
    path=folder/'posthoc-prior-plan.json'
    if path.exists():raise ValueError('Preserve posthoc plan')
    original=json.loads((folder/'development.json').read_text());assert not original['proceed_to_final']
    dump(path,dict(source_commit=commit(),declared_after_initial_development=True,
        question='Does updating terminal continuation cost help beyond the same-budget V5-prior-only distillation?',
        primary_status_unchanged='development_rejected;433/435 stay unread regardless of this diagnostic',
        training='Same phase1 public inputs/root weights/anchors, same phase0 warm start, seed/batches/64epochs/L2/lr. Set only terminal cost loss weight to0. Do not fill unknown outcomes with0.',
        fresh_seeds=list(range(4160000,4160008)),policies=['updated','frozen','prior_only','v5'],
        slots=320,decision_seconds=.25,selection='No model or threshold selection; fixed64epoch, no primary replacement.',
        inference='Eight paired seed clusters across five known contexts; posthoc hypothesis, fresh development worlds. Not final qualification/equivalence/whole-environment evidence.'))


def fit(folder):
    if (folder/'prior-only-selected.npz').exists():raise ValueError('Preserve control fit')
    d=design(folder);assert (folder/'posthoc-prior-plan.json').exists();train=dataset(folder,1,'train','updated')
    net=Network.load(folder/'phase0-selected.npz')[0];warm=net.actor_fingerprint;rng=np.random.default_rng(d['rng_seed'])
    m={k:np.zeros_like(p) for k,p in net.p.items()};v=deepcopy(m);step=0
    idx={g:np.where(train['groups']==g)[0] for g in train['anchors']};ng=len(idx);total=sum(train['weights'].values())
    for epoch in range(d['epochs']):
        order=rng.permutation(ng)
        for start in range(0,ng,d['batch']):
            selected=order[start:start+d['batch']];ix=np.concatenate([idx[g] for g in selected]);reverse={j:i for i,j in enumerate(ix)}
            weights={int(g):float(train['weights'][g]/total*ng/len(selected)) for g in selected}
            anchors={int(g):reverse[train['anchors'][g]] for g in selected}
            _,grads=net.loss_grad(train['x'][ix],train['y'][ix],train['groups'][ix],anchors,weights,d['l2'],cost_weight=0.);step+=1
            norm=np.sqrt(sum(np.sum(g*g) for g in grads.values()));scale=min(1.,5/max(norm,1e-12))
            for k,g in grads.items():
                g=g*scale;m[k]=.9*m[k]+.1*g;v[k]=.999*v[k]+.001*g*g
                net.p[k]-=d['lr']*(m[k]/(1-.9**step))/(np.sqrt(v[k]/(1-.999**step))+1e-8)
    net.target_description='Posthoc negative control: V5 policy prior only; terminal cost loss disabled, not a learned value'
    net.save(folder/'prior-only-selected.npz',dict(source_commit=commit(),validation=dict(qualified=False),value_unfitted=True,
        posthoc_control=True,terminal_cost_weight=0.,not_eligible_for_reselection=True))
    dump(folder/'posthoc-prior-fit.json',dict(source_commit=commit(),warm_start_actor=warm,actor_fingerprint=net.actor_fingerprint,
        optimizer_steps=step,epochs=d['epochs'],parameters=net.parameters,training_roots=ng,terminal_cost_weight=0.,
        unknown_labels_imputed=False,primary_status_unchanged=True))


def development(folder):
    if (folder/'posthoc-prior-development.json').exists():raise ValueError('Preserve diagnostic')
    plan=json.loads((folder/'posthoc-prior-plan.json').read_text());base=Network.load(BASE)[0]
    models={n:Network.load(folder/file)[0] for n,file in (('updated','updated-selected.npz'),('frozen','frozen-selected.npz'),('prior_only','prior-only-selected.npz'))};models['v5']=base
    results=[];behavior=defaultdict(Counter)
    with gzip.open(folder/'posthoc-prior-decisions.jsonl.gz','wt') as decisions,gzip.open(folder/'posthoc-prior-games.jsonl.gz','wt') as sink:
        for group,a,b,souls,style in cases():
            for seed in plan['fresh_seeds']:
                for seat in (0,1):
                    for name,net in models.items():
                        meta=dict(group=group,seed=seed,seat=seat,policy=name);rec=BehaviorRecorder(decisions,meta,LearnedPolicy(base))
                        r=run((a,b),seed,(LearnedPolicy(net),opponent(style)),seat,souls,rec)
                        sink.write(json.dumps(dict(meta,result=small_result(r)))+'\n');results.append(dict(meta,result=r))
                        behavior[name].update(decisions=rec.decisions,changed=rec.changed,raw_changed=rec.raw_changed,unknown=r['unfinished'])
            print(json.dumps(dict(group=group,posthoc_slots=len(results))),flush=True)
    scores={}
    for name in models:
        clusters=[[r['result'] for r in results if r['policy']==name and r['seed']==seed] for seed in plan['fresh_seeds']]
        scores[name]=(np.array([np.mean([0 if r['unfinished'] else int(r['won']) for r in rs]) for rs in clusters]),
                      np.array([np.mean([1 if r['unfinished'] else int(r['won']) for r in rs]) for rs in clusters]))
    lo,hi=scores['updated']
    dump(folder/'posthoc-prior-development.json',dict(source_commit=commit(),declared_after_initial_development=True,
        metrics={n:dict(win=interval(a,b),updated_gain=interval(lo-b,hi-a),behavior=dict(behavior[n])) for n,(a,b) in scores.items()},
        primary_status_unchanged='development_rejected',finals_still_unread=True,no_reselection=True))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','fit','development']);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();globals()[args.mode](args.output)
