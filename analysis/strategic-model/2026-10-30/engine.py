"""New per-card body bridge and causal tactical policies over the frozen engine.

The October20 engine remains unchanged. Candidate identities replace declared
small-role slots, preserving their shuffled entity positions and opponent deck.
Only the named ordinary body is real; all other cards remain aggregate roles.
"""
from pathlib import Path
from dataclasses import dataclass,replace,asdict
import json,sys

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'2026-10-20'
sys.path.insert(0,str(BASE))
from model import (Config,Card,Unit,Policy,View,Game,income,decide as old_decide)
from tactics import choose

VERSION='body-bridge-tactics-0.1'

@dataclass(frozen=True)
class Body:
    name:str
    cost:int
    attack:int
    health:int
    card_id:int|None=None
    counterfactual:str=''


def bodies():
    cards=json.loads((HERE/'real-bodies.json').read_text())['cards']
    out={c['name']:Body(c['name'],c['cost'],c['attack'],c['health'],c['card_id']) for c in cards}
    out['role_2_2']=Body('role_2_2',2,2,2,counterfactual='Original synthetic small-role body; not a real card')
    out['Aaron_cost2']=replace(out['Aaron'],name='Aaron_cost2',cost=2,counterfactual='Unreal cheap Aaron: isolate payment/early access from body')
    out['Candy_cost2']=replace(out['Candy Dish'],name='Candy_cost2',cost=2,counterfactual='Unreal cheap Candy Dish: isolate one-G entry delay')
    out['Rock_health4']=replace(out['Rock Pet'],name='Rock_health4',health=4,counterfactual='Unreal 4HP Rock Pet: cross 3DMG packet threshold')
    return out


ROWS=(Policy('greedy_trade'),Policy('attack_frontier',combat='attack_frontier'),Policy('frontier_board',combat='frontier_board'),
      Policy('frontier_race',combat='frontier_race'),Policy('frontier_durable',combat='frontier_board',order='durable'),
      Policy('frontier_entry',combat='frontier_board',order='window'))
COLS=(Policy('trade_hold_two',response_threshold=2),Policy('face_hold_two',response_threshold=2,combat='face'),
      Policy('frontier_defender',combat='frontier_board'))


def body_for(card,cfg,candidate):
    if card.kind=='candidate':return candidate
    if card.kind in ('small','anchor'):
        return Body(card.kind,cfg.cost(card.kind),getattr(cfg,card.kind+'_attack'),getattr(cfg,card.kind+'_health'))
    return None


def decision(v,p,candidate):
    c=v.cfg;ready=[u for u in v.own if u.ready]
    response=next((h for h in v.hand if h.kind=='response' and v.cash>=c.response_cost),None)
    incoming=sum(u.a for u in v.enemy)
    if p.combat=='attack_frontier' and response and v.enemy:
        old=old_decide(replace(v,hand=tuple(h for h in v.hand if h.kind!='candidate')),p)
        if old[0]=='play' and old[1]==response.uid:return old
    if (p.combat.startswith('frontier') or p.combat=='attack_frontier') and (ready or (response and v.enemy)):
        # Sort by UID to match the engine's forced focus target tie-break.
        own=sorted(v.own,key=lambda u:u.uid);enemy=sorted(v.enemy,key=lambda u:u.uid)
        leaf,_=choose(tuple((u.a,u.h,u.ready) for u in own),tuple((u.a,u.h) for u in enemy),v.hp,v.enemy_hp,
            mode='race' if p.combat=='frontier_race' else 'board',
            response_kind=c.response_kind if response and p.combat!='attack_frontier' else '',packet=c.response_damage,
            end_heal=int(c.soul=='KINDNESS' and v.turn>=3))
        if leaf[-1]:
            action,i,j=leaf[-1][0]
            if action=='response':return ('play',response.uid,-1)
            return ('attack',own[i].uid,-1 if j==-1 else enemy[j].uid)
    elif ready or (response and v.enemy):
        # With ready bodies the original policy always returns attack/response;
        # when none are ready, check only its actual response decision.
        old=old_decide(replace(v,hand=tuple(h for h in v.hand if h.kind!='candidate')),p)
        if old[0]=='attack' or (old[0]=='play' and response and old[1]==response.uid):return old
    heal=next((h for h in v.hand if h.kind=='heal'),None)
    if heal and v.cash>=c.heal_cost and v.hp<=p.heal_at and 30-v.hp>=c.heal_amount:
        return ('play',heal.uid,-1)
    risk=v.enemy_response_unseen>0 and v.enemy_cash+income(v.enemy_turn+1,1-v.seat,c.soul)>=c.response_cost
    reserve=p.reserve_cards if risk else 0
    held=[(h,body_for(h,c,candidate)) for h in v.hand]
    held=[(h,b) for h,b in held if b is not None]
    if p.order=='window' and held and len(v.own)<c.slots:
        # A declared one-turn saving alternative, not perfect forecasting.
        # The desired identity is already in our hand; future draws are unseen.
        h,b=max(held,key=lambda z:(z[1].attack,z[1].health,-z[1].cost,-z[0].uid))
        if v.cash>=b.cost:return ('play',h.uid,-1)
        if v.cash+income(v.turn+1,v.seat,c.soul)>=b.cost and incoming<v.hp:
            return ('end',-1,-1)
    candidates=[]
    if len(v.own)<c.slots:
        for h,b in held:
            if v.cash<b.cost:continue
            if v.own and len(held)-1<reserve:continue
            if risk and v.own and v.cash-b.cost<p.reserve_gold:continue
            if risk and c.response_kind=='sweep' and sum(u.h<=c.response_damage for u in v.own)+int(b.health<=c.response_damage)>p.guard:continue
            candidates.append((h,b))
    if candidates:
        h,b=min(candidates,key=lambda z:((-z[1].health if p.order=='durable' else z[1].cost),z[0].uid))
        return ('play',h.uid,-1)
    draw=next((h for h in v.hand if h.kind=='draw'),None)
    if draw and v.cash>=c.draw_cost and v.deck_count>0 and len(v.hand)<=4 and len(held)<=reserve+1:
        return ('play',draw.uid,-1)
    return ('end',-1,-1)


