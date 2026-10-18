"""Sparse analytical conversion operators for a COMMON demand distribution.

No turns, deck engine, hidden-hand search or whole-card completeness claim.
Every plan returns an endpoint lottery. One plan is fixed before its random
outcomes and possible reply. Future special abilities use disclosed reserves.
"""
from dataclasses import dataclass, replace
from functools import lru_cache
import math

from value_model import BodyScale


@dataclass(frozen=True)
class Unit:
    a: int
    h: int
    base_a: int
    base_h: int
    max_h: int
    dodge: int = 0
    armor: bool = False
    taunt: bool = False
    dust: str = ''
    trigger: str = ''
    root: bool = True


# Literal mechanism descriptors, never card-specific price parameters.
FEATURES={2:('plain',),4:('plain',),9:('charge',),11:('buff_ally',2),
    13:('debuff_all',1),15:('plain',),20:('damage_any',2),
    21:('haste_aoe_face',1,3),43:('dust_discount',),49:('hand_growth',1,1),
    168:('dodge',1),175:('armor',),187:('plain',),243:('draw',1),
    292:('self_damage',5),377:('dodge',1),469:('haste_dust_child',470),
    530:('haste_dodge_chain',1),602:('plain',),649:('count_damage_haste',1,3),
    984:('hand_damage_bull_child',375,2,3)}


def unit(card, *, a_delta=0,h_delta=0,root=True):
    a,h=card['attack']+a_delta,card['health']+h_delta
    return Unit(a,h,a,h,h,root=root)


def hurt(u,amount):
    if u.dodge and amount>0:return replace(u,dodge=u.dodge-1)
    return replace(u,h=u.h-max(0,amount-int(u.armor)))


def silence(u):
    if u.h<u.max_h and u.max_h!=u.base_h:
        raise ValueError('Injured HP-modifier reset is not a known rule')
    h=u.base_h if u.h==u.max_h else u.h
    return Unit(u.base_a,h,u.base_a,u.base_h,u.base_h,root=u.root)


def living(enemies):return tuple(e for e in enemies if e[1]>0)


def deaths(own,cards):
    out=[];discount=False
    for u in own:
        if u.h>0:out.append(u)
        elif u.dust=='child':
            child=unit(cards['470'],root=False)
            out.append(replace(child,taunt=True))
        elif u.dust=='discount':discount=True
    return tuple(out),discount


@lru_cache(maxsize=200000)
def chain_lottery(enemies):
    """Uniform random live target; repeat iff that single 1-DMG instance kills."""
    if not enemies:return ((1.,()),)
    outcomes={};n=len(enemies)
    for i,(a,h) in enumerate(enemies):
        new=list(enemies);new[i]=(a,h-1);new=living(new)
        branches=chain_lottery(new) if h==1 else ((1.,new),)
        for p,state in branches:outcomes[state]=outcomes.get(state,0)+p/n
    return tuple((p,state) for state,p in outcomes.items())


def deployment_plans(card,cards,enemies,hand,*,a_delta=0,h_delta=0):
    """Finite endpoint algebra, not a general card-text compiler.

    Enemy bodies are deliberately ordinary demand probes. Baseline own board
    is empty; extra friendly targets are outside this panel, not valued at0
    for a universal card rating. A plan can always decline its Haste attack.
    """
    f=FEATURES[card['id']];kind=f[0];u=unit(card,a_delta=a_delta,h_delta=h_delta)
    own=(u,);haste=False;face=0.;draw=0;states=[]
    if kind=='hand_growth':u=replace(u,a=u.a+hand*f[1],h=u.h+hand*f[2],max_h=u.max_h+hand*f[2]);own=(u,)
    elif kind=='self_damage':u=replace(u,h=u.h-f[1]);own=(u,)
    elif kind=='dodge':own=(replace(u,dodge=f[1]),)
    elif kind=='armor':own=(replace(u,armor=True),)
    elif kind=='charge':haste=True
    elif kind=='dust_discount':own=(replace(u,dust='discount'),)
    elif kind=='haste_dust_child':haste=True;own=(replace(u,dust='child'),)
    elif kind=='haste_dodge_chain':haste=True;own=(replace(u,dodge=f[1],trigger='chain'),)
    elif kind=='draw':draw=min(f[1],7-hand)
    elif kind=='debuff_all':enemies=tuple((max(0,a-f[1]),h) for a,h in enemies)
    elif kind=='buff_ally':pass # no pre-existing ally in these declared panels
    elif kind=='haste_aoe_face':haste=True;enemies=living(tuple((a,h-f[1]) for a,h in enemies));face=f[2]
    elif kind=='damage_any':
        states.append((own,enemies,float(f[1]),0,False,'magic_face'))
        for i,(a,h) in enumerate(enemies):
            e=list(enemies);e[i]=(a,h-f[1]);states.append((own,living(tuple(e)),0.,0,False,'magic_target_'+str(i)))
    elif kind=='count_damage_haste':
        n=len(enemies);haste=n*f[1]<=f[2]
        if not enemies:
            # Self-target amount0 is a declared harmless interpretation. It
            # has no attack target and does not affect the numerical endpoint.
            states.append((own,(),0.,0,False,'self_zero_no_enemy'))
        for i,(a,h) in enumerate(enemies):
            e=list(enemies);e[i]=(a,h-n*f[1]);states.append((own,living(tuple(e)),0.,0,False,'magic_target_'+str(i)))
    elif kind=='hand_damage_bull_child':
        own=(replace(u,trigger='bull'),)
        if not enemies:states.append((own,(),0.,0,False,'no_enemy_target'))
        for i,(a,h) in enumerate(enemies):
            e=list(enemies);e[i]=(a,h-hand)
            child=unit(cards[str(f[1])],root=False)
            child=replace(child,a=f[2],h=f[3],base_a=f[2],base_h=f[3],max_h=f[3])
            team=own+(child,) if hand==h and hand>0 else own
            states.append((team,living(tuple(e)),0.,0,False,'magic_target_'+str(i)))
    elif kind!='plain':raise ValueError('Unknown feature kind')
    if not states:states=[(own,enemies,face,draw,False,'deploy')]
    plans=[]
    for team,e,face,draw,discount,name in states:
        team,dead_discount=deaths(team,cards);discount=discount or dead_discount
        plans.append((name+':hold_attack',((1.,team,e,face,draw,discount),)))
        if not haste or not team:continue
        actor=team[0]
        if kind=='charge':plans.append((name+':face',((1.,team,e,face+actor.a,draw,discount),)))
        for i,(a,h) in enumerate(e):
            target_dead=actor.a>=h
            damaged=hurt(actor,a);newteam,newdiscount=deaths((damaged,)+team[1:],cards)
            newe=list(e);newe[i]=(a,h-actor.a);newe=living(tuple(newe))
            branches=chain_lottery(newe) if target_dead and actor.trigger=='chain' else ((1.,newe),)
            outcomes=tuple((p,newteam,newenemy,face,draw,discount or newdiscount) for p,newenemy in branches)
            plans.append((name+':attack_'+str(i),outcomes))
    return plans


