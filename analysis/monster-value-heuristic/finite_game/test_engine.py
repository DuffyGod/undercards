import json
from pathlib import Path
import unittest
from dataclasses import replace
from finite_game import Game, UnknownMechanic, compile_card

SNAPSHOT=Path(__file__).resolve().parents[3]/'skills/undercards/references/snapshot.json'
CARDS={c['id']:c for c in json.loads(SNAPSHOT.read_text())['cards']}


def step(game,state,kind,**match):
    for action,child in game.actions(state):
        if action[0]!=kind:continue
        if 'target' in match and action[-1]!=match['target']:continue
        if 'card' in match:
            hand=getattr(state,game.owner(state)+'_hand')
            if not any(h.key==action[1] and h.card_id==match['card'] for h in hand):continue
        return action,child
    raise AssertionError((kind,match))


class PhysicalEngineTests(unittest.TestCase):
    def game(self,**config):return Game(CARDS,config)

    def test_monster_or_you_literal_never_allows_enemy_hero(self):
        g=self.game(hand_ids=[351],gold_before_play=4,own_player_hp=15,
            enemy_bodies=[dict(card_id=15,attack=6,health=5,max_health=5)])
        casts=[(a,s) for a,s in g.actions(g.root()) if a[0]=='play']
        self.assertEqual({a[-1] for a,_ in casts},{'own:hero','enemy:observed:0'})
        self.assertTrue(all(s.own_gold==0 and not s.own_hand for _,s in casts))
        self.assertEqual(next(s for a,s in casts if a[-1]=='own:hero').own_hp,7)
        self.assertFalse(next(s for a,s in casts if a[-1]!='own:hero').enemy_board)

    def test_four_phase_horizon(self):
        g=self.game();s=g.root()
        for p in range(4):
            self.assertEqual(s.phase,p);s=step(g,s,'end')[1]
        self.assertTrue(g.finished(s));self.assertEqual(g.actions(s),[])

    def test_paid_native_cost(self):
        g=self.game(hand_ids=[15],gold_before_play=5)
        a,s=step(g,g.root(),'play',card=15)
        self.assertEqual(s.own_gold,0);self.assertEqual(len(s.own_hand),0)
        self.assertEqual((s.own_board[0].attack,s.own_board[0].health),(6,5))

    def test_unaffordable_no_play(self):
        g=self.game(hand_ids=[15],gold_before_play=4)
        self.assertEqual([a for a,_ in g.actions(g.root())],[('end',)])

    def test_declared_hand_cost_is_paid(self):
        g=self.game(hand_ids=[15],hand_costs=[3],gold_before_play=4)
        self.assertEqual(step(g,g.root(),'play')[1].own_gold,1)

    def test_late_payment_retains_balance(self):
        g=self.game(hand_ids=[15],gold_before_play=3,next_own_gold_income=2)
        s=step(g,g.root(),'end')[1];s=step(g,s,'end')[1]
        self.assertEqual(step(g,s,'play')[1].own_gold,0)

    def test_body_capacity(self):
        g=self.game(hand_ids=[15],gold_before_play=5,ally_bodies_before_play=[{'attack':1,'health':1}]*4)
        self.assertFalse(any(a[0]=='play' for a,_ in g.actions(g.root())))

    def test_fresh_plain_does_not_attack(self):
        g=self.game(hand_ids=[15],gold_before_play=5)
        s=step(g,g.root(),'play')[1]
        self.assertFalse(any(a[0]=='attack' for a,_ in g.actions(s)))

    def test_fresh_haste_only_monsters(self):
        g=self.game(hand_ids=[115],gold_before_play=1,enemy_bodies=[{'attack':0,'health':4}])
        s=step(g,g.root(),'play')[1]
        attacks=[a for a,_ in g.actions(s) if a[0]=='attack']
        self.assertEqual(len(attacks),1);self.assertNotEqual(attacks[0][-1],'enemy:hero')

    def test_fresh_charge_face(self):
        g=self.game(hand_ids=[9],gold_before_play=3)
        s=step(g,g.root(),'play')[1]
        self.assertEqual(step(g,s,'attack',target='enemy:hero')[1].enemy_hp,27)

    def test_next_turn_refreshes_plain(self):
        g=self.game(hand_ids=[15],gold_before_play=5)
        s=step(g,g.root(),'play')[1];s=step(g,s,'end')[1];s=step(g,s,'end')[1]
        self.assertEqual(step(g,s,'attack',target='enemy:hero')[1].enemy_hp,24)

    def test_attack_and_play_both_orders(self):
        g=self.game(hand_ids=[15],gold_before_play=5,ally_bodies_before_play=[{'attack':1,'health':2,'ready':True}])
        self.assertTrue(any(a[0]=='attack' for a,_ in g.actions(step(g,g.root(),'play')[1])))
        self.assertTrue(any(a[0]=='play' for a,_ in g.actions(step(g,g.root(),'attack')[1])))

    def test_simultaneous_retaliation(self):
        g=self.game(ally_bodies_before_play=[{'attack':3,'health':2}],enemy_bodies=[{'attack':2,'health':3}])
        s=step(g,g.root(),'attack',target='enemy:observed:0')[1]
        self.assertEqual((s.own_board,s.enemy_board),((),()))

    def test_taunt_blocks_face(self):
        g=self.game(ally_bodies_before_play=[{'attack':1,'health':4}],enemy_bodies=[{'attack':1,'health':4,'statuses':{'Taunt':1}},{'attack':1,'health':4}])
        self.assertEqual([a[-1] for a,_ in g.actions(g.root()) if a[0]=='attack'],['enemy:observed:0'])

    def test_armor_reduces_each_instance(self):
        g=self.game(ally_bodies_before_play=[{'attack':2,'health':4}],enemy_bodies=[{'attack':0,'health':4,'statuses':{'Armor':1}}])
        self.assertEqual(step(g,g.root(),'attack',target='enemy:observed:0')[1].enemy_board[0].health,3)

    def test_dodge_precedes_armor(self):
        g=self.game(ally_bodies_before_play=[{'attack':2,'health':4}],enemy_bodies=[{'attack':0,'health':4,'statuses':{'Armor':1,'Dodge':1}}])
        b=step(g,g.root(),'attack',target='enemy:observed:0')[1].enemy_board[0]
        self.assertEqual(b.health,4);self.assertFalse(b.status('Dodge'))

    def test_target_magic_pays_and_damages(self):
        g=self.game(hand_ids=[20],gold_before_play=4)
        s=step(g,g.root(),'play',target='enemy:hero')[1]
        self.assertEqual((s.own_gold,s.enemy_hp),(0,28))

    def test_silence_removes_taunt(self):
        g=self.game(hand_ids=[79],gold_before_play=1,enemy_bodies=[{'card_id':1,'health':4,'max_health':4}])
        s=step(g,g.root(),'play',target='enemy:observed:0')[1]
        self.assertTrue(s.enemy_board[0].silenced);self.assertEqual(s.enemy_board[0].statuses,())

    def test_known_draw_and_fatigue(self):
        g=self.game(next_natural_draw_count=2,own_deck_ids=[1])
        s=step(g,g.root(),'end')[1];s=step(g,s,'end')[1]
        self.assertEqual([h.card_id for h in s.own_hand],[1]);self.assertEqual(s.own_hp,29)

    def test_missing_draw_library_unknown(self):
        with self.assertRaises(UnknownMechanic):self.game(next_natural_draw_count=1)

    def test_seven_hand_draw_burns(self):
        g=self.game(hand_ids=[1]*7,next_natural_draw_count=1,own_deck_ids=[15])
        s=step(g,g.root(),'end')[1];s=step(g,s,'end')[1]
        self.assertEqual(len(s.own_hand),7);self.assertEqual(s.own_burned,1)

    def test_full_text_unknown_is_not_vanilla(self):
        with self.assertRaises(UnknownMechanic):self.game(hand_ids=[246])
        with self.assertRaises(UnknownMechanic):compile_card(dict(CARDS[15],effect_readable='Dust: Draw a card.'))

    def test_observed_completed_magic_is_not_replayed(self):
        g=self.game(enemy_bodies=[{'card_id':246,'ready':False}])
        s=step(g,g.root(),'end')[1]
        self.assertEqual((len(s.enemy_hand),s.enemy_board[0].attack),(0,3))

    def test_hidden_identity_and_physical_index_absent(self):
        a=self.game(opponent_hand_ids=[79]);b=self.game(opponent_hand_ids=[86])
        self.assertEqual(a.observation(a.root()),b.observation(b.root()))
        self.assertNotEqual(a.root(),b.root())

    def test_public_enemy_play_ignores_hidden_hand_index(self):
        a=self.game(opponent_hand_ids=[15,1],opponent_gold_before_response=5)
        b=self.game(opponent_hand_ids=[1,15],opponent_gold_before_response=5)
        sa=step(a,a.root(),'end')[1];sb=step(b,b.root(),'end')[1]
        aa,ca=step(a,sa,'play',card=15);ab,cb=step(b,sb,'play',card=15)
        self.assertNotEqual(aa,ab);self.assertEqual(a.action_observation(aa,sa,ca),b.action_observation(ab,sb,cb))
        self.assertEqual(ca.enemy_board[0].key,cb.enemy_board[0].key)

    def test_jerry_cost_defense_and_unknown_guard(self):
        g=self.game(hand_ids=[14],gold_before_play=5,enemy_bodies=[{'card_id':246,'printed_cost':4,'base_cost':4,'current_cost':4}])
        s=step(g,g.root(),'play')[1];s=step(g,s,'end')[1]
        s=step(g,s,'attack',target='own:deployed:0')[1]
        self.assertEqual(s.own_board[0].health,3)
        g=self.game(hand_ids=[14],gold_before_play=5,enemy_bodies=[{'attack':3,'health':6}])
        s=step(g,g.root(),'play')[1];s=step(g,s,'end')[1]
        with self.assertRaises(UnknownMechanic):g.actions(s)

    def test_worsening_delay_generated_once_and_paid(self):
        g=self.game(opponent_hand_ids=[86],opponent_gold_before_response=4,ally_bodies_before_play=[{'attack':0,'health':2},{'attack':0,'health':2}])
        s=step(g,g.root(),'end')[1];s=step(g,s,'play',target='own:observed:0')[1]
        self.assertEqual(len(s.enemy_hand),0)
        s=step(g,s,'end')[1]
        self.assertEqual((len(s.enemy_hand),s.enemy_hand[0].cost,s.enemy_hand[0].generated),(1,2,True))
        s=step(g,s,'end')[1];s=step(g,s,'play',target='own:observed:1')[1]
        self.assertEqual(s.enemy_gold,0)
        s=step(g,s,'end')[1];self.assertEqual(s.enemy_hand,())

    def test_goal_same_body_conjunction(self):
        g=self.game(ally_bodies_before_play=[{'attack':6,'health':1},{'attack':1,'health':6}])
        self.assertFalse(g.goal(g.root(),{'min_own_body_attack':5,'min_own_body_health':5}))
        self.assertEqual(g.hp(g.root()),30)

    def test_start_self_gain_and_heal(self):
        g=self.game(own_player_hp=10,ally_bodies_before_play=[{'card_id':307},{'card_id':6}])
        s=step(g,g.root(),'end')[1];s=step(g,s,'end')[1]
        self.assertEqual(s.own_hp,15);self.assertEqual(s.own_board[0].attack,CARDS[307]['attack']+1)

    def test_heal_fatigue_order_unknown(self):
        g=self.game(ally_bodies_before_play=[{'card_id':6}],next_natural_draw_count=1,own_deck_ids=[])
        s=step(g,g.root(),'end')[1]
        with self.assertRaises(UnknownMechanic):g.actions(s)

    def test_none_card_type_is_unknown(self):
        with self.assertRaises(UnknownMechanic):compile_card(dict(CARDS[15],card_type=None))

    def test_magic_cannot_choose_caster(self):
        g=self.game(hand_ids=[20],gold_before_play=4)
        self.assertFalse(any(a[0]=='play' and a[-1]=='own:deployed:0' for a,_ in g.actions(g.root())))

    def test_buff_cannot_choose_caster_and_empty_rule_unknown(self):
        g=self.game(hand_ids=[11],gold_before_play=4)
        with self.assertRaises(UnknownMechanic):g.actions(g.root())
        g=self.game(hand_ids=[11],gold_before_play=4,ally_bodies_before_play=[{'card_id':1}])
        plays=[(a,s) for a,s in g.actions(g.root()) if a[0]=='play']
        self.assertEqual(len(plays),1);self.assertEqual(plays[0][0][-1],'own:observed:0')

    def test_silence_modified_attack_unknown(self):
        g=self.game(hand_ids=[79],gold_before_play=1,enemy_bodies=[{'card_id':1,'attack':1,'max_health':4}])
        with self.assertRaises(UnknownMechanic):g.actions(g.root())

    def test_silence_modified_maximum_unknown(self):
        g=self.game(hand_ids=[79],gold_before_play=1,enemy_bodies=[{'card_id':1,'max_health':5}])
        with self.assertRaises(UnknownMechanic):g.actions(g.root())

    def test_root_silenced_does_not_restore_printed_taunt(self):
        g=self.game(enemy_bodies=[{'card_id':1,'silenced':True}])
        self.assertEqual(g.root().enemy_board[0].statuses,())

    def test_observed_cost_not_inferred_from_printed_identity(self):
        g=self.game(hand_ids=[14],gold_before_play=5,enemy_bodies=[{'card_id':246}])
        s=step(g,g.root(),'play')[1];s=step(g,s,'end')[1]
        with self.assertRaises(UnknownMechanic):g.actions(s)

    def test_cost_predicate_disagreement_unknown(self):
        g=self.game(hand_ids=[14],gold_before_play=5,enemy_bodies=[{'card_id':246,'printed_cost':4,'base_cost':4,'current_cost':5}])
        s=step(g,g.root(),'play')[1];s=step(g,s,'end')[1]
        with self.assertRaises(UnknownMechanic):g.actions(s)

    def test_unknown_observed_maximum_healing_rejected(self):
        g=self.game(hand_ids=[22],gold_before_play=3,enemy_bodies=[{'card_id':1,'health':2}])
        with self.assertRaises(UnknownMechanic):g.actions(g.root())

    def test_terminal_draw_stops_remaining_events(self):
        g=self.game(own_player_hp=1,next_natural_draw_count=3,own_deck_ids=[])
        s=step(g,g.root(),'end')[1];s=step(g,s,'end')[1]
        self.assertEqual((s.own_hp,s.own_fatigue),(0,1));self.assertTrue(g.finished(s))

    def test_silence_dt_is_immune(self):
        cards=dict(CARDS);cards[1000000]=dict(CARDS[1],id=1000000,rarity='DETERMINATION')
        g=Game(cards,dict(hand_ids=[79],gold_before_play=1,enemy_bodies=[{'card_id':1000000,'max_health':4}]))
        s=step(g,g.root(),'play',target='enemy:observed:0')[1]
        self.assertTrue(s.enemy_board[0].status('Taunt'));self.assertFalse(s.enemy_board[0].silenced)

    def test_generated_flags_validate_physical_length_and_type(self):
        with self.assertRaises(UnknownMechanic):self.game(hand_ids=[1],hand_generated=[])
        with self.assertRaises(UnknownMechanic):self.game(opponent_hand_ids=[86],opponent_hand_generated=[1])
        self.assertTrue(self.game(hand_ids=[1],hand_generated=[True]).root().own_hand[0].generated)

    def test_generated_worsening_does_not_copy(self):
        g=self.game(opponent_hand_ids=[86],opponent_hand_generated=[True],opponent_gold_before_response=2,
                    ally_bodies_before_play=[{'attack':0,'health':2}])
        s=step(g,g.root(),'end')[1];s=step(g,s,'play',target='own:observed:0')[1]
        s=step(g,s,'end')[1]
        self.assertEqual(s.enemy_hand,());self.assertEqual(s.enemy_generated,0)

    def test_enemy_generated_delay_does_not_leak_before_resolution(self):
        common=dict(opponent_hand_ids=[86],opponent_gold_before_response=2,
                    ally_bodies_before_play=[{'attack':0,'health':2}])
        a=self.game(**common,opponent_hand_generated=[False]);b=self.game(**common,opponent_hand_generated=[True])
        self.assertEqual(a.observation(a.root()),b.observation(b.root()))
        sa=step(a,a.root(),'end')[1];sb=step(b,b.root(),'end')[1]
        sa=step(a,sa,'play',target='own:observed:0')[1];sb=step(b,sb,'play',target='own:observed:0')[1]
        self.assertNotEqual(sa.pending_delays,sb.pending_delays)
        self.assertEqual(a.observation(sa),b.observation(sb))
        sa=step(a,sa,'end')[1];sb=step(b,sb,'end')[1]
        self.assertNotEqual(a.observation(sa),b.observation(sb))

    def test_unknown_configuration_fields_are_rejected(self):
        for key in ('max_plays','hp_certificate','own_fatigue_next','opponent_fatigue_next','misspelled_income'):
            with self.subTest(key=key),self.assertRaises(UnknownMechanic):self.game(**{key:1})

    def test_resources_require_exact_integers(self):
        for value in (1.5,True,'2'):
            for key in ('own_player_hp','gold_before_play','next_own_gold_income','next_natural_draw_count'):
                with self.subTest(key=key,value=value),self.assertRaises(UnknownMechanic):self.game(**{key:value})
            with self.subTest(value=value),self.assertRaises(UnknownMechanic):self.game(hand_ids=[1],hand_costs=[value])

    def test_observed_stats_and_phase_resources_require_exact_integers(self):
        for value in (1.5,True,'2'):
            for field in ('attack','health','max_health','current_cost'):
                with self.subTest(field=field,value=value),self.assertRaises(UnknownMechanic):
                    self.game(enemy_bodies=[{field:value}])
            with self.subTest(value=value),self.assertRaises(UnknownMechanic):self.game(income_by_phase={'2':value})

    def test_boolean_phase_key_not_coerced_to_one(self):
        with self.assertRaises(UnknownMechanic):self.game(draw_by_phase={True:1})


if __name__=='__main__':unittest.main()
