"""One-source, one-ordinary-enemy short exchange ledger; no old engine.

One Play, its Magic, optionally ONE Haste attack, then our turn end. Other
hand cards are never played except Bookshelf's explicitly priced new spell.
No Soul tick, opposing action, body price, Power generation, or game score.
"""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path


HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SOURCE=ROOT/'skills/undercards/references/snapshot.json'
CARD_IDS=(932,602,373,869,111,436,225,20,468,54,148,291,469,509,951,466,984,391,185,166,22,53,13,530)
HASTE=frozenset((373,869,111,436,54,291,469,509,951,530))
TARGETS={'icecap':(3,1,1),'vulkin':(4,4,4),'five':(5,5,5),'large':(6,7,7),
         'injured_large':(6,4,7),'huge':(8,8,8)}


def integer(value,label,minimum=0):
    if type(value) is not int or value<minimum:raise ValueError(label+' must be an integer >= '+str(minimum))
    return value


def source_cards():
    data=json.loads(SOURCE.read_text(encoding='utf-8'))
    return {c['id']:c for c in data['cards']}


def target_body(attack,health,max_health=None):
    integer(attack,'enemy ATK');integer(health,'enemy HP',1)
    maximum=health if max_health is None else integer(max_health,'enemy maximum HP',1)
    if maximum<health:raise ValueError('Enemy current HP cannot exceed maximum HP')
    return dict(attack=attack,health=health,max_health=maximum,statuses=[])


def _root(card,power):
    status=[]
    if card['id']==932:status.append('Taunt')
    if card['id']==869:status.append('Wanted')
    if card['id']==530:status.append('Dodge(1)')
    return dict(id=card['id'],name=card['name'],attack=card['attack']+power,
                health=card['health']+power,max_health=card['health']+power,
                statuses=status,attacked=False,can_attack_this_turn=card['id'] in HASTE,
                next_own_turn_can_attack=True,source='played_root',remaining_source_text=card['effect_readable'])


def _append_hand(state,card):
    state['hand_additions'].append(card)
    if state['hand_after']<7:state['hand_after']+=1
    else:state['hand_additions_not_held']+=1


def _draw(state,amount):
    state['draws_requested']+=amount
    held=min(amount,7-state['hand_after'])
    state['draws_to_hand']+=held
    state['draws_erased']+=amount-held
    state['hand_after']+=held


def _heal(state,amount,source,upper=None):
    state['healing'].append(dict(source=source,potential_min=amount,
        potential_max=amount if upper is None else upper))


def _kill_own(state,card):
    state['own']=[]
    cid=card['id']
    if cid==469:
        state['own']=[dict(id=470,name='Blockler O',attack=4,health=3,max_health=3,
            statuses=['Taunt'],attacked=False,can_attack_this_turn=False,
            next_own_turn_can_attack=True,source='Dust_summon')]
    elif cid==54:
        _append_hand(state,dict(id=54,name='Flowey copy',generated=True,cost=card['cost']-1,
            base_attack=card['attack']-1,base_health=card['health']-1))
        state['debts'].append('Returned Flowey is a new weaker 3G 3/3 base copy, not a recovered 4/4 board body.')
    elif cid==951:
        state['own_flame_slots']=1
        state['debts'].append(dict(kind='The Flame',owner='self',next_play_on_slot_damage=2,
            consumes_on_next_play=True,each_own_turn_end_damage=2))
    elif cid==869:state['opponent_gold_gained']+=1


def _base_state(card,enemy,hand_before,power):
    return dict(card_id=card['id'],name=card['name'],required_gold=card['cost'],
        own=[_root(card,power)],enemy=deepcopy(enemy),hand_after=hand_before-1,
        hand_additions=[],hand_additions_not_held=0,draws_requested=0,draws_to_hand=0,
        draws_erased=0,deck_additions=[],generated_spells_spent=0,
        conditional_hand_changes=[],healing=[],hero_damage=0,opponent_gold_gained=0,
        own_flame_slots=0,debts=[],notes=[])


