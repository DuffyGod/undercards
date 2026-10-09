"""Checks exact resource rules and information boundaries, not card rankings."""

import unittest

import resource_curve as rc


def setup(deck, **kwargs):
    cards, cfg, _ = rc.normalize_input({"deck": deck, **kwargs})
    return cards, cfg


class ResourceTests(unittest.TestCase):
    def test_income_and_carry(self):
        cards, cfg = setup([99] * 25, horizon=6)
        trace = rc.simulate_trial(cards, cfg, "deploy")
        self.assertEqual([row["gold_before"] for row in trace["turns"]], [2, 4, 7, 11, 16, 22])
        cfg["first"] = False
        trace = rc.simulate_trial(cards, cfg, "deploy")
        self.assertEqual([row["gold_before"] for row in trace["turns"]], [3, 5, 9, 13, 19, 25])
        self.assertEqual([rc.income(t, False) for t in (9, 10, 11, 12)], [10, 10, 10, 10])

    def test_future_order_cannot_change_current_choice(self):
        cards, cfg = setup([1, 2, 6] + [3] * 11 + [9] * 11, first_turn_draw=False)
        other = cards[:3] + list(reversed(cards[3:]))
        for policy in rc.POLICIES:
            a = rc.simulate_trial(cards, cfg, policy)["turns"][0]
            b = rc.simulate_trial(other, cfg, policy)["turns"][0]
            self.assertEqual(a, b)

    def test_burn_and_draw_timing(self):
        cards, cfg = setup([99] * 25, horizon=6)
        trace = rc.simulate_trial(cards, cfg, "deploy")
        self.assertEqual([row["hand_after"] for row in trace["turns"]], [4, 5, 6, 7, 7, 7])
        self.assertEqual(trace["burns"], 2)
        cfg["first_turn_draw"] = False
        trace = rc.simulate_trial(cards, cfg, "deploy")
        self.assertEqual([row["hand_after"] for row in trace["turns"]], [3, 4, 5, 6, 7, 7])
        self.assertEqual(trace["burns"], 1)

    def test_payments_are_legal_and_cards_never_replayed(self):
        cards, cfg = setup([0, 1, 2, 3, 6] * 5, horizon=30)
        for policy in rc.POLICIES:
            trace = rc.simulate_trial(cards, cfg, policy)
            played = []
            for row in trace["turns"]:
                self.assertGreaterEqual(row["gold_after"], 0)
                self.assertEqual(row["spend"], sum(row["played_costs"]))
                self.assertEqual(row["prior_gold"] + row["income"] - row["spend"], row["gold_after"])
                self.assertLessEqual(row["hand_before"], 7)
                played.extend(row["played_ids"])
            self.assertEqual(len(played), len(set(played)))
            self.assertEqual(trace["cards_remaining_in_deck"], 0)

    def test_save_requires_observed_key(self):
        cards, cfg = setup([1] * 24 + [6])
        chosen, _, reason = rc.choose_subset(cards[:3], 2, "save", cfg)
        self.assertEqual(len(chosen), 2)
        self.assertIsNone(reason)
        chosen, _, reason = rc.choose_subset([cards[0], cards[-1]], 2, "save", cfg)
        self.assertEqual(chosen, [])
        self.assertEqual(reason, "save_for_known_key")
        chosen, _, _ = rc.choose_subset([cards[0], cards[-1]], 6, "save", cfg)
        self.assertEqual(chosen, [1])

    def test_role_and_annotation_are_not_policy_inputs(self):
        a, cfg = setup([{"cost": 2, "role": "defend", "annotation": "play me"}] * 25)
        b, _ = setup([{"cost": 2, "role": "combo", "annotation": "hold me"}] * 25)
        self.assertEqual(rc.choose_subset(a[:7], 4, "deploy", cfg), rc.choose_subset(b[:7], 4, "deploy", cfg))

    def test_resource_plan_changes_key_payment_time(self):
        cards, cfg = setup([1, 1, 6] + [99] * 22, first_turn_draw=False, horizon=4)
        self.assertEqual(rc.simulate_trial(cards, cfg, "save")["first_key_payment"], 3)
        self.assertEqual(rc.simulate_trial(cards, cfg, "deploy")["first_key_payment"], 4)
        chosen, budget, reason = rc.choose_subset(cards[:2], 4, "reserve", cfg)
        self.assertEqual(budget, 1)
        self.assertEqual(len(chosen), 1)
        self.assertEqual(reason, "reserve_budget")

    def test_reproducibility_and_policy_order_pairing(self):
        data = {"deck": [1, 2, 3, 5, 6] * 5, "trials": 20, "trace_trials": 2}
        first = rc.analyze(data)
        self.assertEqual(first, rc.analyze(data))
        reverse = rc.analyze({**data, "policies": list(reversed(rc.POLICIES))})
        self.assertEqual(first["policies"], reverse["policies"])

    def test_input_validation(self):
        for bad in ({"deck": [1] * 24}, {"deck": [True] * 25},
                    {"deck": [1] * 25, "opening_hand": 8}, {"deck": [1] * 25, "first": 1}):
            with self.assertRaises(ValueError):
                rc.normalize_input(bad)


if __name__ == "__main__":
    unittest.main()
