"""Describe frozen V10 changes on its already-used training/diagnostic forks.

These are in-sample/selection diagnostics, never independent quality evidence.
No rollout, refit, parameter choice, or final observation is involved.
"""
from collections import defaultdict, Counter
from pathlib import Path
import argparse, hashlib, json
import numpy as np
from .action_research import raw_rows
from .network import Network
from .policies import LearnedPolicy
from .statistics import interval
from .training import dump, commit


def diagnose(folder):
    nets={a:Network.load(folder/f'{a}-selected.npz')[0] for a in ('centered','pointwise')};output={};aliases=[]
    for stage in ('train','diagnostic'):
        seeds=defaultdict(lambda:defaultdict(list));counts=Counter();origins=Counter()
        for row in raw_rows(folder,stage):
            actions=list(map(tuple,row['legal_actions']));obs=row['observation'];base=row['baseline_action']
            labels={b['action_index']:(None if b['unfinished'] else int(b['won'])) for b in row['branches'] if b['continuation']=='current'}
            def bounds(index):
                y=labels.get(index)
                return (0.,1.) if y is None else (float(y),float(y))
            bl,bh=bounds(base);seed=row['seed'];counts['forks']+=1
            origins['fresh' if row['provenance']=='fresh_V5_on_policy' else 'reused']+=1
            for name,net in nets.items():
                decision=LearnedPolicy(net).choose(obs,actions);chosen=decision['action_index'];counts[name+'_changed']+=chosen!=base
                counts[name+'_chosen_measured']+=labels.get(chosen) is not None
                lo,hi=bounds(chosen)
                # Identical intervention contrasts are identically zero even
                # if its absolute outcome is missing. No win is imputed.
                gain=(0.,0.) if chosen==base else (lo-bh,hi-bl)
                seeds[seed][name].append(gain)
            lows,highs=zip(*(bounds(i) for i in labels))
            seeds[seed]['sampled_hindsight'].append((max(lows)-bh,max(highs)-bl))
            _,(x,_)=nets['centered'].encode(obs,actions);by_input=defaultdict(list)
            for i,y in labels.items():
                if y is not None:by_input[hashlib.sha256(x[i].tobytes()).hexdigest()].append((i,y))
            for matches in by_input.values():
                if len({y for _,y in matches})>1:
                    counts['same_input_different_realized_outcome']+=1
                    if len(aliases)<4:
                        aliases.append(dict(stage=stage,seed=seed,decision=row['decision'],provenance=row['provenance'],
                            actions=[dict(action=actions[i],won=y) for i,y in matches]))
        output[stage]=dict(counts,origins=dict(origins),openings=len(seeds),
            gains={name:interval(*np.array([np.mean(v[name],axis=0) for v in seeds.values()]).T)
                   for name in ('centered','pointwise','sampled_hindsight')})
    return dict(source_commit=commit(),scope='Training/epoch-selection diagnostics only; not new independent evaluation or general-policy qualification',
        datasets=output,input_alias_examples=aliases,
        limits='Sampled realized hindsight is not an optimal policy bound. Unmeasured choices retain0/1 completion bounds. Aliases are specified-continuation outcomes in one coupled world, not Bayes-value irreducibility or natural-frequency estimates.',
        parameters_changed=False,final_used=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    if a.output.exists():raise ValueError('Preserve diagnostic')
    result=diagnose(a.folder);dump(a.output,result);print(json.dumps(result,indent=2))
