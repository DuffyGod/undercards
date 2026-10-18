"""Shared-demand perturbations of the existing sparse valuation experiment.

All candidates use one central price vector and middle-cost resource records.
The panel families are alternative design populations, never matchup weights.
"""
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import statistics

from run_statistical_study import SELECTED, SCENARIOS, evaluate_one
from statistical_value import Prices


HERE = Path(__file__).resolve().parent
OUT = HERE / 'demand-stress'
CARD_EQUAL_SEED = 2026101801
SAMPLES = 512
PAIRS = ((649, 530), (49, 984), (469, 43), (20, 13), (243, 15), (175, 602))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')


def transform_panel(rows, mode):
    """Preserve physical source boards/weights; only transform visible HP.

    The returned original_enemy is the common pre-transform board. Empty
    survivor boards retain their original probability rather than disappearing.
    """
    if mode not in ('full', 'clamp2', 'aoe2_survivors'):
        raise ValueError('Unknown shared demand transformation')
    out = []
    for index, row in enumerate(rows):
        original = tuple(tuple(e) for e in row['enemy'])
        if mode == 'full':
            enemy = original
        elif mode == 'clamp2':
            enemy = tuple((a, max(1, h-2)) for a, h in original)
        else:
            enemy = tuple((a, h-2) for a, h in original if h > 2)
        out.append(dict(enemy=enemy, weight=row['weight'],
                        source_ids=list(row.get('source_ids', [])),
                        source_board_index=row.get('source_board_index', index),
                        original_enemy=original))
    return out


def card_equal_panel(inputs):
    cohort = inputs['cohorts']['aggro']
    rng = random.Random(CARD_EQUAL_SEED)
    rows = []
    for index in range(SAMPLES):
        drawn = [rng.choice(cohort) for _ in range(3)]
        enemy = tuple((c['attack'], c['health']) for c in drawn)
        rows.append(dict(enemy=enemy, original_enemy=enemy,
                         weight=1/SAMPLES, source_ids=[c['id'] for c in drawn],
                         source_board_index=index))
    return rows


def icecap_vulkin_panel():
    # Current ordinary numeric demand templates; not full enemy card effects.
    # Permutations are equivalent for the supported target-anywhere algebra.
    rows = []
    for vulkins in range(4):
        enemy = ((3, 1),)*(3-vulkins) + ((4, 4),)*vulkins
        rows.append(dict(enemy=enemy, original_enemy=enemy,
                         weight=math.comb(3, vulkins)/8,
                         source_ids=[9]*(3-vulkins)+[20]*vulkins,
                         source_board_index=vulkins))
    return rows


def se(values):
    return statistics.stdev(values)/math.sqrt(len(values)) if len(values) > 1 else 0.


