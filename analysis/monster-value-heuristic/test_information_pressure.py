import copy
import unittest
from information_pressure import evaluate


def config():
    return dict(scenario=dict(hand_ids=[15],gold_before_play=5,own_player_hp=15,own_player_max_hp=30,
        enemy_player_hp=30,enemy_player_max_hp=30,opponent_gold_before_response=0,
        enemy_bodies=[dict(card_id=2,attack=2,health=3,max_health=3)],
        own_deck_ids=[],opponent_deck_ids=[]),
        worlds=[dict(id='known_empty',opponent_hand_ids=[])],task=dict(kind='hp'))


class InformationPressureTests(unittest.TestCase):
    def test_independent_plain_body_trade_and_face_bounds(self):
        # Enemy first hits face2; clearing costs Aaron's one next attack:
        # own13/enemy30. Face6 instead permits second enemy face2: own11/E24.
        r=evaluate(config(),floors=[1,13,14])
        self.assertEqual(r['frontier'],[dict(own_hp=13,enemy_hp_cap=30),dict(own_hp=11,enemy_hp_cap=24)])
        self.assertTrue(r['rows'][2]['known']);self.assertFalse(r['rows'][2]['feasible'])
        self.assertIsNone(r['rows'][2]['own_hp'])

    def test_joint_bodies_are_not_independently_pasted(self):
        d=config();d['task']=dict(kind='joint',constraints={'min_own_body_health':4})
        r=evaluate(d,floors=[1]);self.assertTrue(r['complete_sampled_floors'])
        self.assertTrue(all(point['own_hp']<=11 for point in r['frontier']))

    def test_unknown_source_is_not_zero_or_infeasible(self):
        d=config();d['scenario']['hand_ids']=[17];d['scenario']['gold_before_play']=9
        r=evaluate(d,floors=[1]);self.assertFalse(r['rows'][0]['known'])
        self.assertIsNone(r['rows'][0]['feasible']);self.assertEqual(r['frontier'],[])

    def test_positive_distinct_integer_floors(self):
        for floors in [[],[0],[True],[1.5],[1,1]]:
            with self.assertRaises(ValueError):evaluate(config(),floors=floors)


if __name__=='__main__':unittest.main()
