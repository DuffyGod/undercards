"""Independent bounded attack-order oracle and deployment coverage review.

Oracle combat uses tuple updates only, not production hurt/combat/search.
Production import is used solely for the function under review and datatypes.
Reads frozen card data; does not run old studies or query an API.
"""
from itertools import permutations, product, combinations
from pathlib import Path
import argparse
import json

from package_model import Body, Enemy, State, all_replies, package_endpoints

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def snapshot(state):
    return (tuple((u.key,u.cid,u.a,u.h,u.max_h,u.armor,u.dodge,u.taunt) for u in state.own),
            tuple((e.key,e.a,e.h,e.ready) for e in state.enemy),state.hp)


def oracle(initial):
    """Choose an ordered subset of ready enemies, then every target sequence.

    Every ordered subset includes the option to decline all other attacks.
    Damage and retaliation are computed from the precombat actors together.
    """
    own0,enemy0,hp0=initial
    attackers=[e[0] for e in enemy0 if e[3] and e[1]>0]
    endpoints=set()
    def visit(state,order):
        own,enemy,hp=state
        if not order or hp<=0:
            endpoints.add(state)
            return
        actor=next(e for e in enemy if e[0]==order[0])
        taunts=[u[0] for u in own if u[7]]
        targets=taunts or [None]+[u[0] for u in own]
        for target in targets:
            if target is None:
                next_enemy=tuple((e[0],e[1],e[2],False) if e[0]==actor[0] else e for e in enemy)
                visit((own,next_enemy,hp-actor[1]),order[1:])
                continue
            defender=next(u for u in own if u[0]==target)
            hp_after=defender[3]
            dodge_after=defender[6]
            if dodge_after:
                dodge_after-=1
            else:
                hp_after-=max(0,actor[1]-(1 if defender[5] else 0))
            next_own=[]
            for u in own:
                if u[0]!=target:
                    next_own.append(u)
                elif hp_after>0:
                    next_own.append(u[:3]+(hp_after,)+u[4:6]+(dodge_after,)+u[7:])
            next_enemy=[]
            for e in enemy:
                if e[0]!=actor[0]:
                    next_enemy.append(e)
                elif e[2]-defender[2]>0:
                    next_enemy.append((e[0],e[1],e[2]-defender[2],False))
            visit((tuple(next_own),tuple(next_enemy),hp),order[1:])
    for count in range(len(attackers)+1):
        for order in permutations(attackers,count):
            visit(initial,order)
    return endpoints


def combat_checks():
    # Standalone Armor and Dodge only, matching the supported cards.
    palette=((3,2,False,0,False),(2,6,False,0,False),
             (0,4,False,0,True),(3,2,False,1,False),(3,1,True,0,False))
    threats=((1,1,True),(2,4,True),(4,1,True),(5,7,True),
             (0,3,True),(4,4,False))
    checks=states_checked=0
    for own_count in range(3):
        for friend_types in product(palette,repeat=own_count):
            own=tuple(Body(i,100+i,a,h,h,armor,dodge,taunt)
                      for i,(a,h,armor,dodge,taunt) in enumerate(friend_types))
            for enemy_count in range(3):
                for foe_types in product(threats,repeat=enemy_count):
                    enemy=tuple(Enemy(i,a,h,ready) for i,(a,h,ready) in enumerate(foe_types))
                    for hp in (1,4,10):
                        initial=State(own,enemy,hp)
                        expected=oracle(snapshot(initial))
                        actual={snapshot(s) for s,path in all_replies(initial)}
                        if expected!=actual:
                            raise AssertionError(dict(initial=snapshot(initial),
                                missing=list(expected-actual)[:2],extra=list(actual-expected)[:2]))
                        checks+=1
                        states_checked+=len(expected)
    return dict(initial_windows=checks,full_physical_endpoints=states_checked,mismatches=0,
                range='0..2 friends, 0..2 enemies; hero HP 1/4/10; five friend and six enemy types')


def deployment_checks():
    cards={str(c['id']):c for c in json.loads((ROOT/'skills/undercards/references/snapshot.json').read_text())['cards']}
    hand=[38,15,15,602,187,377,1]
    rows_checked=0
    for soul in ('INTEGRITY','KINDNESS','JUSTICE','DISABLED_COUNTERFACTUAL'):
        case=dict(hand=hand,soul=soul,seat='second',previous_spends=[1,0,0],
                  enemy=[[4,1]],own_hp=29,minimum_hp=1,minimum_bodies=0,enemy_cash=0,
                  enemy_soul='INTEGRITY',enemy_previous_spent=0)
        gold,rows=package_endpoints(cards,case)
        if gold['cash']!=12 or gold['turn']!=4:
            raise AssertionError('Declared 12G ledger mismatch')
        subsets=set()
        for count in range(5):
            for chosen in combinations(range(len(hand)),count):
                ids=tuple(sorted(hand[i] for i in chosen))
                if sum(cards[str(cid)]['cost'] for cid in ids)<=12:subsets.add(ids)
        actual={(tuple(r['package']),r['play_order'][-1] if soul=='KINDNESS' and r['play_order'] else None)
                for r in rows}
        expected={(ids,last) for ids in subsets for last in
                  (set(ids) if soul=='KINDNESS' and ids else {None})}
        if actual!=expected or len(rows)!=len(expected):
            raise AssertionError('Missing/duplicate deployment equivalence class')
        for row in rows:
            if row['cards_used']!=len(row['package']):raise AssertionError('Card-count mismatch')
            if sorted(row['remaining_hand']+row['package'])!=sorted(hand):
                raise AssertionError('Physical hand conservation mismatch')
            if soul=='KINDNESS':
                if row['hp_before_reply']!=30:raise AssertionError('Kindness hero heal not applied before response')
                for i,u in enumerate(row['own_before_reply']):
                    expected_hp=cards[str(u['cid'])]['health']+int(i==len(row['own_before_reply'])-1)
                    if u['h']!=expected_hp or u['max_h']!=expected_hp:
                        raise AssertionError('Kindness rightmost full-health bonus mismatch')
            expected_enemy=[] if soul=='JUSTICE' else [dict(key=0,a=4,h=1,ready=True)]
            if row['enemy_before_reply']!=expected_enemy:
                raise AssertionError('Justice start damage must precede deployment/reply')
            expected_refund=int(soul=='INTEGRITY' and row['paid']>0)
            if row['refund']!=expected_refund or row['cash_after']!=12-row['paid']+expected_refund:
                raise AssertionError('Actual-expenditure refund mismatch')
            rows_checked+=1
    return dict(deployment_variants=rows_checked,souls=4,mismatches=0,
                checks='multiset subsets, Kindness last-cid classes, hand conservation, stage snapshots, 12G ledger/refund')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():p.error('Use a new review receipt path')
    result=dict(combat=combat_checks(),deployment=deployment_checks(),
                old_experiments_executed=False,api_calls=0,
                limitations='Tuple oracle covers ordinary attacks only; same declared rules, not independent server validation. No proof for >2 enemies/friends, clipping, F calibration, or real opening reachability.')
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
