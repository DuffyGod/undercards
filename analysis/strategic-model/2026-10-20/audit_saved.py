"""Read-only checks of NEW saved controls/prefixes; never resimulate."""
from pathlib import Path
import argparse,gzip,json
from run import HERE


def records(path):
    with gzip.open(path,'rt') as f:
        for line in f:yield json.loads(line)


def audit(path):
    controls=[]
    for name in ('no_response','unfunded_response'):
        index={(r['split'],r['seed'],r['row'],r['column']):r for r in records(path/f'{name}.jsonl.gz')}
        pairs=0
        for (split,seed,row,col),a in index.items():
            # commit->guard and pressure_commit->pressure_guard, same body
            # order/combat: all threat-dependent differences must disappear.
            if row%6 not in (0,3):continue
            b=index[split,seed,row+1,col]
            aa={k:v for k,v in a.items() if k!='row'};bb={k:v for k,v in b.items() if k!='row'}
            if aa!=bb:raise ValueError(f'Threat-off policy difference: {name}/{seed}/{row}/{col}')
            pairs+=1
        controls.append(dict(world=name,exact_seed_policy_pairs=pairs,passed=True))
    base={(r['split'],r['seed'],r['row'],r['column']):r['snapshots'] for r in records(path/'sweep_integrity_seat0.jsonl.gz')}
    prefixes=0
    for r in records(path/'longer_horizon.jsonl.gz'):
        key=r['split'],r['seed'],r['row'],r['column'];a=base[key];b=r['snapshots']
        if a!=b[:len(a)]:raise ValueError(f'Horizon influenced prior causal play: {key}')
        prefixes+=1
    result=dict(new_simulations=0,controls=controls,exact_horizon_prefixes=prefixes,
        evidence_limit='Exact consistency of selected new saved controls and causal prefixes; not external game accuracy or strategic completeness')
    (path/'derived/saved-audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2));return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',type=Path,default=HERE/'experiment-v01')
    audit(p.parse_args().experiment)