class Prices:
    """One common scalar scale, plus explicitly uncalibrated continuation reserves."""
    def __init__(self,inputs,face_share=.2,threshold=.4,tail=.5,draw=.65,face=.25,stock=1.):
        self.scale=BodyScale(inputs['reference'],face_share,threshold)
        self.tail,self.draw,self.face,self.stock=tail,draw,face,stock
        ref=inputs['reference']
        self.challenge=tuple((r['attack'],r['health'],r['weight']) for r in ref)
        self.mean_attack=sum(a*w for a,h,w in self.challenge)
        self.one_damage=sum(w*(self.scale.value(a,h)-self.scale.value(a,max(0,h-1))) for a,h,w in self.challenge)
        self.one_hp_mass=sum(w for a,h,w in self.challenge if h==1)

    @lru_cache(maxsize=300000)
    def body(self,u,discount_value):
        f=self.scale.value(u.a,u.h)
        reserve=0.
        if u.dodge or u.armor:
            reserve+=sum(w*(self.scale.value(u.a,max(0,hurt(u,a).h))-
                           self.scale.value(u.a,max(0,u.h-a))) for a,h,w in self.challenge)
        if u.taunt:reserve+=self.face*self.mean_attack
        if u.dust=='child':reserve+=self.scale.value(4,3)+self.face*self.mean_attack
        elif u.dust=='discount':reserve+=discount_value
        if u.trigger=='bull':
            exact=sum(w for a,h,w in self.challenge if h==u.a and u.h>a)
            reserve+=exact*self.scale.value(2,3)
        elif u.trigger=='chain':
            kill=sum(w for a,h,w in self.challenge if h<=u.a and (u.dodge or u.h>max(0,a-int(u.armor))))
            reserve+=kill*self.one_damage*(1+self.one_hp_mass)
        return f+self.tail*reserve


@lru_cache(maxsize=None)
def discount_option(costs,cash,quality=1.):
    """One known future payment menu, reused under c and max(c-1,0).

    Future gross=cost+quality is an explicit net-quality prior. This is a
    payment sensitivity probe, not a claim about actual future card identities.
    """
    def best(discount):
        values=[0.]*(int(cash)+1)
        for cost in costs:
            paid=max(0,cost-discount);net=cost+quality-paid
            if paid>cash:continue
            old=values[:]
            for g in range(paid,int(cash)+1):values[g]=max(old[g],old[g-paid]+net)
        return values[-1]
    return best(1)-best(0)


def best_value(card,cards,enemy,hand,prices,response,reply_probability,discount_value,*,a_delta=0,h_delta=0,details=False):
    original=sum(prices.scale.value(*e) for e in enemy)
    def endpoint(team,e,face,draw,discount):
        return (prices.stock*(sum(prices.body(u,discount_value) for u in team)+original-
            sum(prices.scale.value(*x) for x in e))+face*prices.face+draw*prices.draw*prices.stock+
            (discount_value if discount else 0.))
    def replied(team,e,face,draw,discount):
        # Opponent observes the endpoint, may decline, or target any one live
        # unit. Response chance is a design opportunity, not mandatory waste.
        best=endpoint(team,e,face,draw,discount)
        roots=[i for i,u in enumerate(team) if u.root]
        # Source-resolved focal response. Avoid inventing Silence reset rules
        # for Archer's explicitly overwritten summoned Clover stats.
        eligible=roots if roots else list(range(len(team)))
        for i in eligible:
            u=team[i]
            if response=='silence':v=silence(u)
            elif response=='damage4':v=hurt(u,4)
            elif response=='damage2':v=hurt(u,2)
            elif response=='headshot':v=replace(silence(u),h=0)
            elif response=='none':continue
            else:raise ValueError('Unknown response panel')
            changed=list(team);changed[i]=v;changed,delta=deaths(tuple(changed),cards)
            best=min(best,endpoint(changed,e,face,draw,discount or delta))
        return best
    best=-math.inf;chosen=None;values={}
    for name,outcomes in deployment_plans(card,cards,enemy,hand,a_delta=a_delta,h_delta=h_delta):
        q=sum(p*((1-reply_probability)*endpoint(team,e,face,draw,d)+
            reply_probability*replied(team,e,face,draw,d)) for p,team,e,face,draw,d in outcomes)
        values[name]=q
        if q>best:best,chosen=q,name
    return (best,chosen,values) if details else (best,chosen)
