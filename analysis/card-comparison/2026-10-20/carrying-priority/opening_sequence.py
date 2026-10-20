"""Short known-arrival diagnostics: fixed deployments, optimal ordinary combat.

Not deck construction or hidden-information play. Both sides get real income,
draw one known card each own turn, and pay for prescribed monster deployments.
The MAX/MIN search chooses attack orders, targets and stopping, not new plays.
"""
from dataclasses import dataclass,replace,asdict
from functools import lru_cache
from pathlib import Path
from collections import Counter
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from package_model import BodyScale,income,integer

SOULS=('INTEGRITY','KINDNESS','DISABLED_COUNTERFACTUAL')
SUPPORTED={1:'taunt',2:'plain',4:'plain',15:'plain',38:'one_guard',168:'dodge',
           175:'armor',187:'plain',377:'dodge',602:'plain',243:'draw_one'}
OWN_INITIAL=(602,38,243)
OWN_DRAWS=(15,1,187,2,377,4)
ENEMY_INITIAL=(38,602,15)
ENEMY_DRAWS=(1,4,2,187,377,175)
POLICIES={
    'save_5':{3:(15,)},
    'bridge_5':{1:(602,),3:(15,)},
    'save_9':{4:(38,)},
    'bridge_9':{1:(602,),4:(38,)},
    'draw_5':{3:(243,)},
    'bridge_draw_5':{1:(602,),3:(243,)},
    'staggered_three':{1:(602,),3:(15,),4:(187,)},
    'late_same_three':{4:(602,15,187)},
    'draw_accelerates_two':{1:(602,),3:(243,2),4:(187,)},
    'normal_two_later':{1:(602,),3:(15,),4:(2,187)},
}
ENEMY_SCRIPTS={'empty':{},'two_low':{1:(602,),2:(4,)},
               'mid_pressure':{1:(602,),3:(15,)},'save_heavy':{4:(38,)}}


@dataclass(frozen=True)
class Unit:
    key:int
    cid:int
    a:int
    h:int
    max_h:int
    ready:bool=False
    armor:bool=False
    dodge:int=0
    taunt:bool=False


@dataclass(frozen=True)
class Player:
    hp:int=30
    cash:int=1
    hand:tuple=()
    deck:tuple=()
    field:tuple=()
    previous_spent:int=0
    next_key:int=0
    played:int=0
    bonus_draws:int=0
    burned:int=0


@dataclass(frozen=True)
class Game:
    players:tuple
    phase:int=0


def damage(unit,amount):
    if amount>0 and unit.dodge:return replace(unit,dodge=unit.dodge-1)
    return replace(unit,h=unit.h-max(0,amount-int(unit.armor)))


def draw(player,bonus=False):
    if not player.deck:raise ValueError('Known arrival prefix exhausted; no invented draw')
    card=player.deck[0]
    if len(player.hand)>=7:
        return replace(player,deck=player.deck[1:],burned=player.burned+1,
                       bonus_draws=player.bonus_draws+int(bonus)),dict(card=card,burned=True,bonus=bonus)
    return replace(player,deck=player.deck[1:],hand=player.hand+(card,),
                   bonus_draws=player.bonus_draws+int(bonus)),dict(card=card,burned=False,bonus=bonus)


def phase_actor(phase,seat):
    return phase%2 if seat=='first' else 1-phase%2


def begin(game,seat,souls,deployments,cards):
    side=phase_actor(game.phase,seat);turn=game.phase//2+1
    p=game.players[side];foe=game.players[1-side]
    before=p.cash+income(turn,'first' if (side==0)==(seat=='first') else 'second')
    p=replace(p,cash=before,field=tuple(replace(u,ready=True) for u in p.field))
    p,draw_event=draw(p)
    paid=0;plays=[]
    for cid in deployments[side].get(turn,()):
        if cid not in SUPPORTED:raise ValueError('Unsupported deployment mechanism')
        if cid not in p.hand:raise ValueError('Script cannot play a card that has not arrived')
        card=cards[str(cid)];cost=card['cost'];kind=SUPPORTED[cid]
        if p.cash<cost:raise ValueError('Script spends unearned gold')
        if len(p.field)>=4:raise ValueError('Fixed deployment cannot fit the actual field')
        if cid==38 and any(u.cid==38 for u in p.field):
            raise ValueError('Royal Guard Dust would have a recipient')
        hand=list(p.hand);hand.remove(cid)
        unit=Unit(p.next_key,cid,card['attack'],card['health'],card['health'],
                  armor=kind=='armor',dodge=int(kind=='dodge'),taunt=kind=='taunt')
        p=replace(p,hand=tuple(hand),cash=p.cash-cost,field=p.field+(unit,),
                  next_key=p.next_key+1,played=p.played+1)
        paid+=cost;event=dict(cid=cid,cost=cost)
        if kind=='draw_one':p,event['draw']=draw(p,bonus=True)
        plays.append(event)
    players=list(game.players);players[side]=p
    return Game(tuple(players),game.phase),paid,dict(actor=side,own_turn=turn,
             before_cash=before,draw=draw_event,plays=plays,after_play_cash=p.cash)


