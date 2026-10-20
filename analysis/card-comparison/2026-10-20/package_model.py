"""New bounded deployment/response experiment, not an opening match engine.

Fixed visible hand, natural-income ledger, own SOUL, ordinary enemy attacks.
All supported plays are non-immediate bodies; no old experiment is rerun.
"""
from dataclasses import dataclass, replace, asdict
from itertools import combinations
from collections import Counter
from pathlib import Path
import math
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent/'2026-10-19'))
from run_study import settings
from value_model import BodyScale

SOULS = ('INTEGRITY', 'KINDNESS', 'JUSTICE', 'DISABLED_COUNTERFACTUAL')
SUPPORTED = {1:'taunt', 2:'plain', 4:'plain', 15:'plain', 168:'dodge',
             175:'armor', 187:'plain', 377:'dodge', 602:'plain',
             38:'guard_without_other_guard', 64:'ex_without_gold_trigger'}


def integer(x, name, low=0, high=None):
    if type(x) is not int or x < low or (high is not None and x > high):
        raise ValueError(name+' is outside its integer range')
    return x


def income(turn, seat):
    integer(turn,'turn',1,10)
    if seat not in ('first','second'):raise ValueError('Unknown seat')
    return turn + int(seat=='second' and turn in (1,3,5,7,9))


def ledger(seat, soul, previous_spends):
    """Return next action-window balance. Does not simulate prior battles/draws."""
    if soul not in SOULS:raise ValueError('Unsupported SOUL, never silently ignored')
    cash=1;last=0;rows=[]
    for turn,spent in enumerate(previous_spends,1):
        integer(spent,'actual expenditure')
        before=cash+income(turn,seat)
        if spent>before:raise ValueError('Historical spending exceeds available cash')
        bonus=int(soul=='INTEGRITY' and turn>1 and spent>last)
        cash=before-spent+bonus
        rows.append(dict(turn=turn,income=income(turn,seat),before=before,
                         actual_spent=spent,end_bonus=bonus,after=cash))
        last=spent
    turn=len(previous_spends)+1
    return dict(turn=turn,seat=seat,soul=soul,history=rows,previous_spent=last,
                cash=cash+income(turn,seat),initial_cash=1,
                scope='Budget reachability only; prior board and draw history are conditioned, not simulated')


@dataclass(frozen=True)
class Body:
    key: int
    cid: int
    a: int
    h: int
    max_h: int
    armor: bool=False
    dodge: int=0
    taunt: bool=False


@dataclass(frozen=True)
class Enemy:
    key: int
    a: int
    h: int
    ready: bool=True


@dataclass(frozen=True)
class State:
    own: tuple
    enemy: tuple
    hp: int


def hurt(body, amount):
    if amount>0 and body.dodge:return replace(body,dodge=body.dodge-1)
    return replace(body,h=body.h-max(0,amount-int(body.armor)))


def all_replies(state):
    """Every order, target and optional stop. Each ordinary foe attacks once.

    A stopped prefix represents declining every still-unused attack. Reaching
    hero death terminates the window. One witness per identical physical state.
    """
    if len(state.own)>4 or len(state.enemy)>4:raise ValueError('Four physical slots per side')
    if state.hp<1:raise ValueError('Initial hero must be alive')
    visited={state:()};stack=[state]
    while stack:
        s=stack.pop()
        if s.hp<=0:continue
        taunts=[u for u in s.own if u.taunt]
        for foe in s.enemy:
            if not foe.ready or foe.a<=0:continue
            targets=taunts if taunts else (None,)+s.own
            for target in targets:
                if target is None:
                    new=State(s.own,tuple(replace(e,ready=False) if e.key==foe.key else e
                                          for e in s.enemy),s.hp-foe.a)
                    action=dict(attacker=foe.key,target='hero')
                else:
                    damaged=hurt(target,foe.a)
                    own=tuple((damaged if u.key==target.key else u) for u in s.own)
                    own=tuple(u for u in own if u.h>0)
                    enemy=tuple((replace(e,h=e.h-target.a,ready=False) if e.key==foe.key else e)
                                for e in s.enemy)
                    enemy=tuple(e for e in enemy if e.h>0)
                    new=State(own,enemy,s.hp)
                    action=dict(attacker=foe.key,target=target.key)
                if new not in visited:
                    visited[new]=visited[s]+(action,);stack.append(new)
                    if len(visited)>100000:raise ValueError('Declared finite search exceeds state cap')
    return tuple((s,path) for s,path in visited.items())


