"""Independent physical anchors for the sparse statistical experiment.

These tests use literal source-card states and primitive F expressions rather
than copying the production feature compiler. They do not validate Gold prices.
"""
from pathlib import Path
import json
from itertools import combinations
import unittest
from unittest.mock import patch

import statistical_value as model
from run_statistical_study import evaluate_one, mean_discount
from discount_statistics import expected_discount


HERE = Path(__file__).resolve().parent


class StatisticalValueAnchors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = json.loads((HERE / 'statistical_inputs.json').read_text(encoding='utf-8'))
        cls.cards = cls.inputs['cards']
        cls.prices = model.Prices(cls.inputs, tail=0.)

    def card(self, card_id):
        return self.cards[str(card_id)]

    def plans(self, card_id, enemy, hand=2):
        return dict(model.deployment_plans(self.card(card_id), self.cards, enemy, hand))

    def value(self, card_id, enemy, hand=2):
        return model.best_value(self.card(card_id), self.cards, enemy, hand,
                                self.prices, 'none', 0., 0., details=True)

    def test_archer_exact_bullseye_overrides_clover_body(self):
        enemy = ((3, 2),) * 3
        outcomes = self.plans(984, enemy)['magic_target_0:hold_attack']
        probability, own, remaining, face, draw, discount = outcomes[0]
        self.assertEqual(probability, 1.)
        self.assertEqual([(u.a, u.h) for u in own], [(3, 4), (2, 3)])
        self.assertEqual(remaining, ((3, 2), (3, 2)))
        self.assertFalse(own[1].root)
        f = self.prices.scale.value
        self.assertAlmostEqual(self.value(984, enemy)[0], f(3, 4) + f(2, 3) + f(3, 2))

    def test_archer_overkill_has_no_child_and_silence_keeps_damage(self):
        enemy = ((3, 2),) * 3
        outcomes = self.plans(984, enemy, hand=4)['magic_target_0:hold_attack']
        self.assertEqual([(u.a, u.h) for u in outcomes[0][1]], [(3, 4)])
        self.assertEqual(outcomes[0][2], ((3, 2), (3, 2)))
        f = self.prices.scale.value
        actual, _ = model.best_value(self.card(984), self.cards, enemy, 4,
                                     self.prices, 'silence', 1., 0.)
        self.assertAlmostEqual(actual, f(3, 4) + f(3, 2))

    def test_car_magic_and_haste_have_two_distinct_kills(self):
        enemy = ((3, 2),) * 3
        outcomes = self.plans(649, enemy)['magic_target_0:attack_0']
        _, own, remaining, *_ = outcomes[0]
        self.assertEqual([(u.a, u.h) for u in own], [(3, 4)])
        self.assertEqual(remaining, ((3, 2),))
        f = self.prices.scale.value
        _, _, menu = self.value(649, enemy)
        self.assertAlmostEqual(menu['magic_target_0:attack_0'], f(3, 4) + 2 * f(3, 2))

    def test_piranhas_two_hp_targets_stop_random_chain_and_spend_dodge(self):
        enemy = ((3, 2),) * 3
        outcomes = self.plans(530, enemy)['deploy:attack_0']
        self.assertEqual(len(outcomes), 2)
        self.assertEqual({(p, e) for p, team, e, *_ in outcomes},
                         {(.5, ((3, 1), (3, 2))), (.5, ((3, 2), (3, 1)))})
        for _, own, *_ in outcomes:
            self.assertEqual([(u.a, u.h, u.dodge) for u in own], [(4, 4, 0)])
        f = self.prices.scale.value
        _, _, menu = self.value(530, enemy)
        self.assertAlmostEqual(menu['deploy:attack_0'], f(4, 4) + 2*f(3, 2) - f(3, 1))

    def test_piranhas_one_hp_chain_clears_board_and_no_kill_means_no_ping(self):
        outcomes = self.plans(530, ((3, 1),) * 3)['deploy:attack_0']
        self.assertAlmostEqual(sum(x[0] for x in outcomes), 1.)
        for _, own, enemy, *_ in outcomes:
            self.assertEqual(enemy, ())
            self.assertEqual([(u.a, u.h, u.dodge) for u in own], [(4, 4, 0)])
        outcomes = self.plans(530, ((6, 7),))['deploy:attack_0']
        self.assertEqual(len(outcomes), 1)
        _, own, enemy, *_ = outcomes[0]
        self.assertEqual(enemy, ((6, 3),))
        self.assertEqual([(u.a, u.h, u.dodge) for u in own], [(4, 4, 0)])

    def test_blockler_mutual_kill_replaces_b_with_one_o(self):
        enemy = ((4, 3),)
        _, own, remaining, *_ = self.plans(469, enemy)['deploy:attack_0'][0]
        self.assertEqual(remaining, ())
        self.assertEqual([(u.a, u.h, u.taunt, u.root, u.dust) for u in own],
                         [(4, 3, True, False, '')])
        f = self.prices.scale.value
        _, _, menu = self.value(469, enemy)
        self.assertAlmostEqual(menu['deploy:attack_0'], 2*f(4, 3))

    def test_lesser_dog_single_future_card_discount_payment_threshold(self):
        # One known cost-6 card has gross value 7 under the stated quality prior.
        # At cash5 discount unlocks value 7-5; at cash6 it changes net 1 to2.
        self.assertEqual(model.discount_option((6,), 4), 0.)
        self.assertEqual(model.discount_option((6,), 5), 2.)
        self.assertEqual(model.discount_option((6,), 6), 1.)
        self.assertEqual(model.discount_option((0,), 0), 0.)

    def test_discount_source_order_is_not_future_hand_information(self):
        costs = (0, 2, 2, 5, 6)
        reordered = (6, 2, 0, 5, 2)
        for hand in (0, 1, 2, 4, 5):
            with self.subTest(hand=hand):
                self.assertAlmostEqual(mean_discount(costs, hand),
                                       mean_discount(reordered, hand))
                self.assertAlmostEqual(expected_discount(costs, hand),
                                       expected_discount(reordered, hand))

    def test_discount_multiset_matches_physical_copy_hypergeometric_enumeration(self):
        # Equal-cost copies are different physical draws. Enumerating indices
        # is independent of the production cost-count recursion/multiplicity.
        costs = (1, 1, 3, 6)
        for hand in (0, 1, 2, 3, 4):
            for cash in (0, 2, 5, 6):
                with self.subTest(hand=hand, cash=cash):
                    subsets = list(combinations(range(len(costs)), hand))
                    expected = sum(model.discount_option(tuple(costs[i] for i in selected), cash)
                                   for selected in subsets)/len(subsets)
                    self.assertAlmostEqual(expected_discount(costs, hand, cash), expected)

    def test_haste_is_optional_and_cannot_lose_the_plain_hold_plan(self):
        # Same numeric body, one ordinary profile and one Charge profile.
        # Charge includes the Haste enemy-attack menu plus its face option.
        plain = dict(self.card(15))
        immediate = dict(plain, id=9)
        enemy = ((100, 100),)
        plain_value, _ = model.best_value(plain, self.cards, enemy, 2,
                                         self.prices, 'none', 0., 0.)
        boosted_value, _, menu = model.best_value(immediate, self.cards, enemy, 2,
                                                 self.prices, 'none', 0., 0., details=True)
        self.assertIn('deploy:hold_attack', menu)
        self.assertAlmostEqual(menu['deploy:hold_attack'], plain_value)
        self.assertGreaterEqual(boosted_value, plain_value)

    def test_random_endpoint_values_are_integrated_before_plan_selection(self):
        high = model.Unit(10, 1, 10, 1, 1)
        low = model.Unit(0, 1, 0, 1, 1)
        a = ((.5, (high,), (), 0., 0, False), (.5, (low,), (), 0., 0, False))
        b = ((.5, (low,), (), 0., 0, False), (.5, (high,), (), 0., 0, False))
        with patch.object(model, 'deployment_plans', return_value=[('A', a), ('B', b)]):
            value, _, menu = self.value(15, ())
        f = self.prices.scale.value
        expected = .5*f(10, 1) + .5*f(0, 1)
        self.assertAlmostEqual(value, expected)
        self.assertAlmostEqual(menu['A'], expected)
        self.assertAlmostEqual(menu['B'], expected)
        self.assertLess(value, f(10, 1))

    def test_same_statistical_panel_plus_attack_changes_value_without_policy_switch(self):
        panel = [dict(enemy=((6, 7),), weight=1., source_ids=[])]
        result = evaluate_one(self.card(15), self.inputs, panel,
                              'midrange_single', self.prices, True)
        f = self.prices.scale.value
        # The fixed reply opportunity is25%; Aaron survives damage4 with1HP.
        expected = .75*(f(7, 5)-f(6, 5)) + .25*(f(7, 1)-f(6, 1))
        self.assertAlmostEqual(result['plus_attack'], expected)
        self.assertAlmostEqual(result['fixed_policy_plus_attack'], expected)
        self.assertEqual(result['changed_plan_mass'], 0.)
        self.assertGreater(result['plus_attack'], 0.)


if __name__ == '__main__':
    unittest.main()
