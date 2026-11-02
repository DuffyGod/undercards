"""Read-only V12 evidence audit; never replays games or repairs missing labels."""
from collections import Counter, defaultdict
from pathlib import Path
import argparse
import json
import numpy as np
from .action_value import encode
from .continuation_gate import MODES
from .continuation_research import (BASE, PROPOSER, design, read_lines, attribution,
                                    dataset, prediction_metrics, stopping_roots, source_episodes)
from .suffix_research import cases
from .network import Network
from .policies import LearnedPolicy
from .statistics import interval
from .training import dump, commit
from .relations import state_features
from .relational_research import value_metrics, paired_value_gain, phase_metrics
from .action_research import suppress_sparse


def value_episodes(folder, stage, actor):
    episodes = []; states = []
    for path in sorted(folder.glob(f'value-{stage}-*.jsonl.gz')):
        for r in read_lines(path):
            if r['record_type'] == 'decision':
                if r['observation']['player'] == 0:
                    states.append(state_features(r['observation']))
                assert tuple(r['selection']['action']) in list(map(tuple, r['legal_actions']))
            else:
                assert r['metadata']['actor_fingerprint'] == actor
                result = r['result']
                episodes.append(dict(seed=r['metadata']['seed'], terminal=not result['unfinished'], won=result['won'], states=states,
                    error=result.get('error')))
                states = []
        assert not states
    return episodes