def _magic(state,card,hand_after_play):
    cid=card['id'];enemy=state['enemy']
    if cid==932:
        enemy['attack']=max(0,enemy['attack']-1)
        enemy['health']-=1;enemy['max_health']-=1
    elif cid==20:enemy['health']-=2
    elif cid==984:
        exact=hand_after_play==enemy['health']
        enemy['health']-=hand_after_play
        if exact and hand_after_play>0:
            state['own'].append(dict(id=375,name='Green Clover',attack=2,health=3,max_health=3,
                statuses=[],attacked=False,can_attack_this_turn=False,
                next_own_turn_can_attack=True,source='Bullseye_summon'))
    elif cid==391:enemy['health']-=4 if enemy['health']<enemy['max_health'] else 1
    elif cid==166:enemy['health']-=1
    elif cid==13:enemy['attack']=max(0,enemy['attack']-1)
    elif cid==148:
        enemy['attack']=max(0,enemy['attack']-2)
        _append_hand(state,dict(kind='random_non_DT_card',cost=enemy['attack'],generated=True))
    elif cid==436:
        state['conditional_hand_changes'].append(dict(condition='A Haste monster is actually in the other hand cards',
            change='Give one such monster +1 ATK',resolved=False))
    elif cid==466:
        _append_hand(state,dict(kind='chosen_own_SOUL_spell',cost_modifier=-2,generated=True))
    elif cid==185:
        _draw(state,3)
        state['deck_additions'].append(dict(kind='random_cards',count=3,cost_modifier=-1,generated=True))
    elif cid==468:_heal(state,5,'Rudolph Magic')
    elif cid==22:_heal(state,4,'Shyren Magic targeting own hero')
    if enemy['health']<=0:state['enemy']=None


def _attack(state,card):
    actor=state['own'][0];enemy=state['enemy']
    if not actor['can_attack_this_turn'] or enemy is None:raise ValueError('No legal immediate monster attack')
    if card['id']==111:
        # A bare enemy may be injured, but has no removable numerical modifier.
        state['notes'].append('Memorial silences the ordinary target before combat; existing injury is retained.')
    actor['attacked']=True;actor['can_attack_this_turn']=False
    raw_damage=actor['attack'];effective_damage=min(raw_damage,enemy['health'])
    enemy['health']-=raw_damage
    if 'Dodge(1)' in actor['statuses']:actor['statuses'].remove('Dodge(1)')
    else:actor['health']-=enemy['attack']
    if card['id']==373 and raw_damage>0:
        _heal(state,effective_damage,'Worm monster-damage trigger',upper=raw_damage)
        if effective_damage!=raw_damage:
            state['notes'].append('Worm overkill DMG accounting unresolved: report effective-HP-loss to raw-damage healing interval.')
    if enemy['health']<=0:state['enemy']=None
    if actor['health']<=0:_kill_own(state,card)
    elif card['id']==291:
        actor['statuses'].append('Paralyze')
        actor['next_own_turn_can_attack']=False
    if card['id']==530 and state['enemy'] is None:
        state['notes'].append('Kill trigger has no remaining enemy to hit; no invented second target.')


def _end(state,card,missing_hp):
    roots=[u for u in state['own'] if u['source']=='played_root']
    if roots:
        actor=roots[0]
        if card['id']==869:
            state['debts'].append(dict(condition='This Wanted source later dies',opponent_gold_gain=1))
        elif card['id']==951:
            state['debts'].append(dict(condition='This source later dies',own_slot_enchantment='The Flame',
                next_play_on_slot_damage=2,each_own_turn_end_damage=2))
        if card['id']==225:_draw(state,1)
        elif card['id']==509 and not actor['attacked']:_heal(state,3,'Long Sink unspent-attack turn end')
        elif card['id']==53:
            actor['attack']=max(0,actor['attack']-1)
            state['debts'].append('Each later own turn end loses 1 ATK; dies when ATK becomes 0.')
            if actor['attack']==0:_kill_own(state,card)
    if state['own_flame_slots']:
        state['hero_damage']+=2
        state['notes'].append('The unconsumed own Flame deals 2 to own hero at this turn end and remains a burden.')
    lower=sum(x['potential_min'] for x in state['healing'])
    upper=sum(x['potential_max'] for x in state['healing'])
    state['healing_potential_interval']=[lower,upper]
    state['actual_healing_interval']=(None if missing_hp is None else [min(missing_hp,lower),min(missing_hp,upper)])
    state['clears_this_turn']=state['enemy'] is None


