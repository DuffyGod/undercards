"""Audit completed saved joint-opening runs without importing/replaying the engine.

Default inputs: main/ and counterfactual/. Writes audit.json. Exit 0=pass,
1=invariant/schema failure, 2=incomplete or unreadable input. A partial run is
never labeled audited. This checks recorded accounting, not game-rule truth.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
GROUP_KEYS = ('composition', 'policy', 'soul', 'opponent', 'seat', 'intervention')
KNOWN_INTERVENTIONS = {
    'base', 'no_bonus_draw', 'extra_natural', 'hand10', 'slots6',
    'no_foe_hero_heal', 'hp_loss', 'soul_first', 'no_t1_draw',
}


def effective_limits(design, group):
    """Use saved defaults; hand10/slots6 encode their overrides in saved names.

    The design does not serialize per-group Config objects. Do not import the
    current runner to reconstruct historical settings or silently use defaults.
    """
    config = design['default_config']
    hand, slots = config['hand_cap'], config['slots']
    intervention = group['intervention']
    if intervention not in KNOWN_INTERVENTIONS:
        raise ValueError(f'Unrecognized saved intervention: {intervention}')
    if re.fullmatch(r'hand\d+', intervention):
        hand = int(intervention[4:])
    if re.fullmatch(r'slots\d+', intervention):
        slots = int(intervention[5:])
    if min(hand, slots) < 1:
        raise ValueError('Invalid saved capacities')
    no_heal = {i for i, enabled in enumerate(config['hero_healing']) if not enabled}
    if not config['healing']:
        no_heal.update((0, 1))
    if intervention == 'no_foe_hero_heal':
        no_heal.add(1-group['seat'])
    return hand, slots, no_heal


def audit_row(row, design, group):
    """Return named violations; no engine imports, policy calls or random draws."""
    errors = []
    def check(name, condition):
        if not condition:
            errors.append(name)

    for key in GROUP_KEYS:
        check('group_identity.'+key, row[key] == group[key])
    check('version', row['version'] == design['version'])
    check('two_players', len(row['players']) == 2)
    if len(row['players']) != 2:
        return errors
    hand_cap, slots, no_heal = effective_limits(design, group)
    side = group['seat']
    composition_names = [None, None]
    composition_names[side] = group['composition']
    composition_names[1-side] = design['opponents'][group['opponent']][0]
    for i, p in enumerate(row['players']):
        foe = row['players'][1-i]
        prefix = f'p{i}.'
        deck_size = len(design['compositions'][composition_names[i]])
        check(prefix+'declared_25_card_deck', deck_size == 25)
        check(prefix+'hp_conservation', p['hp'] == 30+p['healed']-foe['damage']-p['fatigue_damage'])
        check(prefix+'deck_conservation', p['draws']+p['deck_remaining'] == deck_size)
        check(prefix+'draw_conservation', p['draws'] == p['played']+p['hand']+p['burned'])
        check(prefix+'bonus_conservation', p['bonus_draws'] >= p['bonus_played']+p['bonus_burned'])
        check(prefix+'bonus_draw_subset', p['bonus_draws'] <= p['draws'])
        check(prefix+'bonus_play_subset', p['bonus_played'] <= p['played'])
        check(prefix+'bonus_burn_subset', p['bonus_burned'] <= p['burned'])
        check(prefix+'hp_bounds', 0 <= p['hp'] <= 30)
        check(prefix+'hand_bounds', 0 <= p['hand'] <= hand_cap)
        check(prefix+'field_bounds', 0 <= p['field'] <= slots)
        check(prefix+'cash_nonnegative', p['cash'] >= 0)
        for key in ('draws', 'deck_remaining', 'played', 'burned', 'bonus_draws',
                    'bonus_played', 'bonus_burned', 'damage', 'healed', 'fatigue_damage'):
            check(prefix+key+'_nonnegative', p[key] >= 0)
        if i in no_heal:
            check(prefix+'disabled_hero_heal_zero', p['healed'] == 0)
    snapshots = row['snapshots']
    check('snapshots_present', bool(snapshots))
    for j, snapshot in enumerate(snapshots):
        check('snapshot_two_players', len(snapshot['players']) == 2)
        for i, state in enumerate(snapshot['players']):
            prefix = f'snapshot{j}.p{i}.'
            # Saved snapshots retain negative lethal overkill; final results
            # normalize HP to zero. Only a terminal snapshot may contain it.
            check(prefix+'hp_upper_bound', state['hp'] <= 30)
            if state['hp'] <= 0:
                check(prefix+'death_is_absorbing', j == len(snapshots)-1)
            check(prefix+'hand_bounds', 0 <= state['hand'] <= hand_cap)
            check(prefix+'field_bounds', 0 <= state['slots'] <= slots)
            check(prefix+'cash_nonnegative', state['cash'] >= 0)
            check(prefix+'deck_bounds', 0 <= state['deck'] <= 25)
    if snapshots and len(snapshots[-1]['players']) == 2:
        for i, state in enumerate(snapshots[-1]['players']):
            p = row['players'][i]
            check(f'p{i}.final_snapshot_hp', max(0, state['hp']) == p['hp'])
            for saved, final in (('cash', 'cash'), ('hand', 'hand'), ('slots', 'field'), ('deck', 'deck_remaining')):
                check(f'p{i}.final_snapshot_{saved}', state[saved] == p[final])
    return errors


def read_design(directory):
    design = json.loads((directory/'design.json').read_text())
    receipt = json.loads((directory/'receipt.json').read_text())
    expected = set(range(len(design['groups'])))
    if (not receipt.get('complete') or set(receipt['completed_groups']) != expected
            or receipt['trials'] != len(expected)*design['samples'] or receipt.get('failed')):
        raise ValueError(f'Incomplete or failed receipt: {directory}')
    if receipt['version'] != design['version'] or receipt['source_commit'] != design['source_commit']:
        raise ValueError(f'Receipt/design provenance mismatch: {directory}')
    actual = {p.name for p in directory.glob('group-*.jsonl.gz')}
    required = {f'group-{i:03d}.jsonl.gz' for i in expected}
    if actual != required:
        raise ValueError(f'Incomplete or unexpected group files: {directory}')
    return design


def audit_directory(directory, design):
    counts = Counter()
    examples = []
    rows_checked = 0
    expected_seeds = set(range(design['seed_start'], design['seed_start']+design['samples']))
    def record(name, group, seed=None):
        counts[name] += 1
        if len(examples) < 40:
            examples.append(dict(group=group, seed=seed, error=name))
    for index, group in enumerate(design['groups']):
        seeds = []
        path = directory/f'group-{index:03d}.jsonl.gz'
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            for line in stream:
                if not line.strip():
                    record('blank_record', index)
                    continue
                row = json.loads(line)
                seed = row.get('seed')
                seeds.append(seed)
                rows_checked += 1
                try:
                    errors = audit_row(row, design, group)
                except (KeyError, TypeError, ValueError, IndexError) as exc:
                    errors = ['schema_or_config.'+str(exc)]
                for error in errors:
                    record(error, index, seed)
        if len(seeds) != design['samples']:
            record('incomplete_group_row_count', index)
        if len(seeds) != len(set(seeds)):
            record('duplicate_seed', index)
        if set(seeds) != expected_seeds:
            record('unexpected_or_missing_seed', index)
    return dict(directory=str(directory), stage=design['stage'], version=design['version'],
                source_commit=design['source_commit'], groups=len(design['groups']),
                expected_rows=len(design['groups'])*design['samples'], rows_checked=rows_checked,
                passed=not counts, violations=dict(counts), examples=examples,
                default_limits={k:design['default_config'][k] for k in ('hand_cap', 'slots')},
                intervention_limits='Saved handN/slotsN names override saved defaults; all other capacity limits retain defaults.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directories', nargs='*', type=Path)
    parser.add_argument('--output', type=Path, default=HERE/'audit.json')
    args = parser.parse_args()
    directories = args.directories or [HERE/'main', HERE/'counterfactual']
    report = dict(auditor='saved-accounting-v1', created_utc=datetime.now(timezone.utc).isoformat(),
                  scope='Independent saved accounting/capacity checks only; no simulation rerun and no full rule verification.',
                  hp_convention='Final HP is nonnegative. Raw snapshot HP may be negative only at the terminal lethal event.',
                  runs=[])
    code = 0
    try:
        # Validate completeness of every requested input before auditing any run.
        designs = [read_design(directory) for directory in directories]
        report['runs'] = [audit_directory(directory, design) for directory, design in zip(directories, designs)]
        report['status'] = 'pass' if all(r['passed'] for r in report['runs']) else 'fail'
        code = 0 if report['status'] == 'pass' else 1
    except (OSError, ValueError, KeyError, TypeError, EOFError) as exc:
        report.update(status='incomplete_or_unreadable', error=str(exc))
        code = 2
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(status=report['status'], output=str(args.output),
                          rows_checked=sum(r['rows_checked'] for r in report['runs']))))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
