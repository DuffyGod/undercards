"""Read-only V10 evidence audit: no game replay, fitting, or model selection."""
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path
import argparse, hashlib, json
import numpy as np
from .network import Network
from .memory_research import read_rows
from .relational_research import load_value_data, value_metrics, paired_value_gain
from .statistics import interval
from .training import commit, dump


def audit(folder):
    d=json.loads((folder/'design.json').read_text());final=json.loads((folder/'final.json').read_text())
    for path,digest in d['source_files'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Frozen reusable source hash mismatch')
    for stage in ('train','diagnostic'):
        info=json.loads((folder/f'{stage}-input.json').read_text());path=folder/f'action-{stage}.npz'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=info['sha256']:raise ValueError('Cached action inputs changed')
        with np.load(path,allow_pickle=False) as data:
            if not np.isin(data['y'],(0,1)).all():raise ValueError('Nonterminal outcome used for fitting')
            if len(set(data['seeds']))!=info['openings']:raise ValueError('Opening denominator mismatch')
            if set(data['seeds']) & set(d['final_seeds']+d['value_final_seeds']):raise ValueError('Final leakage')
            for seed in set(data['seeds']):
                if not np.isclose(data['weights'][data['seeds']==seed].sum(),1.):raise ValueError('Opening weighting mismatch')
    records=list(read_rows(folder/'final-games.jsonl.gz'))
    expected=set(product(d['final_cases'],d['final_seeds'],(0,1),d['final_policies']))
    keys=[(r['group'],r['seed'],r['seat'],r['policy']) for r in records]
    if len(keys)!=len(set(keys)) or set(keys)!=expected:raise ValueError('Final slot missing, duplicate, or unexpected')
    unknown=Counter();index={key:r['result'] for key,r in zip(keys,records)}
    for row in records:
        r=row['result']
        if r['unfinished']:
            unknown[row['policy']]+=1
            if r['won'] is not None:raise ValueError('Unknown outcome imputed')
        elif type(r['won']) is not bool:raise ValueError('Invalid terminal binary outcome')
    recomputed=[]
    for group in d['final_cases']:
        scores={}
        for policy in d['final_policies']:
            lows=[];highs=[]
            for seed in d['final_seeds']:
                rs=[index[group,seed,seat,policy] for seat in (0,1)]
                lows.append(np.mean([0 if r['unfinished'] else int(r['won']) for r in rs]))
                highs.append(np.mean([1 if r['unfinished'] else int(r['won']) for r in rs]))
            scores[policy]=(np.asarray(lows),np.asarray(highs))
        a,b=scores['centered'];cs=[]
        saved=next(g for g in final['groups'] if g['group']==group)
        for policy,(lo,hi) in scores.items():
            item=dict(policy=policy,win=interval(lo,hi),primary_gain=interval(a-hi,b-lo),family_gain=interval(a-hi,b-lo,alpha=.05/8))
            if item!=next(c for c in saved['policies'] if c['policy']==policy):raise ValueError('Reported paired interval mismatch')
            cs.append(item)
        recomputed.append(dict(group=group,policies=cs))
    qualified=not sum(unknown.values()) and all(c['primary_gain']['low']>0 for g in recomputed for c in g['policies'] if c['policy']!='centered')
    if qualified!=final['qualified']:raise ValueError('Qualification mismatch')
    net,meta=Network.load(folder/'primary-value.npz');selected=Network.load(folder/'centered-selected.npz')[0]
    if net.actor_fingerprint!=selected.actor_fingerprint or meta['critic_actor_fingerprint']!=net.actor_fingerprint:raise ValueError('Value training changed/mismatched actor')
    for stage,seedfield in (('train','value_train_seeds'),('dev','value_dev_seeds'),('final','value_final_seeds')):
        outcomes=[]
        for path in sorted(folder.glob(f'value-{stage}-*.jsonl.gz')):
            for row in read_rows(path):
                if row['record_type']=='outcome':
                    if row['metadata']['actor_fingerprint']!=net.actor_fingerprint:raise ValueError('Value rollout policy mismatch')
                    outcomes.append(row['episode'])
        if sorted(outcomes)!=sorted(d[seedfield]):raise ValueError('Value rollout denominator mismatch')
    episodes=load_value_data(folder,'final');value=json.loads((folder/'value-final.json').read_text())
    prior=json.loads((folder/'value.json').read_text())['train_prior'];simple=Network.load(folder/'value-simple.npz')[0];v5=Network.load(d['baseline'])[0]
    for key,model in (('primary',net),('simple',simple),('stale_v5',v5)):
        if value_metrics(model,episodes,prior)!=value[key]:raise ValueError('Value metric mismatch')
    for key,model in (('gain_vs_simple',simple),('gain_vs_stale_v5',v5)):
        if paired_value_gain(net,model,episodes)!=value[key]:raise ValueError('Value comparison mismatch')
    return dict(status='passed',source_commit=commit(),scope='Read-only input, slot, weighting, policy/target and metric audit; no replay/refit',
        final_slots=len(keys),unresolved_slots=sum(unknown.values()),unresolved_by_policy=dict(unknown),qualified=qualified,
        actor_fingerprint=net.actor_fingerprint,model_fingerprint=net.fingerprint,
        value_final_openings=len(episodes),value_final_unknown=sum(not e['terminal'] for e in episodes),no_final_selection=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',required=True,type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    result=audit(a.folder)
    if a.output:
        if a.output.exists():raise ValueError('Preserve audit receipt')
        dump(a.output,result)
    print(json.dumps(result,indent=2))
