"""Causal opening rollouts. Restricted real cards; no deck optimizer or win oracle.

The environment alone owns shuffled decks. Policy functions only receive View.
Combat plans enumerate ordinary attacks for this turn, with a declared heuristic
cutoff; they do not search future turns. Deployment is a causal greedy policy.
"""
from dataclasses import dataclass, replace, asdict
from pathlib import Path
from collections import Counter
from functools import lru_cache
import json, random, sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'analysis/method-lab/2026-10-18'))
from value_model import BodyScale
VERSION='joint-opening-0.3'
SNAPSHOT=json.loads((ROOT/'skills/undercards/references/snapshot.json').read_text())
CARDS={c['id']:c for c in SNAPSHOT['cards']}
REFERENCE=json.loads((ROOT/'analysis/method-lab/2026-10-18/statistical_inputs.json').read_text())['reference']
SCALE=BodyScale(REFERENCE)
SUPPORTED={2,4,15,17,21,44,91,168,175,187,196,225,243,377,602}

# Positions are explicit entities: replacements retain their slot for paired draws.
SMALL=tuple([196]*3+[2]*3+[4]*3+[602]*3+[175]*3+[377]*3+[187]*3+[15]*3+[17])
MIDDLE=tuple([243]*3+[2]*3+[4]*3+[602]*3+[168]*3+[377]*3+[187]*3+[15]*3+[17])
DRAW_MIDDLE=tuple(225 if c==187 else c for c in MIDDLE)
HEAVY=list(MIDDLE)
for i,c in zip(range(3,9),(17,17,44,44,21,21)):HEAVY[i]=c
COMPOSITIONS={'small':SMALL,'small_draw':tuple(225 if c==187 else c for c in SMALL),
              'middle':MIDDLE,'middle_draw':DRAW_MIDDLE,'heavy':tuple(HEAVY),
              'middle_heal':tuple(91 if c==4 else c for c in DRAW_MIDDLE)}
COMPOSITIONS['small_anchor']=tuple(243 if c==196 else c for c in COMPOSITIONS['small_draw'])
COMPOSITIONS['small_reach']=tuple(([21,21,168]+list(COMPOSITIONS['small_draw'][3:])))
POLICIES=('pressure','balanced','reserve_slot')

@dataclass(frozen=True)
class Config:
    horizon:int=8
    hand_cap:int=7
    slots:int=4
    first_turn_draw:bool=True
    extra_natural_draw:int=0  # 0 is actual default; 1 is a labeled intervention.
    bonus_draw:bool=True
    healing:bool=True
    hero_healing:tuple=(True,True)
    knight_damage:str='packet'  # alternate 'hp_loss' for unresolved overkill ruling.
    end_order:str='draw_then_soul'  # alternate 'soul_then_draw' for fatigue sensitivity.
    public_tactics:bool=False
    combat_cap:int=25000

@dataclass(frozen=True)
class Held:
    uid:int
    cid:int
    source:str='normal'

@dataclass(frozen=True)
class Unit:
    uid:int
    cid:int
    a:int
    h:int
    max_h:int
    ready:bool=False
    dodge:int=0
    armor:bool=False
    taunt:bool=False
    face_allowed:bool=True

@dataclass(frozen=True)
class Board:
    own:tuple
    foe:tuple
    hp:int
    foe_hp:int

@dataclass(frozen=True)
class View:
    board:Board
    hand:tuple
    cash:int
    turn:int
    seat:int
    hand_cap:int
    slots:int
    soul:str
    healing:bool
    knight_damage:str
    deck_count:int
    fatigue:int
    # No enemy hand identities, deck order, seed or hidden-state reference.

@dataclass
class Player:
    deck:list
    hand:list
    field:tuple=()
    hp:int=30
    cash:int=1
    previous_spent:int=0
    fatigue:int=0


def validate_deck(deck,soul):
    if len(deck)!=25:raise ValueError('A composition must have exactly 25 entities')
    for cid,n in Counter(deck).items():
        if cid not in SUPPORTED:raise ValueError(f'Unsupported card {cid}')
        c=CARDS[cid]
        limit={'BASE':3,'COMMON':3,'RARE':3,'EPIC':2,'LEGENDARY':1,'DETERMINATION':1,'DT':1}.get(c['rarity'])
        if limit is None or n>limit or c['pool_category']!='ordinary_non_token':raise ValueError(f'Illegal copies/pool {cid}')
        if c['soul'] and c['soul']!=soul:raise ValueError('Wrong SOUL spell')


