"""A small set of independent hand-calculated checks, not game calibration."""
import json
from pathlib import Path
import unittest

from value_model import (Asset, BodyScale, after_packets, after_silence, endpoint,
                         response_curve, crossing, common_plan,
                         fixed_deadline_option, hand_budget_value)


class MethodChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scale=BodyScale(json.loads((Path(__file__).parent/'inputs.json').read_text(encoding='utf-8'))['reference'])

    def test_capped_attack_identity(self):
        s=BodyScale([dict(attack=2,health=6,weight=.8),dict(attack=2,health=8,weight=.2)],face_share=.1)
        # Direct tail mass, independently calculated from the two target HPs.
        self.assertAlmostEqual(s.effective_attack(7)-s.effective_attack(6),.1+.9*.2)
        self.assertAlmostEqual(s.effective_attack(9)-s.effective_attack(8),.1)
        self.assertGreater(s.value(8,5)-s.value(7,5),s.value(9,5)-s.value(8,5))

    def test_no_clawback_of_realized_magic(self):
        a=Asset(6,6,2,2)
        q=response_curve(self.scale,a,realized=2,enemy_cash=1,response_cost=1)
        self.assertAlmostEqual(q['answered'],2+self.scale.value(2,2))
        q0=response_curve(self.scale,a,realized=0,enemy_cash=1,response_cost=1)
        self.assertAlmostEqual(q['loss'],q0['loss'])

    def test_damage_is_not_a_silence_heal(self):
        a=Asset(7,4,7,9,damage_taken=5)
        self.assertEqual(after_silence(a).health,4)
        with self.assertRaises(ValueError):after_silence(Asset(6,5,2,2,damage_taken=1))

    def test_response_must_be_payable(self):
        a=Asset(7,7,2,2)
        low=response_curve(self.scale,a,enemy_cash=0,response_cost=1)
        high=response_curve(self.scale,a,enemy_cash=1,response_cost=1)
        self.assertEqual(low['loss'],0)
        self.assertGreater(high['loss'],0)

    def test_common_action_cannot_use_world_oracle(self):
        r=common_plan([[10,0],[0,10]],[.5,.5])
        self.assertEqual(r['value'],5)
        self.assertEqual(r['oracle_diagnostic'],10)

    def test_wait_once_has_a_real_deadline(self):
        r=fixed_deadline_option(2.5,[1,5],[.5,.5],1)
        self.assertEqual(r['value'],2.5)
        self.assertEqual(r['choices']['wait_once'],2)
        self.assertEqual(fixed_deadline_option(-2,[-4,-1],[.5,.5],.1)['value'],0)

    def test_same_slot_same_budget_replacement(self):
        # Payoffs are declared endpoint gains, not a fitted price for a card.
        candidate=hand_budget_value([(6,7),(4,6)],6)
        reference=hand_budget_value([(2,2),(4,6)],6)
        self.assertEqual(candidate['value']-reference['value'],-1)
        self.assertEqual(candidate['paid'],reference['paid'])

    def test_packet_count_changes_protection_in_opposite_directions(self):
        armor=Asset(3,20,3,20,armor=True)
        dodge=Asset(3,20,3,20,dodge=1)
        self.assertEqual(after_packets(armor,[6]).health,15)
        self.assertEqual(after_packets(armor,[2,2,2]).health,17)
        self.assertEqual(after_packets(dodge,[6]).health,20)
        self.assertEqual(after_packets(dodge,[2,2,2]).health,16)

    def test_crossing_and_endpoint_invariance(self):
        self.assertAlmostEqual(crossing(dict(no_reply=7,loss=1),dict(no_reply=8,loss=7)),1/6)
        # The sole stock is the endpoint body, regardless of how it was reached.
        self.assertEqual(endpoint(self.scale,Asset(6,5,6,5)),endpoint(self.scale,Asset(6,5,2,2)))
        self.assertAlmostEqual(endpoint(self.scale,Asset(6,5,6,5)),5)

    def test_sparse_bridge_rejects_invalid_observations(self):
        from run_experiment import card_endpoint
        profiles=json.loads((Path(__file__).parent/'inputs.json').read_text(encoding='utf-8'))['profiles']
        draw=next(p for p in profiles if p['feature_kind']=='draw')
        for bad in (-1,7,8,2.5,True):
            with self.assertRaises(ValueError):card_endpoint(draw,self.scale,hand=bad)
        with self.assertRaises(ValueError):card_endpoint(draw,self.scale,enemy_count=-1)
        with self.assertRaises(ValueError):card_endpoint(draw,self.scale,draw_value=float('nan'))
        _,low,_=card_endpoint(draw,self.scale,draw_value=.3)
        _,high,_=card_endpoint(draw,self.scale,draw_value=.9)
        self.assertAlmostEqual(high-low,.6)


if __name__=='__main__':unittest.main()
