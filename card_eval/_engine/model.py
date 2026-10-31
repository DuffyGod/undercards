"""A falsifiable resource/pressure abstraction, NOT an Undercards card engine.

All policy observations are immutable and exclude shuffled decks, enemy hand
identities and RNG. Cards are mechanism roles, not actual card IDs. Whole-game
claims require checking this abstraction against real mechanisms and policies.
"""
from dataclasses import dataclass, field, replace, asdict
from collections import Counter
import random

VERSION='resource-response-0.1'
KINDS=('small','anchor','draw','heal','response')
STRUCTURES={
    'wide':dict(zip(KINDS,(15,4,3,1,2))),
    'anchor':dict(zip(KINDS,(9,10,3,1,2))),
    'refill':dict(zip(KINDS,(12,4,6,1,2))),
    'recovery':dict(zip(KINDS,(12,4,3,4,2))),
    'opponent':dict(zip(KINDS,(10,6,3,3,3))),
}

@dataclass(frozen=True)
class Config:
    rounds:int=12
    soul:str='INTEGRITY'
    seat:int=0  # A's actual first/second seat, not actor identity
    first_draw:bool=True
    response_kind:str='sweep'
    response_cost:int=5
    response_damage:int=3
    responses_enabled:bool=True
    small_cost:int=2
    small_attack:int=2
    small_health:int=2
    anchor_cost:int=6
    anchor_attack:int=5
    anchor_health:int=7
    draw_cost:int=3
    draw_amount:int=2
    heal_cost:int=2
    heal_amount:int=5
    hand_cap:int=7
    slots:int=4

    def cost(self,kind):return getattr(self,kind+'_cost')

@dataclass(frozen=True)
class Card:
    uid:int
    kind:str

@dataclass(frozen=True)
class Unit:
    uid:int
    kind:str
    a:int
    h:int
    max_h:int
    ready:bool=False

@dataclass(frozen=True)
class Policy:
    name:str
    order:str='cheap'
    guard:int=4  # fragile bodies allowed if an unseen response can be funded
    reserve_cards:int=0
    reserve_gold:int=0
    response_threshold:int=1
    combat:str='trade'
    danger_override:bool=True
    heal_at:int=15
    combo_response:bool=False

ROW_POLICIES=(
    Policy('commit'),
    Policy('guard_two',guard=2,reserve_cards=1),
    Policy('bank_rebuild',guard=1,reserve_cards=1,reserve_gold=2,order='durable'),
    Policy('pressure_commit',combat='face'),
    Policy('pressure_guard',guard=2,reserve_cards=1,combat='face'),
    Policy('pressure_bank',guard=1,reserve_cards=1,reserve_gold=2,order='durable',combat='face'),
)
COL_POLICIES=(
    Policy('immediate',response_threshold=1),
    Policy('hold_two',response_threshold=2),
    Policy('hold_three',response_threshold=3),
    Policy('pressure_hold',response_threshold=2,combat='face'),
    Policy('setup_trade',response_threshold=1,combo_response=True),
)

@dataclass(frozen=True)
class View:
    hand:tuple
    own:tuple
    enemy:tuple
    hp:int
    enemy_hp:int
    cash:int
    enemy_cash:int
    turn:int
    enemy_turn:int
    seat:int
    deck_count:int
    enemy_response_unseen:int
    cfg:Config

@dataclass
class Player:
    deck:list
    hand:list=field(default_factory=list)
    units:list=field(default_factory=list)
    hp:int=30
    cash:int=1
    turn:int=0
    previous_spent:int=0
    spent:int=0
    total_spent:int=0
    income:int=0
    bonus_gold:int=0
    fatigue:int=0
    response_public:int=0
    draws:int=0
    burned:int=0
    played:int=0
    damage:int=0
    healing:int=0
    penalties:int=0
    held_opportunities:int=0
    first_effective_penalty_turn:int=0
    first_penalty_killed:int=0
    first_penalty_wiped:bool=False
    rebuilt_deploy_turn:int=0
    rebuilt_attack_turn:int=0
    post_penalty_uids:set=field(default_factory=set)


def counts_for(structure,cfg):
    counts=dict(STRUCTURES[structure])
    if not cfg.responses_enabled:counts['small']+=counts['response'];counts['response']=0
    return counts