def hurt(u,amount):
    if amount>0 and u.dodge:return replace(u,dodge=u.dodge-1),0,0
    packet=max(0,amount-int(u.armor));return replace(u,h=u.h-packet),packet,min(max(u.h,0),packet)


def unit(held):
    c=CARDS[held.cid]
    return Unit(held.uid,held.cid,c['attack'],c['health'],c['health'],
                ready=held.cid==21,dodge=int(held.cid in (168,377)),armor=held.cid==175,
                taunt=held.cid==44,face_allowed=held.cid!=21)


def attack(board,actor,target,config):
    a=next(u for u in board.own if u.uid==actor)
    taunts=tuple(u for u in board.foe if u.taunt)
    if not a.ready or a.a<=0:raise ValueError('No usable attack')
    if target is None:
        if taunts or not a.face_allowed:raise ValueError('Illegal hero target')
        remaining=replace(a,ready=False)
        actual=min(max(0,board.foe_hp),a.a)
        healed=0
        if a.cid==17 and config.healing:
            healed=min(a.max_h-a.h,a.a if config.knight_damage=='packet' else actual)
            remaining=replace(remaining,h=remaining.h+healed)
        return replace(board,own=tuple(remaining if u.uid==actor else u for u in board.own),foe_hp=board.foe_hp-a.a),dict(actor=actor,target='hero',hero_damage=actual,monster_heal=healed)
    b=next(u for u in board.foe if u.uid==target)
    if taunts and not b.taunt:raise ValueError('Taunt prevents target')
    aa,_,_=hurt(a,b.a);bb,packet,actual=hurt(b,a.a);aa=replace(aa,ready=False)
    healed=0
    if aa.h>0 and a.cid==17 and config.healing:
        healed=min(aa.max_h-aa.h,packet if config.knight_damage=='packet' else actual)
        aa=replace(aa,h=aa.h+healed)
    own=tuple(aa if u.uid==actor else u for u in board.own)
    foe=tuple(bb if u.uid==target else u for u in board.foe)
    return replace(board,own=tuple(u for u in own if u.h>0),foe=tuple(u for u in foe if u.h>0)),dict(actor=actor,target=target,packet=packet,hp_loss=actual,monster_heal=healed,killed=bb.h<=0,lost=aa.h<=0)


@lru_cache(maxsize=100000)
def body_value(u):return SCALE.value(u.a,u.h)


def board_score(b,policy):
    if b.foe_hp<=0:return (2,0.)
    if b.hp<=0:return (0,0.)
    face=1.0 if policy=='pressure' else .25
    # A transparent danger proxy, not a guaranteed opponent response bound.
    exposed=sum(u.a for u in b.foe) if not any(u.taunt for u in b.own) else 0
    risk=0. if policy=='pressure' else 4*max(0,exposed-b.hp+1)
    return (1,sum(map(body_value,b.own))-sum(map(body_value,b.foe))+face*(b.hp-b.foe_hp)-risk)


def choose_combat(view,policy,config):
    root=view.board;seen={root:()};stack=[root];best=root
    while stack:
        b=stack.pop()
        if board_score(b,policy)>board_score(best,policy):best=b
        if b.hp<=0 or b.foe_hp<=0:continue
        targets=[u.uid for u in b.foe if u.taunt]
        for a in b.own:
            if not a.ready or a.a<=0:continue
            legal=targets or ([None] if a.face_allowed else [])+[u.uid for u in b.foe]
            for target in legal:
                new,_=attack(b,a.uid,target,config)
                if new not in seen:
                    if len(seen)>=config.combat_cap:raise RuntimeError('Combat cap exceeded; rejected, not truncated')
                    seen[new]=seen[b]+((a.uid,target),);stack.append(new)
    return seen[best],len(seen)


