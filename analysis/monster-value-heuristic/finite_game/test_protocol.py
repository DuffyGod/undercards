import copy
import unittest
from .belief import evaluate,ProtocolError


def case():
    return dict(scenario=dict(hand_ids=[14,15],hand_generated=[False,False],gold_before_play=5,
        own_player_hp=15,own_player_max_hp=30,enemy_player_hp=30,enemy_player_max_hp=30,
        opponent_gold_before_response=2,own_deck_ids=[],opponent_deck_ids=[],
        enemy_bodies=[dict(card_id=246,attack=3,health=6,max_health=6,printed_cost=4,base_cost=4,current_cost=4)]),
        worlds=[dict(id='generated_silence',opponent_hand_ids=[79],opponent_hand_generated=[True]),
                dict(id='generated_worsening',opponent_hand_ids=[86],opponent_hand_generated=[True])],
        task=dict(kind='hp'))


class InformationProtocolTests(unittest.TestCase):
    def test_real_independent_counterexample_and_payment_threshold(self):
        d=case();r=evaluate(d)
        self.assertTrue(r['known']);self.assertEqual(r['common_policy']['guaranteed_player_hp'],9)
        self.assertEqual(r['informed_world_upper_bound']['guaranteed_player_hp'],12)
        self.assertEqual(r['information_gap_hp'],3);self.assertTrue(r['policy_audit']['passed'])
        d['scenario']['opponent_gold_before_response']=1;r=evaluate(d)
        self.assertEqual(r['common_policy']['guaranteed_player_hp'],12)
        self.assertEqual(r['information_gap_hp'],0)

    def test_unknown_source_and_budget_have_no_numeric_quote(self):
        d=case();d['node_limit']=1;r=evaluate(d)
        self.assertFalse(r['known']);self.assertIsNone(r['common_policy']['value'])
        d=case();d['scenario']['hand_ids']=[17];d['scenario']['hand_generated']=[False]
        r=evaluate(d);self.assertFalse(r['known']);self.assertIsNone(r['root_action'])

    def test_public_hand_count_cannot_be_hidden_by_world_wrapper(self):
        d=case();d['worlds'][1]['opponent_hand_ids']=[];d['worlds'][1]['opponent_hand_generated']=[]
        with self.assertRaises(ProtocolError):evaluate(d)

    def test_hidden_hand_indexes_do_not_reveal_an_order_permutation(self):
        d=case();d['worlds']=[dict(id='left_first',opponent_hand_ids=[1,2]),dict(id='right_first',opponent_hand_ids=[2,1])]
        r=evaluate(d);self.assertTrue(r['known']);self.assertEqual(r['information_gap_hp'],0)
        self.assertTrue(any(len(n['possible_worlds'])==2 for n in r['policy']))


if __name__=='__main__':unittest.main()
