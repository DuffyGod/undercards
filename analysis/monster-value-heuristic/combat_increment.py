"""One response window and one next-turn attack; no complete-match simulator.

Counterfactuals preserve identical Magic-adjusted bodies. Haste permits one
extra current monster attack; both get one next-turn attack if still alive.
Keywords change legal actions/damage handling, not a flat Gold bonus.
"""
import copy
import math

import score_cards as prices

VERSION = 'paired-response-window-0.2.0'
RESPONSE_WEIGHTS = {
    'aggro': {'none':.15, 'enemy_face':.45, 'enemy_contact':.20, 'chip':.15, 'silence':.05},
    'control': {'none':.20, 'enemy_face':.10, 'enemy_contact':.25, 'chip':.25, 'silence':.20},
    'combo': {'none':.60, 'enemy_face':.10, 'enemy_contact':.10, 'chip':.10, 'silence':.10},
    'midrange': {'none':.20, 'enemy_face':.25, 'enemy_contact':.30, 'chip':.15, 'silence':.10},
}
HP_WEIGHTS = {'aggro':.40,'control':.25,'combo':.20,'midrange':.30}
CASH_WEIGHT = .50


def state(attack, health, enemy_bodies, statuses, enemy_gold, own_player_hp=30, enemy_player_hp=30):
    actor = dict(attack=attack,health=health,dodge=statuses.get('dodge',0),
                 armor=statuses.get('armor',False),taunt=statuses.get('taunt',False))
    enemies = [dict(t,id=i) for i,t in enumerate(enemy_bodies)]
    return dict(actor=actor,enemies=enemies,hp_delta=0.,enemy_hp_delta=0.,
                own_player_hp=own_player_hp,enemy_player_hp=enemy_player_hp,enemy_gold=enemy_gold,
                own_attacks=0,log=[])


def hurt(unit, amount):
    if amount <= 0 or unit['health'] <= 0:
        return 0
    if unit.get('dodge',0)>0:
        unit['dodge']-=1
        return 0
    received=max(0,amount-int(unit.get('armor',False)))
    unit['health']-=received
    return received


def trade(s, index, attacker_is_actor=True):
    actor=s['actor']
    if actor['health']<=0 or terminal(s) or (attacker_is_actor and actor['attack']<=0):
        return False
    enemy=next((t for t in s['enemies'] if t['id']==index and t['health']>0),None)
    if enemy is None:
        return False
    if attacker_is_actor and index not in legal_own_targets(s):
        return False
    incoming,outgoing=enemy['attack'],actor['attack']
    hurt(actor,incoming)
    hurt(enemy,outgoing)
    if attacker_is_actor:
        s['own_attacks']+=1
    s['log'].append(dict(event='own_attack' if attacker_is_actor else 'enemy_attack',target=index))
    return True


def legal_own_targets(s):
    if terminal(s) or s['actor']['health']<=0 or s['actor']['attack']<=0:
        return []
    alive=[t for t in s['enemies'] if t['health']>0]
    taunts=[t for t in alive if t.get('taunt')]
    return [t['id'] for t in taunts or alive]


def utility_components(s,reference,role):
    p=prices.role_parameters(role)
    bv=lambda t:prices.body_value(t['attack'],max(0,t['health']),reference,p)
    return dict(remaining_actor_body=bv(s['actor']),
                remaining_enemy_bodies=-sum(bv(t) for t in s['enemies']),
                own_player_hp=HP_WEIGHTS[role]*s['hp_delta'],
                enemy_player_hp=-p['face_damage_value']*s['enemy_hp_delta'],
                opponent_cash_utility=-CASH_WEIGHT*s['enemy_gold'])


def utility(s,reference,role):
    return sum(utility_components(s,reference,role).values())


def terminal(s):
    return s['own_player_hp']<=0 or s['enemy_player_hp']<=0


def reply(s,event):
    if terminal(s):
        return
    actor=s['actor']
    alive=[t for t in s['enemies'] if t['health']>0 and t['attack']>0]
    if event in ('enemy_face','enemy_contact') and alive:
        # Shared declared rule: strongest existing attacker, tie by stable slot.
        attacker=max(alive,key=lambda t:(t['attack'],-t['id']))
        if actor['health']>0 and (event=='enemy_contact' or actor.get('taunt')):
            trade(s,attacker['id'],False)
        else:
            damage=min(s['own_player_hp'],attacker['attack'])
            s['hp_delta']-=damage
            s['own_player_hp']-=damage
            s['log'].append(dict(event='enemy_face',damage=damage))
    elif event=='chip' and actor['health']>0 and s['enemy_gold']>=2:
        s['enemy_gold']-=2
        hurt(actor,2)
        s['log'].append(dict(event='synthetic_paid_chip',cost=2))
    elif event=='silence' and actor['health']>0 and s['enemy_gold']>=3:
        s['enemy_gold']-=3
        actor['dodge']=0
        actor['armor']=False
        actor['taunt']=False
        s['log'].append(dict(event='synthetic_paid_keyword_silence',cost=3))
    # Unavailable events do nothing; never conjure money or new response bodies.


