"""Exact hand-statistic compression for the frozen mechanism descriptors.

For hand-independent effects, preserve the entire cash distribution but
replace the irrelevant hand count by zero. Hand-driven cards keep the full
joint distribution. This changes runtime, not the decision or pricing model.
"""
from functools import lru_cache

from run_statistical_study import SCENARIOS, evaluate_one
from statistical_value import FEATURES

INDEPENDENT_KINDS=frozenset(('plain','charge','buff_ally','debuff_all','damage_any',
    'haste_aoe_face','dodge','armor','self_damage','haste_dust_child',
    'haste_dodge_chain','count_damage_haste'))


def evaluate_compressed(card,inputs,panels,scenario,prices,marginals):
    kind=FEATURES[card['id']][0]
    key=SCENARIOS[scenario]['resource']
    resource=inputs['resources'][key]
    if kind=='draw':
        # The frozen Draw1 has no burn when after-play hand is at most6.
        independent=all(1<=r['hand_size_before_play']<=7 for r in resource['records'])
    else:independent=kind in INDEPENDENT_KINDS
    if not independent:
        return evaluate_one(card,inputs,panels,scenario,prices,marginals)
    compact=dict(resource,records=[dict(r,hand_size_before_play=1) for r in resource['records']])
    compressed=dict(inputs,resources=dict(inputs['resources'],**{key:compact}))
    result=evaluate_one(card,compressed,panels,scenario,prices,marginals)
    result['by_hand_gross']={r['hand_size_before_play']-1:result['gross_value'] for r in resource['records']}
    return result
