"""Targeted new counterexamples; no old simulation or historical tests rerun."""
import unittest
from build_tactics import main_routes
from resource_routes import build_routes
from tactic_core import F, quote, compare


class TacticalCounterexamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        a,_,_=main_routes();b,_,_=build_routes()
        cls.rs={r['id']:r for r in a+b}

    def r(self,cid,root,action):
        return self.rs[f'tactics/{cid}/{root}/{action}']

    def test_mantis_target_changes_actual_death_chain(self):
        good=self.r(964,'carousel_target','kill_0')
        bad=self.r(964,'carousel_target','kill_1')
        self.assertEqual(good['ledger']['enemy_after'],[])
        self.assertEqual(good['ledger']['own_after'],[dict(a=3,h=3)])
        self.assertEqual(len(good['features']['carousel_waves']),4)
        self.assertEqual([u['h'] for u in bad['ledger']['enemy_after']],[2,1,2])
        self.assertEqual([u['h'] for u in bad['ledger']['own_after']],[1,6])

    def test_pancakes_actual_healing_after_surviving_trade(self):
        a=self.r(868,'pancakes_order','trade_then_heal')
        b=self.r(868,'pancakes_order','heal_then_trade')
        self.assertEqual(a['ledger']['events']['hero_heal'],5)
        self.assertEqual(b['ledger']['events']['hero_heal'],0)
        self.assertAlmostEqual(compare(a,b,'test')['central_net_difference'],F(6,8)-F(6,3)+1.25)

    def test_setup_full_payment_and_ally_loox_growth(self):
        r=self.r(437,'agent_setup','loox_then_agent')
        self.assertEqual(r['ledger']['paid_gold'],8)
        self.assertEqual(r['inventory']['net_relative_cards'],-2)
        self.assertEqual([(u['a'],u['h']) for u in r['ledger']['own_after']],[(4,5),(2,2),(5,7)])
        self.assertEqual(r['ledger']['enemy_after'],[])

    def test_sheary_damaged_check_is_not_extra_four_after_initial_one(self):
        a=self.r(391,'sheary_order','loox_then_sheary')
        b=self.r(391,'sheary_order','sheary_then_loox')
        self.assertEqual(a['ledger']['enemy_after'],[])
        self.assertEqual(b['ledger']['enemy_after'][0]['h'],3)
        self.assertEqual(a['ledger']['paid_gold'],b['ledger']['paid_gold'])

    def test_searby_bullseye_not_cash_discount(self):
        a=self.r(852,'searby_order','loox_then_searby')
        b=self.r(852,'searby_order','searby_then_loox')
        self.assertEqual(a['inventory']['net_relative_cards'],-1)
        self.assertEqual(b['inventory']['net_relative_cards'],-2)
        self.assertNotIn('usable_gold',a['ledger']['events'])
        self.assertAlmostEqual(compare(a,b,'test')['central_net_difference'],1)

    def test_sadmobile_generated_then_played_card_not_retained(self):
        r=self.r(546,'sadmobile_previous_spend_7','draw_then_play_froggit')
        self.assertEqual(r['inventory']['net_relative_cards'],-1)
        self.assertEqual(r['ledger']['paid_gold'],6)
        self.assertEqual(len(r['ledger']['own_after']),2)

    def test_guard_order_realizes_gold_and_changes_funding(self):
        a=self.r(743,'guard_same_two_cards','knight_then_guard')
        b=self.r(743,'guard_same_two_cards','guard_then_knight')
        self.assertEqual(a['ledger']['own_after'],b['ledger']['own_after'])
        self.assertEqual((a['ledger']['paid_gold'],b['ledger']['paid_gold']),(11,14))
        self.assertAlmostEqual(compare(a,b,'test')['central_net_difference'],3)

    def test_knightdyne_kills_not_unused_packets(self):
        r=self.r(892,'knightdyne_chain','four_packets')
        self.assertEqual(r['features']['spear_taunt_count'],2)
        self.assertEqual(len(r['ledger']['own_after']),3)
        self.assertEqual(r['ledger']['enemy_after'],[dict(a=4,h=4)])
        blocked=self.r(892,'knightdyne_armor','four_packets_blocked')
        self.assertEqual(blocked['features']['spear_taunt_count'],0)

    def test_g_machine_dead_body_removed_before_delay_reward(self):
        r=self.r(609,'one_5_5','attack_0')
        self.assertEqual(r['ledger']['own_after'],[])
        self.assertEqual(r['ledger']['enemy_after'],[])
        self.assertEqual(r['inventory']['net_relative_cards'],0)
        self.assertEqual(r['ledger']['valuation_stage'],'after_own_Delay')

    def test_hydra_hand_cap_realized_inventory(self):
        r=self.r(266,'hydra_hand6','magic_then_haste')
        self.assertEqual(r['inventory']['net_relative_cards'],1)
        self.assertEqual(r['features']['burned_draws'],1)
        self.assertEqual(r['ledger']['own_after'],[dict(a=3,h=1)])

    def test_copy_does_not_remove_enemy_or_grant_haste(self):
        r=self.r(151,'one_8_8','copy_0')
        self.assertEqual([(u['a'],u['h']) for u in r['ledger']['enemy_after']],[(8,8)])
        self.assertEqual([(u['a'],u['h']) for u in r['ledger']['own_after']],[(8,8)])
        self.assertFalse(any('/151/one_8_8/attack' in key for key in self.rs))

    def test_microwave_both_play_and_erasure_cost_inventory(self):
        r=self.r(226,'microwave_spare_card','play_and_erase')
        self.assertEqual(r['inventory']['net_relative_cards'],-2)

    def test_sink_choice_reverses_with_hp_price(self):
        a=self.r(509,'sink_hero27_tiny','decline_attack_heal3')
        b=self.r(509,'sink_hero27_tiny','haste_kill_tiny')
        diff=lambda p:quote(a['ledger'],dict(face=p,card=1,gold=1))['net_payment_margin']-quote(b['ledger'],dict(face=p,card=1,gold=1))['net_payment_margin']
        self.assertGreater(diff(.25),0)
        self.assertLess(diff(.15),0)


if __name__=='__main__':unittest.main(verbosity=2)
