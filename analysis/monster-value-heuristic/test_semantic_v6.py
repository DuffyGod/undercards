import copy
import unittest

import semantic_v6 as v


class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.examples = {x["correct_annotation"]["card_id"]: x["correct_annotation"] for x in v.few_shots()}

    def validate_row(self, row):
        return v.validate({"annotations": [row]}, [row["card_id"]])

    def test_all_twelve_fewshots_are_valid_and_no_prices(self):
        self.assertEqual(len(self.examples), 12)
        for cid, row in self.examples.items():
            with self.subTest(card=cid):
                self.assertEqual(self.validate_row(row), [])
                self.assertNotIn("gross_model_gold", str(row))

    def test_same_branch_multiple_actions_are_bundled(self):
        row = self.examples[394]
        bundles = v.choice_bundles(row["modules"])
        self.assertEqual([b["module_indexes"] for b in bundles], [[0, 1], [2, 3]])
        self.assertEqual(row["modules"][3]["recipient_ref"], "c")

    def test_forward_self_and_cross_branch_binding_rejected(self):
        row = copy.deepcopy(self.examples[394])
        row["modules"][3]["recipient_ref"] = "d"
        self.assertTrue(any("future/self" in e for e in self.validate_row(row)))
        row["modules"][1]["recipient"] = "event_output"
        row["modules"][1]["recipient_ref"] = "c"
        self.assertTrue(any("future/self" in e for e in self.validate_row(row)))
        row = copy.deepcopy(self.examples[394])
        row["modules"][3]["choice_branch"] = "left"
        row["modules"][3]["branch_guard"] = {"code": "left_side", "value": True}
        self.assertTrue(any("unavailable choice branch" in e for e in self.validate_row(row)))

    def test_shock_is_not_magic_and_pronouns_are_distinct(self):
        row = copy.deepcopy(self.examples[775])
        row["modules"][2]["trigger"] = "magic"
        self.assertTrue(any("mislabeled magic" in e for e in self.validate_row(row)))
        self.assertEqual([m["recipient"] for m in self.examples[10001]["modules"]], ["player_self", "monster_this"])

    def test_generated_modifiers_bind_to_output_and_cost_is_present(self):
        modules = self.examples[471]["modules"]
        self.assertEqual(modules[0]["recipient"], "player_self")
        self.assertEqual([m["recipient_ref"] for m in modules[2:]], ["b", "b", "b"])
        self.assertEqual(modules[2]["stat"], "COST")
        self.assertEqual(modules[2]["amount"], 1)

    def test_hand_empty_is_distinct_and_dynamic_multiplier_required(self):
        row = copy.deepcopy(self.examples[503])
        self.assertEqual(row["modules"][0]["amount_basis"], "hand_empty_after_play")
        row["modules"][0]["amount"] = None
        self.assertTrue(any("explicit multiplier" in e for e in self.validate_row(row)))

    def test_normal_kill_is_not_exact_and_forced_choice_is_not_free(self):
        row = copy.deepcopy(self.examples[201])
        row["condition_codes"].append("exact_kill")
        self.assertTrue(any("ordinary kill" in e for e in self.validate_row(row)))
        row = copy.deepcopy(self.examples[948])
        self.assertEqual(row["modules"][0]["choice_mode"], "condition")
        row["modules"][0]["branch_guard"] = None
        self.assertTrue(any("requires an explicit guard" in e for e in self.validate_row(row)))

    def test_source_count_event_dependencies_and_filter_validation(self):
        row = copy.deepcopy(self.examples[664])
        self.assertEqual(row["modules"][1]["count_expression"]["source_ref"], "a")
        row["modules"][3]["amount_expression"]["source_ref"] = "later"
        self.assertTrue(any("future/self" in e for e in self.validate_row(row)))
        row = copy.deepcopy(self.examples[664])
        row["modules"][0]["count_expression"]["filters"] = [{"kind": "eval", "value": "arbitrary code"}]
        self.assertTrue(any("invalid finite filter" in e for e in self.validate_row(row)))

    def test_cost_and_stat_sources_are_finite_typed_data(self):
        row = v.annotation(10002, "Magic: Gain HP equal to this card's COST.",
                           [v.module("a", "buff", "magic", "monster_this", "Magic: Gain HP equal to this card's COST.",
                                     1, basis="source_cost", stat="HP", amount_expression=v.expression("monster_this", stat="COST"))])
        self.assertEqual(self.validate_row(row), [])
        row["modules"][0]["amount_expression"]["stat"] = "ATK"
        self.assertTrue(any("source_cost" in e for e in self.validate_row(row)))

    def test_signature_ignores_prose_and_alpha_renames_but_preserves_binding(self):
        row = copy.deepcopy(self.examples[471])
        reference = v.signature(row)
        row["notes"] = "Different wording"
        for m in row["modules"]:
            m["condition"] = "Explanation only"
            m["module_id"] = "renamed-" + m["module_id"]
            if m["recipient_ref"]:
                m["recipient_ref"] = "renamed-" + m["recipient_ref"]
        self.assertEqual(reference, v.signature(row))
        row["modules"][2]["amount"] = 2
        self.assertNotEqual(reference, v.signature(row))

    def test_literal_evidence_placeholder_unknown_and_full_schema(self):
        row = copy.deepcopy(self.examples[138])
        row["modules"][0]["evidence"] = "Invented amount"
        self.assertTrue(any("exact nonempty substring" in e for e in self.validate_row(row)))
        row = v.annotation(571, "WAITING FOR A NEW EFFECT", [], timing="none", status="placeholder", unresolved=["Placeholder, not a usable printed ability"])
        self.assertEqual(self.validate_row(row), [])
        row = copy.deepcopy(self.examples[138])
        row["modules"][0]["amount_basis"] = "unknown"
        self.assertTrue(any("partial status" in e for e in self.validate_row(row)))
        row["annotation_status"] = "partial"
        self.assertEqual(self.validate_row(row), [])
        row["extra"] = True
        self.assertTrue(self.validate_row(row))

    def test_state_switches_player_damage_and_partial_full_heal(self):
        row = self.examples[958]
        self.assertEqual(row["modules"][1]["recipient"], "all_enemies")
        self.assertEqual([m["amount"] for m in row["modules"] if m["kind"] == "state_change"], [0, 1])
        self.assertEqual(row["annotation_status"], "partial")
        self.assertEqual(row["silence_exposure"], "future")

    def test_source_binding_and_malformed_enums_return_errors(self):
        row = copy.deepcopy(self.examples[471])
        row["modules"][2]["source"] = "event_output"
        row["modules"][2]["source_ref"] = "b"
        self.assertEqual(self.validate_row(row), [])
        row["modules"][2]["source_ref"] = "e"
        self.assertTrue(self.validate_row(row))
        for field in ("kind", "amount_basis", "recipient", "trigger"):
            row = copy.deepcopy(self.examples[138])
            row["modules"][0][field] = []
            self.assertTrue(self.validate_row(row))
        row["timing"] = {}
        self.assertTrue(self.validate_row(row))

    def test_parsed_draw_cannot_have_unknown_fixed_count(self):
        row = v.annotation(243, "Magic: Draw a card.", [v.module("a", "draw", "magic", "hand_self", "Magic: Draw a card.")])
        row["modules"][0]["count"] = None
        self.assertTrue(any("fixed count" in e for e in self.validate_row(row)))
        row["modules"][0]["count_basis"] = "unknown"
        self.assertTrue(any("partial status" in e for e in self.validate_row(row)))
        row["annotation_status"] = "partial"
        self.assertEqual(self.validate_row(row), [])
        row["modules"][0]["count_basis"] = "fixed"
        row["modules"][0]["count"] = 1
        row["annotation_status"] = "parsed"
        self.assertEqual(self.validate_row(row), [])


if __name__ == "__main__":
    unittest.main()
