"""Use fresh, already recorded paired continuations to inspect first choices.

This is not a win-rate evaluation of the whole searched policy. Unmeasured
choices keep0/1 bounds; an identical intervention has exactly zero contrast.
"""
from collections import Counter,defaultdict
from pathlib import Path
import argparse,gzip,json,time
import numpy as np
from .entity_research import models,agent,rows
from ._proof_first_v2 import PublicPlanner
from .statistics import interval
from .training import dump,commit


def diagnostic(folder):
    folder=Path(folder)
    if (folder/'action-choices.jsonl.gz').exists():raise ValueError('Preserve action diagnostic')
    d=json.loads((folder/'design.json').read_text());margin=json.loads((folder/'development.json').read_text())['selected_margin'];ms=models(folder)
    counts=Counter();differences={n:defaultdict(list) for n in ('proof','v5')}
    with gzip.open(folder/'action-choices.jsonl.gz','wt') as sink:
        for row in rows(folder,'diagnostic',reused=False):
            counts['forks']+=1;obs=row['observation'];actions=list(map(tuple,row['legal_actions']))
            labels={b['action_index']:b for b in row['branches'] if b['continuation']=='baseline'};choices={}
            policies=dict(entity=agent('entity',ms,d,margin),proof=PublicPlanner(ms['entity'],'proof',margin,**d['planner']),v5=agent('v5',ms,d,margin))
            for name,policy in policies.items():
                start=time.perf_counter();selected=policy.choose(obs,actions);seconds=time.perf_counter()-start;valid=seconds<=d['decision_seconds']
                index=actions.index(tuple(selected['action']));branch=labels.get(index)
                measured=valid and branch is not None and not branch['unfinished']
                bounds=[int(branch['won'])]*2 if measured else [0,1]
                counts[name+'_measured']+=measured;counts[name+'_decision_budget_unknown']+=not valid
                choices[name]=dict(index=index,valid=valid,measured=measured,terminal_bounds=bounds,
                    reason=selected.get('planner_reason','v5'),policy=selected['policy'],seconds=seconds,nodes=selected.get('planner_nodes',0))
            contrasts={}
            for name in differences:
                a,b=choices['entity'],choices[name]
                identical=a['valid'] and b['valid'] and a['index']==b['index']
                low,high=[0,0] if identical else [a['terminal_bounds'][0]-b['terminal_bounds'][1],a['terminal_bounds'][1]-b['terminal_bounds'][0]]
                differences[name][row['seed']].append([low,high]);contrasts[name]=[low,high]
                counts['entity_differs_'+name]+=not identical
            sink.write(json.dumps(dict(seed=row['seed'],decision=row['decision'],choices=choices,contrasts=contrasts),separators=(',',':'))+'\n')
    result={}
    for name,per in differences.items():
        bounds=np.asarray([np.asarray(values).mean(0) for values in per.values()]);result[name]=interval(bounds[:,0],bounds[:,1])
    output=dict(source_commit=commit(),counts=dict(counts),entity_minus_control=result,no_selection=True,
        target='One first-action intervention followed by frozenV5, on fresh public prefixes. Not full-search policy value, Q* or card strength.',
        unknown='Unmeasured/unfinished choices0..1, unknown budget choices0..1. Same valid action has exactly zero causal contrast even if outcome unmeasured; not an imputed win.',
        limits='At most6 sampled actions per fork, one hidden-world draw; two forks share an opening. Proof commitments may need a different continuation than V5.')
    dump(folder/'action-diagnostic.json',output);return output


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',required=True,type=Path);args=p.parse_args();print(json.dumps(diagnostic(args.folder),indent=2))
