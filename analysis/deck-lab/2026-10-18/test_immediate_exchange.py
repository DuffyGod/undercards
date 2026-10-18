import unittest

from immediate_exchange import exchange_options,target_body


class ImmediateExchangeAnchors(unittest.TestCase):
    def line(self,cid,enemy,plan='hold_attack',**kwargs):
        return next(p for p in exchange_options(cid,enemy,**kwargs) if p['plan']==plan)

    def test_b_child_never_gets_a_second_immediate_attack(self):
        enemy=target_body(6,7)
        choices=exchange_options(469,enemy)
        attack=next(p for p in choices if p['plan']=='attack_enemy_once')
        self.assertFalse(attack['clears_this_turn'])
        self.assertEqual(attack['enemy']['health'],4)
        self.assertEqual([(u['attack'],u['health'],u['can_attack_this_turn']) for u in attack['own']],[(4,3,False)])
        self.assertEqual(len(choices),2)

    def test_archer_counts_four_after_play_and_exact_kill_child_is_two_three(self):
        result=self.line(984,target_body(4,4))
        self.assertTrue(result['clears_this_turn'])
        self.assertEqual([(u['attack'],u['health']) for u in result['own']],[(3,4),(2,3)])
        result=self.line(984,target_body(3,1))
        self.assertEqual(len(result['own']),1)

    def test_fire_flame_is_own_end_damage_and_future_burden(self):
        result=self.line(951,target_body(8,8),'attack_enemy_once')
        self.assertEqual(result['own'],[])
        self.assertEqual(result['hero_damage'],2)
        self.assertEqual(result['own_flame_slots'],1)
        self.assertEqual(result['debts'][0]['next_play_on_slot_damage'],2)

    def test_normal_npc_paralyzes_its_own_survivor(self):
        result=self.line(291,target_body(4,4),'attack_enemy_once')
        self.assertTrue(result['clears_this_turn'])
        self.assertEqual(result['own'][0]['health'],2)
        self.assertIn('Paralyze',result['own'][0]['statuses'])
        self.assertFalse(result['own'][0]['next_own_turn_can_attack'])

    def test_bookshelf_extra_spell_really_costs_seven_or_ten_total(self):
        enemy=target_body(6,4,7)
        seven=self.line(466,enemy,'buy_and_cast_Punishment',cash=7)
        ten=self.line(466,target_body(8,8),'buy_and_cast_Headshot',cash=7)
        self.assertEqual(seven['required_gold'],7)
        self.assertTrue(seven['payable']);self.assertTrue(seven['clears_this_turn'])
        self.assertEqual(seven['hand_after'],4)
        self.assertEqual(ten['required_gold'],10);self.assertFalse(ten['payable'])

    def test_ordinary_rock_pet_cannot_attack_and_long_sink_can_hold_for_heal(self):
        choices=exchange_options(602,target_body(3,1))
        self.assertEqual(len(choices),1)
        self.assertFalse(choices[0]['clears_this_turn'])
        hold=self.line(509,target_body(8,8),hero_missing_hp=2)
        attack=self.line(509,target_body(8,8),'attack_enemy_once',hero_missing_hp=2)
        self.assertEqual(hold['healing_potential_interval'],[3,3])
        self.assertEqual(hold['actual_healing_interval'],[2,2])
        self.assertEqual(attack['healing_potential_interval'],[0,0])

    def test_sheary_uses_existing_damage_not_damage_it_is_about_to_deal(self):
        injured=self.line(391,target_body(6,4,7))
        full=self.line(391,target_body(4,4))
        self.assertTrue(injured['clears_this_turn'])
        self.assertFalse(full['clears_this_turn'])
        self.assertEqual(full['enemy']['health'],3)

    def test_fifth_attack_point_changes_five_five_clear_without_fire_debt(self):
        fountain=self.line(951,target_body(5,5),'attack_enemy_once')
        sink=self.line(509,target_body(5,5),'attack_enemy_once')
        self.assertTrue(fountain['clears_this_turn'])
        self.assertEqual([(u['attack'],u['health']) for u in fountain['own']],[(5,1)])
        self.assertEqual(fountain['hero_damage'],0)
        self.assertFalse(sink['clears_this_turn'])
        self.assertEqual(sink['enemy']['health'],1)

    def test_archer_three_five_seven_hand_probes_use_h_minus_one(self):
        for hand,damage in ((3,2),(5,4),(7,6)):
            with self.subTest(hand=hand):
                result=self.line(984,target_body(8,8),hand_before=hand)
                self.assertEqual(result['enemy']['health'],8-damage)
        self.assertFalse(self.line(984,target_body(5,5),hand_before=5)['clears_this_turn'])
        self.assertTrue(self.line(984,target_body(5,5),hand_before=7)['clears_this_turn'])


if __name__=='__main__':unittest.main()
