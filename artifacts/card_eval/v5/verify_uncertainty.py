"""Reproduce the post-test interval sensitivity; never select or alter a model."""
from pathlib import Path
import gzip,json,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from card_eval.statistics import interval

folder=Path(__file__).resolve().parent
cells={}
with gzip.open(folder/'final-games.jsonl.gz','rt') as stream:
    for line in stream:
        row=json.loads(line)
        if row['policy'] in ('primary','previous_v4'):
            cells.setdefault((row['group'],row['seed']),{}).setdefault(row['policy'],[]).append(row['result'])
groups={}
for (group,seed),policies in cells.items():
    def bounds(rs):
        return [np.mean([endpoint if r['unfinished'] else float(r['won']) for r in rs]) for endpoint in (0,1)]
    a,b=bounds(policies['primary']),bounds(policies['previous_v4'])
    groups.setdefault(group,[]).append((a[0]-b[1],a[1]-b[0]))
expected=json.loads((folder/'multiple-context-sensitivity.json').read_text())['comparisons']
actual={group:interval(*np.asarray(values).T,alpha=.05/7) for group,values in groups.items()}
assert actual==expected
print('Seven-context interval sensitivity reconstructed; original gate and weights unchanged.')