def justice(enemies):
    if not enemies:return enemies
    low=min(e.h for e in enemies)
    targets=[e for e in enemies if e.h==low]
    if len({(e.a,e.h,e.ready) for e in targets})>1:
        raise ValueError('Unresolved Justice tie among mechanically different enemies')
    target=targets[0]
    return tuple(replace(e,h=e.h-1) if e.key==target.key else e for e in enemies
                 if e.key!=target.key or e.h>1)


def kindness(own,hp,turn):
    if turn<3:return own,hp
    injured=any(u.h<u.max_h for u in own)
    if injured:
        own=tuple(replace(u,h=min(u.h+1,u.max_h)) if u.h<u.max_h else u for u in own)
    elif own:
        own=own[:-1]+(replace(own[-1],h=own[-1].h+1,max_h=own[-1].max_h+1),)
    return own,min(30,hp+1)


def validate_hand(cards, hand):
    if len(hand)>7:raise ValueError('Hand capacity exceeded')
    for cid,n in Counter(hand).items():
        if cid not in SUPPORTED:raise ValueError('Unsupported card mechanism')
        c=cards[str(cid)]
        if c['card_type']!='monster' or c['pool_category']!='ordinary_non_token':
            raise ValueError('Only actual ordinary monsters')
        limit=1 if c['rarity'] in ('LEGENDARY','DETERMINATION') else 2 if c['rarity']=='EPIC' else 3
        if n>limit:raise ValueError('Initial copy limit exceeded')
    if hand.count(38)>1:raise ValueError('Other Royal Guards would make Dust nonempty')


def package_endpoints(cards,case):
    """One representative per ordering-equivalence class of supported plays.

    Only Kindness's rightmost full-health bonus depends on play order here.
    Empty hand subsets are legal; no invented access to absent cards.
    """
    hand=case['hand'];validate_hand(cards,hand)
    soul=case['soul']
    if soul not in SOULS:raise ValueError('Unsupported SOUL')
    gold=ledger(case['seat'],soul,case['previous_spends'])
    turn=gold['turn'];cash=gold['cash']
    integer(case['own_hp'],'own HP',1,30)
    integer(case.get('minimum_hp',1),'HP floor',1,30)
    integer(case.get('minimum_bodies',0),'body floor',0,4)
    integer(case.get('enemy_cash',0),'enemy cash',0)
    if 64 in hand and (cash>=20 or case.get('enemy_cash',0)>=10):
        raise ValueError('Mettaton EX gold reset must not be ignored')
    enemies=tuple(Enemy(i,integer(a,'enemy ATK'),integer(h,'enemy HP',1))
                  for i,(a,h) in enumerate(case['enemy']))
    if len(enemies)>4:raise ValueError('Enemy capacity exceeded')
    after_start=justice(enemies) if soul=='JUSTICE' else enemies
    rows=[];seen=set()
    for count in range(min(4,len(hand))+1):
        for indices in combinations(range(len(hand)),count):
            ids=tuple(sorted(hand[i] for i in indices))
            if ids in seen:continue
            seen.add(ids)
            paid=sum(cards[str(cid)]['cost'] for cid in ids)
            if paid>cash:continue
            variants=tuple(dict.fromkeys(ids)) if soul=='KINDNESS' and ids else (None,)
            for last_cid in variants:
                ordered=list(ids)
                if last_cid is not None:ordered.remove(last_cid);ordered.append(last_cid)
                bodies=[]
                for key,cid in enumerate(ordered):
                    c=cards[str(cid)];kind=SUPPORTED[cid]
                    bodies.append(Body(key,cid,c['attack'],c['health'],c['health'],
                                       armor=kind=='armor',dodge=int(kind=='dodge'),taunt=kind=='taunt'))
                hp=case['own_hp'];own=tuple(bodies)
                if soul=='KINDNESS':own,hp=kindness(own,hp,turn)
                outcomes=all_replies(State(own,after_start,hp))
                hp_state,hp_path=min(outcomes,key=lambda p:p[0].hp)
                body_state,body_path=min(outcomes,key=lambda p:len(p[0].own))
                bonus=int(soul=='INTEGRITY' and turn>1 and paid>gold['previous_spent'])
                rows.append(dict(package=list(ids),play_order=ordered,paid=paid,cards_used=count,
                                 refund=bonus,net_paid=paid-bonus,cash_after=cash-paid+bonus,
                                 remaining_hand=list((Counter(hand)-Counter(ids)).elements()),
                                 free_slots_after_deploy=4-count,
                                 guaranteed_hp=hp_state.hp,minimum_hp_reply=hp_path,
                                 guaranteed_bodies=len(body_state.own),minimum_body_reply=body_path,
                                 feasible=hp_state.hp>=case.get('minimum_hp',1) and
                                          len(body_state.own)>=case.get('minimum_bodies',0),
                                 own_before_reply=[asdict(u) for u in own],
                                 enemy_before_reply=[asdict(e) for e in after_start],
                                 hp_before_reply=hp,outcome_count=len(outcomes),
                                 outcomes=outcomes))
    return gold,rows


