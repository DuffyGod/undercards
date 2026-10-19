"""New single-card study: shared prices, full cash-price frontier, payment thresholds.

Consumes frozen source inputs; does not regenerate old experiments or use API.
Historical deck proposals are not an input. Results are heuristic conditionals.
"""
from __future__ import annotations

from dataclasses import asdict
from itertools import combinations, product
from pathlib import Path
import argparse
import csv
import gzip
import json
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
METHOD = ROOT / 'analysis/method-lab/2026-10-18'
sys.path.insert(0, str(METHOD))
from slot_value import SlotSolver
from value_model import BodyScale
from frontier import envelope, value, weighted_curve, paired_range, mixture

IDS = (2, 4, 9, 13, 15, 20, 21, 43, 49, 168, 175, 187, 377, 469, 530, 602, 984)
FACTORS = dict(face_share=(.1, .35), threshold=(.2, .6), face_price=(.15, .4))


def settings(pilot=False):
    out = {'central': dict(face_share=.2, threshold=.4, face_price=.25)}
    names = list(FACTORS)
    for bits in product((0, 1), repeat=3):
        out['corner_' + ''.join(map(str, bits))] = {
            name: FACTORS[name][bit] for name, bit in zip(names, bits)}
    return dict(list(out.items())[:2]) if pilot else out


def case_id(menu, board, cash, slots):
    return f'{menu}/{board}/g{cash}/k{slots}'


def physical_curve(quotes, cash):
    return envelope([dict(intercept=q.asset_value, slope=-q.paid,
                          action=asdict(q.plan), remaining_bodies=q.remaining_body_count)
                     for q in quotes if q.paid <= cash])