def main():
    OUT.mkdir(exist_ok=True)
    inputs_path = HERE/'statistical_inputs.json'
    final_path = HERE/'statistical-results/final-design.json'
    inputs = json.loads(inputs_path.read_text(encoding='utf-8'))
    final = json.loads(final_path.read_text(encoding='utf-8'))
    final_hash = sha(final_path)
    source_names = ('value_model.py', 'statistical_value.py', 'run_statistical_study.py',
                    'discount_statistics.py', 'demand_stress.py')
    source_hashes = {name:sha(HERE/name) for name in source_names}
    input_hash = sha(inputs_path)
    if final['input_sha256'] != input_hash:
        raise ValueError('Frozen final design input does not match current input')
    cfg = final['scenarios']['aggro_wide']
    if cfg != SCENARIOS['aggro_wide'] or cfg['resource'] != 'middle_cost':
        raise ValueError('Demand-only stress requires the unchanged middle-cost aggro configuration')
    original = final['panels']['aggro_wide']
    if len(original) != SAMPLES or any(not math.isclose(r['weight'], 1/SAMPLES, abs_tol=1e-14) for r in original):
        raise ValueError('Expected the frozen 512 equally weighted shared demand boards')
    panels = {
        'strata_full':transform_panel(original, 'full'),
        'strata_clamp2':transform_panel(original, 'clamp2'),
        'strata_aoe2_survivors':transform_panel(original, 'aoe2_survivors'),
        'card_equal_full':card_equal_panel(inputs),
        'icecap_vulkin':icecap_vulkin_panel(),
    }
    metadata = {}
    for name, panel in panels.items():
        if not math.isclose(sum(r['weight'] for r in panel), 1., abs_tol=1e-12):
            raise ValueError('Panel probability mass must remain one')
        counts = Counter()
        for row in panel:counts[len(row['enemy'])] += row['weight']
        metadata[name] = dict(boards=len(panel), sampled=name != 'icecap_vulkin',
            survivor_count_mass=dict(sorted(counts.items())),
            empty_mass=counts[0],
            expected_enemy_count=sum(len(r['enemy'])*r['weight'] for r in panel))
    write_json('panels.json', dict(card_equal_seed=CARD_EQUAL_SEED,
        card_equal_source_count=len(inputs['cohorts']['aggro']),
        icecap_vulkin='Three independent numeric targets, P(3/1)=P(4/4)=1/2; exact binomial count states',
        panels=panels,metadata=metadata))
    prices = Prices(inputs)
    scores = []; values = {}; paired = []
    for name, panel in panels.items():
        values[name] = {}
        panel_scores = []
        for cid in SELECTED:
            card = inputs['cards'][str(cid)]
            result = evaluate_one(card, inputs, panel, 'aggro_wide', prices, True)
            values[name][cid] = result.pop('board_values')
            result.pop('by_hand_gross')
            if name == 'icecap_vulkin':
                # Value and numeric marginals are permutation invariant. Plan
                # names can change under tied target choices, so their change
                # mass is not identified by the four canonical count states.
                result['changed_plan_mass'] = None
            row = dict(panel=name, id=cid, name=card['name'],cost=card['cost'],**result,
                       demand_mc_se=se(values[name][cid]) if metadata[name]['sampled'] else None)
            scores.append(row);panel_scores.append(row)
            print(json.dumps(dict(panel=name,completed_card=cid,score_rows=len(scores))),flush=True)
        by_id = {r['id']:r for r in panel_scores}
        for left, right in PAIRS:
            vector = [a-b for a,b in zip(values[name][left],values[name][right])]
            paired.append(dict(panel=name,left=left,right=right,
                net_difference=by_id[left]['net_value']-by_id[right]['net_value'],
                paired_demand_mc_se=se(vector) if metadata[name]['sampled'] else None))
        write_json(name+'-scores.json', panel_scores)
    # Three transformations share the SAME original board index, so both the
    # card shift and change in a paired ranking have paired difference errors.
    score_index = {(r['panel'],r['id']):r for r in scores}
    transformation_changes = []; paired_transformation_changes = []
    for baseline,name in (('strata_full','strata_clamp2'),
                          ('strata_full','strata_aoe2_survivors'),
                          ('strata_clamp2','strata_aoe2_survivors')):
        for cid in SELECTED:
            vector = [a-b for a,b in zip(values[name][cid],values[baseline][cid])]
            transformation_changes.append(dict(panel=name,baseline=baseline,id=cid,
                net_change=score_index[name,cid]['net_value']-score_index[baseline,cid]['net_value'],
                paired_change_mc_se=se(vector)))
        for left,right in PAIRS:
            vector = [(a-b)-(c-d) for a,b,c,d in zip(values[name][left],values[name][right],
                values[baseline][left],values[baseline][right])]
            change = (score_index[name,left]['net_value']-score_index[name,right]['net_value']-
                      score_index[baseline,left]['net_value']+score_index[baseline,right]['net_value'])
            paired_transformation_changes.append(dict(panel=name,baseline=baseline,
                left=left,right=right,paired_gap_change=change,paired_change_mc_se=se(vector)))
    if (source_hashes != {name:sha(HERE/name) for name in source_names}
            or input_hash != sha(inputs_path) or final_hash != sha(final_path)):
        raise RuntimeError('Sources changed during the experiment; do not publish mixed results')
    with (OUT/'scores.csv').open('w',encoding='utf-8',newline='') as handle:
        writer = csv.DictWriter(handle,fieldnames=list(scores[0]));writer.writeheader();writer.writerows(scores)
    write_json('results.json',dict(scores=scores,paired_differences=paired,
        transformation_changes=transformation_changes,paired_transformation_changes=paired_transformation_changes))
    write_json('board-values.json',values)
    write_json('provenance.json',dict(schema_version=1,source_hashes=source_hashes,
        input_sha256=input_hash,final_design_sha256=final_hash,
        response_and_resource_config=cfg,price_parameters={},candidates=SELECTED,
        panel_metadata=metadata,card_equal_seed=CARD_EQUAL_SEED,
        probability_meaning='Within-panel declared demand distribution only; panels have no matchup probabilities',
        reply='Same focal damage2 opportunity p=.1 for every panel; no pre-AOE reward or cost credited',
        monte_carlo_error='Demand sampling only, not model uncertainty; icecap_vulkin is exact finite enumeration',
        compressed_plan_change_mass='Omitted: arbitrary tied target-plan labels are not permutation invariant',
        price_reference='Unchanged original F reference; card_equal_full changes demand weights only',
        transformation_comparison='Paired original board indices, preserving dead/empty outcomes and source weights'))
    print(json.dumps(dict(finished=True,score_rows=len(scores),paired=paired),ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
