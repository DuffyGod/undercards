import copy
import unittest

from payment_frontier import PaymentFrontier, compare_discount, optimize_payments


class PaymentTests(unittest.TestCase):
    def test_unused_card_has_no_cash_savings(self):
        result = compare_discount([{"cost": 1, "gross_model_gold": 0}], [1, 1], cost_delta=-1)
        self.assertEqual(result["old"]["optimal_plan"]["used_indexes"], [])
        self.assertEqual(result["new"]["optimal_plan"]["used_indexes"], [])
        self.assertEqual(result["direct_paid_savings_gold"], 0)
        self.assertEqual(result["total_net_improvement_model_gold"], 0)

    def test_discount_just_unlocks_second_card_and_decomposition(self):
        hand = [{"cost": 3, "gross_model_gold": 5}, {"cost": 3, "gross_model_gold": 5}]
        result = compare_discount(hand, [3, 1], max_plays=1, cost_delta=-1)
        self.assertEqual(len(result["old"]["optimal_plan"]["used_indexes"]), 1)
        self.assertEqual(len(result["new"]["optimal_plan"]["used_indexes"]), 2)
        self.assertEqual(result["old"]["max_net_model_gold"], 2)
        self.assertEqual(result["new"]["max_net_model_gold"], 6)
        self.assertEqual(result["direct_paid_savings_gold"], 1)
        self.assertEqual(result["additional_unlocked_net_model_gold"], 3)
        self.assertEqual(result["total_net_improvement_model_gold"], 4)

    def test_previously_unaffordable_card_is_unlock_not_old_cash_saving(self):
        result = compare_discount([{"cost": 5, "gross_model_gold": 7}], [1, 1], cost_delta=-3)
        self.assertEqual(result["direct_paid_savings_gold"], 0)
        self.assertEqual(result["additional_unlocked_net_model_gold"], 5)

    def test_negative_net_and_unused_gold_are_not_losses(self):
        result = optimize_payments([{"cost": 3, "gross_model_gold": 2}], [4, 4], initial_gold=1)
        self.assertEqual(result["max_net_model_gold"], 0)
        self.assertEqual(result["optimal_plan"]["assignment"], [0])
        self.assertEqual(result["optimal_plan"]["closing_gold"], 9)

    def test_gold_carries_and_cannot_borrow_later_income(self):
        frontier = PaymentFrontier([{"cost": 5, "gross_model_gold": 8}], [2, 2], initial_gold=1)
        result = frontier.optimize()
        self.assertEqual(result["optimal_plan"]["assignment"], [2])
        self.assertEqual(result["optimal_plan"]["windows"][0]["closing_gold"], 3)
        self.assertEqual(result["optimal_plan"]["windows"][1]["closing_gold"], 0)
        with self.assertRaisesRegex(ValueError, "overdraws"):
            frontier.evaluate_plan([1])

    def test_caps_limit_free_actions_and_one_use_per_card(self):
        hand = [{"cost": 0, "gross_model_gold": 1} for _ in range(7)]
        result = optimize_payments(hand, [0, 0, 0], max_plays=1)
        self.assertEqual(result["max_net_model_gold"], 3)
        self.assertEqual(len(result["optimal_plan"]["used_indexes"]), 3)
        self.assertTrue(all(len(w["played_indexes"]) <= 1 for w in result["optimal_plan"]["windows"]))
        self.assertEqual(len(set(result["optimal_plan"]["used_indexes"])), 3)
        self.assertEqual(optimize_payments(hand, [0, 0], max_plays=0)["max_net_model_gold"], 0)

    def test_floor_clips_payment_savings(self):
        result = compare_discount([{"cost": 1, "gross_model_gold": 5}], [1, 0], cost_delta=-3)
        self.assertEqual(result["direct_paid_savings_gold"], 1)
        self.assertEqual(result["new"]["optimal_plan"]["paid_cost"], 0)
        self.assertTrue(result["scope"]["payment_floor_is_model_assumption"])

    def test_replay_is_feasible_and_same_assignment_quotes(self):
        hand = [{"cost": 2, "gross_model_gold": 3}, {"cost": 5, "gross_model_gold": 8},
                {"cost": 1, "gross_model_gold": .5}]
        original = copy.deepcopy(hand)
        result = compare_discount(hand, [3, 2, 4], initial_gold=1, max_plays=1, cost_delta=-1)
        self.assertEqual(hand, original)
        self.assertEqual(result["old"]["optimal_plan"]["assignment"], result["old_plan_at_new_cost"]["assignment"])
        self.assertEqual(result["old"]["optimal_plan"]["gross_model_gold"], result["old_plan_at_new_cost"]["gross_model_gold"])
        self.assertTrue(result["old_plan_at_new_cost"]["feasible"])
        self.assertAlmostEqual(result["total_net_improvement_model_gold"],
                               result["direct_paid_savings_gold"] + result["additional_unlocked_net_model_gold"])

    def test_two_optimal_old_ties_use_fewer_plays_then_stable_schedule(self):
        hand = [{"cost": 1, "gross_model_gold": 1}, {"cost": 2, "gross_model_gold": 4}]
        result = optimize_payments(hand, [4, 0])
        self.assertEqual(result["optimal_plan"]["used_indexes"], [1])
        self.assertEqual(result["optimal_plan"]["assignment"], [0, 1])

    def test_invalid_inputs_and_unsupported_increase(self):
        for args in [([{"cost": 1}], [1, 1]),
                     ([{"cost": 1, "gross_model_gold": float("nan")}], [1, 1]),
                     ([], [1]), ([], [1, -1])]:
            with self.assertRaises(ValueError):
                optimize_payments(*args)
        with self.assertRaises(ValueError):
            optimize_payments([], [1, 1], max_plays=True)
        with self.assertRaises(ValueError):
            compare_discount([], [1, 1], cost_delta=1)


if __name__ == "__main__":
    unittest.main()
