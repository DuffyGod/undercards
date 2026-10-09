import unittest

import resource_profile_bridge as bridge
import score_cards as cards
import unified_value as unified


def request(costs, **kwargs):
    return {"deck_costs": costs, "policy": "deploy",
            "future_income_available_fraction": .6,
            "resource_config": {"trials": 30, "seed": 20261008}, **kwargs}


class ResourceProfileTests(unittest.TestCase):
    def test_joint_representatives_are_observed_not_independent_means(self):
        result = bridge.build_profile(request([1, 2, 3, 5, 8] * 5))
        for summary in result["phase_summaries"].values():
            pairs = {(row["gold_before"], row["hand_before"]) for row in summary["joint_frequencies"]}
            self.assertAlmostEqual(sum(stats["conditional_nonempty_weight"] for stats in summary["buckets"].values()), 1)
            for stats in summary["buckets"].values():
                rep = stats["representative"]
                if rep is not None:
                    self.assertIn((rep["gold_before_play"], rep["hand_size_before_play"]), pairs)
        panel = unified.make_panel(result["unified_profile"])
        self.assertAlmostEqual(sum(row["weight"] for row in panel), 1)

    def test_all_observed_pairs_reach_scorer_without_representative_compression(self):
        result=bridge.build_profile(request([1,2,3,5,8]*5))
        panel=unified.make_panel(result['unified_profile'])
        self.assertEqual(result['unified_profile']['context_overrides'],{})
        for phase,summary in result['phase_summaries'].items():
            rows=[s for s in panel if s['own_turn']==int(phase)]
            phase_weight=result['unified_profile']['phase_weights'][phase]
            for observed in summary['joint_frequencies']:
                weight=sum(s['weight'] for s in rows if s['gold_before_play']==observed['gold_before']
                           and s['hand_size_before_play']==observed['hand_before'])
                self.assertAlmostEqual(weight/phase_weight,observed['conditional_nonempty_frequency'])

    def test_empty_bucket_retains_zero_weight_and_no_representative(self):
        result = bridge.build_profile(request([99] * 25))
        for phase, summary in result["phase_summaries"].items():
            self.assertEqual(summary["buckets"]["deployed"]["conditional_nonempty_weight"], 0)
            self.assertIsNone(summary["buckets"]["deployed"]["representative"])
            self.assertEqual(result["unified_profile"]["joint_resource_weights"][phase]["reserved"], 1)
            for role in unified.ROLES:
                self.assertNotIn(f"{role}-t{phase}-deployed", result["unified_profile"]["context_overrides"])

    def test_all_empty_phase_is_reported_without_normalized_fabrication(self):
        summary = bridge.summarize_phase([(2, 0)] * 10, 3)
        self.assertTrue(summary["no_nonempty_samples"])
        self.assertEqual(summary["empty_hand_rate"], 1)
        self.assertEqual(summary["joint_frequencies"], [])
        self.assertTrue(all(stats["conditional_nonempty_weight"] == 0 and stats["representative"] is None for stats in summary["buckets"].values()))

    def test_initial_gold_carry_and_second_player_are_not_clipped(self):
        for first, expected in ((True, {"3": 7, "5": 16, "8": 37}),
                                (False, {"3": 9, "5": 19, "8": 41})):
            result = bridge.build_profile(request([99] * 25, resource_config={"trials": 5, "seed": 9, "first": first}))
            self.assertEqual(result["unified_profile"]["second_player"], not first)
            for phase, gold in expected.items():
                rep = result["phase_summaries"][phase]["buckets"]["reserved"]["representative"]
                self.assertEqual(rep["gold_before_play"], gold)
            unified.make_panel(result["unified_profile"])

    def test_labels_do_not_affect_resource_profile(self):
        costs = [1, 2, 3, 5, 8] * 5
        decorated = [{"cost": value, "role": "unknown", "annotation": "valuable"} for value in costs]
        a, b = bridge.build_profile(request(costs)), bridge.build_profile(request(decorated))
        self.assertEqual(a, b)

    def test_id_lookup_uses_only_snapshot_costs(self):
        cost = next(card["cost"] for card in cards.load_cards() if card["id"] == 2)
        by_id = request([cost] * 25)
        del by_id["deck_costs"]
        by_id["deck_card_ids"] = [2] * 25
        a = bridge.build_profile(by_id)
        b = bridge.build_profile(request([cost] * 25))
        self.assertEqual(a["phase_summaries"], b["phase_summaries"])
        self.assertEqual(a["unified_profile"], b["unified_profile"])
        self.assertIn("snapshot_sha256", a["source"])

    def test_fraction_is_explicit_not_derived_from_spending_and_reproducible(self):
        data = request([0] * 25, future_income_available_fraction=.2)
        a = bridge.build_profile(data)
        self.assertEqual(a, bridge.build_profile(data))
        self.assertEqual(a["unified_profile"]["future_income_available_fraction"], .2)
        self.assertEqual(a["resource_config"]["trials"], 30)
        self.assertEqual(a["resource_config"]["seed"], 20261008)

    def test_invalid_inputs_fail(self):
        valid = request([1] * 25)
        cases = [{**valid, "deck_card_ids": [2] * 25},
                 {**valid, "deck_costs": [1] * 24},
                 {**valid, "policy": "quality_oracle"},
                 {**valid, "future_income_available_fraction": float("nan")},
                 {**valid, "resource_config": {"horizon": 7}}]
        missing = dict(valid)
        del missing["future_income_available_fraction"]
        cases.append(missing)
        for data in cases:
            with self.assertRaises(ValueError):
                bridge.build_profile(data)


if __name__ == "__main__":
    unittest.main()