class BridgeGame(Game):
    def __init__(self,structure,seed,cfg,policies,candidate,copies=3,trace=False):
        if not 0<=copies<=3:raise ValueError('Respect declared ordinary-copy cap3')
        self.candidate=candidate;self.copies=copies
        super().__init__(structure,seed,cfg,policies,trace)
        # Initial draws already happened. Replace matching original entity IDs
        # in both hand and deck, never resample/reorder based on a draw result.
        a=self.players[0]
        convert=lambda h:replace(h,kind='candidate') if h.uid<copies else h
        a.hand=[convert(h) for h in a.hand];a.deck=[convert(h) for h in a.deck]
        if self.trace is not None:
            for event in self.trace:
                if event['actor']==0 and event['action']=='draw' and event['card']['uid']<copies:
                    event['card']['kind']='candidate'
        self.candidate_drawn=sum(h.kind=='candidate' for h in a.hand)
        self.candidate_played=0;self.candidate_first_turn=0;self.candidate_wait=0
        self.candidate_burned=0;self.candidate_unfunded_turns=0;self.candidate_slot_blocked_turns=0

    def draw(self,actor):
        # During initial super().__init__, instrumentation is not initialized.
        candidate=actor==0 and self.players[actor].deck and self.players[actor].deck[0].kind=='candidate'
        burned=candidate and len(self.players[actor].hand)==self.cfg.hand_cap
        super().draw(actor)
        if candidate and hasattr(self,'candidate_drawn'):
            if burned:self.candidate_burned+=1
            else:self.candidate_drawn+=1

    def play(self,actor,uid):
        a=self.players[actor];h=next(h for h in a.hand if h.uid==uid)
        if h.kind!='candidate':return super().play(actor,uid)
        if actor!=0:raise ValueError('Candidate belongs only to A')
        b=self.candidate
        if a.cash<b.cost or len(a.units)>=self.cfg.slots:raise ValueError('Illegal candidate payment/slot')
        a.hand.remove(h);a.cash-=b.cost;a.spent+=b.cost;a.total_spent+=b.cost;a.played+=1
        a.units.append(Unit(uid,h.kind,b.attack,b.health,b.health))
        self.candidate_played+=1
        if not self.candidate_first_turn:self.candidate_first_turn=a.turn
        if a.first_effective_penalty_turn:
            a.post_penalty_uids.add(uid)
            if not a.rebuilt_deploy_turn:a.rebuilt_deploy_turn=a.turn
        self.event(actor,'play',card=asdict(h),body=asdict(b),cost=b.cost,cash_after=a.cash)

    def act_turn(self,actor):
        # Same income/draw/soul/termination rules as the frozen base engine.
        a,b=self.players[actor],self.players[1-actor];c=self.cfg
        a.turn+=1;a.spent=0;seat=c.seat if actor==0 else 1-c.seat
        grant=income(a.turn,seat,c.soul)
        a.cash+=grant;a.income+=grant;a.units=[replace(u,ready=True) for u in a.units]
        self.event(actor,'start',income=grant,cash=a.cash)
        if c.first_draw or a.turn>1:self.draw(actor)
        if a.hp<=0:return
        if actor==0 and any(h.kind=='candidate' for h in a.hand):
            self.candidate_wait+=1
            self.candidate_unfunded_turns+=a.cash<self.candidate.cost
            self.candidate_slot_blocked_turns+=len(a.units)==c.slots
        for _ in range(100):
            action,uid,target=decision(self.view(actor),self.policies[actor],self.candidate if actor==0 else None)
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
            if any(u.h<u.max_h for u in a.units):a.units=[replace(u,h=min(u.max_h,u.h+1)) for u in a.units]
            elif a.units:a.units[-1]=replace(a.units[-1],h=a.units[-1].h+1,max_h=a.units[-1].max_h+1)
        a.previous_spent=a.spent
        if a.cash<0 or len(a.hand)>c.hand_cap or len(a.units)>c.slots:raise ValueError('Physical resource violation')
        self.event(actor,'end',hp=a.hp,enemy_hp=b.hp,cash=a.cash,hand=[asdict(h) for h in a.hand],units=[asdict(u) for u in a.units])

    def run(self):
        r=super().run()
        r.update(candidate=asdict(self.candidate),copies=self.copies,candidate_drawn=self.candidate_drawn,
            candidate_played=self.candidate_played,candidate_first_turn=self.candidate_first_turn,
            candidate_wait=self.candidate_wait,candidate_burned=self.candidate_burned,
            candidate_unfunded_turns=self.candidate_unfunded_turns,candidate_slot_blocked_turns=self.candidate_slot_blocked_turns,
            candidate_held=sum(h.kind=='candidate' for h in self.players[0].hand))
        return r
