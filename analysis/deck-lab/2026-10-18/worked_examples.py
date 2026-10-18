"""Three explicitly audited two-source lines, plus a bounded face clock.

Not a general sequencing solver: the first source has no turn-end effects,
and none of these second sources modifies the first source's body.
"""
from pathlib import Path
import hashlib
import json
import deck_metrics as dm
import immediate_exchange as ie
HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def sequence(cards,first,second,hand,cash,second_plan,deck_name):
    assert first in [20,984] and second in [436,984,951]
    one=next(p for p in ie.exchange_options(first,ie.target_body(6,7),hand_before=hand,cash=cash,cards=cards) if p['plan']=='hold_attack')
    assert one['enemy'] is not None and one['hero_damage']==0
    two=next(p for p in ie.exchange_options(second,one['enemy'],hand_before=one['hand_after'],cash=one['cash_after'],cards=cards) if p['plan']==second_plan)
    assert one['payable'] and two['payable'] and len(one['own'])+len(two['own'])<=4
    deck=json.loads((HERE/(deck_name+'.json')).read_text(encoding='utf8'))
    return {'initial_enemy':[6,7,7],'initial_hand':hand,'initial_cash':cash,'first_id':first,'second_id':second,
        'first_line':one,'second_line':two,'surviving_own_bodies':one['own']+two['own'],
        'clears_this_turn':two['clears_this_turn'],'total_gold':one['required_gold']+two['required_gold'],
        'p_two_sources_in_uniform_original_hand':dm.pair_access_probability(deck['counts'],hand,first,second),
        'access_deck':deck_name,'extra_assumption':'No relevant Town Hall hand buff is cashed in this two-source line; all four own slots start empty.'}

def produce():
    cards=ie.source_cards()
    rows=[sequence(cards,984,436,5,9,'attack_enemy_once','A_early'),
        sequence(cards,20,984,7,10,'hold_attack','A_early'),
        sequence(cards,20,984,5,10,'hold_attack','A_early'),
        sequence(cards,20,951,5,9,'attack_enemy_once','A_quality_bookshelf')]
    assert rows[0]['clears_this_turn'] and [(x['attack'],x['health']) for x in rows[0]['surviving_own_bodies']]==[(3,4)]
    assert rows[1]['clears_this_turn'] and len(rows[1]['surviving_own_bodies'])==3
    assert not rows[2]['clears_this_turn']
    assert rows[3]['clears_this_turn'] and rows[3]['second_line']['hero_damage']==2
    clocks=[]
    for cid in [602,373,436,20,54,291,53,466]:
        card=cards[cid];attack=card['attack']-(1 if cid==53 else 0);skip=False;damage=[]
        for own_turn_after_play in range(1,4):
            amount=0 if skip else attack;damage.append(amount)
            skip=(cid==291 and amount>0)
            if cid==53:attack=max(0,attack-1)
        immediate=2 if cid==20 else 0
        assert cid!=20 or card['target']=='ALL'
        clocks.append({'id':cid,'name':card['name'],'cost':card['cost'],
            'immediate_face_magic':immediate,'next_three_own_action_turn_face_damage':damage,
            'total_face_damage':immediate+sum(damage)})
    result={'assumptions':['Exact worked lines, no opponent response, no preexisting own body or Soul/Power tick.',
        'First sources have no end trigger in these examples; no artificial end-of-turn effect is resolved between the two Plays.',
        'Face clock: enemy board stays empty, source never removed, no other plays/buffs/spell casts, three subsequent own action turns.',
        'All printed Haste is monster-only and cannot add immediate face attacks; NPC never attacks on entry in this empty-board clock.',
        'Clock is conditional pressure, not expected game damage; unused healing/draw and card survival are not priced at zero.'],
        'two_source_examples':rows,'unopposed_clocks':clocks,
        'source_sha256':{'snapshot':sha(ie.SOURCE),'producer':sha(Path(__file__)),'kernel':sha(HERE/'immediate_exchange.py')}}
    (HERE/'worked-examples.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    for r in rows:print(r['first_id'],r['second_id'],r['initial_hand'],r['total_gold'],r['clears_this_turn'],round(100*r['p_two_sources_in_uniform_original_hand'],2))
    for r in clocks:print(r['name'],r['total_face_damage'],r['next_three_own_action_turn_face_damage'])
if __name__=='__main__':produce()