def write_csv(path, rows):
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pilot', action='store_true')
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('Use a new output directory; existing evidence is never overwritten')
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    inputs = json.loads((METHOD / 'statistical_inputs.json').read_text(encoding='utf-8'))
    original = json.loads((METHOD / 'slot-results/slot-design.json').read_text(encoding='utf-8'))
    prices = settings(args.pilot)
    ids = IDS if not args.pilot else (2, 4, 13, 20, 49, 984)
    menus = original['background_menus']
    if args.pilot:
        menus = {'three_plain': menus['three_plain']}
    cash_levels = (5, 8) if args.pilot else tuple(range(13))
    slot_levels = (1, 2) if args.pilot else (1, 2, 3, 4)
    named = [b for b in original['boards'] if b['group'] != 'aggro_32']
    sampled = [] if args.pilot else [b for b in original['boards'] if b['group'] == 'aggro_32']
    cases = {}
    for menu in menus:
        for board in named:
            for cash in cash_levels:
                for slots in slot_levels:
                    key = case_id(menu, board['name'], cash, slots)
                    cases[key] = dict(menu=menu, board=board['name'], cash=cash, slots=slots,
                                      enemy=board['enemy'], settings={})
    for board in sampled:
        key = case_id('three_plain', board['name'], 8, 2)
        cases[key] = dict(menu='three_plain', board=board['name'], cash=8, slots=2,
                          enemy=board['enemy'], settings={})
    count = 0
    for name, p in prices.items():
        scale = BodyScale(inputs['reference'], p['face_share'], p['threshold'])
        solver = SlotSolver(inputs['cards'], scale, p['face_price'])
        for case in cases.values():
            enemy = tuple(tuple(e) for e in case['enemy'])
            curves = {}
            for cid in ids:
                quotes = solver.quotes(cid, tuple(menus[case['menu']]), enemy, case['slots'])
                curves[str(cid)] = physical_curve(quotes, case['cash'])
                if 'background' not in curves:
                    curves['background'] = physical_curve(
                        [q for q in quotes if not q.plan.candidate_used], case['cash'])
                count += 1
            case['settings'][name] = curves
        # Method caches include self; release them before changing common prices.
        solver.quotes.cache_clear(); solver._focal_plans.cache_clear()
        scale.value.cache_clear(); scale.effective_attack.cache_clear()
        print(json.dumps({'completed_price': name, 'new_envelopes': count}), flush=True)
    if sampled:
        aggregate = dict(menu='three_plain', board='aggro32_design', cash=8, slots=2,
                         enemy=None, settings={}, design_weights=True,
                         board_policy='Own menu may depend on the observed public board')
        for name in prices:
            curves = {}
            for cid in [*(str(i) for i in ids), 'background']:
                curves[cid] = weighted_curve(
                    [cases[case_id('three_plain', b['name'], 8, 2)]['settings'][name][cid] for b in sampled],
                    [b['weight'] for b in sampled])
            aggregate['settings'][name] = curves
        cases[case_id('three_plain', 'aggro32_design', 8, 2)] = aggregate
    pairs = [(a, b) for a, b in combinations(ids, 2)
             if inputs['cards'][str(a)]['cost'] == inputs['cards'][str(b)]['cost']]
    pair_rows = []; card_rows = []; mix_rows = []
    status_counts = {}
    for key, case in cases.items():
        if case['board'].startswith('aggro_'):
            continue  # Individual sampled boards remain in raw curves.
        common = {k: case[k] for k in ('menu', 'board', 'cash', 'slots')}
        for a, b in pairs:
            r = paired_range(case['settings'], a, b)
            status_counts[r['status']] = status_counts.get(r['status'], 0) + 1
            pair_rows.append(dict(case=key, **common, left=a, right=b,
                                  minimum=r['minimum'], maximum=r['maximum'], status=r['status'],
                                  minimum_setting=r['minimum_witness']['setting'],
                                  minimum_cash_price=r['minimum_witness']['cash_price'],
                                  maximum_setting=r['maximum_witness']['setting'],
                                  maximum_cash_price=r['maximum_witness']['cash_price']))
        for cid in ids:
            r = paired_range(case['settings'], cid, 'background')
            replacement = paired_range(case['settings'], cid, 2)
            c = case['settings']['central']
            card_rows.append(dict(case=key, **common, card_id=cid,
                                  gain_over_background_min=r['minimum'], gain_over_background_max=r['maximum'],
                                  relative_to_froggit_min=replacement['minimum'],
                                  relative_to_froggit_max=replacement['maximum'],
                                  central_gain_at_cash_price_0=value(c[str(cid)], 0)-value(c['background'], 0),
                                  central_gain_at_cash_price_half=value(c[str(cid)], .5)-value(c['background'], .5),
                                  central_gain_at_cash_price_1=value(c[str(cid)], 1)-value(c['background'], 1),
                                  holding_cost_estimated=False, full_card_value=False))
    if not args.pilot:
        for cash in (6, 8, 10):
            for slots in (1, 2, 4):
                first = cases[case_id('three_plain', 'empty', cash, slots)]['settings']
                second = cases[case_id('three_plain', 'three_3_2', cash, slots)]['settings']
                for a, b in pairs:
                    r = mixture(first, second, a, b)
                    central = mixture({'central': first['central']}, {'central': second['central']}, a, b, .5)
                    mix_rows.append(dict(cash=cash, slots=slots, left=a, right=b,
                        left_mass_range=json.dumps(r['left_weakly_preferred_mass']),
                        right_mass_range=json.dumps(r['right_weakly_preferred_mass']),
                        central_half_left_mass_range=json.dumps(central['left_weakly_preferred_mass']),
                        central_half_right_mass_range=json.dumps(central['right_weakly_preferred_mass'])))
    # Validate the NEW envelope transformation against already stored old point
    # values, reading them rather than rerunning the old producer or test suite.
    reused_points = 0; largest_error = 0.
    with gzip.open(METHOD / 'slot-results/slot-primary.csv.gz', 'rt', encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            key = case_id(row['menu'], row['board'], int(row['cash']), int(row['empty_slots']))
            cid = row['candidate_id']
            if key not in cases or cid not in cases[key]['settings']['central']:
                continue
            curves = cases[key]['settings']['central']; lam = float(row['cash_residual'])
            predicted = value(curves[cid], lam) - value(curves['2'], lam)
            largest_error = max(largest_error, abs(predicted - float(row['slot_delta'])))
            reused_points += 1
    if largest_error > 1e-8:
        raise RuntimeError('New frontier disagrees with retained point results')
    write_csv(args.output / 'pairwise.csv', pair_rows)
    write_csv(args.output / 'card-conditions.csv', card_rows)
    if mix_rows:
        write_csv(args.output / 'mixture-thresholds.csv', mix_rows)
    with gzip.GzipFile(filename=str(args.output / 'curves.json.gz'), mode='wb', mtime=0) as f:
        f.write(json.dumps(cases, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    dump(args.output / 'design.json', dict(
        assessment_kind='heuristic', empirically_calibrated=False,
        source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        source_files=['analysis/method-lab/2026-10-18/' + p for p in
                      ('statistical_inputs.json', 'slot_value.py', 'statistical_value.py', 'value_model.py',
                       'slot-results/slot-design.json', 'slot-results/slot-primary.csv.gz')],
        candidate_ids=ids, names={str(i):inputs['cards'][str(i)]['name'] for i in ids},
        native_costs={str(i):inputs['cards'][str(i)]['cost'] for i in ids},
        price_settings=prices, cash_residual_interval=[0, 1], background_menus=menus,
        cash_levels=cash_levels, slot_levels=slot_levels,
        pair_selection='Every same-native-cost pair within the supported focal subset',
        no_parameter_probabilities=True, no_cross_cash_or_slot_average=True,
        stock_unit='F(6,5)=5 model-G; retained hypothetical body scale, not calibrated Gold',
        objective='max(asset - lambda*paid); common lambda*starting_cash cancels in every comparison',
        current_window_only=True, future_tail=0, opponent_response='none',
        holding_cost_estimated=False, player_survival_constraint=False,
        limits=['Only finite shared body-price settings; no continuous bound on body parameters',
                'Named ordinary enemy bodies and a retained 32-board integration design, not a meta distribution',
                'Cash lambda has a continuous finite-menu envelope, with floating-point tolerance',
                'Observed-board policy differs across boards; focal card identity is fixed before mixing',
                'No value assigned to future Dust/Dodge/Armor after the deadline; equality can be projection loss',
                'The focal mechanism menu and summon-capacity assumptions are inherited, not independently server validated',
                'Current same-slot loss is not a multi-turn holding cost or a deck recommendation'] ))
    dump(args.output / 'receipt.json', dict(new_envelopes=count, cases=len(cases), same_cost_pairs=len(pairs),
        pair_rows=len(pair_rows), card_rows=len(card_rows), mixture_rows=len(mix_rows),
        pair_classification_counts=status_counts, retained_point_values_reused=reused_points,
        largest_discrepancy_from_retained_points=largest_error,
        old_producer_executed=False, api_requests=0, elapsed_seconds=time.monotonic()-started))
    print(json.dumps({'finished':True,'new_envelopes':count,'pair_rows':len(pair_rows),
                      'reused_points':reused_points,'max_discrepancy':largest_error,
                      'seconds':time.monotonic()-started}), flush=True)


if __name__ == '__main__':
    main()