def exchange_options(card_id,enemy,*,hand_before=5,cash=None,power=0,hero_missing_hp=None,cards=None):
    """Return every supported short line, including the no-attack option.

    Need is declared met. At least3 library cards remain for Draw3; no prior
    hero terminal event. Power0 is normal; Power1 spends ONE known counter on
    the played source only, never its summoned child. No counter is generated.
    If cash is None only the printed price is available. Bookshelf's Justice
    alternatives remain listed as unpayable until total7/10G is provided.
    """
    if card_id not in CARD_IDS:raise ValueError('Candidate outside this narrow verified set')
    integer(hand_before,'hand before Play',1)
    if hand_before>7:raise ValueError('Hand limit is7')
    if power not in (0,1) or type(power) is not int:raise ValueError('Power probe is0 or one available counter')
    if hero_missing_hp is not None:integer(hero_missing_hp,'hero missing HP')
    enemy=target_body(enemy['attack'],enemy['health'],enemy.get('max_health'))
    cards=source_cards() if cards is None else cards;card=cards[card_id]
    cash=card['cost'] if cash is None else integer(cash,'available Gold')
    base=_base_state(card,enemy,hand_before,power)
    _magic(base,card,hand_before-1)
    plans=[('hold_attack',base)]
    if card_id in HASTE and base['enemy'] is not None:
        attacked=deepcopy(base);_attack(attacked,card);plans.append(('attack_enemy_once',attacked))
    if card_id==466:
        for spell_id in (96,100):
            spell=cards[spell_id];state=deepcopy(base)
            state['required_gold']+=max(0,spell['cost']-2)
            state['generated_spells_spent']=1;state['hand_after']-=1
            state['hand_additions'][0].update(id=spell_id,name=spell['name'],cost=max(0,spell['cost']-2))
            state['notes'].append('Justice spell selection; no Justice passive tick is included.')
            if spell_id==96:
                state['enemy']['health']-=4
                if state['enemy']['health']<=0:state['enemy']=None
            else:state['enemy']=None
            plans.append(('buy_and_cast_'+spell['name'],state))
    for name,state in plans:
        state['plan']=name;state['payable']=cash>=state['required_gold']
        state['cash_after']=cash-state['required_gold'] if state['payable'] else None
        _end(state,card,hero_missing_hp)
    return plans_as_records(plans)


def plans_as_records(plans):
    return [state for _,state in plans]


def clear_coverage(enemy,*,cash,hand_before=5,power=0,cards=None):
    cards=source_cards() if cards is None else cards
    return [cid for cid in CARD_IDS if any(p['payable'] and p['clears_this_turn']
        for p in exchange_options(cid,enemy,hand_before=hand_before,cash=cash,power=power,cards=cards))]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cash',type=int,default=6)
    parser.add_argument('--hand-before',type=int,choices=(3,5,7),default=5)
    parser.add_argument('--power',type=int,choices=(0,1),default=0)
    parser.add_argument('--summary',action='store_true')
    args=parser.parse_args();cards=source_cards()
    rows=[]
    for name,(a,h,m) in TARGETS.items():
        enemy=target_body(a,h,m)
        if args.summary:
            rows.append(dict(target=name,body=enemy,clear_card_ids=clear_coverage(enemy,cash=args.cash,
                hand_before=args.hand_before,power=args.power,cards=cards)))
        else:
            for cid in CARD_IDS:
                rows.append(dict(target=name,options=exchange_options(cid,enemy,cash=args.cash,
                    hand_before=args.hand_before,power=args.power,cards=cards)))
    print(json.dumps(dict(source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        own_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        context=dict(hand_before=args.hand_before,hand_after_play=args.hand_before-1,own_initial_monsters=0,empty_slots=4,
            cash=args.cash,power_counter_spent=args.power,Need='declared met',Soul_passive='excluded',
            draws='At least3 cards remain; no draw-trigger side effects modeled',
            healing='Potential interval; actual amount unknown without own missing HP'),rows=rows),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
