"""Read-only V11 input and held-suffix diagnostics; no replay or fitting."""
from collections import Counter,defaultdict
from pathlib import Path
import argparse,hashlib,json
import numpy as np
from .action_value import encode
from .suffix_sampling import stable
from .memory_research import read_rows
from .network import Network
from .policies import LearnedPolicy
from .statistics import interval
from .training import dump,commit


def audit(folder):
    d=json.loads((folder/'design.json').read_text());stages={};files={}
    for name,digest in d['source_files'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:raise ValueError('Reusable source changed')
    for stage in ('train','diagnostic'):
        rows=list(read_rows(folder/f'{stage}-targets.jsonl.gz'));seen=set();counts=Counter();group=offset=0
        info=json.loads((folder/f'{stage}-inputs.json').read_text());path=folder/f'{stage}-inputs.npz'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=info['sha256']:raise ValueError('Input cache hash mismatch')
        with np.load(path,allow_pickle=False) as ds:
            for r in rows:
                key=(r['seed'],r['decision'])
                if key in seen:raise ValueError('Duplicate root')
                seen.add(key);counts[r['origin']]+=1
                bs=r['branches'];keys=[(b['suffix'],b['action_index']) for b in bs]
                expected={(s,a) for s in range(1,d['suffixes'][stage]+1) for a in r['indices']}
                if len(keys)!=len(set(keys)) or set(keys)!=expected:raise ValueError('Missing/duplicate continuation slot')
                permutations={};opponent=set();own_bags=set()
                for b in bs:
                    counts['slots']+=1;counts['unknown']+=b['unfinished']
                    if b['unfinished']:
                        if b['won'] is not None:raise ValueError('Unknown outcome imputed')
                    elif type(b['won']) is not bool:raise ValueError('Invalid terminal outcome')
                    m=b['sampler_private']
                    if m is None:
                        if not b['unfinished']:raise ValueError('Missing successful sampler receipt')
                        continue
                    if not m['information_unchanged'] or not m['opponent_hidden_unchanged'] or m['observation_hash']!=stable(r['observation']):raise ValueError('Information constraint mismatch')
                    order=tuple(m['own_future_uids']);hand={h['uid'] for h in r['observation']['hand']}
                    if len(order)!=r['observation']['deck_count'] or len(order)!=len(set(order)) or hand.intersection(order):raise ValueError('Hidden-card conservation mismatch')
                    if b['suffix'] in permutations and permutations[b['suffix']]!=order:raise ValueError('Unpaired own future')
                    permutations[b['suffix']]=order;own_bags.add(tuple(sorted(order)));opponent.add(m['opponent_hidden_hash'])
                    counts['reused_identical']+=m['reused_identical_continuation']
                if len(opponent)>1 or len(own_bags)>1:raise ValueError('Different root latent component across branches')
                if len(set(permutations.values()))!=r['unique_orders']:raise ValueError('Unique suffix count mismatch')
                used=[b for b in bs if b['suffix']<=4]
                if any(b['unfinished'] for b in used):counts['excluded_fit_groups']+=1;continue
                actions=list(map(tuple,r['legal_actions']));x=encode(r['observation'],actions)[1][0].astype(np.float32);n=len(x)
                one=np.full(n,np.nan);mean=one.copy()
                for index in r['indices']:
                    labels=sorted([b for b in used if b['action_index']==index],key=lambda b:b['suffix'])
                    one[index]=int(labels[0]['won']);mean[index]=np.mean([b['won'] for b in labels])
                if (not np.array_equal(ds['x'][offset:offset+n],x) or not np.array_equal(ds['single'][offset:offset+n],one,equal_nan=True)
                    or not np.array_equal(ds['mean'][offset:offset+n],mean,equal_nan=True) or ds['anchors'][group]!=offset+r['baseline_action'] or ds['seeds'][group]!=r['seed']):raise ValueError('Cached target/feature/anchor mismatch')
                offset+=n;group+=1
            if group!=len(ds['anchors']) or offset!=len(ds['x']):raise ValueError('Cache denominator mismatch')
            for seed in set(ds['seeds']):
                if not np.isclose(ds['weights'][ds['seeds']==seed].sum(),1.):raise ValueError('Opening weight mismatch')
                if seed in d['final_seeds']+d['value_final_seeds']:raise ValueError('Final data leakage')
        status=json.loads((folder/f'{stage}-collection.json').read_text())
        if counts['slots']!=status['continuations'] or counts['unknown']!=status['unknown_continuations']:raise ValueError('Collection count mismatch')
        metadata=[r for r in read_rows(folder/f'{stage}-fresh-rollins.jsonl.gz') if r['record_type']=='input']
        joint=Counter((r['opponent'],r['seat']) for r in metadata)
        if len(joint)!=8 or len(set(joint.values()))!=1:raise ValueError('Fresh opponent/seat allocation not crossed')
        stages[stage]=dict(counts,roots=len(rows),original_openings=len({r['seed'] for r in rows}),fitted_groups=group,
            fresh_joint=[dict(opponent=a,seat=b,inputs=n) for (a,b),n in sorted(joint.items())])
        target_path=folder/f'{stage}-targets.jsonl.gz';files[str(target_path)]=hashlib.sha256(target_path.read_bytes()).hexdigest()
    return dict(status='passed',source_commit=commit(),stages=stages,input_hashes=files,
        scope='All continuation keys, masks, exact encoded inputs, pairing, information constraints and opening weights; no game replay or refit')


def noise(folder):
    rows=list(read_rows(folder/'diagnostic-targets.jsonl.gz'));nets={a:Network.load(folder/f'{a}-selected.npz')[0] for a in ('regret_mean','regret_single','centered_mean','centered_single')}
    summaries={}
    for origin in ('all','reused_retrospective','fresh_online_stopping_time'):
        values=defaultdict(lambda:defaultdict(list));counts=Counter();gains=defaultdict(lambda:defaultdict(list));choice_counts=defaultdict(Counter)
        for r in rows:
            if origin!='all' and r['origin']!=origin:continue
            counts['roots']+=1;seed=r['seed'];indices=r['indices'];base=indices.index(r['baseline_action']);lookup={(b['suffix'],b['action_index']):b for b in r['branches']}
            complete=all(not b['unfinished'] for b in r['branches'])
            if complete:
                y=np.array([[int(lookup[s,a]['won']) for a in indices] for s in range(1,9)]);adv=y-y[:,base,None];other=np.arange(len(indices))!=base
                held=adv[4:].mean(0);first=adv[0];mean=adv[:4].mean(0)
                values[seed]['advantage_mse_single'].append(float(np.mean((first[other]-held[other])**2)))
                values[seed]['advantage_mse_mean'].append(float(np.mean((mean[other]-held[other])**2)))
                values[seed]['paired_advantage_variance'].append(float(np.var(adv[:,other],axis=0,ddof=1).mean()))
                values[seed]['unpaired_variance_reference'].append(float((np.var(y[:,other],axis=0,ddof=1)+np.var(y[:,base],ddof=1)).mean()))
                values[seed]['absolute_action_variance'].append(float(np.var(y[:,other],axis=0,ddof=1).mean()))
                counts['roots_with_sign_flip']+=bool(np.any((adv.min(0)<0)&(adv.max(0)>0)));counts['complete_noise_roots']+=1
                def greedy(v):return base if v[base]==v.max() else int(v.argmax())
                held_y=y[4:].mean(0)
                for name,pred in (('single',y[0]),('mean',y[:4].mean(0))):
                    values[seed]['held_regret_'+name].append(float(held_y.max()-held_y[greedy(pred)]))
            else:counts['unknown_noise_roots']+=1
            actions=list(map(tuple,r['legal_actions']));x=encode(r['observation'],actions)[1][0]
            def bounds(index):
                if index not in indices:return (0.,1.)
                bs=[lookup[s,index] for s in (5,6,7,8)];wins=sum(int(b['won']) for b in bs if not b['unfinished']);unknown=sum(b['unfinished'] for b in bs)
                return wins/4,(wins+unknown)/4
            blo,bhi=bounds(r['baseline_action'])
            for name,net in nets.items():
                selected=LearnedPolicy(net).choose(r['observation'],actions)['action_index'];lo,hi=bounds(selected)
                gain=(0.,0.) if selected==r['baseline_action'] else (lo-bhi,hi-blo)
                gains[seed][name].append(gain);choice_counts[name].update(roots=1,raw_changed=int(selected!=r['baseline_action']),
                    semantic_changed=int(not np.array_equal(x[selected],x[r['baseline_action']])),measured=int(selected in indices),unknown_held=int(lo!=hi))
        metrics={name:interval([np.mean(v[name]) for v in values.values()]) for name in next(iter(values.values()),{})}
        if values:
            metrics['mean_target_error_reduction']=interval([np.mean(v['advantage_mse_single'])-np.mean(v['advantage_mse_mean']) for v in values.values()])
            metrics['mean_target_held_regret_reduction']=interval([np.mean(v['held_regret_single'])-np.mean(v['held_regret_mean']) for v in values.values()])
        summaries[origin]=dict(counts,noise_seed_clusters=len(values),metrics=metrics,
            choices={a:dict(choice_counts[a],held_suffix_gain=interval(*np.array([np.mean(v[a],axis=0) for v in gains.values()]).T)) for a in nets})
    return dict(source_commit=commit(),cohorts=summaries,parameters_changed=False,
        scope='Suffix5..8 were not used for fitting/epoch selection. Same diagnostic roots, not new independent worlds or a global final. Q target still holds opponent latent state fixed; unknown choices/outcomes retain0/1 bounds.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['audit','noise']);p.add_argument('--folder',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    if a.output.exists():raise ValueError('Preserve receipt')
    result=globals()[a.mode](a.folder);dump(a.output,result);print(json.dumps(result,indent=2))