def deployment_scores(view,policy):
    """Declared local heuristic; no future draws or estimated ladder frequencies.

    F and face prices are retained from preceding studies. Card/coin shadow
    prices are policy hypotheses, NOT extra terms in final outcome statistics.
    """
    out=[]
    current=view.board
    for h in view.hand:
        c=CARDS[h.cid];cost=c['cost']
        if cost>view.cash:continue
        if h.cid==91:
            missing=30-current.hp
            restored=min(3,missing)*int(view.healing)
            flow=.6 if view.deck_count else -.25*(view.fatigue+1)
            score=.25*restored+flow-.5*cost
            if not view.deck_count and current.hp+restored<=view.fatigue+1:score=-1e9
            out.append((score,h.uid));continue
        if len(current.own)>=view.slots:continue
        u=unit(h);f=body_value(u)
        face=1.0 if policy=='pressure' else .25
        score=f+face*u.a-(.25 if policy=='pressure' else .5)*cost
        score-=.5 if len(view.hand)<=2 else .1
        if h.cid==21:
            score+=face*min(3,max(0,current.foe_hp))
            score+=sum(body_value(e)-body_value(hurt(e,1)[0]) for e in current.foe)
        if h.cid in (243,44):
            count=min(1 if h.cid==243 else 2,view.hand_cap-len(view.hand)+1,view.deck_count)
            score+=.6*count
            if h.cid==243 and not view.deck_count:
                score-=.25*(view.fatigue+1)
                if current.hp<=view.fatigue+1:score=-1e9
        if h.cid==225:
            score+=.6 if view.deck_count else -.25*(view.fatigue+1)
            if not view.deck_count and current.hp<=view.fatigue+1:score=-1e9
        if u.taunt:score+=.25*min(sum(e.a for e in current.foe),u.h)
        if policy=='reserve_slot' and len(current.own)==view.slots-1:
            # Reserve last slot only for a stronger currently held monster
            # affordable by next turn, ignoring unknown future draws.
            soon=view.cash+min(view.turn+1,10)+int(view.seat==1 and view.turn+1 in (1,3,5,7,9))
            better=[x for x in view.hand if x.cid!=91 and CARDS[x.cid]['cost']<=soon
                    and body_value(unit(x))>1.5*f]
            if better:score=-1.
        out.append((score,h.uid))
    return out


def choose_deployment(view,policy):
    choices=deployment_scores(view,policy)
    if not choices:return None
    score,uid=max(choices,key=lambda z:(z[0],-z[1]))
    return uid if score>0 else None


