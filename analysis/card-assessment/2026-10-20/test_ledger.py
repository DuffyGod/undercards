import unittest
from copy import deepcopy
from value_ledger import *
from build_assessments import base,derive,combat_options,PROFILES

class LedgerTests(unittest.TestCase):
    def test_toriel_and_q_counterfactual(self):
        good=derive(8,'toriel','tall')[0];bad=derive(8,'toriel','small')[0]
        self.assertAlmostEqual(quote(good)['absolute_gross'],11.03627,places=5)
        self.assertAlmostEqual(quote(bad)['absolute_gross'],6.80548,places=5)
        x=carrying(good,bad,q=0,holding_cost=.75)
        self.assertEqual(x['carrying_margin'],-.75)  # no forced 8G bad play
        self.assertAlmostEqual(x['required_q'],.75/(11.03627-8),places=5)
        self.assertGreater(carrying(good,bad,q=.5,holding_cost=.75)['carrying_margin'],0)

    def test_bench_aaron_same_cost_price_threshold(self):
        a=base(15,'empty');b=base(243,'empty',usable_cards=1)
        d=paired_difference(b,a)
        self.assertAlmostEqual(d['card_price_tie_at_central_other_prices'],.315037,places=5)
        self.assertGreater(quote(b)['absolute_gross'],quote(a)['absolute_gross'])
        b['events']['usable_cards']=0
        self.assertLess(quote(b)['absolute_gross'],quote(a)['absolute_gross'])

    def test_haste_must_lose_body_when_both_die(self):
        l=base(115,'small');l['enemy_before']=[dict(a=1,h=2)];l['enemy_after']=[dict(a=1,h=2)]
        attack_line=[r for r in combat_options(l,115) if r.get('action')][0]
        self.assertEqual(attack_line['own_after'],[]);self.assertEqual(attack_line['enemy_after'],[])
        self.assertAlmostEqual(quote(attack_line)['absolute_gross'],F(1,2))

    def test_one_retained_card_cannot_lose_one_new_card_each_turn(self):
        x=extra_burns(7,[1]*5,[0]*5)
        self.assertEqual((x['held_burn'],x['freed_burn'],x['additional_burn']),(5,4,1))
        self.assertEqual(extra_burns(5,[1,1],[1,1])['additional_burn'],0)

    def test_draw_dust_and_returns_are_distinct(self):
        chest=next(x for x in derive(311,'chest','empty') if x['events'].get('usable_cards')==2)
        self.assertEqual(chest['own_after'],[])
        self.assertEqual(quote(chest)['absolute_gross'],2)
        lesser=next(x for x in derive(43,'lesser','empty') if x['events'].get('usable_gold')==3)
        self.assertEqual(lesser['own_after'],[])
        # This is the post-Dust reward projection; body service is not invented.
        self.assertTrue(lesser['unpriced'])
        skate=[x for x in derive(221,'skate','small') if x['events'].get('usable_cards')]
        self.assertTrue(skate)
        self.assertEqual(skate[0]['own_after'],[])

    def test_papyrus_monster_chain_cannot_finish_face_after_kill(self):
        l=base(60,'empty');l['enemy_before']=[dict(a=1,h=1),dict(a=1,h=1)];l['enemy_after']=deepcopy(l['enemy_before'])
        out=combat_options(l,60,charge=True,chain=True)
        self.assertTrue(any(not q['enemy_after'] for q in out))
        self.assertFalse(any(q['events'].get('hero_damage') and len(q['enemy_after'])<2 for q in out))

    def test_undyne_unused_packets_not_blocked_damage(self):
        q=derive(62,'undyne','empty')[0]
        self.assertEqual([(u['a'],u['h']) for u in q['own_after']],[(7,8),(10,10)])
        q=derive(62,'undyne','small')[0]
        self.assertEqual(q['own_after'][-1]['a'],5)

    def test_statue_counts_its_new_body_and_boat_does_not_double_claim(self):
        bad=derive(111,'statue','ally')
        self.assertTrue(all(not q.get('action') for q in bad))
        self.assertTrue(any(q.get('action') for q in derive(111,'statue','small')))
        boat=derive(605,'boat','empty')
        used=next(q for q in boat if len(q['own_after'])==2)
        self.assertEqual(used['paid_gold'],4)
        self.assertEqual(used['events'].get('usable_cards'),0)
        self.assertAlmostEqual(quote(used)['absolute_gross'],F(3,3)+F(2,1))

    def test_dust_mutual_trade_has_a_concrete_redemption_threshold(self):
        l=dict(own_before=[],enemy_before=[dict(a=5,h=5)],own_after=[],enemy_after=[],paid_gold=6,events=dict(usable_gold=3))
        self.assertAlmostEqual(quote(l)['net_payment_margin'],F(5,5)+3-6)
        l['events']['usable_gold']=0
        self.assertLess(quote(l)['net_payment_margin'],0)

    def test_generic_new_card_ledger_needs_no_card_support(self):
        l=dict(own_before=[],enemy_before=[dict(a=8,h=8)],own_after=[dict(a=3,h=4)],enemy_after=[],paid_gold=5,events={})
        self.assertAlmostEqual(quote(l)['absolute_gross'],F(3,4)+F(8,8))
        with self.assertRaises(ValueError):quote(l,dict(face=-1,card=1,gold=1))
        b=deepcopy(l);b['enemy_before']=[]
        with self.assertRaises(ValueError):paired_difference(l,b)

if __name__=='__main__':unittest.main()