def attack_endpoints(game,side):
    """All optional attacks of current side, with fully symmetric defenses."""
    reached={game:()};stack=[game]
    while stack:
        g=stack.pop();attacker=g.players[side];defender=g.players[1-side]
        if attacker.hp<=0 or defender.hp<=0:continue
        taunts=tuple(u for u in defender.field if u.taunt)
        for actor in attacker.field:
            if not actor.ready or actor.a<=0:continue
            for target in taunts if taunts else (None,)+defender.field:
                own=list(attacker.field)
                if target is None:
                    own=[replace(u,ready=False) if u.key==actor.key else u for u in own]
                    new_defender=replace(defender,hp=defender.hp-actor.a)
                    action=dict(attacker=actor.key,target='hero',damage=actor.a)
                else:
                    a=replace(damage(actor,target.a),ready=False);b=damage(target,actor.a)
                    own=[a if u.key==actor.key else u for u in own]
                    team=[b if u.key==target.key else u for u in defender.field]
                    new_defender=replace(defender,field=tuple(u for u in team if u.h>0))
                    action=dict(attacker=actor.key,target=target.key)
                new_attacker=replace(attacker,field=tuple(u for u in own if u.h>0))
                players=list(g.players);players[side]=new_attacker;players[1-side]=new_defender
                new=Game(tuple(players),g.phase)
                if new not in reached:
                    reached[new]=reached[g]+(action,);stack.append(new)
    return tuple(reached.items())


def end(game,side,turn,soul,paid):
    p=game.players[side]
    if all(x.hp>0 for x in game.players):
        if soul=='KINDNESS' and turn>=3:
            injured=any(u.h<u.max_h for u in p.field)
            field=tuple(replace(u,h=min(u.h+1,u.max_h)) if u.h<u.max_h else u for u in p.field)
            if not injured and field:field=field[:-1]+(replace(field[-1],h=field[-1].h+1,max_h=field[-1].max_h+1),)
            p=replace(p,hp=min(30,p.hp+1),field=field)
        bonus=int(soul=='INTEGRITY' and turn>1 and paid>p.previous_spent)
        p=replace(p,cash=p.cash+bonus,previous_spent=paid)
    players=list(game.players);players[side]=p
    return Game(tuple(players),game.phase+1)


class OpeningGraph:
    def __init__(self,cards,policy,enemy,seat='first',soul='INTEGRITY',horizon=4,cap=200000):
        if soul not in SOULS or seat not in ('first','second'):raise ValueError('Unsupported SOUL or seat')
        integer(horizon,'horizon',1,5)
        self.cards=cards;self.policy=policy;self.enemy=enemy;self.seat=seat
        self.souls=(soul,'INTEGRITY');self.horizon=horizon;self.cap=cap
        self.deployments=(POLICIES[policy],ENEMY_SCRIPTS[enemy]);self.edges={}
        self.root=Game((Player(hand=OWN_INITIAL,deck=OWN_DRAWS),Player(hand=ENEMY_INITIAL,deck=ENEMY_DRAWS)))
        self._build(self.root)

    def _build(self,g):
        if g in self.edges:return
        if len(self.edges)>=self.cap:raise ValueError('Finite opening graph state cap exceeded; no truncated answer')
        self.edges[g]=None
        if g.phase>=2*self.horizon or any(p.hp<=0 for p in g.players):return
        side=phase_actor(g.phase,self.seat);turn=g.phase//2+1
        prepared,paid,event=begin(g,self.seat,self.souls,self.deployments,self.cards)
        children={}
        for endpoint,path in attack_endpoints(prepared,side):
            child=end(endpoint,side,turn,self.souls[side],paid)
            children.setdefault(child,dict(**event,attacks=path,after_end_cash=child.players[side].cash))
        self.edges[g]=tuple(children.items())
        for child in children:self._build(child)

    def evaluate(self,scale,face_price,cash_price,hand_price):
        @lru_cache(None)
        def solve(g):
            if self.edges[g] is None:
                a,b=g.players
                rank=1 if b.hp<=0<a.hp else -1 if a.hp<=0 else 0
                asset=(sum(scale.value(u.a,u.h) for u in a.field)-sum(scale.value(u.a,u.h) for u in b.field)+
                       face_price*(a.hp-b.hp)+cash_price*a.cash+hand_price*len(a.hand))
                return (rank,asset),g,None
            choose=max if phase_actor(g.phase,self.seat)==0 else min
            candidate=choose(((solve(child)[0],child,event) for child,event in self.edges[g]),key=lambda r:r[0])
            return candidate
        value,_,_=solve(self.root);path=[];node=self.root
        while self.edges[node] is not None:
            _,child,event=solve(node);path.append(event);node=child
        return dict(terminal_result=value[0],value=value[1],final=asdict(node),witness=path,
                    meaning='One worst-value witness of optimal ordinary combat under FIXED known deployment scripts; not separate HP/body guarantees')
