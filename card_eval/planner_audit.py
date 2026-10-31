"""Read-only V7 evidence checks, without replaying old games or retraining."""
from pathlib import Path
import argparse,hashlib,json
from .network import Network
from .planner_research import rows,samples,BASE,SOURCE
from .memory_research import read_rows
from .public_planner import PublicPlanner
from .relations import state_features
from .knowledge import vector
import numpy as np
from .training import commit


def audit(folder):
    folder=Path(folder);design=json.loads((folder/'design.json').read_text());fit=json.loads((folder/'fit.json').read_text())
    for path,digest in design['source_files'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Reusable source changed')
    data,counts=samples(rows(SOURCE,'train'))
    if counts!=fit['counts']:raise ValueError('Training input counts mismatch')
    base=Network.load(BASE)[0]
    for name in ('root','afterstate'):
        net=Network.load(folder/(name+'-value.npz'))[0]
        if net.actor_fingerprint!=base.actor_fingerprint or net.fingerprint!=fit['fits'][name]['fingerprint']:
            raise ValueError('Frozen weights changed')
    dev=json.loads((folder/'development.json').read_text());plan=json.loads((folder/'final-plan.json').read_text())
    for name,mode,net in [('primary','value',Network.load(folder/'afterstate-value.npz')[0]),('proof','proof',base),('old_value','value',base)]:
        policy=PublicPlanner(net,mode,dev['selected_margin'],**design['planner'])
        if policy.fingerprint!=plan['frozen_policies'][name]:raise ValueError('Final planner differs from frozen selection')
    used=[set(design['development_seeds']),set(design['final_seeds']),set(design['diagnostic_seeds']),set(s for s,*_ in data)]
    for i,a in enumerate(used):
        if any(a&b for b in used[i+1:]):raise ValueError('Seed split overlap')
    expected={(g,s,seat,p) for g in design['final_cases'] for s in design['final_seeds'] for seat in (0,1) for p in design['final_policies']}
    seen=set();unknown=[];events={}
    for row in read_rows(folder/'final-games.jsonl.gz'):
        key=(row['group'],row['seed'],row['seat'],row['policy'])
        if key in seen:raise ValueError('Duplicate final slot')
        seen.add(key)
        if row['result']['unfinished']:unknown.append(key)
        if row['planner'].get('proof_mismatch',0):raise ValueError('Committed public proof diverged from live engine')
    if seen!=expected:raise ValueError('Missing or extra final slots')
    final=json.loads((folder/'final.json').read_text())
    if len(unknown)!=len(final['failures']):raise ValueError('Unknown completion accounting mismatch')
    value=json.loads((folder/'final-value.json').read_text());_,counts=samples(rows(folder,'diagnostic',reused=False))
    if counts!=value['counts']:raise ValueError('Final value input mismatch')
    witness=json.loads((folder/'value-alias-witness.json').read_text());a,b=witness['observations']
    if not np.array_equal(state_features(a),state_features(b)) or not np.array_equal(vector(a),vector(b)) or witness['outcomes']!=[1,0]:
        raise ValueError('Structural counterexample mismatch')
    return dict(status='passed',source_commit=commit(),training_counts=fit['counts'],final_slots=len(seen),
        unresolved_slots=len(unknown),value_counts=counts,actor_unchanged=True,final_selection=False,
        replayed_games=0,refitted_models=0,representation_alias_checked=True,scope='Internal evidence consistency; no server-rule or general-policy certification.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True);args=p.parse_args()
    print(json.dumps(audit(args.folder),ensure_ascii=False,indent=2))
