import copy
import random
import unittest

import candidate_resource_observations as obs
import resource_curve as resource
import score_cards


def request(costs, indexes=(0,), **kwargs):
    return {"deck_costs": costs, "candidate_indexes": list(indexes), "policy": "deploy",
            "resource_config": {"trials": 30, "seed": 19}, **kwargs}


def fixed(costs, indexes, phases, **cfg):
    cards, config, _ = resource.normalize_input({"deck": costs, **cfg})
    return obs.reconstruct_trial(cards, config, cfg.get("policy", "deploy"), indexes, phases)


class CandidateObservationsTests(unittest.TestCase):
    def test_phase_is_before_current_choice_and_physical_copies_do_not_merge(self):
        result = fixed([0] * 25, [0, 1, 4], [1, 2], opening_hand=3, first_turn_draw=True, horizon=2)
        first = result["phase_snapshots"]["1"]
        self.assertEqual(first["candidate_copy_states"], {"0": "in_hand", "1": "in_hand", "4": "not_yet_drawn"})
        self.assertEqual(first["candidate_proxy_played_on_this_turn"], [0, 1])
        self.assertEqual(first["hand_ids_before_decision"], [0, 1, 2, 3])
        second = result["phase_snapshots"]["2"]
        self.assertEqual(second["candidate_copy_states"], {"0": "used_before_decision", "1": "used_before_decision", "4": "in_hand"})
        self.assertEqual(result["copy_timings"]["0"]["first_in_hand_turn"], 0)
        self.assertIsNone(result["copy_timings"]["0"]["drawn_turn"])
        self.assertEqual(result["copy_timings"]["4"]["drawn_turn"], 2)

    def test_burn_does_not_enter_hand_or_become_payable_and_no_samples_are_fabricated(self):
        trial = fixed([99] * 7 + [0] + [99] * 17, [7], [1, 2], opening_hand=7, horizon=2)
        phase = trial["phase_snapshots"]["1"]
        self.assertEqual(phase["candidate_copy_states"]["7"], "burned")
        self.assertEqual(phase["group_state"], "all_copies_used_or_burned")
        self.assertEqual(phase["hand_before"], 7)
        self.assertNotIn(7, phase["hand_ids_before_decision"])
        self.assertFalse(phase["resource_payable_in_hand"])
        timing = trial["copy_timings"]["7"]
        self.assertEqual(timing["burned_turn"], 1)
        self.assertEqual(timing["drawn_turn"], 1)
        self.assertIsNone(timing["first_in_hand_turn"])
        self.assertIsNone(timing["proxy_played_turn"])
        self.assertIsNone(timing["first_resource_payable_turn"])
        empty = obs._joint([], 10)
        self.assertTrue(empty["no_conditioning_samples"])
        self.assertEqual(empty["joint_frequencies"], [])
        self.assertEqual(empty["conditioning_rate"], 0)

    def test_resource_affordability_precedes_proxy_play_under_reserve(self):
        cards, cfg, _ = resource.normalize_input({"deck": [2] + [99] * 24, "opening_hand": 1,
                                                 "first_turn_draw": False, "horizon": 3})
        result = obs.reconstruct_trial(cards, cfg, "reserve", [0], [1, 2, 3])
        self.assertEqual(result["copy_timings"]["0"]["first_resource_payable_turn"], 1)
        self.assertEqual(result["copy_timings"]["0"]["proxy_played_turn"], 3)
        self.assertEqual(result["group_first_resource_payable_turn"], 1)
        self.assertEqual(result["group_first_proxy_played_turn"], 3)
        self.assertEqual(result["phase_snapshots"]["3"]["candidate_copy_states"]["0"], "in_hand")

    def test_same_shuffled_seed_exactly_reuses_resource_trace_for_all_policies(self):
        for policy in resource.POLICIES:
            data = request([1, 2, 3, 5, 8] * 5, indexes=(0, 4), policy=policy,
                           resource_config={"trials": 5, "seed": 11, "trace_trials": 5})
            result = obs.analyze(data)
            cards, cfg, _ = resource.normalize_input({"deck": data["deck_costs"], **result["resource_config"]})
            rng = random.Random(cfg["seed"])
            for trial in result["traces"]:
                order = list(cards)
                rng.shuffle(order)
                self.assertEqual(trial["resource_trace"], resource.simulate_trial(order, cfg, policy))

    def test_unseen_tail_does_not_change_earlier_snapshot_or_decision(self):
        cards, cfg, _ = resource.normalize_input({"deck": [2, 1, 99, 3] + [5] * 21, "horizon": 8})
        other = cards[:4] + list(reversed(cards[4:]))
        other[-1] = {**other[-1], "cost": 0}
        for policy in resource.POLICIES:
            a = obs.reconstruct_trial(cards, cfg, policy, [0, 4], [1])
            b = obs.reconstruct_trial(other, cfg, policy, [0, 4], [1])
            self.assertEqual(a["phase_snapshots"], b["phase_snapshots"])
            self.assertEqual(a["resource_trace"]["turns"][0], b["resource_trace"]["turns"][0])

    def test_conditional_joint_frequencies_and_state_proportions_are_recomputable(self):
        data = request([1, 2, 3, 5, 8] * 5, indexes=(0, 1, 2),
                       resource_config={"trials": 50, "seed": 17, "trace_trials": 50})
        report = obs.analyze(data)
        for phase, summary in report["phase_summaries"].items():
            self.assertAlmostEqual(sum(summary["group_state_rates"].values()), 1)
            joint = summary["joint_resources_given_candidate_in_hand"]
            actual = [trial["phase_snapshots"][phase] for trial in report["traces"]
                      if trial["phase_snapshots"][phase]["candidate_copies_in_hand"]]
            self.assertEqual(joint["conditioning_observations"], len(actual))
            if actual:
                self.assertAlmostEqual(sum(row["conditional_frequency"] for row in joint["joint_frequencies"]), 1)
            self.assertAlmostEqual(sum(row["all_trial_frequency"] for row in joint["joint_frequencies"]), len(actual) / 50)
            for row in joint["joint_frequencies"]:
                self.assertEqual(row["count"], sum((sample["gold_before"], sample["hand_before"]) ==
                                                  (row["gold_before"], row["hand_before"]) for sample in actual))
            for stats in summary["physical_copies"].values():
                self.assertAlmostEqual(sum(stats["state_rates"].values()), 1)
                self.assertEqual(sum(stats["state_counts"].values()), 50)
        self.assertNotIn("unified_profile", report)
        self.assertNotIn("value", report)
        self.assertIn("never assigned zero", report["prior_use_value_boundary"])

    def test_second_player_income_and_retained_gold_are_not_clipped(self):
        for first, expected in ((True, {3: 7, 5: 16, 8: 37}), (False, {3: 9, 5: 19, 8: 41})):
            trial = fixed([99] * 25, [0], [3, 5, 8], first=first, horizon=8)
            for phase, gold in expected.items():
                sample = trial["phase_snapshots"][str(phase)]
                self.assertEqual(sample["gold_before"], gold)
                self.assertEqual(sample["candidate_copy_states"]["0"], "in_hand")
                self.assertLessEqual(sample["hand_before"], 7)

    def test_snapshot_lookup_selects_all_matching_copies_without_policy_labels(self):
        card_cost = next(c["cost"] for c in score_cards.load_cards() if c["id"] == 2)
        ids = {"deck_card_ids": [2] * 2 + [20] * 23, "candidate_card_id": 2, "policy": "deploy",
               "resource_config": {"trials": 10, "seed": 12}}
        by_id = obs.analyze(ids)
        by_cost = obs.analyze({"deck_costs": by_id["source"]["costs"], "candidate_indexes": [0, 1],
                              "policy": "deploy", "resource_config": ids["resource_config"]})
        self.assertEqual(by_id["source"]["candidate_indexes"], [0, 1])
        self.assertEqual(by_id["source"]["costs"][:2], [card_cost] * 2)
        self.assertEqual(by_id["phase_summaries"], by_cost["phase_summaries"])
        self.assertEqual(by_id["copy_timing_summaries"], by_cost["copy_timing_summaries"])
        labeled = request([{"cost": cost, "role": "high_quality", "annotation": "do not burn"}
                           for cost in [1, 2, 3, 5, 8] * 5])
        plain = request([1, 2, 3, 5, 8] * 5)
        self.assertEqual(obs.analyze(labeled), obs.analyze(plain))
        self.assertEqual(obs.analyze(plain), obs.analyze(plain))

    def test_zero_opening_no_first_draw_leaves_candidate_unseen_at_first_decision(self):
        trial = fixed([0] * 25, [0], [1, 2], opening_hand=0, first_turn_draw=False, horizon=2)
        first = trial["phase_snapshots"]["1"]
        self.assertEqual(first["hand_before"], 0)
        self.assertEqual(first["group_state"], "not_in_hand_with_unseen")
        self.assertFalse(first["any_candidate_opening_or_drawn"])
        self.assertEqual(trial["copy_timings"]["0"]["drawn_turn"], 2)
        self.assertEqual(trial["copy_timings"]["0"]["first_resource_payable_turn"], 2)

    def test_invalid_deck_selection_and_phase_inputs_fail(self):
        valid = request([1] * 25)
        invalid = [{**valid, "deck_card_ids": [2] * 25},
                   {**valid, "candidate_indexes": []}, {**valid, "candidate_indexes": [0, 0]},
                   {**valid, "candidate_indexes": [True]}, {**valid, "candidate_indexes": [25]},
                   {**valid, "candidate_card_id": 2}, {**valid, "phases": [1, 9]},
                   {**valid, "policy": "quality"}, {**valid, "resource_config": {"future_gold": 999}},
                   {**valid, "resource_config": {"horizon": 2}}]
        for data in invalid:
            with self.assertRaises(ValueError):
                obs.analyze(data)


if __name__ == "__main__":
    unittest.main()