def price_rows(rows,case,scale,face_price):
    original=sum(scale.value(a,h) for a,h in case['enemy'])
    out=[]
    for row in rows:
        record={k:v for k,v in row.items() if k!='outcomes'}
        if row['feasible']:
            def asset(item):
                state,_=item
                return (sum(scale.value(u.a,u.h) for u in state.own)+original-
                        sum(scale.value(e.a,e.h) for e in state.enemy)+
                        face_price*(state.hp-case['own_hp']))
            state,path=min(row['outcomes'],key=asset)
            record.update(intercept=asset((state,path)),asset_worst_reply=path,
                          asset_worst_hp=state.hp,
                          asset_worst_own=[asdict(u) for u in state.own],
                          asset_worst_enemy=[asdict(e) for e in state.enemy])
        else:record.update(intercept=None)
        out.append(record)
    # A chosen ordering is fixed before any response, not selected per branch.
    best={}
    for r in out:
        key=tuple(r['package'])
        if key not in best or (r['feasible'] and (not best[key]['feasible'] or r['intercept']>best[key]['intercept'])):
            best[key]=r
    return list(best.values()),out


def score(row,cash_price,hand_price):
    if not row['feasible']:return None
    for value in (cash_price,hand_price):
        if type(value) not in (int,float) or not math.isfinite(value) or value<0:
            raise ValueError('Finite nonnegative common resource prices required')
    return row['intercept']-cash_price*row['net_paid']-hand_price*row['cards_used']


def clip(poly,a,b,c):
    """Clip price rectangle by a+b*cash_price+c*hand_price >= 0."""
    out=[]
    for p,q in zip(poly,poly[1:]+poly[:1]):
        fp=a+b*p[0]+c*p[1];fq=a+b*q[0]+c*q[1]
        if fp>=-1e-10:out.append(p)
        if (fp<0<fq) or (fq<0<fp):
            t=fp/(fp-fq);out.append([p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1])])
    return out


def regions(rows,hand_ceiling=3.):
    feasible=[r for r in rows if r['feasible']]
    out=[]
    for row in feasible:
        poly=[[0.,0.],[1.,0.],[1.,hand_ceiling],[0.,hand_ceiling]]
        for other in feasible:
            poly=clip(poly,row['intercept']-other['intercept'],
                      other['net_paid']-row['net_paid'],other['cards_used']-row['cards_used'])
            if not poly:break
        if poly:
            out.append(dict(package=row['package'],price_polygon=poly,
                            value_plane=[row['intercept'],-row['net_paid'],-row['cards_used']]))
    return out
