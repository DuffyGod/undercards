"""Common multidimensional assessment of Agent-authored endpoint ledgers.

No card effects, match scripts, deck optimizer or card-name price bonuses live
here. An arbitrary card can be assessed once its conditional before/after assets
and event counts have been reasoned about and reviewed. This calculator checks
accounting, NOT whether the claimed endpoints follow from server rules.
"""
from pathlib import Path
from functools import lru_cache
from itertools import product
from math import isfinite
import sys,json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'analysis/method-lab/2026-10-18'))
from value_model import BodyScale
REFERENCE=json.loads((ROOT/'analysis/method-lab/2026-10-18/statistical_inputs.json').read_text())['reference']
VERSION='agent-ledger-1.0'
PRICE_CORNERS=[dict(face=p,card=r,gold=g) for p,r,g in product((.15,.4),(0.,2.),(.5,1.))]
CENTRAL=dict(face=.25,card=1.,gold=1.)


def finite(x):
    if type(x) not in (int,float) or not isfinite(x):raise ValueError('Finite numeric quantities required')
    return x

@lru_cache(maxsize=16)
def scale(face_share=.2,threshold=.4):return BodyScale(REFERENCE,face_share,threshold)

def F(a,h,face_share=.2,threshold=.4):return scale(face_share,threshold).value(a,h)


def assets(units,body_parameters=None):
    kw=body_parameters or {}
    return sum(F(finite(u['a']),finite(u['h']),**kw) for u in units if u['h']>0)


def coefficients(ledger,body_parameters=None):
    """Absolute gross vs not playing focal; payment separately reported.

    Mandatory own losses and adverse effects can make gross negative. The
    outside option (do not play) is added only after paying is considered.
    """
    required={'own_before','own_after','enemy_before','enemy_after','paid_gold','events'}
    if not required<=ledger.keys():raise ValueError('Incomplete endpoint ledger')
    for k in ('own_before','own_after','enemy_before','enemy_after'):
        if len(ledger[k])>4:raise ValueError('Four physical slots; state must be feasible')
        for u in ledger[k]:
            if finite(u['a'])<0 or finite(u['h'])<=0:raise ValueError('Only live endpoint assets')
    events=ledger['events']
    allowed={'hero_damage','hero_heal','self_damage','opponent_heal','usable_cards','usable_gold'}
    if not set(events)<=allowed:raise ValueError('Unknown event coefficient')
    for k,v in events.items():finite(v)
    paid=finite(ledger['paid_gold'])
    if paid<0:raise ValueError('Payment cannot be negative')
    body=(assets(ledger['own_after'],body_parameters)-assets(ledger['own_before'],body_parameters)
          +assets(ledger['enemy_before'],body_parameters)-assets(ledger['enemy_after'],body_parameters))
    return dict(body=body,face=events.get('hero_damage',0)+events.get('hero_heal',0)-events.get('self_damage',0)-events.get('opponent_heal',0),
                card=events.get('usable_cards',0),gold=events.get('usable_gold',0),paid_gold=paid)


def quote(ledger,prices=None,body_parameters=None):
    prices=CENTRAL if prices is None else prices
    if set(prices)!={'face','card','gold'} or any(finite(v)<0 for v in prices.values()):raise ValueError('Explicit nonnegative prices')
    c=coefficients(ledger,body_parameters)
    gross=c['body']+sum(c[k]*prices[k] for k in ('face','card','gold'))
    net=gross-c['paid_gold']*prices['gold']
    return dict(absolute_gross=gross,net_payment_margin=net,decline_or_play_surplus=max(0.,net),coefficients=c,
                prices=prices,unpriced=ledger.get('unpriced',[]),
                quote_scope=ledger.get('scope','declared conditional endpoint'),
                full_card_unconditional_value=None)


