"""Read-only reconstruction of V4 denominators, freezes and completion bounds."""
from collections import Counter
from pathlib import Path
import argparse, gzip, hashlib, itertools, json
import numpy as np
from .network import Network
from .profiles import training_pool
from .catalog import semantic_key
from .training import decode, dump, commit
from .relational_research import load_value_data, value_metrics, paired_value_gain


def audit(folder):
    design = json.loads((folder / 'design.json').read_text()); plan = json.loads((folder / 'final-plan.json').read_text())
    final = json.loads((folder / 'final.json').read_text()); value = json.loads((folder / 'value.json').read_text())
    actor = Network.load(folder / (design['primary'] + '.npz'))[0]
    net = Network.load(folder / 'primary-value.npz')[0]; baseline = Network.load(folder / 'value-hp-board.npz')[0]
    assert actor.actor_fingerprint == net.actor_fingerprint == baseline.actor_fingerprint == plan['actor_fingerprint'] == value['frozen_actor']
    assert net.fingerprint == plan['primary_fingerprint'] == final['primary_fingerprint']
    assert baseline.fingerprint == plan['value_baseline_fingerprint']
    for path, digest in design['input_sha256'].items(): assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    ranges = [set(design[k]) for k in ('development_seeds', 'final_seeds', 'value_train_seeds', 'value_dev_seeds', 'value_final_seeds')]
    assert all(not a & b for a, b in itertools.combinations(ranges, 2))
    assert not set(range(1210000, 1210064)) & set.union(*ranges)
    with gzip.open(folder / 'final-games.jsonl.gz', 'rt') as stream: rows = [json.loads(line) for line in stream]
    keys = Counter((r['group'], r['seed'], r['seat'], r['policy']) for r in rows)
    expected = set(itertools.product(design['final_cases'], design['final_seeds'], (0, 1), design['final_policies']))
    assert set(keys) == expected and all(v == 1 for v in keys.values())
    unresolved = sum(r['result']['unfinished'] for r in rows)
    assert unresolved == len(final['failures'])
    for r in rows:
        result = r['result']
        if not result['unfinished']: assert bool(result['won']) != bool(result['lost'])
    for group in final['groups']:
        for policy in group['policies']:
            subset = [r['result'] for r in rows if r['group'] == group['group'] and r['policy'] == policy['policy']]
            lo = np.mean([0 if r['unfinished'] else int(r['won']) for r in subset])
            hi = np.mean([1 if r['unfinished'] else int(r['won']) for r in subset])
            np.testing.assert_allclose([lo, hi], policy['win']['completion_range'], rtol=0, atol=1e-14)
    pool = {semantic_key(s) for s in training_pool()}
    for case in plan['cases']:
        if case['name'] in ('new_parameters', 'new_composition'):
            assert semantic_key(decode(case['decks'][0][0])) not in pool
    val = load_value_data(folder, 'final'); recomputed = value_metrics(net, val, value['train_prior'])
    for key in ('brier', 'constant_brier', 'brier_gain', 'all_episode_brier', 'all_episode_gain'):
        assert recomputed[key] == final['value_final'][key]
    assert paired_value_gain(net, baseline, val) == final['value_gain_vs_hp_board']
    all_value = {stage: load_value_data(folder, stage) for stage in ('train', 'dev', 'final')}
    assert all(len(all_value[stage]) == len(design['value_' + stage + '_seeds']) for stage in all_value)
    maximum = max(t['maximum'] for g in final['groups'] for t in g['timings'].values())
    assert maximum <= design['decision_seconds'] or unresolved
    return dict(status='passed', audit_source_commit=commit(), final_source_commit=final['source_commit'],
        raw_final_slots=len(rows), unique_slots=len(keys), unresolved_slots=unresolved,
        heldout_specs_absent_from_training_pool=True, seed_ranges_disjoint=True, prior_final_seeds_retired=True,
        actor_identical_before_after_value=True, frozen_fingerprints_match=True,
        input_digests_match=True, complete_denom_reconstructed=True, value_metrics_reconstructed=True,
        value_episodes={k: len(v) for k, v in all_value.items()}, maximum_decision_seconds=maximum,
        qualified=final['qualified'], meaning='Evidence integrity and contracts, not proof of strategy quality or server rules.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', required=True, type=Path); args = p.parse_args()
    result = audit(args.output); dump(args.output / 'audit.json', result); print(json.dumps(result))
