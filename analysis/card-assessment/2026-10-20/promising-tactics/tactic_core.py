"""Explicit action accounting, independent of card identity or effect scripts.

Unlike the older common-one-card deployment quote, an action-vs-pass quote
must account for ALL cards consumed. No game legality or opponent policy is
inferred here. The analyst supplies a feasible trajectory and its endpoint.
"""
from copy import deepcopy
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from value_ledger import analyze, quote, paired_difference, PRICE_CORNERS, CENTRAL
from build_assessments import CARDS, B, F, hit, live


def route(cid, scenario, name, own, enemy, own_end, enemy_end, *, used=None,
          paid=None, gained=0, erased=0, enemy_gained=0, damage=0, heal=0,
          self_damage=0, stage='after_current_turn_actions', condition='',
          path=(), unknown=(), features=None):
    used = [cid] if used is None else used
    paid = sum(CARDS[i]['cost'] for i in used) if paid is None else paid
    if min(gained, erased, enemy_gained) < 0:
        raise ValueError('Use nonnegative realized inventory flows')
    inventory = gained-erased-len(used)-enemy_gained
    ledger = dict(own_before=deepcopy(own), enemy_before=deepcopy(enemy),
        own_after=deepcopy(own_end), enemy_after=deepcopy(enemy_end),
        paid_gold=paid, events=dict(usable_cards=inventory, hero_damage=damage,
            hero_heal=heal, self_damage=self_damage), valuation_stage=stage,
        condition=condition, scope='Explicit conditional action endpoint; all played/erased cards charged; symmetric marginal card price assumption',
        unpriced=list(unknown))
    # Validate now. Gross here includes inventory, so report legacy-style body
    # plus effect gross separately; do not silently mix the two definitions.
    valuation = analyze(ledger)
    no_hand = deepcopy(ledger)
    no_hand['events']['usable_cards'] = gained-erased-enemy_gained
    deployment = quote(no_hand)
    return dict(id=f'tactics/{cid}/{scenario}/{name}', card_id=cid, root=scenario,
        action=name, path=list(path), ledger=ledger, valuation=valuation,
        conditional_gross_before_played_cards=deployment['absolute_gross'],
        payment_margin_before_played_cards=deployment['net_payment_margin'],
        inventory_adjusted_action_margin=valuation['central']['net_payment_margin'],
        inventory=dict(cards_played=used, usable_gained=gained, erased=erased,
            enemy_usable_gained=enemy_gained, net_relative_cards=inventory),
        features=features or {})


def compare(left, right, reason):
    d = paired_difference(left['ledger'], right['ledger'])
    cs = [quote(left['ledger'], p)['net_payment_margin']-quote(right['ledger'], p)['net_payment_margin'] for p in PRICE_CORNERS]
    return dict(left=left['id'], right=right['id'], reason=reason, **d,
        price_corner_difference=[min(cs), max(cs)],
        interpretation='Exact same-root endpoint comparison under stated prices; no future reply or occurrence frequency inferred')
