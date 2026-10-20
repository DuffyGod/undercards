"""New recommendations, sensitivity and an explicit survival counterexample.

No match simulation is rerun. The response witness only attacks face with the
ordinary surviving enemy units; all three compared own bodies lack Taunt.
"""
import json
from copy import deepcopy
from itertools import product
from math import isclose
from tactic_core import *


def derive():
    out=HERE/'results'
    source=json.loads((out/'dossiers.json').read_text())
    ds=source['cards']
    rs={r['id']:r for c in ds for r in c['records']}
    cs=json.loads((out/'comparisons.json').read_text())['comparisons']
    comparisons=[]
    for c in cs:
        a,b=rs[c['left']],rs[c['right']]
        values=[quote(a['ledger'],body_parameters=dict(face_share=s,threshold=t))['net_payment_margin']-
                quote(b['ledger'],body_parameters=dict(face_share=s,threshold=t))['net_payment_margin']
                for s,t in product((.1,.35),(.2,.6))]
        comparisons.append(dict(**c,body_corner_difference=[min(values),max(values)]))
    # Each root means an ordinary8/8 whose source costs10. Toriel is reused
    # from its exact known mechanism, normalized to ALL-cards inventory here.
    enemy=[B(8,8,cost=10)]
    toriel=route(8,'one_8_8','existing_toriel_bridge',[],enemy,[B(CARDS[8]['attack'],CARDS[8]['health']+7)],[B(1,8,cost=10)],
        condition='Ordinary8ATK; Toriel removes7ATK and gains7HP; source remains1/8',
        path=['Reuse known Toriel formula; charge its one played card for matched accounting'])
    old=json.loads((HERE.parent/'results/dossiers.json').read_text())['cards']
    reference=next(r for c in old if c['card_id']==8 for r in c['records'] if r['id']=='8/tall/0')
    if not isclose(toriel['conditional_gross_before_played_cards'],reference['valuation']['central']['absolute_gross'],abs_tol=1e-10):
        raise ValueError('Toriel bridge disagrees with saved, previously verified mechanism; do not overwrite history')
    chosen=[rs['tactics/151/one_8_8/copy_0'],rs['tactics/443/one_8_8/magic_0'],
            rs['tactics/443/one_8_8/magic_0_attack_0'],toriel]
    witness=[]
    for hp in (4,8,9,12):
        for r in chosen:
            # A LEGAL reply, not opponent optimum: all ordinary enemies attack
            # hero. It suffices to reject a claimed no-immediate-lethal goal.
            attack=sum(u['a'] for u in r['ledger']['enemy_after'])
            witness.append(dict(record=r['id'],hero_hp_before=hp,
                enemy_face_damage=attack,hero_hp_after_legal_reply=hp-attack,
                fails_no_immediate_lethal=hp<=attack,
                J=r['inventory_adjusted_action_margin'],
                interpretation='No enemy hand plays, SOUL, end effects or Taunt. This is a legal lethal witness, not a full survival guarantee.'))
    sink=next(c for c in comparisons if '/509/' in c['left'])
    # ΔJ=Δbody +3p, because cards and gold cancel. Thus this exact threshold
    # need not be fitted by sampling a response or a metagame distribution.
    sink_threshold=-sink['coefficients']['body']/sink['coefficients']['face']
    slices=[]
    for p in (0,.15,sink_threshold,.25,.4):
        left,right=rs[sink['left']]['ledger'],rs[sink['right']]['ledger']
        prices=dict(face=p,card=1,gold=1)
        slices.append(dict(face_price=p,idle_minus_attack=quote(left,prices)['net_payment_margin']-quote(right,prices)['net_payment_margin']))
    # Relative erasure price is an explicit counterexample to a universal rho:
    # retain Aaron vs Tiny. The route comparison cannot discover their quality.
    bomb_a=rs['tactics/29/bomb_cheapest_replacement/bomb_erase_tiny']
    bomb_b=rs['tactics/29/bomb_cheapest_replacement/tiny_then_bomb_erase_aaron']
    db=compare(bomb_b,bomb_a,'Uniform marginal-card approximation hides erased-card identity')
    bomb=dict(db,predeploy_tiny_preferred_iff='value(retain Aaron) < F(Tiny1/1)',
        body_gain=F(1,1),uniform_price_tie=F(1,1),
        interpretation='Both routes already consume Tiny. Only the early-Tiny route additionally loses Aaron. Uniform rho givesΔ=F(Tiny)-rho; replace rho by value(retain Aaron), not by Aaron-minus-Tiny. No global winner claimed.')
    choices=[rs['tactics/506/one_5_5/loox_then_soul_cage'],rs['tactics/852/one_5_5/magic_0'],rs['tactics/201/one_5_5/loox_then_dancer']]
    affordable=[]
    for cash,p,rho in product((5,7,8),(.15,.25,.4),(0.,.5,1.,2.)):
        feasible=[r for r in choices if r['ledger']['paid_gold']<=cash]
        prices=dict(face=p,card=rho,gold=1.)
        best=max(feasible,key=lambda r:quote(r['ledger'],prices)['net_payment_margin'])
        affordable.append(dict(cash=cash,prices=prices,best_declared_action=best['id'],
            J=quote(best['ledger'],prices)['net_payment_margin']))
    dancer_soul=next(c for c in comparisons if c['left']=='tactics/201/one_3_4/attack_0')
    d=dancer_soul['coefficients']
    healing_tie=-(d['body']+(d['gold']-d['paid_gold']))/d['face']
    result=dict(source_commit=source['source_commit'],source_dirty=source['source_dirty'],comparisons=comparisons,
        long_sink=dict(face_price_tie=sink_threshold,slices=slices,
            warning='At full heroHP actual heal=0; at27HP leaving Tiny may threaten another attack. This is a price-sensitive local choice, not a default instruction.'),
        survival_counterexample=dict(toriel_bridge=toriel,replies=witness,
            finding='Pure endpoint J may prefer keeping Spade4/9 and leaving enemy8/1, but hero8HP loses to the legal8face reply. Clear it or use another response before ranking by J.'),
        bomb_card_identity_counterexample=bomb,
        clear_5_5_frontier=dict(affordable_price_slices=affordable,
            condition='All listed required cards are initially held, enough slots, ordinary5/5, missing heroHP>=4, current-turn clearing goal; only these three plans are searched',
            scope='Action selection if cards held. Does not infer how often held or recommend a whole deck.'),
        dancer_vs_soul_3_4=dict(comparison=dancer_soul,hero_heal_price_tie_at_gold1=healing_tie,
            enemy_turn_knife_transfer_q=None,
            warning='Current advantage can be reversed by SoulCage handing Knife to the enemy on a later enemy-turn death. No death probability guessed.'),
        calibration_counterexample=dict(aaron_J=F(6,5)-5-1,rock_pet_J=F(3,3)-2-1,
            finding='These normal board-building cards can have negative instantaneous J. Do not convert max(0,J) into a pass/carry policy without a matched waiting horizon.'),
        opportunity_model=dict(variables=['joint executable use-window q under a causal policy','holding friction H','foregone best alternative R'],
            unknown=['actual joint frequencies','future survival and hand quality','metagame response mix'],
            rule='For current tactics compare matched feasible actions. For carrying retain existing conditional q/H/R framework but do not plug tacticalJ into an unvalidated zero-pass threshold.'))
    (out/'recommendations.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


if __name__=='__main__':
    x=derive()
    print(json.dumps(dict(comparisons=len(x['comparisons']),long_sink_face_tie=x['long_sink']['face_price_tie'],survival_witnesses=len(x['survival_counterexample']['replies'])),indent=2))