def audit(folder):
    d = design(folder); source = {(m['group'], m['seed'], m['seat']): (rows, r) for m, rows, r in source_episodes()}
    base = Network.load(BASE)[0]; proposer = Network.load(PROPOSER)[0]
    checked = Counter(); failures = []; stages = {}
    for stage in ('source', 'train', 'diagnostic'):
        coverage = Counter(); seeds = []
        for path in sorted((folder / stage).glob('episode-*.jsonl.gz')):
            records = list(read_lines(path)); meta = records[0]; seeds.append(meta['seed'])
            coverage[meta['opponent'], meta['seat']] += 1
            decisions = [r for r in records if r['record_type'] == 'decision']
            outcomes = [r for r in records if r['record_type'] == 'outcome']
            if stage == 'source':
                decisions, result = source[meta['group'], meta['seed'], meta['seat']]
            else:
                assert len(outcomes) == 1
                result = outcomes[0]['result']
                assert meta['actor_fingerprint'] == proposer.actor_fingerprint
            roots = [r for r in records if r['record_type'] == 'root']
            expected = stopping_roots(decisions)
            assert [(r['root'], r['decision'], r['baseline_action'], r['proposal_action']) for r in roots] == expected
            for r in roots:
                obs = r['observation']; actions = list(map(tuple, r['legal_actions'])); a = r['proposal_action']; b = r['baseline_action']
                assert obs == decisions[r['decision']]['observation']
                assert actions == list(map(tuple, decisions[r['decision']]['legal_actions']))
                assert obs['player'] == 0 and a != b
                assert LearnedPolicy(base).choose(obs, actions)['action_index'] == b
                assert LearnedPolicy(proposer).choose(obs, actions)['action_index'] == a
                assert not np.array_equal(encode(obs, actions)[1][0][a], encode(obs, actions)[1][0][b])
                assert {(c['action'], c['continuation']) for c in r['cells']} == {(0, 0), (1, 0), (0, 1), (1, 1)}
                assert len(r['cells']) == 4
                for cell in r['cells']:
                    assert cell['prefix_checked']
                    assert cell['reused'] == (cell['action'] == 1 and cell['continuation'] == 1)
                    if cell['reused']:
                        # NativeGame.run attaches SOUL metadata after calling
                        # recorder.finish. Compare every recorded outcome field,
                        # then verify that sole post-finish annotation separately.
                        assert all(cell['result'].get(k) == v for k, v in result.items())
                        assert set(cell['result']) - set(result) <= {'souls'}
                        if 'souls' in cell['result']:
                            assert cell['result']['souls'] == list(meta['souls'])
                    if cell['result']['unfinished']:
                        assert cell['result']['won'] is None
                        failures.append(dict(stage=stage, file=str(path), seed=r['seed'], root=r['root'], decision=r['decision'],
                            action=cell['action'], continuation=cell['continuation'], reused=cell['reused'], error=cell['result'].get('error')))
                    checked['cells'] += 1
                checked['roots'] += 1
            checked['openings'] += 1
        if stage != 'source':
            assert seeds == d[stage + '_seeds'] and len(set(seeds)) == len(seeds)
            assert set(coverage) == {(name, seat) for name in ('race', 'board', 'guard', 'delayed') for seat in (0, 1)}
            assert len(set(coverage.values())) == 1
        actual = attribution(folder / stage); saved = json.loads((folder / f'{stage}-collection.json').read_text())
        assert all(saved[k] == v for k, v in actual.items())
        stages[stage] = dict(coverage={str(k): v for k, v in coverage.items()}, counts=actual['counts'])

    fit = json.loads((folder / 'fit.json').read_text()); train = dataset(folder, 'train'); diagnostic = dataset(folder, 'diagnostic')
    for entry in fit['curve']:
        net = Network.load(folder / f"epoch-{entry['epoch']:03}.npz")[0]
        assert entry['train'] == prediction_metrics(net, train)
        assert entry['diagnostic'] == prediction_metrics(net, diagnostic)
    chosen = min(fit['curve'], key=lambda row: (row['diagnostic']['mse'], row['epoch']))['epoch']
    assert chosen == fit['selected_epoch']
    reference = Network.load(folder / f'epoch-{chosen:03}.npz')[0]
    for mode in MODES:
        net, meta = Network.load(folder / f'{mode}-selected.npz')
        assert net.mode == mode and meta['value_unfitted'] and not meta['validation']['qualified']
        assert net.proposer.fingerprint == proposer.fingerprint
        assert all(np.array_equal(net.p[k], reference.p[k]) for k in net.p)
    checked['fit_candidate_metrics'] = len(fit['curve'])

    if (folder / 'development.json').exists():
        development = json.loads((folder / 'development.json').read_text())
        behavior = defaultdict(Counter); outcomes = {}; primary = Network.load(folder / 'robust-selected.npz')[0]
        for row in read_lines(folder / 'development-decisions.jsonl.gz'):
            meta = row['metadata']; name = meta['policy']; key = (name, meta['group'], meta['seed'], meta['seat'])
            if row['record_type'] == 'outcome':
                assert key not in outcomes; outcomes[key] = row['result']; behavior[name]['unknown'] += row['result']['unfinished']
                if row['result']['unfinished']:
                    failures.append(dict(stage='development', metadata=meta, error=row['result'].get('error')))
                continue
            actions = list(map(tuple, row['legal_actions'])); selection = row['selection']; obs = row['observation']
            assert tuple(selection['action']) == actions[selection['action_index']]
            if obs['player'] != 0:
                continue
            behavior[name]['decisions'] += 1; baseline = row['baseline']; a = selection['action_index']; b = baseline['action_index']
            assert tuple(baseline['action']) == actions[b]
            if a != b:
                behavior[name]['raw_changed'] += 1; x = encode(obs, actions)[1][0]
                behavior[name]['changed'] += not np.array_equal(x[a], x[b])
            if name == 'robust':
                assert selection['policy'] == primary.fingerprint
            checked['development_actor_decisions'] += 1
        games = list(read_lines(folder / 'development-games.jsonl.gz'))
        assert len(games) == len(outcomes) == 600
        souls_by_group = {g: list(souls) for g, _, _, souls, _ in cases()}
        for r in games:
            key = (r['policy'], r['group'], r['seed'], r['seat'])
            assert all(r['result'].get(k) == v for k, v in outcomes[key].items())
            assert set(r['result']) - set(outcomes[key]) <= {'souls'}
            if 'souls' in r['result']:
                assert r['result']['souls'] == souls_by_group[r['group']]
        perseed = {}
        for name in (*MODES, 'v5', 'v11'):
            lows = []; highs = []
            for seed in d['development_seeds']:
                rs = [r['result'] for r in games if r['policy'] == name and r['seed'] == seed]
                assert len(rs) == 10
                lows.append(np.mean([0 if r['unfinished'] else int(r['won']) for r in rs]))
                highs.append(np.mean([1 if r['unfinished'] else int(r['won']) for r in rs]))
            perseed[name] = np.array(lows), np.array(highs)
        a, b = perseed['robust']
        for name, (lo, hi) in perseed.items():
            assert development['metrics'][name]['win'] == interval(lo, hi)
            assert development['metrics'][name]['primary_gain'] == interval(a - hi, b - lo)
            for key in ('decisions', 'changed', 'raw_changed', 'unknown'):
                assert development['metrics'][name]['behavior'].get(key, 0) == behavior[name][key]
        ratio = behavior['robust']['changed'] / max(1, behavior['robust']['decisions'])
        assert ratio == development['activation']
        proceed = bool(a.mean() >= perseed['v5'][1].mean() and development['metrics']['v5']['primary_gain']['low'] >= -.1
                       and ratio >= .01 and not behavior['robust']['unknown'])
        assert proceed == development['proceed_to_final']
        if not proceed:
            status = json.loads((folder / 'final-status.json').read_text())
            assert status['status'] == 'not_executed' and status['final_seeds_unread'] and status['value_final_unread']
            assert not list(folder.glob('final-games*')) and not list(folder.glob('value-*'))
        checked['development_slots'] = len(games)
    if (folder / 'value.json').exists():
        primary, meta = Network.load(folder / 'primary-value.npz'); value = json.loads((folder / 'value.json').read_text())
        simple = Network.load(folder / 'value-simple.npz')[0]
        assert primary.actor_fingerprint == reference.actor_fingerprint == value['actor_fingerprint']
        assert meta['value_unfitted'] is False and meta['critic_actor_fingerprint'] == primary.actor_fingerprint
        train = value_episodes(folder, 'train', primary.actor_fingerprint)
        dev = value_episodes(folder, 'dev', primary.actor_fingerprint)
        for stage, episodes in (('train', train), ('dev', dev)):
            assert [e['seed'] for e in episodes] == d['value_' + stage + '_seeds']
            checked['value_' + stage + '_openings'] = len(episodes)
            for e in episodes:
                if not e['terminal']:
                    failures.append(dict(stage='value_' + stage, seed=e['seed'], error=e['error']))
        prior = np.mean([e['won'] for e in train if e['terminal']])
        assert prior == value['train_prior']
        assert value['train_states'] == sum(len(e['states']) for e in train if e['terminal'])
        assert value['development'] == value_metrics(primary, dev, prior)
        assert value['simple_development'] == value_metrics(simple, dev, prior)
        assert value['gain_vs_simple'] == paired_value_gain(primary, simple, dev)
    if (folder / 'final.json').exists():
        final = json.loads((folder / 'final.json').read_text()); plan = json.loads((folder / 'final-plan.json').read_text())
        assert plan['primary_actor'] == reference.actor_fingerprint
        assert plan['models']['robust'] == primary.fingerprint
        raw = list(read_lines(folder / 'final-games.jsonl.gz'))
        assert len(raw) == 3 * len(plan['cases']) * len(d['final_seeds']) * 2 == 1536
        keys = [(r['group'], r['seed'], r['seat'], r['policy']) for r in raw]
        expected_keys = {(c['group'], seed, seat, name) for c in plan['cases'] for seed in d['final_seeds']
                         for seat in (0, 1) for name in ('robust', 'v5', 'v11')}
        assert len(keys) == len(set(keys)) and set(keys) == expected_keys
        for output_group, case in zip(final['groups'], plan['cases']):
            assert output_group['group'] == case['group']
            perseed = {}
            for name in ('robust', 'v5', 'v11'):
                low = []; high = []
                for seed in d['final_seeds']:
                    rows = [r['result'] for r in raw if r['group'] == case['group'] and r['seed'] == seed and r['policy'] == name]
                    assert len(rows) == 2
                    low.append(np.mean([0 if r['unfinished'] else int(r['won']) for r in rows]))
                    high.append(np.mean([1 if r['unfinished'] else int(r['won']) for r in rows]))
                perseed[name] = np.array(low), np.array(high)
            lo, hi = perseed['robust']
            for comparison in output_group['policies']:
                a0, b0 = perseed[comparison['policy']]
                assert comparison['win'] == interval(a0, b0)
                assert comparison['primary_gain'] == interval(lo - b0, hi - a0)
                assert comparison['family_gain'] == interval(lo - b0, hi - a0, alpha=.05 / (2 * len(plan['cases'])))
        raw_failures = [dict(group=r['group'], seed=r['seed'], seat=r['seat'], policy=r['policy'], error=r['result'].get('error'))
                        for r in raw if r['result']['unfinished']]
        assert raw_failures == final['failures']
        failures.extend(dict(stage='final_policy', **r) for r in raw_failures)
        qualified = (not any(r['policy'] == 'robust' for r in raw_failures) and
                     all(c['primary_gain']['low'] > 0 for g in final['groups'] for c in g['policies'] if c['policy'] != 'robust'))
        assert qualified == final['qualified'] == json.loads((folder / 'validation.json').read_text())['qualified']
        episodes = value_episodes(folder, 'final', primary.actor_fingerprint)
        assert [e['seed'] for e in episodes] == d['value_final_seeds']
        assert final['value_final'] == value_metrics(primary, episodes, prior)
        assert final['value_simple'] == value_metrics(simple, episodes, prior)
        assert final['value_previous_v5'] == value_metrics(base, episodes, prior)
        assert final['value_gain_vs_simple'] == paired_value_gain(primary, simple, episodes)
        assert final['value_gain_vs_v5'] == paired_value_gain(primary, base, episodes)
        assert final['phases'] == suppress_sparse(phase_metrics(primary, episodes, prior))
        failures.extend(dict(stage='value_final', seed=e['seed'], error=e['error']) for e in episodes if not e['terminal'])
        checked.update(final_policy_slots=len(raw), value_final_openings=len(episodes))
    interface_path = folder / 'interface/verification.json'
    interface_status = None
    if interface_path.exists():
        interface = json.loads(interface_path.read_text()); interface_status = interface['status']
        assert interface['actor_contract']['slots'] == 8 and interface['actor_contract']['unresolved'] == 0
        assert interface['actor_contract']['frozen_policy'] == reference.fingerprint
        assert interface['fitted_value_contract']['base_model'] == primary.fingerprint
        for r in interface['fitted_value_contract']['failures']:
            assert r['unfinished'] and r['won'] is None
            failures.append(dict(stage='engineering_value_search', **r))
        checked.update(engineering_actor_slots=8, engineering_value_search_slots=8,
                       engineering_value_search_unknown=interface['fitted_value_contract']['unresolved'])
    dump(folder / 'evidence-audit.json', dict(source_commit=commit(), status='passed', checked=dict(checked), stages=stages,
         selected_epoch=chosen, selected_actor=reference.actor_fingerprint,
         interface_status=interface_status,
         no_game_replays=True, no_label_repairs=True, limitations='Audit checks consistency, not simulator validity, posterior beliefs or policy qualification.'))
    dump(folder / 'failures.json', dict(unknown_cells_and_slots=failures, unknowns_not_retried=True,
        lock_recovery='Original V12 holder pid1147 became a zombie during environment reconnection. Verified OS lock free and reacquired as pid2583/session16666; no second research round started.',
        method_limitations=d['limits']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    audit(parser.parse_args().output)
