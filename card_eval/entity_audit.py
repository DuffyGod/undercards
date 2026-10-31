"""Read-only V8 input/model/final-accounting checks; no replay or training."""
from pathlib import Path
import argparse,hashlib,json
import numpy as np
from .entity_research import SOURCE,BASE,rows,dataset,models,agent,on_policy
from .network import Network
from .training import commit
from .memory_research import read_rows


def audit(folder):
    folder=Path(folder);d=json.loads((folder/'design.json').read_text());fit=json.loads((folder/'fit.json').read_text());dev=json.loads((folder/'development.json').read_text())
    for p,digest in d['source_files'].items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=digest:raise ValueError('Source evidence changed')
    train,counts=dataset(rows(SOURCE,'train'),on_policy('train') if d.get('include_on_policy') else None)
    if counts!=fit['training']:raise ValueError('Source counts mismatch')
    with np.load(folder/'value-train.npz',allow_pickle=False) as data:
        for k,v in train.items():
            if not np.array_equal(v,data[k]):raise ValueError('Saved training input differs: '+k)
    ms=models(folder);base=Network.load(BASE)[0]
    for arm in ('entity','aggregate'):
        model=ms[arm];report=fit['arms'][arm]
        if model.fingerprint!=report['fingerprint'] or model.actor_fingerprint!=base.actor_fingerprint:raise ValueError('Frozen weights/actor mismatch')
        epoch=min(report['curve'],key=lambda r:(r['development']['nll'],r['epoch']))['epoch']
        if epoch!=report['selected_epoch'] or model.parameters!=d['arms'][arm]:raise ValueError('Checkpoint selection mismatch')
    margin=max(dev['results'],key=lambda r:(r['lower'],r['margin']))['margin']
    if margin!=dev['selected_margin']:raise ValueError('Margin selection mismatch')
    plan=json.loads((folder/'final-plan.json').read_text())
    for name in ('entity','aggregate','linear'):
        if agent(name,ms,d,margin).fingerprint!=plan['frozen_policies'][name]:raise ValueError('Final policy mismatch')
    expected={(g,s,seat,p) for g in d['final_cases'] for s in d['final_seeds'] for seat in (0,1) for p in d['final_policies']};seen=set();unknown=0
    for row in read_rows(folder/'final-games.jsonl.gz'):
        key=(row['group'],row['seed'],row['seat'],row['policy'])
        if key in seen:raise ValueError('Duplicate final slot')
        seen.add(key);unknown+=bool(row['result']['unfinished'])
        if row['planner'].get('proof_mismatch',0):raise ValueError('Committed proof diverged from public rules')
    final=json.loads((folder/'final.json').read_text())
    if seen!=expected or unknown!=len(final['failures']):raise ValueError('Final denominator/unknown accounting mismatch')
    fresh,fc=dataset(rows(folder,'diagnostic',reused=False))
    if fc!=json.loads((folder/'final-value.json').read_text())['counts']:raise ValueError('Final value denominator mismatch')
    split=[set(train['seeds']),set(d['development_seeds']),set(d['final_seeds']),set(d['diagnostic_seeds'])]
    for i,s in enumerate(split):
        if any(s&t for t in split[i+1:]):raise ValueError('Seed splits overlap')
    return dict(status='passed',source_commit=commit(),training_counts=counts,final_slots=len(seen),unresolved_slots=unknown,
        value_counts=fc,actor_unchanged=True,final_selection=False,replayed_games=0,refitted_models=0,
        scope='Internal consistency only; not server-rule certification or a general-quality guarantee.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',required=True,type=Path);args=p.parse_args();print(json.dumps(audit(args.folder),indent=2))
