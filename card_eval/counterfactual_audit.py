"""Reconstruct V5 evidence without replaying any game or changing a model."""
from collections import Counter
from pathlib import Path
import argparse, gzip, hashlib, itertools, json
import numpy as np
from .advantage_model import AdvantageNetwork
from .catalog import semantic_key
from .counterfactual_research import groups
from .network import Network
from .policies import LearnedPolicy
from .profiles import training_pool
from .relational_research import load_value_data, value_metrics, paired_value_gain
from .training import dump, decode, commit


def rows(path):
    with gzip.open(path,'rt',encoding='utf-8') as stream:
        for line in stream: yield json.loads(line)


def public_digest(row):
    return hashlib.sha256(json.dumps([row['observation'],row['legal_actions']],sort_keys=True).encode()).hexdigest()


def audit(folder):
    d=json.loads((folder/'design.json').read_text()); final=json.loads((folder/'final.json').read_text())
    plan=json.loads((folder/'final-plan.json').read_text()); fit=json.loads((folder/'fit.json').read_text())
    heads={name:Network.load(folder/(name+'.npz'))[0] for name in ('action-head','selected-actor','primary-value','value-hp-board')}
    base=Network.load(d['baseline'])[0]; primary=heads['primary-value']; simple=heads['value-hp-board']
    for net in heads.values():
        np.testing.assert_array_equal(net.actor,base.actor)
        np.testing.assert_array_equal(net.advantage,heads['action-head'].advantage)
    assert heads['action-head'].fingerprint==fit['checkpoint_fingerprint']
    assert primary.actor_fingerprint==heads['selected-actor'].actor_fingerprint==simple.actor_fingerprint==plan['actor_fingerprint']
    assert primary.fingerprint==plan['primary_fingerprint']==final['primary_fingerprint']
    assert fit['fit']['converged'] is None and fit['fit']['iterations'] is None
    seed_ranges=[set(d[k]) for k in ('train_seeds','diagnostic_seeds','development_seeds','final_seeds','value_train_seeds','value_dev_seeds','value_final_seeds')]
    assert all(not a&b for a,b in itertools.combinations(seed_ranges,2))
    old=set(range(1210000,1210064))|set(range(1310000,1310048))|set(range(1330000,1330096))
    assert not old&set.union(*seed_ranges)
    collection={}
    for stage in ('train','diagnostic'):
        observed={}; episode_inputs={}; terminal_seeds=set()
        for path in sorted(folder.glob(f'{stage}-rollins-*.jsonl.gz')):
            for row in rows(path):
                if row['record_type']=='decision': observed[row['episode'],row['decision']]=public_digest(row)
                elif row['record_type']=='input': episode_inputs[row['seed']]=row
                else: terminal_seeds.add(row['episode'])
        assert set(episode_inputs)==set(d[stage+'_seeds'])==terminal_seeds
        forks=0; branches=0; unknown=0; excluded=0
        for path in sorted(folder.glob(f'{stage}-forks-*.jsonl.gz')):
            for row in rows(path):
                assert public_digest(row)==observed[row['seed'],row['decision']]
                indices=row['sampled_action_indices']; assert 0 in indices and row['baseline_action'] in indices and len(indices)<=d['max_actions']
                assert all(0<=j<len(row['legal_actions']) for j in indices)
                keys=Counter((b['action_index'],b['continuation']) for b in row['branches'])
                assert set(keys)==set(itertools.product(indices,d['continuations'])) and all(v==1 for v in keys.values())
                for b in row['branches']:
                    if b['unfinished']: assert b['won'] is None and b['lost'] is None
                    else: assert bool(b['won'])!=bool(b['lost'])
                forks+=1; branches+=len(keys); unknown+=sum(b['unfinished'] for b in row['branches'])
                excluded+=any(b['unfinished'] for b in row['branches'])
        recorded=json.loads((folder/f'{stage}-collection.json').read_text())
        assert (forks,branches,unknown)==(recorded['forks'],recorded['branches'],recorded['unresolved_branches'])
        collection[stage]=dict(episodes=len(episode_inputs),forks=forks,branches=branches,unresolved=unknown,unlabeled_forks=excluded)
    data=groups(folder,'train'); x=[];y=[];weights=[]
    for matrix,target,_ in data:
        x.extend(matrix-matrix.mean(axis=0));y.extend(target-target.mean());weights.extend([1/len(target)]*len(target))
    x=np.asarray(x);y=np.asarray(y);weights=np.asarray(weights);weights/=weights.sum();beta=heads['action-head'].advantage
    residual=x@beta-y;loss=float(.5*weights@(residual**2)+.5*d['l2']*(beta@beta))
    gradient=x.T@(weights*residual)+d['l2']*beta
    assert abs(loss-fit['fit']['loss'])<1e-12 and abs(np.linalg.norm(gradient)-fit['fit']['gradient_norm'])<1e-12
    assert len(data)==fit['fit']['paired_groups']==collection['train']['forks']-collection['train']['unlabeled_forks']
    games=list(rows(folder/'final-games.jsonl.gz'));keys=Counter((r['group'],r['seed'],r['seat'],r['policy']) for r in games)
    expected=set(itertools.product(d['final_cases'],d['final_seeds'],(0,1),d['final_policies']))
    assert set(keys)==expected and all(v==1 for v in keys.values())
    assert sum(r['result']['unfinished'] for r in games)==len(final['failures'])
    for group in final['groups']:
        for policy in group['policies']:
            rs=[r['result'] for r in games if r['group']==group['group'] and r['policy']==policy['policy']]
            bounds=[np.mean([endpoint if r['unfinished'] else int(r['won']) for r in rs]) for endpoint in (0,1)]
            np.testing.assert_allclose(bounds,policy['win']['completion_range'],rtol=0,atol=1e-14)
    pool={semantic_key(s) for s in training_pool()}
    for case in plan['cases']:
        if case['group'] in ('new_parameters','new_composition'): assert semantic_key(decode(case['decks'][0][0])) not in pool
    val=load_value_data(folder,'final');prior=json.loads((folder/'value.json').read_text())['train_prior']
    assert value_metrics(primary,val,prior)==final['value_final']
    assert paired_value_gain(primary,simple,val)==final['value_gain_vs_simple']
    return dict(status='passed',audit_source_commit=commit(),final_source_commit=final['source_commit'],collection=collection,
        paired_loss_and_gradient_reconstructed=True,missing_optimizer_details_preserved=True,public_prefixes_match=True,
        complete_final_slots=len(games),unresolved_final_slots=len(final['failures']),seed_ranges_disjoint=True,
        actor_unchanged_by_value=True,weights_unchanged_after_fit=True,value_metrics_reconstructed=True,
        qualified=final['qualified'],meaning='Evidence and information contract; not server certification or proof of general policy quality.')


def action_diagnostics(folder):
    """Compare frozen actions on saved on-policy observations; no game replay."""
    base=LearnedPolicy(Network.load(json.loads((folder/'design.json').read_text())['baseline'])[0]);counts=Counter();changes=Counter()
    for path in sorted(folder.glob('value-final-*.jsonl.gz')):
        for row in rows(path):
            if row['record_type']!='decision' or row['observation']['player']!=0: continue
            actions=list(map(tuple,row['legal_actions']));before=tuple(base.choose(row['observation'],actions)['action']);after=tuple(row['selection']['action'])
            counts['decisions']+=1
            if before!=after:
                counts['changes']+=1
                def kind(a): return ('face' if a[-1]==-1 else 'trade') if a[0]=='attack' else a[0]
                changes[kind(before)+' -> '+kind(after)]+=1
    return dict(counts=counts,changes=changes,scope='V5 value-final observations only; frozen V4 alternative recomputed from public observations, no replay. Disagreement is not proof of causal win improvement.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=audit(args.output);dump(args.output/'audit.json',result)
    dump(args.output/'action-diagnostics.json',action_diagnostics(args.output));print(json.dumps(result))
