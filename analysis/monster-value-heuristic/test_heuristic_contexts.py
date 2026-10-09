import copy
import unittest

import heuristic_contexts as h


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.contexts = h.make_contexts()

    def test_24_joint_contexts_equal_weights_and_stage_targets(self):
        self.assertEqual(len(self.contexts), 24)
        self.assertEqual(len({c["context_id"] for c in self.contexts}), 24)
        self.assertAlmostEqual(sum(c["weight"] for c in self.contexts), 1)
        for role in h.ROLES:
            self.assertAlmostEqual(sum(c["weight"] for c in self.contexts if c["role"] == role), .25)
        for turn in h.PHASES:
            same_stage = [c for c in self.contexts if c["own_turn"] == turn]
            self.assertAlmostEqual(sum(c["weight"] for c in same_stage), 1 / 3)
            self.assertTrue(all(c["stage_target_bodies"] == same_stage[0]["stage_target_bodies"] for c in same_stage))

    def test_pre_post_hand_and_both_board_counts(self):
        for ctx in self.contexts:
            self.assertEqual(ctx["hand_size_after_play"], ctx["hand_size_before_play"] - 1)
            self.assertLessEqual(ctx["hand_size_before_play"], 7)
            self.assertLess(ctx["ally_count_before_play"], 4)
            self.assertEqual(ctx["other_monster_count"], ctx["ally_count_after_play"] + ctx["enemy_count"] - 1)
            self.assertEqual(len(ctx["ally_bodies_before_play"]), ctx["ally_count_before_play"])
            self.assertEqual(len(ctx["enemy_bodies"]), ctx["enemy_count"])
            self.assertTrue(h.validate_context(ctx))
        ctx = self.contexts[0]
        self.assertEqual(h.evaluate_amount({"amount": 1, "amount_basis": "hand_size_after_play"}, ctx), 2)
        self.assertEqual(h.evaluate_amount({"amount": 1, "amount_basis": "other_monster_count"}, ctx), 5)
        self.assertEqual(h.evaluate_amount({"amount": 1, "amount_basis": "ally_count"}, ctx), 3)
        self.assertEqual(h.evaluate_amount({"amount": 1, "amount_basis": "other_ally_monster_count"}, ctx), 2)

    def test_income_retention_and_affordable_binding(self):
        self.assertEqual(h.cumulative_base_gold(3), 7)
        self.assertEqual(h.cumulative_base_gold(3, True), 9)
        for ctx in self.contexts:
            self.assertLessEqual(ctx["gold_before_play"], h.cumulative_base_gold(ctx["own_turn"]))
            self.assertIsNone(ctx["gold_after_play"])
            bound = h.bind_candidate(ctx, 4)
            self.assertEqual(bound["gold_after_play"], ctx["gold_before_play"] - 4)
            self.assertIsNone(ctx["gold_after_play"])
            for response in ctx["response_states"]:
                self.assertEqual(response["affordable"], response["paid_cost"] <= ctx["opponent_gold_before_response"])
        with self.assertRaisesRegex(ValueError, "unaffordable"):
            h.bind_candidate(self.contexts[0], 8)

    def test_invalid_context_constraints_are_rejected(self):
        ctx = copy.deepcopy(self.contexts[0])
        ctx["gold_before_play"] = 99
        with self.assertRaises(ValueError):
            h.validate_context(ctx)
        ctx = copy.deepcopy(self.contexts[0])
        ctx["ally_count_before_play"] = 4
        with self.assertRaises(ValueError):
            h.validate_context(ctx)

    def test_expression_fixed_unknown_and_no_future_reading(self):
        ctx = copy.deepcopy(self.contexts[0])
        module = {"amount": 2, "amount_basis": "hand_size_after_play", "count": 5, "repeat_rule": "on_kill"}
        self.assertEqual(h.evaluate_amount(module, ctx), 4)
        ctx["death_event_hand_costs"] = [100] * 7
        ctx["actually_used_mask"] = [False] * 7
        ctx["resource_use_window"] = {"available_gold_assumption": 999}
        self.assertEqual(h.evaluate_amount(module, ctx), 4)
        self.assertEqual(h.evaluate_amount({"amount": 3, "amount_basis": "fixed"}, ctx), 3)
        for basis in ("unknown", "death_event_hand_costs", "future_hand_size"):
            with self.assertRaises(ValueError):
                h.evaluate_amount({"amount": 1, "amount_basis": basis}, ctx)
        with self.assertRaises(ValueError):
            h.evaluate_amount({"amount": None, "amount_basis": "fixed"}, ctx)

    def test_choice_groups_exactly_one_and_common_terms_shared(self):
        modules = [{"choice_group": None}, {"choice_group": "A"}, {"choice_group": "A"},
                   {"choice_group": "B"}, {"choice_group": "B"}]
        branches = h.enumerate_choice_branches(modules)
        self.assertEqual(len(branches), 4)
        for b in branches:
            indexes = b["selected_module_indexes"]
            self.assertIn(0, indexes)
            self.assertEqual(len(set(indexes) & {1, 2}), 1)
            self.assertEqual(len(set(indexes) & {3, 4}), 1)
        self.assertEqual(h.enumerate_choice_branches([]), [{"selected_module_indexes": [], "choice_selection": {}}])

    def test_actual_payments_floor_and_unused_cards(self):
        self.assertEqual(h.paid_cost_discount(1, -2), 1)
        self.assertEqual(h.paid_cost_discount(7, 6, False), 0)
        self.assertEqual(h.paid_cost_discount(0, -1), 0)
        self.assertEqual(h.paid_cost_discount(2, 4), -2)
        with self.assertRaises(ValueError):
            h.paid_cost_discount(4, 3, 1)
        ctx = self.contexts[0]
        ledger = h.discount_payment_ledger(ctx, -1)
        self.assertEqual(ledger["total_old_paid"], 4)
        self.assertEqual(ledger["total_new_paid"], 2)
        self.assertEqual(ledger["total_saved_paid_gold"], 2)
        self.assertEqual(ledger["rows"][2]["saved_paid_gold"], 0)

    def test_choice_preserves_multiple_actions_in_the_same_branch(self):
        modules = [{'choice_group':'A','choice_branch':'left'},
                   {'choice_group':'A','choice_branch':'left'},
                   {'choice_group':'A','choice_branch':'right'}, {'choice_group':None}]
        branches = h.enumerate_choice_branches(modules)
        self.assertEqual({tuple(b['selected_module_indexes']) for b in branches}, {(0,1,3),(2,3)})

    def test_malformed_or_unaffordable_future_mask_cannot_claim_actual_payment(self):
        ctx = copy.deepcopy(self.contexts[0])
        ctx["actually_used_mask"] = [True]
        with self.assertRaises(ValueError):
            h.discount_payment_ledger(ctx, -1)
        ctx = copy.deepcopy(self.contexts[0])
        ctx["actually_used_mask"] = [True, True, True]
        with self.assertRaisesRegex(ValueError, "resource window"):
            h.discount_payment_ledger(ctx, -1)


if __name__ == "__main__":
    unittest.main()
