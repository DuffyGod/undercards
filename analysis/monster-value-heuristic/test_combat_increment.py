import unittest
import combat_increment as c
import score_cards as b


class FirstContactTests(unittest.TestCase):
    def setUp(self):
        self.reference,_=b.make_reference(b.load_cards())

    def test_advancing_same_exchange_without_response_has_no_resource_bonus(self):
        x=c.premium(4,5,[{'attack':3,'health':3}],{'haste':True},0,self.reference,'aggro',{'none':1},one_exchange=True)
        self.assertAlmostEqual(x['premium_model_gold'],0)
        self.assertEqual(x['keyword_bundle']['outcomes']['none']['state']['own_attacks'],1)

    def test_advance_blocks_one_face_attack_not_an_extra_full_kill_award(self):
        x=c.premium(4,5,[{'attack':3,'health':3}],{'haste':True},0,self.reference,'aggro',{'enemy_face':1},one_exchange=True)
        self.assertAlmostEqual(x['premium_model_gold'],3*c.HP_WEIGHTS['aggro'])
        self.assertEqual(x['keyword_bundle']['plan'],0)

    def test_dodge_consumed_by_first_instance_not_reused_for_later_chip(self):
        s=c.state(4,5,[{'attack':6,'health':3}],{'dodge':1},2)
        self.assertTrue(c.trade(s,0))
        x=c.premium(4,5,[{'attack':0,'health':10,'taunt':True},{'attack':3,'health':3}],
                    {'haste':True},0,self.reference,'aggro',{'enemy_face':1})
        self.assertIn(x['keyword_bundle']['plan'], ['delay',0])
        self.assertEqual(s['actor']['dodge'],0)
        self.assertEqual(s['actor']['health'],5)
        c.reply(s,'chip')
        self.assertEqual(s['actor']['health'],3)
        self.assertEqual(s['enemy_gold'],0)

    def test_unaffordable_response_is_not_free(self):
        s=c.state(4,5,[],{'dodge':1},1)
        c.reply(s,'chip')
        self.assertEqual(s['actor']['health'],5)
        self.assertEqual(s['enemy_gold'],1)
        c.reply(s,'silence')
        self.assertEqual(s['actor']['dodge'],1)

    def test_taunt_changes_target_not_a_separate_bonus(self):
        s=c.state(4,5,[{'attack':3,'health':3}],{'taunt':True},0)
        c.reply(s,'enemy_face')
        self.assertEqual(s['hp_delta'],0)
        self.assertEqual(s['actor']['health'],2)
        self.assertLessEqual(s['enemies'][0]['health'],0)

    def test_early_plan_is_shared_across_unknown_responses(self):
        x=c.premium(4,5,[{'attack':3,'health':3},{'attack':5,'health':4}],{'haste':True,'dodge':1},3,self.reference,'control')
        self.assertIn(x['keyword_bundle']['plan'],['delay',0,1])
        for outcome in x['keyword_bundle']['outcomes'].values():
            self.assertLessEqual(outcome['state']['own_attacks'],2)
        self.assertGreaterEqual(x['premium_model_gold'],0)

    def test_enemy_taunt_blocks_illegal_haste_target(self):
        s=c.state(4,5,[{'attack':0,'health':10,'taunt':True},{'attack':3,'health':3}],{},0)
        self.assertFalse(c.trade(s,1))
        self.assertEqual(s['own_attacks'],0)
        self.assertTrue(c.trade(s,0))

    def test_invalid_response_or_out_of_scope_status_is_rejected(self):
        for weights in ({'typo':1},{'none':float('nan')},{}):
            with self.assertRaises(ValueError):
                c.premium(4,5,[],{},3,self.reference,'aggro',weights)
        for statuses in ({'transparency':True},{'darkspawn':True}):
            with self.assertRaises(ValueError):
                c.premium(4,5,[],statuses,3,self.reference,'aggro')

    def test_two_stage_haste_can_trade_twice_and_empty_board_cannot_haste_face(self):
        x=c.premium(2,5,[{'attack':1,'health':1},{'attack':1,'health':1}],{'haste':True},0,self.reference,'aggro',{'none':1})
        special=x['keyword_bundle']['outcomes']['none']['state']
        self.assertEqual(special['own_attacks'],2)
        self.assertTrue(all(t['health']<=0 for t in special['enemies']))
        self.assertGreater(x['premium_model_gold'],0)
        empty=c.premium(2,5,[],{'haste':True},0,self.reference,'aggro',{'none':1})
        self.assertAlmostEqual(empty['premium_model_gold'],0)
        self.assertEqual(empty['keyword_bundle']['plan'],'delay')

    def test_next_turn_face_obeys_taunt_zero_attack_and_terminal_stops(self):
        s=c.state(0,5,[],{},0)
        self.assertEqual(c.later_attack(s,self.reference,'aggro')['own_attacks'],0)
        s=c.state(4,5,[{'attack':0,'health':10,'taunt':True}],{},0)
        result=c.later_attack(s,self.reference,'aggro')
        self.assertFalse(any(row['event']=='own_face' for row in result['log']))
        x=c.premium(4,5,[{'attack':3,'health':3}],{},0,self.reference,'aggro',{'enemy_face':1},own_player_hp=2)
        self.assertIsNone(x['premium_model_gold'])
        self.assertEqual(x['ordinary']['outcomes']['enemy_face']['state']['own_attacks'],0)

    def test_invalid_status_values_cannot_create_free_keyword(self):
        for statuses in ({'haste':'false'},{'dodge':.1},{'dodge':True}):
            with self.assertRaises(ValueError):
                c.premium(4,5,[],statuses,3,self.reference,'aggro')

    def test_zero_attack_enemy_cannot_force_a_free_retaliation(self):
        s=c.state(3,3,[{'attack':0,'health':2}],{'taunt':True},0)
        c.reply(s,'enemy_face')
        self.assertEqual(s['enemies'][0]['health'],2)
        self.assertFalse(s['log'])
        self.assertTrue(c.trade(s,0))


if __name__=='__main__': unittest.main()
