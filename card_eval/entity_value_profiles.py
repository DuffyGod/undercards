"""Phase diagnostics from fresh V5 roll-ins already saved by collection.

Only baseline-behavior episodes have the correct frozen-V5 continuation label.
Race episodes and unfinished episodes are never silently relabelled as V5.
No model/epoch/margin selection occurs here.
"""
from collections import Counter
from pathlib import Path
import argparse,json
import numpy as np
from .entity_research import models,probabilities
from .entity_value import entity_state
from .memory_research import read_rows
from .statistics import interval
from .training import dump,commit


def phase_interval(values):
    result=interval(values)
    if len(values)<8:
        result.update(low=None,high=None,inference='Too few opening clusters for phase CI; descriptive mean only')
    return result


def profile(folder):
    folder=Path(folder);ms=models(folder);rows=[];counts=Counter()
    for path in sorted(folder.glob('diagnostic-rollins-*.jsonl.gz')):
        meta=None;observations=[]
        for row in read_rows(path):
            if row['record_type']=='input':meta=row;observations=[]
            elif row['record_type']=='decision' and row['observation']['player']==0:
                if meta['behavior']=='baseline':
                    if row['selection']['policy']!=ms['v5'].fingerprint:raise ValueError('Wrong roll-in actor')
                    observations.append(row['observation'])
            elif row['record_type']=='outcome':
                if meta['behavior']!='baseline':counts['other_actor_episodes_excluded']+=1;continue
                counts['baseline_episodes']+=1
                if row['result']['unfinished']:counts['unknown_baseline_episodes']+=1;continue
                for obs in observations:
                    rows.append((meta['seed'],obs['turn'],obs['deck_count']==0,entity_state(obs).astype(np.float32),int(row['result']['won'])))
    output={}
    for name,keep in [('all',lambda r:True),('turns1_5',lambda r:r[1]<=5),('turns6_12',lambda r:6<=r[1]<=12),('past12',lambda r:r[1]>12),('empty_own_deck',lambda r:r[2])]:
        selected=[r for r in rows if keep(r)];seeds=sorted(set(r[0] for r in selected))
        if not selected:output[name]=dict(states=0,opening_clusters=0,brier=None,reason='No observed states, not zero error');continue
        data=dict(states=np.asarray([r[3] for r in selected]),labels=np.array([r[4] for r in selected]));seed_array=np.array([r[0] for r in selected]);errors={}
        for model in ('entity','aggregate','linear'):
            p=probabilities(ms[model],data);e=(p-data['labels'])**2
            errors[model]={s:float(np.mean(e[seed_array==s])) for s in seeds}
        output[name]=dict(states=len(selected),opening_clusters=len(seeds),brier={m:phase_interval([v[s] for s in seeds]) for m,v in errors.items()},
            entity_error_reduction={m:phase_interval([errors[m][s]-errors['entity'][s] for s in seeds]) for m in ('aggregate','linear')})
    result=dict(source_commit=commit(),counts=dict(counts),profiles=output,
        target='FrozenV5 continuation only; full natural trajectories from baseline-behavior half of fresh value worlds.',
        no_selection=True,limits='Per-phase opening clusters can be few. Phases are correlated, not independent experiments. No unobserved tail filled with zero.')
    dump(folder/'value-profiles.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',required=True,type=Path);args=p.parse_args();print(json.dumps(profile(args.folder),indent=2))