def make_deck(structure,seed,actor,cfg=None):
    counts=counts_for(structure,cfg or Config())
    if sum(counts.values())!=25:raise ValueError('Exactly25 role slots required')
    cards=[Card(i,k) for i,k in enumerate(k for k in KINDS for _ in range(counts[k]))]
    order=list(range(25));random.Random(seed*11+actor*1000003).shuffle(order)
    return [cards[i] for i in order]


def income(turn,seat,soul):
    base=11 if soul=='INTEGRITY' and turn>10 else min(turn,10)
    return base+int(seat==1 and turn in (1,3,5,7,9))


def decide(v,p):
    """A declared causal policy class; no claim of full game best response."""
    c=v.cfg
    ready=[u for u in v.own if u.ready]
    if ready and sum(u.a for u in ready)>=v.enemy_hp:
        return ('attack',max(ready,key=lambda u:(u.a,-u.uid)).uid,-1)
    response=next((h for h in v.hand if h.kind=='response'),None)
    incoming=sum(u.a for u in v.enemy)
    if response and v.cash>=c.response_cost and v.enemy:
        if c.response_kind=='sweep':
            kills=sum(u.h<=c.response_damage for u in v.enemy)
            worth=kills>=p.response_threshold
            if p.combo_response and ready:
                # Newly deployable cards/future draws are NOT consulted. A
                # surviving ready attacker can finish a previously unkillable
                # target after the packet. This only enlarges the policy pool.
                finishes=sum(e.h>c.response_damage and any(e.h>u.a>=e.h-c.response_damage and u.h>e.a for u in ready) for e in v.enemy)
                worth=worth or kills+finishes>=p.response_threshold
            # A large but nonlethal packet can still avert imminent death only
            # if it actually removes enough attack. Never invent target damage.
            removed=sum(u.a for u in v.enemy if u.h<=c.response_damage)
        else:
            target=max(v.enemy,key=lambda u:(u.a,u.h,-u.uid))
            worth=target.h>=(0,4,7)[p.response_threshold-1]
            removed=target.a
        if worth or (p.danger_override and incoming>=v.hp and removed>0):
            return ('play',response.uid,-1)
    if ready:
        for u in sorted(ready,key=lambda u:(-u.a,u.uid)):
            safe=[e for e in v.enemy if u.a>=e.h and u.h>e.a]
            mutual=[e for e in v.enemy if u.a>=e.h and e.a>=u.h]
            targets=safe or mutual
            if p.combat=='trade' and targets:
                return ('attack',u.uid,max(targets,key=lambda e:(e.a,e.h,-e.uid)).uid)
        if incoming>=v.hp and v.enemy:
            u=max(ready,key=lambda u:(u.a,-u.uid))
            targets=[e for e in v.enemy if u.a>=e.h]
            if targets:return ('attack',u.uid,max(targets,key=lambda e:(e.a,-e.uid)).uid)
        return ('attack',max(ready,key=lambda u:(u.a,-u.uid)).uid,-1)
    heal=next((h for h in v.hand if h.kind=='heal'),None)
    if heal and v.cash>=c.heal_cost and v.hp<=p.heal_at and 30-v.hp>=c.heal_amount:
        return ('play',heal.uid,-1)
    # Availability is a PUBLIC possibility, not a fitted posterior. Not seeing
    # a cast does not prove a hidden response absent. No hypergeom posterior is
    # used after selective play; that would be invalid without a policy model.
    next_enemy=v.enemy_turn+1
    cash_next=v.enemy_cash+income(next_enemy,1-v.seat,c.soul)
    risk=v.enemy_response_unseen>0 and cash_next>=c.response_cost
    reserve=p.reserve_cards if risk else 0
    bodies=[h for h in v.hand if h.kind in ('small','anchor')]
    candidates=[]
    if len(v.own)<c.slots:
        for h in bodies:
            cost=c.cost(h.kind)
            if v.cash<cost:continue
            if v.own and len(bodies)-1<reserve:continue
            if risk and v.own and v.cash-cost<p.reserve_gold:continue
            if risk and c.response_kind=='sweep':
                fragile=sum(u.h<=c.response_damage for u in v.own)
                new_health=getattr(c,h.kind+'_health')
                if fragile+int(new_health<=c.response_damage)>p.guard:continue
            candidates.append(h)
    if candidates:
        h=sorted(candidates,key=lambda h:(c.cost(h.kind) if p.order=='cheap' else -getattr(c,h.kind+'_health'),h.uid))[0]
        return ('play',h.uid,-1)
    draw=next((h for h in v.hand if h.kind=='draw'),None)
    if draw and v.cash>=c.draw_cost and v.deck_count>0 and len(v.hand)<=4 and len(bodies)<=reserve+1:
        return ('play',draw.uid,-1)
    return ('end',-1,-1)


