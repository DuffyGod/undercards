"""Reconstruct V6 shared groups, legal knowledge and frozen final evidence."""
from collections import Counter
from pathlib import Path
import argparse,gzip,hashlib,itertools,json
import numpy as np
from .memory_research import read_rows,augmented_episodes,data
from .memory_model import MemoryNetwork
from .knowledge import vector
from .network import Network
from .profiles import training_pool
from .catalog import semantic_key
from .relational_research import value_metrics,paired_value_gain
from .training import dump,decode,commit
from .relations import state_features


def value_episodes(folder,stage):
    output=[]
    for path in sorted(folder.glob(f'value-{stage}-*.jsonl.gz')):
        pending={}
        for row in read_rows(path):
            key=row['episode']
            if row['record_type']=='decision':
                if row['observation']['player']==0:pending.setdefault(key,[]).append(np.r_[state_features(row['observation']),vector(row['observation'])])
            else:
                r=row['result'];output.append(dict(seed=key,states=pending.pop(key,[]),terminal=not r['unfinished'],won=r['won']))
        if pending:raise ValueError('Unclosed value episodes')
    return output


def audit(folder):
    d=json.loads((folder/'design.json').read_text());plan=json.loads((folder/'final-plan.json').read_text());final=json.loads((folder/'final.json').read_text());fit=json.loads((folder/'fit.json').read_text())
    for path,digest in d['source_files'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
    primary=Network.load(folder/'primary-value.npz')[0];actor=Network.load(folder/'selected-actor.npz')[0]
    assert primary.actor_fingerprint==actor.actor_fingerprint==plan['actor_fingerprint']
    assert primary.fingerprint==plan['primary_fingerprint']==final['primary_fingerprint']
    np.testing.assert_array_equal(primary.advantage,actor.advantage)
    before=Network.load(folder/'known_current.npz')[0];np.testing.assert_array_equal(primary.advantage,before.advantage)
    old=Network.load(d['baseline'])[0];assert primary.base.actor_fingerprint==old.actor_fingerprint
    collection={}
    for stage in ('train','diagnostic'):
        source={}
        for meta,records in augmented_episodes(stage):
            for row in records:source[meta['seed'],row['decision']]=row
        forks=0;branches=0;unknown=0;source_unknown=0
        for path in sorted(folder.glob(f'{stage}-targets-*.jsonl.gz')):
            for row in read_rows(path):
                original=source[row['seed'],row['decision']]
                assert row['observation']==original['observation'] and row['legal_actions']==original['legal_actions']
                keys=Counter((b['action_index'],b['continuation']) for b in row['branches'])
                assert set(keys)==set(itertools.product(row['indices'],('old','race','current'))) and all(v==1 for v in keys.values())
                assert row['baseline_action'] in row['indices']
                for b in row['branches']:
                    if b['unfinished']:assert b['won'] is None and b['lost'] is None
                    else:assert bool(b['won'])!=bool(b['lost'])
                forks+=1;branches+=len(row['indices'])+2*(len(row['indices'])-len(row['source_old_indices']))
                unknown+=sum(b['unfinished'] for b in row['branches'] if b['continuation']=='current' or b['action_index'] not in row['source_old_indices'])
                source_unknown+=sum(b['unfinished'] for b in row['branches'] if b['continuation']!='current' and b['action_index'] in row['source_old_indices'])
        status=json.loads((folder/f'{stage}-collection.json').read_text());assert forks==status['forks'] and branches==status['new_branches'] and unknown==status['unresolved']
        collection[stage]=dict(forks=forks,new_branches=branches,new_unresolved=unknown,reused_unresolved=source_unknown)
    counts=[fit['arms'][arm]['fit']['paired_groups'] for arm in fit['arms']];assert len(set(counts))==1
    games=list(read_rows(folder/'final-games.jsonl.gz'));keys=Counter((r['group'],r['seed'],r['seat'],r['policy']) for r in games)
    expected=set(itertools.product(d['final_cases'],d['final_seeds'],(0,1),('primary','v5','race','board','guard')))
    assert set(keys)==expected and all(v==1 for v in keys.values());assert sum(r['result']['unfinished'] for r in games)==len(final['failures'])
    for group in final['groups']:
        for policy in group['policies']:
            rs=[r['result'] for r in games if r['group']==group['group'] and r['policy']==policy['policy']]
            bounds=[np.mean([end if r['unfinished'] else float(r['won']) for r in rs]) for end in (0,1)]
            np.testing.assert_allclose(bounds,policy['win']['completion_range'],rtol=0,atol=1e-14)
    ranges=[set(d[k]) for k in ('source_train_seeds','source_diagnostic_seeds','development_seeds','final_seeds','value_train_seeds','value_dev_seeds','value_final_seeds')]
    assert all(not a&b for a,b in itertools.combinations(ranges,2))
    old_finals=set(range(1210000,1210064))|set(range(1310000,1310048))|set(range(1330000,1330096))|set(range(1610000,1610064))|set(range(1630000,1630096))
    assert not old_finals&set.union(*ranges)
    pool={semantic_key(s) for s in training_pool()}
    for case in plan['cases']:
        if case['group'] in ('new_parameters','new_composition'):assert semantic_key(decode(case['decks'][0][0])) not in pool
    val=value_episodes(folder,'final');prior=json.loads((folder/'value.json').read_text())['train_prior']
    assert value_metrics(primary,val,prior)==final['value_final']
    for name in ('old74','five'):
        other=Network.load(folder/('value-'+name+'.npz'))[0];assert other.actor_fingerprint==primary.actor_fingerprint
        assert paired_value_gain(primary,other,val)==final['value_baselines'][name]['gain']
    return dict(status='passed',audit_source_commit=commit(),final_source_commit=final['source_commit'],collection=collection,
        same_matched_groups=True,public_knowledge_reconstructed=True,reused_input_digests_match=True,actor_unchanged_by_value=True,
        complete_final_slots=len(games),unresolved_final_slots=len(final['failures']),value_metrics_reconstructed=True,seed_ranges_disjoint=True,
        qualified=final['qualified'],meaning='Information and evidence contracts, not server rules or general policy certification.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);args=p.parse_args();result=audit(args.output);dump(args.output/'audit.json',result);print(json.dumps(result))