def later_attack(s,reference,role):
    if terminal(s) or s['actor']['health']<=0 or s['actor']['attack']<=0:
        return s
    options=[copy.deepcopy(s)]
    for target_id in legal_own_targets(s):
        child=copy.deepcopy(s)
        if trade(child,target_id): options.append(child)
    if not any(t.get('taunt') and t['health']>0 for t in s['enemies']):
        child=copy.deepcopy(s)
        damage=min(child['enemy_player_hp'],child['actor']['attack'])
        child['enemy_player_hp']-=damage
        child['enemy_hp_delta']-=damage
        child['own_attacks']+=1
        child['log'].append(dict(event='own_face',damage=damage))
        options.append(child)
    # Decision occurs after observing the response, not before hidden events.
    return max(options,key=lambda x:utility(x,reference,role))


def evaluate_plan(initial,plan,event,reference,role,one_exchange=False):
    s=copy.deepcopy(initial)
    if plan!='delay': trade(s,plan)
    reply(s,event)
    if plan=='delay' or not one_exchange: s=later_attack(s,reference,role)
    assert s['own_attacks']<=(1 if one_exchange or plan=='delay' else 2)
    return dict(utility=utility(s,reference,role),components=utility_components(s,reference,role),state=s,terminal=terminal(s))


def optimal_declared_plan(initial,haste,weights,reference,role,one_exchange=False):
    plans=['delay']+legal_own_targets(initial) if haste else ['delay']
    choices=[]
    for plan in plans:
        outcomes={event:evaluate_plan(initial,plan,event,reference,role,one_exchange) for event in weights}
        expected=sum(weights[event]*outcomes[event]['utility'] for event in weights)
        choices.append(dict(plan=plan,expected=expected,outcomes=outcomes))
    best=max(choices,key=lambda x:x['expected'])
    best['terminal_candidate_present']=any(o['terminal'] and weights[event]>0 for p in choices for event,o in p['outcomes'].items())
    return best


def premium(attack,health,enemy_bodies,statuses,enemy_gold,reference,role,weights=None,
            own_player_hp=30,enemy_player_hp=30,one_exchange=False):
    weights=RESPONSE_WEIGHTS[role] if weights is None else weights
    if not weights or not set(weights)<=set(RESPONSE_WEIGHTS[role]):
        raise ValueError('Unknown or empty response events')
    if any(type(v) not in (float,int) or not math.isfinite(v) or v<0 for v in weights.values()) or abs(sum(weights.values())-1)>1e-10:
        raise ValueError('Response weights must be nonnegative and sum to one')
    if not set(statuses)<= {'haste','dodge','armor','taunt'} or any(not set(t)<= {'attack','health','id','dodge','armor','taunt'} for t in enemy_bodies):
        raise ValueError('Unsupported status: do not silently approximate spell/target immunity')
    for unit in [statuses]+enemy_bodies:
        if any(type(unit[k]) is not bool for k in ('haste','armor','taunt') if k in unit):
            raise ValueError('Keyword flags must be booleans')
        if 'dodge' in unit and (type(unit['dodge']) is not int or unit['dodge']<0):
            raise ValueError('Dodge charges must be nonnegative integers')
    numeric=[attack,health,enemy_gold,own_player_hp,enemy_player_hp]+[t[k] for t in enemy_bodies for k in ('attack','health')]
    if any(type(x) not in (float,int) or not math.isfinite(x) for x in numeric) or attack<0 or enemy_gold<0 or any(t['attack']<0 for t in enemy_bodies):
        raise ValueError('Body/Gold/HP inputs must be finite with nonnegative attacks and Gold')
    ordinary=state(attack,health,enemy_bodies,{},enemy_gold,own_player_hp,enemy_player_hp)
    bundled=state(attack,health,enemy_bodies,statuses,enemy_gold,own_player_hp,enemy_player_hp)
    normal=optimal_declared_plan(ordinary,False,weights,reference,role,one_exchange)
    special=optimal_declared_plan(bundled,statuses.get('haste',False),weights,reference,role,one_exchange)
    has_terminal=any(p['terminal_candidate_present'] for p in (normal,special))
    deltas={key:sum(weights[event]*(special['outcomes'][event]['components'][key]-normal['outcomes'][event]['components'][key]) for event in weights)
            for key in normal['outcomes'][next(iter(weights))]['components']}
    return dict(premium_model_gold=None if has_terminal else special['expected']-normal['expected'],
                component_deltas=deltas,
                opponent_cash_note='opponent resource utility only; no cash is received by our player',
                ordinary=normal,keyword_bundle=special,response_weights=weights,
                terminal_requires_separate_outcome_evaluation=has_terminal,
                scope='paired one-response resource window; Magic preserved; no full opponent deck or pricing terminal wins',
                one_exchange=one_exchange,normative_parameters=dict(hp_weight=HP_WEIGHTS[role],cash_weight=CASH_WEIGHT))