class Game:
    def __init__(self,structure,seed,cfg,policies,trace=False):
        self.cfg=cfg;self.structure=structure;self.seed=seed;self.policies=policies
        self.players=[Player(make_deck(structure,seed,0,cfg)),Player(make_deck('opponent',seed,1,cfg))]
        self.trace=[] if trace else None
        self.snapshots=[]
        for actor in (0,1):
            for _ in range(3):self.draw(actor)

    def event(self,actor,action,**kw):
        if self.trace is not None:
            self.trace.append(dict(actor=actor,turn=self.players[actor].turn,action=action,**kw))

    def draw(self,actor):
        p=self.players[actor];p.draws+=1
        if not p.deck:
            p.fatigue+=1;p.hp-=p.fatigue
            self.event(actor,'fatigue',damage=p.fatigue);return
        card=p.deck.pop(0)
        if len(p.hand)==self.cfg.hand_cap:
            p.burned+=1
            if card.kind=='response':p.response_public+=1
            self.event(actor,'burn',card=asdict(card))
        else:p.hand.append(card);self.event(actor,'draw',card=asdict(card))

    def view(self,actor):
        a,b=self.players[actor],self.players[1-actor]
        total=counts_for('opponent' if actor==0 else self.structure,self.cfg)['response']
        return View(tuple(a.hand),tuple(a.units),tuple(b.units),a.hp,b.hp,a.cash,b.cash,a.turn,b.turn,
                    self.cfg.seat if actor==0 else 1-self.cfg.seat,len(a.deck),total-b.response_public,self.cfg)

    def play(self,actor,uid):
        a,b=self.players[actor],self.players[1-actor];c=self.cfg
        h=next(h for h in a.hand if h.uid==uid);cost=c.cost(h.kind)
        if a.cash<cost:raise ValueError('Unfunded action')
        a.hand.remove(h);a.cash-=cost;a.spent+=cost;a.total_spent+=cost;a.played+=1
        self.event(actor,'play',card=asdict(h),cost=cost,cash_after=a.cash)
        if h.kind in ('small','anchor'):
            if len(a.units)>=c.slots:raise ValueError('Entry requires free slot')
            ah=getattr(c,h.kind+'_health')
            a.units.append(Unit(uid,h.kind,getattr(c,h.kind+'_attack'),ah,ah))
            if a.first_effective_penalty_turn:
                a.post_penalty_uids.add(uid)
                if not a.rebuilt_deploy_turn:a.rebuilt_deploy_turn=a.turn
        elif h.kind=='draw':
            for _ in range(c.draw_amount):
                if a.hp<=0:break
                self.draw(actor)
        elif h.kind=='heal':
            n=min(c.heal_amount,30-a.hp);a.hp+=n;a.healing+=n
        else:
            a.response_public+=1;a.penalties+=1
            before=list(b.units)
            if c.response_kind=='sweep':b.units=[replace(u,h=u.h-c.response_damage) for u in b.units if u.h>c.response_damage]
            elif b.units:
                target=max(b.units,key=lambda u:(u.a,u.h,-u.uid))
                b.units=[u for u in b.units if u.uid!=target.uid]
            killed=len(before)-len(b.units)
            self.event(actor,'punishment',kind=c.response_kind,killed=killed,enemy_before=[asdict(u) for u in before],enemy_after=[asdict(u) for u in b.units])
            if killed and not b.first_effective_penalty_turn:
                # The punished player's turn clock, not caster's clock; future
                # recovery deadlines are counted in the punished player's turns.
                b.first_effective_penalty_turn=b.turn
                b.first_penalty_killed=killed;b.first_penalty_wiped=not b.units

    def attack(self,actor,uid,target):
        a,b=self.players[actor],self.players[1-actor]
        u=next(u for u in a.units if u.uid==uid)
        if not u.ready:raise ValueError('Summoning sick or already used')
        if target==-1:
            b.hp-=u.a;a.damage+=u.a
            a.units=[replace(x,ready=False) if x.uid==uid else x for x in a.units]
        else:
            e=next(e for e in b.units if e.uid==target)
            a.units=[replace(x,h=x.h-e.a,ready=False) if x.uid==uid else x for x in a.units]
            b.units=[replace(x,h=x.h-u.a) if x.uid==target else x for x in b.units]
            a.units=[x for x in a.units if x.h>0];b.units=[x for x in b.units if x.h>0]
        if uid in a.post_penalty_uids and not a.rebuilt_attack_turn:a.rebuilt_attack_turn=a.turn
        self.event(actor,'attack',unit=uid,target=target,attack=u.a)

    def act_turn(self,actor):
        a,b=self.players[actor],self.players[1-actor];c=self.cfg
        a.turn+=1;a.spent=0
        seat=c.seat if actor==0 else 1-c.seat
        grant=income(a.turn,seat,c.soul)
        a.cash+=grant;a.income+=grant;a.units=[replace(u,ready=True) for u in a.units]
        self.event(actor,'start',income=grant,cash=a.cash)
        if c.first_draw or a.turn>1:self.draw(actor)
        if a.hp<=0:return
        for _ in range(100):
            v=self.view(actor);action,uid,target=decide(v,self.policies[actor])
            if action=='end':break
            if action=='play':self.play(actor,uid)
            elif action=='attack':self.attack(actor,uid,target)
            else:raise ValueError('Unknown action')
            if min(a.hp,b.hp)<=0:return
        else:raise ValueError('Action loop failed to terminate')
        a.held_opportunities+=int(any(h.kind=='response' for h in a.hand) and a.cash>=c.response_cost and bool(b.units))
        if c.soul=='INTEGRITY' and a.turn>1 and a.spent>a.previous_spent:a.cash+=1;a.bonus_gold+=1
        if c.soul=='KINDNESS' and a.turn>=3:
            n=min(1,30-a.hp);a.hp+=n;a.healing+=n
            wounded=any(u.h<u.max_h for u in a.units)
            if wounded:a.units=[replace(u,h=min(u.max_h,u.h+1)) for u in a.units]
            elif a.units:a.units[-1]=replace(a.units[-1],h=a.units[-1].h+1,max_h=a.units[-1].max_h+1)
        a.previous_spent=a.spent
        if a.cash<0 or len(a.hand)>c.hand_cap or len(a.units)>c.slots:raise ValueError('Physical resource violation')
        self.event(actor,'end',hp=a.hp,enemy_hp=b.hp,cash=a.cash,hand=[asdict(h) for h in a.hand],units=[asdict(u) for u in a.units])

    def run(self):
        order=(0,1) if self.cfg.seat==0 else (1,0)
        for n in range(1,self.cfg.rounds+1):
            for actor in order:
                self.act_turn(actor)
                a,b=self.players
                if min(a.hp,b.hp)<=0:break
            a,b=self.players
            self.snapshots.append(dict(round=n,a_hp=a.hp,b_hp=b.hp,terminal=min(a.hp,b.hp)<=0))
            if min(a.hp,b.hp)<=0:break
        a,b=self.players
        return dict(seed=self.seed,structure=self.structure,row_policy=self.policies[0].name,col_policy=self.policies[1].name,
            config=asdict(self.cfg),a_hp=a.hp,b_hp=b.hp,won=b.hp<=0<a.hp,lost=a.hp<=0<b.hp,
            unfinished=min(a.hp,b.hp)>0,round=self.snapshots[-1]['round'],
            # Explicit finite-deadline objective, not a guessed game winner.
            deadline_life_margin=(max(0,a.hp)-max(0,b.hp))/30,
            a_draws=a.draws,a_burned=a.burned,a_played=a.played,a_cash=a.cash,a_damage=a.damage,a_healing=a.healing,
            a_hand=len(a.hand),a_units=len(a.units),b_cash=b.cash,b_held=b.held_opportunities,b_penalties=b.penalties,
            first_punished=a.first_effective_penalty_turn,rebuild_deploy=a.rebuilt_deploy_turn,rebuild_attack=a.rebuilt_attack_turn,
            first_penalty_killed=a.first_penalty_killed,first_penalty_wiped=a.first_penalty_wiped,
            a_income=a.income,a_bonus_gold=a.bonus_gold,a_total_spent=a.total_spent,a_deck=len(a.deck),
            snapshots=self.snapshots,trace=self.trace)


def play(structure,seed,cfg,row,col,trace=False):return Game(structure,seed,cfg,(row,col),trace).run()