def analyze(ledger):
    central=quote(ledger);corners=[quote(ledger,p) for p in PRICE_CORNERS]
    body_corners=[quote(ledger,body_parameters=dict(face_share=s,threshold=t)) for s,t in product((.1,.35),(.2,.6))]
    return dict(central=central,price_sensitivity=dict(gross=[min(x['absolute_gross'] for x in corners),max(x['absolute_gross'] for x in corners)],
                    net=[min(x['net_payment_margin'] for x in corners),max(x['net_payment_margin'] for x in corners)]),
                body_sensitivity=dict(gross=[min(x['absolute_gross'] for x in body_corners),max(x['absolute_gross'] for x in body_corners)]))


def carrying(good_ledger,bad_ledger=None,*,q,holding_cost,replacement_surplus=0.,prices=None):
    """Conditional arrival/use-window adequacy, NOT a learned probability.

    q is ONE joint chance of an executable favorable window within the horizon.
    Never independently multiply 'target exists', cash, survival and arrival.
    Failed use may be declined; holding/replacement costs remain real.
    """
    if not 0<=finite(q)<=1:raise ValueError('q must be in [0,1]')
    if finite(holding_cost)<0 or finite(replacement_surplus)<0:raise ValueError('Nonnegative opportunity costs')
    good=quote(good_ledger,prices)['decline_or_play_surplus']
    bad=0. if bad_ledger is None else quote(bad_ledger,prices)['decline_or_play_surplus']
    threshold=None if good<=bad else (replacement_surplus+holding_cost-bad)/(good-bad)
    return dict(good_optional_surplus=good,fallback_optional_surplus=bad,q=q,holding_cost=holding_cost,
                replacement_surplus=replacement_surplus,carrying_margin=q*good+(1-q)*bad-holding_cost-replacement_surplus,
                required_q=threshold,threshold_feasible=threshold is not None and 0<=threshold<=1,
                boundary='q and costs are assumptions, not inferred frequencies. q=within-horizon joint executable opportunity under a declared causal use policy, including arrival only if stated; not a future-aware best-window oracle.')


def extra_burns(initial_hand,draws,other_plays):
    """One retained card vs one alternative already used; identical other uses.

    Draw first then other plays each step. Burn difference is inventory cost
    only, separate from the alternative's board/tempo value. Cannot charge
    every future full-hand draw again for the same one retained card.
    """
    if not 1<=initial_hand<=7 or len(draws)!=len(other_plays):raise ValueError('Invalid hand path')
    counts=[initial_hand,initial_hand-1];burn=[0,0]
    for d,u in zip(draws,other_plays):
        if type(d)is not int or type(u)is not int or min(d,u)<0:raise ValueError('Nonnegative draw/use counts')
        for j in (0,1):
            burn[j]+=max(0,counts[j]+d-7);counts[j]=min(7,counts[j]+d)
            if u>counts[j]:raise ValueError('Use count infeasible in paired hand path')
            counts[j]-=u
    return dict(held_burn=burn[0],freed_burn=burn[1],additional_burn=burn[0]-burn[1],
                caveat='Inventory-only counterfactual with shared feasible other uses; not a full holding cost.')


def paired_difference(left,right):
    # A genuine common outside option requires exactly the same pre-play board.
    for k in ('own_before','enemy_before'):
        if left[k]!=right[k]:raise ValueError('Cannot compare different conditional roots as same-state replacement')
    if left.get('valuation_stage','deployment')!=right.get('valuation_stage','deployment'):
        raise ValueError('Different realization stages are not same-window replacements')
    a=coefficients(left);b=coefficients(right)
    d={k:a[k]-b[k] for k in a}
    # dbody + dface*p + dcard*r + (dgold-dpaid)*g.
    r=None
    if d['card']:
        r=-(d['body']+d['face']*CENTRAL['face']+(d['gold']-d['paid_gold'])*CENTRAL['gold'])/d['card']
    return dict(coefficients=d,central_net_difference=quote(left)['net_payment_margin']-quote(right)['net_payment_margin'],
                card_price_tie_at_central_other_prices=r,
                scope='Same-root deployment difference, not a carrying or optimal-play ranking')