class Match:
    def __init__(self,decks,souls,policies,seed,config=Config(),trace=False):
        if len(decks)!=2 or len(souls)!=2 or len(policies)!=2:raise ValueError('Two players required')
        if not 1<=config.horizon<=10 or config.hand_cap<1 or config.slots<1:raise ValueError('Unsupported limits')
        if config.knight_damage not in ('packet','hp_loss') or config.end_order not in ('draw_then_soul','soul_then_draw'):raise ValueError('Unknown ruling')
        if config.extra_natural_draw not in (0,1):raise ValueError('Unsupported draw intervention')
        self.config=config;self.souls=souls;self.policies=policies;self.turn=0;self.actor=0
        self.players=[];self.trace=[];self.keep_trace=trace;self.snapshots=[]
        self.stats=[dict(draws=0,bonus_draws=0,burned=0,bonus_burned=0,played=0,bonus_played=0,
                         spent=0,damage=0,healed=0,monster_healed=0,fatigue_damage=0,
                         slot_blocked_turns=0,slot_missed=0,reserve_withheld_turns=0,empty_hand_turns=0,first_turn_no_opener=False,
                         first_turn_available_but_no_play=False,first_turn_no_play=False,first_play=None,
                         big_reply=None,small_killed_by_big=0,small_deployed=0,drawn_ids=[]) for _ in range(2)]
        for side,(deck,soul,policy) in enumerate(zip(decks,souls,policies)):
            validate_deck(deck,soul)
            if soul not in ('INTEGRITY','KINDNESS') or policy not in POLICIES:raise ValueError('Unsupported SOUL/policy')
            order=list(range(25));random.Random(seed*2+side+982451653).shuffle(order)
            self.players.append(Player([Held(i,deck[i]) for i in order],[]))
        for side in (0,1):
            for _ in range(3):self.draw(side,'initial')

    def event(self,kind,**kwargs):
        if self.keep_trace:self.trace.append(dict(turn=self.turn,actor=self.actor,kind=kind,**kwargs))

    def alive(self):return all(p.hp>0 for p in self.players)

    def draw(self,side,source='normal'):
        p=self.players[side];s=self.stats[side];bonus=source=='bonus'
        if bonus and not self.config.bonus_draw:return
        if not p.deck:
            p.fatigue+=1;actual=min(max(0,p.hp),p.fatigue);p.hp-=p.fatigue
            s['fatigue_damage']+=actual;self.event('fatigue',side=side,damage=actual);return
        h=replace(p.deck.pop(0),source=source);s['draws']+=1;s['bonus_draws']+=int(bonus)
        s['drawn_ids'].append(h.cid)
        burn=len(p.hand)>=self.config.hand_cap
        if burn:s['burned']+=1;s['bonus_burned']+=int(bonus)
        else:p.hand.append(h)
        self.event('draw',side=side,card=h.cid,uid=h.uid,source=source,burned=burn)

    def heal(self,side,amount):
        p=self.players[side];actual=min(30-p.hp,amount) if self.config.healing and self.config.hero_healing[side] else 0
        p.hp+=actual;self.stats[side]['healed']+=actual
        self.event('heal',side=side,actual=actual)

    def view(self,side):
        p=self.players[side];e=self.players[1-side]
        return View(Board(p.field,e.field,p.hp,e.hp),tuple(p.hand),p.cash,self.turn,side,
                    self.config.hand_cap,self.config.slots,self.souls[side],self.config.healing and self.config.hero_healing[side],self.config.knight_damage,len(p.deck),p.fatigue)

    def apply_attack(self,side,a,target):
        v=self.view(side);before=v.board
        after,details=attack(before,a,target,self.config)
        actor=next(u for u in before.own if u.uid==a)
        if target is not None:
            victim=next(u for u in before.foe if u.uid==target)
            if details['killed'] and CARDS[actor.cid]['cost']>=7 and CARDS[victim.cid]['cost']<=3:
                self.stats[1-side]['small_killed_by_big']+=1
            if details['lost'] and CARDS[victim.cid]['cost']>=7 and CARDS[actor.cid]['cost']<=3:
                self.stats[side]['small_killed_by_big']+=1
        self.players[side].field=after.own;self.players[side].hp=after.hp
        self.players[1-side].field=after.foe;self.players[1-side].hp=after.foe_hp
        self.stats[side]['damage']+=details.get('hero_damage',0)
        self.stats[side]['monster_healed']+=details['monster_heal']
        self.event('attack',side=side,**details)

    def deploy(self,side,uid):
        p=self.players[side];e=self.players[1-side];s=self.stats[side]
        held=next(h for h in p.hand if h.uid==uid);c=CARDS[held.cid]
        if c['cost']>p.cash or (held.cid!=91 and len(p.field)>=self.config.slots):raise ValueError('Illegal deployment')
        p.hand.remove(held);p.cash-=c['cost'];s['spent']+=c['cost'];s['played']+=1
        s['bonus_played']+=int(held.source=='bonus')
        if s['first_play'] is None:s['first_play']=self.turn
        if c['card_type']=='monster':
            p.field=p.field+(unit(held),)
            s['small_deployed']+=int(c['cost']<=3)
            if c['cost']>=7 and self.stats[1-side]['big_reply'] is None:
                self.stats[1-side]['big_reply']=dict(turn=self.turn,opponent_hp=p.hp,
                    small_field=sum(CARDS[u.cid]['cost']<=3 for u in e.field),
                    pressure_below_half=p.hp>15,visible_attack=sum(u.a for u in e.field))
        self.event('play',side=side,card=held.cid,uid=uid,cost=c['cost'],source=held.source)
        if held.cid==91:
            self.heal(side,3);self.draw(side,'bonus')
        elif held.cid==243:self.draw(side,'bonus')
        elif held.cid==44:
            # "up to 2": causal policy chooses only draws which fit after play.
            for _ in range(min(2,self.config.hand_cap-len(p.hand),len(p.deck))):
                if not self.alive():break
                self.draw(side,'bonus')
        elif held.cid==21:
            e.field=tuple(hurt(u,1)[0] for u in e.field)
            e.field=tuple(u for u in e.field if u.h>0)
            amount=min(max(0,e.hp),3);e.hp-=3;s['damage']+=amount
            self.event('magic_damage',side=side,hero_damage=amount)
        return c['cost']

    def full_slot_candidate(self,side):
        v=self.view(side)
        if len(v.board.own)<self.config.slots:return False
        # Current legal monster utility if one slot existed, before seeing result.
        test=replace(v,slots=self.config.slots+1)
        return any(score>0 and next(h.cid for h in v.hand if h.uid==uid)!=91
                   for score,uid in deployment_scores(test,'balanced'))

    def soul_end(self,side):
        p=self.players[side]
        if self.souls[side]=='KINDNESS' and self.turn>=3:
            self.heal(side,1)
            injured=any(u.h<u.max_h for u in p.field)
            healed=sum(min(1,u.max_h-u.h) for u in p.field) if self.config.healing else 0
            if self.config.healing:p.field=tuple(replace(u,h=min(u.max_h,u.h+1)) for u in p.field)
            self.stats[side]['monster_healed']+=healed
            if not injured and p.field:
                u=p.field[-1];p.field=p.field[:-1]+(replace(u,h=u.h+1,max_h=u.max_h+1),)

    def rod_end(self,side):
        for u in self.players[side].field:
            if u.cid==225 and self.alive():self.draw(side,'bonus')

    def take_turn(self,side,turn):
        self.turn=turn;self.actor=side;p=self.players[side];s=self.stats[side]
        p.cash+=min(turn,10)+int(side==1 and turn in (1,3,5,7,9))
        p.field=tuple(replace(u,ready=True,face_allowed=True) for u in p.field)
        self.event('start',side=side,hp=p.hp,cash=p.cash,hand=[h.cid for h in p.hand],field=[asdict(u) for u in p.field])
        if turn>1 or self.config.first_turn_draw:
            for _ in range(1+self.config.extra_natural_draw):
                if not self.alive():break
                self.draw(side)
        if turn==1:
            op=[h for h in p.hand if h.cid!=91 and CARDS[h.cid]['cost']<=p.cash]
            s['first_turn_no_opener']=not op
            opener_ids={h.uid for h in op}
        paid=0;blocked=False;withheld=False;steps=0
        while self.alive():
            steps+=1
            if steps>45:raise RuntimeError('Turn policy guard exceeded')
            blocked=blocked or self.full_slot_candidate(side)
            if self.config.public_tactics:
                from tactical import precombat_choice
                early=precombat_choice(self.view(side),self.policies[side],self.config)
                if early is not None:
                    paid+=self.deploy(side,early)
                    continue
            plan,_=choose_combat(self.view(side),self.policies[side],self.config)
            if plan:
                for a,target in plan:
                    if self.alive():self.apply_attack(side,a,target)
                continue
            v=self.view(side)
            uid=choose_deployment(v,self.policies[side])
            if self.policies[side]=='reserve_slot' and len(p.field)==self.config.slots-1:
                base_uid=choose_deployment(v,'balanced')
                withheld=withheld or (uid!=base_uid and base_uid is not None)
            if uid is None:break
            paid+=self.deploy(side,uid)
        if turn==1:
            s['first_turn_available_but_no_play']=bool(opener_ids) and opener_ids <= {h.uid for h in p.hand}
            s['first_turn_no_play']=s['played']==0
        s['reserve_withheld_turns']+=int(withheld)
        s['slot_blocked_turns']+=int(blocked)
        s['slot_missed']+=int(self.alive() and self.full_slot_candidate(side))
        s['empty_hand_turns']+=int(not p.hand)
        if self.alive():
            order=(self.rod_end,self.soul_end) if self.config.end_order=='draw_then_soul' else (self.soul_end,self.rod_end)
            for action in order:
                if self.alive():action(side)
        if self.alive() and self.souls[side]=='INTEGRITY' and turn>1 and paid>p.previous_spent:p.cash+=1
        p.previous_spent=paid
        self.event('end',side=side,hp=p.hp,cash=p.cash,hand=len(p.hand),slots=len(p.field))
        self.snapshots.append(dict(turn=turn,actor=side,players=[dict(hp=x.hp,cash=x.cash,hand=len(x.hand),deck=len(x.deck),slots=len(x.field),attack=sum(u.a for u in x.field)) for x in self.players]))

    def run(self):
        for turn in range(1,self.config.horizon+1):
            for side in (0,1):
                if not self.alive():break
                self.take_turn(side,turn)
            if not self.alive():break
        p0,p1=self.players
        # Shared time: after both players' nth turn, unless death ended play.
        result=[]
        for side,p in enumerate(self.players):
            foe=self.players[1-side]
            result.append(dict(**self.stats[side],hp=max(0,p.hp),opponent_hp=max(0,foe.hp),
                dead=p.hp<=0,killed=foe.hp<=0,pressure_15=foe.hp<=15,
                pressure_10=foe.hp<=10,cash=p.cash,hand=len(p.hand),field=len(p.field),
                field_attack=sum(u.a for u in p.field),field_value=sum(map(body_value,p.field)),
                deck_remaining=len(p.deck),fatigue=p.fatigue,
                stalled_pressure=foe.hp>15 and sum(u.a for u in p.field)<foe.hp,
                small_countered_insufficient=self.stats[side]['small_killed_by_big']>0 and foe.hp>15,
                survived_15=p.hp>=15 and foe.hp>0))
        return dict(version=VERSION,ended_own_turn=self.turn,ended_actor=self.actor,players=result,
                    snapshots=self.snapshots,trace=self.trace if self.keep_trace else None)
