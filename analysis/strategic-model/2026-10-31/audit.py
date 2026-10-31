"""Read-only validation of saved decision data, split contracts and value head."""
from collections import defaultdict
from pathlib import Path
import argparse, gzip, json, subprocess
import hashlib
import numpy as np
from study import from_dict, interval, OPPONENTS, source_commit, dump
from learner import Network
from records import load_episodes
from features import encode


def audit(dest):
    design = json.loads((dest / 'design.json').read_text())
    training = json.loads((dest / 'training.json').read_text())
    evaluation = json.loads((dest / 'evaluation.json').read_text())
    net, metadata = Network.load(dest / 'policy.npz')
    if metadata['design_sha256'] != hashlib.sha256((dest / 'design.json').read_bytes()).hexdigest():
        raise ValueError('Frozen design changed after training')
    if training['status'] != 'complete' or evaluation['status'] != 'complete':
        raise ValueError('Incomplete study')
    if net.fingerprint != evaluation['frozen_policy'] or net.fingerprint != training['final_fingerprint']:
        raise ValueError('Frozen policy mismatch')
    train_seeds = set(range(training['seed_start'], training['training_seed_end'] + 1))
    if train_seeds & set(design['evaluation_seeds'] + design['replacement_seeds']):
        raise ValueError('Seed leakage')
    train_specs = list(map(from_dict, design['training_specs']))
    param = lambda s: (s.cost, s.attack, s.health)
    structure = lambda s: json.dumps([s.semantic()['keywords'], s.semantic()['effects']], sort_keys=True)
    cases = {c['group']: c for c in design['cases']}
    if param(from_dict(cases['heldout_parameters']['spec'])) in set(map(param, train_specs)):
        raise ValueError('Parameter holdout leaked')
    if structure(from_dict(cases['heldout_mechanism_composition']['spec'])) in set(map(structure, train_specs)):
        raise ValueError('Mechanism holdout leaked')
    if cases['heldout_deck_structure']['structure'] in design['training_structures']:
        raise ValueError('Host structure holdout leaked')
    def behavior(policy):
        from dataclasses import asdict
        d = asdict(policy); d.pop('name'); return d
    from environment import bridge
    held = behavior(OPPONENTS[cases['heldout_opponent']['opponent']])
    trained_fixed = [bridge.ROWS[i] for i in design['warmup_rows']] + [OPPONENTS[i] for i in design['fixed_training_opponents']]
    if held in list(map(behavior, trained_fixed)): raise ValueError('Only renamed a training opponent')
    grid = set(); unfinished = 0
    with gzip.open(dest / 'evaluation-records.jsonl.gz', 'rt') as f:
        for row in map(json.loads, f):
            key = row['group'], row['seed'], row['seat'], row['policy']
            if key in grid: raise ValueError('Duplicate evaluation row')
            grid.add(key); unfinished += row['unfinished']
            if row['unfinished']:
                if row['won'] is not None or row['lost'] is not None: raise ValueError('Rejected run was assigned a winner')
            elif row['won'] + row['lost'] != 1: raise ValueError('Nonterminal evaluation row')
    if len(grid) != 5 * len(design['evaluation_seeds']) * 2 * 7:
        raise ValueError('Incomplete comparison grid')
    briers = defaultdict(list); phases = defaultdict(list); decisions = 0; episodes = 0
    for rec in load_episodes(dest / 'evaluation-decisions.jsonl.gz'):
        episodes += 1
        if not rec.result['terminated']: continue
        episode_scores = []
        for row in rec.rows:
            obs = row['observation']
            if any(key in obs for key in ('seed', 'deck', 'enemy_hand', 'players', 'rng')):
                raise ValueError('Private information in observation')
            if row['policy'] != net.fingerprint: continue
            actions = list(map(tuple, row['legal_actions']))
            if tuple(row['action']) not in actions: raise ValueError('Illegal recorded choice')
            _, value, _ = net.forward(*encode(obs, actions))
            if abs(value - row['value']) > 1e-10: raise ValueError('Value prediction cannot be reproduced')
            target = (rec.result['returns'][obs['player']] + 1) / 2
            score = ((value + 1) / 2 - target) ** 2
            episode_scores.append(score); decisions += 1
            phase = 'early_t1_4' if obs['turn'] <= 4 else 'middle_t5_10' if obs['turn'] <= 10 else 'late_t11_plus'
            phases[(rec.result['metadata']['group'], phase)].append(score)
        meta = rec.result['metadata']
        if episode_scores: briers[(meta['group'], meta['seed'])].append(float(np.mean(episode_scores)))
    value_summary = {}
    for group in cases:
        clustered = [float(np.mean(xs)) for (g, seed), xs in briers.items() if g == group]
        value_summary[group] = dict(per_seed_episode_mean_brier=interval(clustered),
            constant_half_probability_brier=.25,
            phases={p: dict(mean_brier=float(np.mean(xs)), decisions=len(xs))
                    for (g, p), xs in phases.items() if g == group})
    old_paths = ['analysis/strategic-model/2026-10-20', 'analysis/strategic-model/2026-10-30']
    changed = subprocess.check_output(['git', 'diff', '--name-only', 'c27b0da', '--', *old_paths], text=True).strip()
    if changed: raise ValueError('Historical engine/results changed: ' + changed)
    result = dict(status='passed', independent_seed_clusters_per_group=len(design['evaluation_seeds']),
        evaluation_rows=len(grid), evaluation_episodes=episodes, reproduced_value_decisions=decisions,
        unfinished=unfinished, private_inputs_found=False, old_sources_and_results_unchanged=True,
        frozen_policy=net.fingerprint, value=value_summary, new_simulations=0,
        meaning='Saved-data contracts, split non-overlap and reproducibility; no independent server-rule certification.')
    dump(dest / 'audit.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'value'}))


def audit_extensions(dest):
    """Validate new saved outputs without repeating value inference or games."""
    design = json.loads((dest / 'design.json').read_text())
    primary = json.loads((dest / 'audit.json').read_text())
    net, meta = Network.load(dest / 'policy.npz')
    if net.fingerprint != primary['frozen_policy']: raise ValueError('Checkpoint changed')
    if meta['design_sha256'] != hashlib.sha256((dest / 'design.json').read_bytes()).hexdigest():
        raise ValueError('Frozen design changed')
    replacement = json.loads((dest / 'replacements.json').read_text())
    if replacement['frozen_policy'] != net.fingerprint: raise ValueError('Per-card policy mismatch')
    index = {}
    with gzip.open(dest / 'replacement-records.jsonl.gz', 'rt') as f:
        for row in map(json.loads, f):
            key = row['card'], row['seed'], row['seat']
            if key in index: raise ValueError('Duplicate replacement')
            if row['card'] not in design['replacement_cards'] or row['seed'] not in design['replacement_seeds']:
                raise ValueError('Unplanned replacement')
            index[key] = row
    if len(index) != len(design['replacement_cards']) * len(design['replacement_seeds']) * 2:
        raise ValueError('Incomplete replacement grid')
    unchanged_no_draw = 0
    for (card, seed, seat), row in index.items():
        base = index['Rock Pet', seed, seat]
        if not row['unfinished'] and row['candidate_drawn'] == 0:
            if base['candidate_drawn'] != 0 or row['won'] != base['won']:
                raise ValueError('An unseen candidate changed the shared policy outcome')
            unchanged_no_draw += 1
    for card in replacement['cards']:
        d = card['diagnostics']
        if d['never_received'] + d['received_unplayed'] + d['played'] + d['diagnostic_unknown'] != d['games']:
            raise ValueError('Opportunity denominators do not partition games')
    with gzip.open(dest / 'evaluation-records.jsonl.gz', 'rt') as f:
        base = {(r['group'], r['seed'], r['seat']): r for r in map(json.loads, f) if r['policy'] == 'shared_policy_value'}
    ablation = json.loads((dest / 'value-search-ablation.json').read_text())
    if ablation['frozen_policy'] != net.fingerprint: raise ValueError('Ablation changed network')
    keys = set(); unfinished = 0
    with gzip.open(dest / 'value-search-ablation-records.jsonl.gz', 'rt') as f:
        for row in map(json.loads, f):
            key = row['group'], row['seed'], row['seat']
            if key in keys: raise ValueError('Duplicate ablation')
            keys.add(key); unfinished += row['unfinished']
            if row['seed'] not in design['evaluation_seeds'][:design['value_search_ablation_seeds']]:
                raise ValueError('Unplanned ablation seed')
            if row['baseline_won'] != base[key]['won']: raise ValueError('Ablation baseline changed')
            if row['unfinished'] and row['won'] is not None: raise ValueError('Ablation failure assigned a winner')
    if len(keys) != 5 * design['value_search_ablation_seeds'] * 2: raise ValueError('Incomplete ablation')
    result = dict(status='passed', replacement_rows=len(index), no_received_counterfactual_rows_unchanged=unchanged_no_draw,
        valid_ablation_rows=len(keys), valid_ablation_unresolved=unfinished, frozen_design_unchanged=True,
        frozen_policy=net.fingerprint, new_simulations=0, repeated_value_inference=0,
        scope='Saved-grid and complete-denominator checks. The primary generalization gate remains failed.')
    dump(dest / 'extensions-audit.json', result); print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--extensions-only', action='store_true'); args = parser.parse_args()
    (audit_extensions if args.extensions_only else audit)(args.output)
