"""Checks guard actual ledger boundaries, not expected card rankings."""
import copy
import json
import tempfile
from pathlib import Path
import unittest

import score_cards as model


class LedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = model.load_cards()
        cls.by_id = {c["id"]: c for c in cls.cards}
        cls.reference, cls.counts = model.make_reference(cls.cards)

    def test_reference_is_real_and_cost_stratified(self):
        self.assertEqual(set(self.counts), {"4", "5", "6", "7"})
        self.assertAlmostEqual(sum(r["weight"] for r in self.reference), 1)
        for cost in range(4, 8):
            members = [r for r in self.reference if self.by_id[r["card_id"]]["cost"] == cost]
            self.assertAlmostEqual(sum(r["weight"] for r in members), .25)
        self.assertTrue(all(self.by_id[r["card_id"]]["pool_category"] == "ordinary_non_token"
                            for r in self.reference))

    def test_anchor_is_scale_and_no_duplicate_hand_or_slot_tax(self):
        row = model.score_card(self.by_id[15], self.reference)
        self.assertEqual(row["support_status"], "supported")
        self.assertAlmostEqual(row["gross_model_gold"], 5)
        self.assertAlmostEqual(row["net_model_gold"], 0)
        for role in row["roles"].values():
            self.assertEqual(len(role["ledger"]), 1)
            self.assertAlmostEqual(role["gross_model_gold"], 5)

    def test_attack_saturation_and_integer_thresholds(self):
        p = model.role_parameters("midrange")
        b = lambda a, h: model.body_value(a, h, self.reference, p)
        self.assertGreater(b(7, 7) - b(6, 7), 0)
        self.assertLess(b(7, 7) - b(6, 7), .77)
        self.assertLess(b(40, 7) - b(39, 7), b(7, 7) - b(6, 7))
        p["face_share"] = 0
        max_h = max(r["health"] for r in self.reference)
        self.assertAlmostEqual(model.body_value(max_h + 3, 7, self.reference, p),
                               model.body_value(max_h + 4, 7, self.reference, p))

    def test_cost_counterfactual_changes_only_cost(self):
        row = model.score_card(self.by_id[11], self.reference)
        self.assertAlmostEqual(row["sensitivity"]["cost_minus_1"]["complete_card_delta_model_gold"], 1)
        self.assertAlmostEqual(row["sensitivity"]["cost_plus_1"]["complete_card_delta_model_gold"], -1)

    def test_partial_omission_is_not_a_final_score_or_bound(self):
        for cid in (43, 469, 530, 649, 49):
            with self.subTest(card_id=cid):
                row = model.score_card(self.by_id[cid], self.reference)
                self.assertEqual(row["support_status"], "partial")
                self.assertIsNone(row["net_model_gold"])
                self.assertIsNone(row["gross_model_gold"])
                self.assertTrue(row["unsupported_effects"])
                self.assertIsNotNone(row["supported_terms_net_model_gold"])

    def test_no_fixed_status_bonuses_or_separate_exchange_rewards(self):
        row = model.score_card(self.by_id[530], self.reference)
        for ledger in row["ledger"].values():
            self.assertEqual([r["term"] for r in ledger], ["printed_body"])
        tsun = model.score_card(self.by_id[21], self.reference)
        self.assertEqual(tsun["support_status"], "partial")
        self.assertEqual([m["kind"] for m in tsun["parsed_modules"]], ["damage", "face_damage"])

    def test_damage_uses_removal_threshold_not_flat_unit_price(self):
        ref = model.BodyReference([{"card_id": -1, "attack": 3, "health": 3, "weight": 1}])
        p = model.role_parameters("midrange")
        p["enemy_presence"] = 1
        values = [model.effect_value({"kind": "damage", "amount": n,
                   "target": "enemy_monster", "evidence": "test"}, ref, p)["value_model_gold"]
                  for n in (1, 2, 3)]
        self.assertGreater(values[2] - values[1], values[1] - values[0])
        overkill = model.effect_value({"kind": "damage", "amount": 6,
                   "target": "enemy_monster", "evidence": "test"}, ref, p)["value_model_gold"]
        self.assertAlmostEqual(overkill, values[2])

    def test_draw_is_not_entire_drawn_body_and_does_not_draw_on_full_hand(self):
        modules, unknown = model.parse_effect(self.by_id[243])
        self.assertFalse(unknown)
        p = model.role_parameters("control")
        row = model.effect_value(modules[0], self.reference, p)
        self.assertLess(row["value_model_gold"], 1)
        p["hand_room"] = 0
        self.assertEqual(model.effect_value(modules[0], self.reference, p)["value_model_gold"], 0)

    def test_conditional_or_replacement_text_is_not_prefix_priced(self):
        card = copy.deepcopy(self.by_id[243])
        card["effect_readable"] = "Magic: Draw a card. If damaged, draw 3 instead."
        modules, unknown = model.parse_effect(card)
        self.assertFalse(modules)
        self.assertTrue(unknown)

    def test_annotation_cannot_set_score_or_parameters(self):
        card = self.by_id[11]
        good = {"card_id": 11, "printed_effect": card["effect_readable"],
                "modules": [{"kind": "buff", "evidence": card["effect_readable"],
                             "amount": 900, "condition": ""}],
                "conditions": [], "unresolved": [], "notes": "", "gold": 999,
                "parameters": {"face_share": 1}}
        raw = model.score_card(card, self.reference)
        gated = model.score_card(card, self.reference, good)
        self.assertAlmostEqual(raw["net_model_gold"], gated["net_model_gold"])
        self.assertEqual(raw["parameters"], gated["parameters"])
        bad = copy.deepcopy(good)
        bad["modules"][0]["evidence"] = "invented text"
        self.assertIsNone(model.score_card(card, self.reference, bad)["net_model_gold"])

    def test_roles_share_parameters_and_equal_aggregation(self):
        a = model.score_card(self.by_id[11], self.reference)
        b = model.score_card(self.by_id[13], self.reference)
        for role in model.ROLE_PARAMETERS:
            self.assertEqual(a["roles"][role]["parameters"], b["roles"][role]["parameters"])
        self.assertAlmostEqual(a["net_model_gold"], sum(r["net_model_gold"] for r in a["roles"].values()) / 4)

    def test_standard_target_condition_text_is_information_not_a_gate(self):
        card = self.by_id[11]
        annotation = {"card_id": 11, "printed_effect": card["effect_readable"],
                      "modules": [{"kind": "buff", "evidence": card["effect_readable"],
                                   "condition": "Must have an ally monster target", "condition_codes": ["target_exists"]}],
                      "conditions": ["Must have an ally monster target"], "condition_codes": ["target_exists"],
                      "unresolved": []}
        direct = model.score_card(card, self.reference)
        audited = model.score_card(card, self.reference, annotation, True)
        self.assertEqual(audited["support_status"], "supported")
        self.assertTrue(audited["formal_score_publishable"])
        self.assertAlmostEqual(direct["net_model_gold"], audited["net_model_gold"])
        self.assertTrue(audited["annotation_audit"]["conditions_text"])
        annotation["condition_codes"] = ["hand_size"]
        self.assertEqual(model.score_card(card, self.reference, annotation, True)["support_status"], "partial")
        annotation["condition_codes"] = ["invented_condition"]
        self.assertIsNone(model.score_card(card, self.reference, annotation, True)["net_model_gold"])

    def test_batch_inconsistency_prevents_formal_numeric_publication(self):
        card = self.by_id[15]
        annotation = {"card_id": 15, "printed_effect": card["effect_readable"],
                      "modules": [], "conditions": [], "condition_codes": [], "unresolved": []}
        result = model.run(self.cards, [15], {"consistency_passed": False, "annotations": [annotation]})
        row = result["scores"][0]
        self.assertEqual(result["publication_status"], "batch_rejected")
        self.assertIsNone(row["net_model_gold"])
        self.assertFalse(row["formal_score_publishable"])
        self.assertEqual(row["audit_status"], "batch_rejected")
        self.assertAlmostEqual(row["supported_terms_net_model_gold"], 0)

    def test_unannotated_requested_card_is_explicitly_unreviewed(self):
        result = model.run(self.cards, [15, 11], {"consistency_passed": True, "annotations": []})
        for row in result["scores"]:
            self.assertEqual(row["audit_status"], "unreviewed")
            self.assertFalse(row["formal_score_publishable"])
            self.assertFalse(row["annotation_audit"]["provided"])

    def test_annotation_unknown_kind_cannot_upgrade_supported_parser(self):
        card = self.by_id[11]
        annotation = {"card_id": 11, "printed_effect": card["effect_readable"],
                      "modules": [{"kind": "unknown", "evidence": card["effect_readable"]}],
                      "conditions": [], "unresolved": []}
        self.assertIsNone(model.score_card(card, self.reference, annotation, True)["net_model_gold"])
        annotation["modules"][0]["kind"] = "made_up"
        self.assertIsNone(model.score_card(card, self.reference, annotation, True)["net_model_gold"])

    def test_semantic_review_gate_is_separate_from_batch_consistency(self):
        card = self.by_id[15]
        annotations = {"annotations": [{"card_id": 15, "printed_effect": card["effect_readable"],
                                         "modules": [], "unresolved": []}],
                       "consistency_passed": True, "semantic_review_required": True}
        for value in (None, False):
            with self.subTest(semantic_audit_passed=value):
                annotations["semantic_audit_passed"] = value
                result = model.run(self.cards, [15], annotations)
                row = result["scores"][0]
                self.assertEqual(result["publication_status"], "semantic_review_pending")
                self.assertIsNone(row["gross_model_gold"])
                self.assertIsNone(row["net_model_gold"])
                self.assertFalse(row["formal_score_publishable"])
                self.assertAlmostEqual(row["supported_terms_gross_model_gold"], 5)
        annotations["semantic_audit_passed"] = True
        row = model.run(self.cards, [15], annotations)["scores"][0]
        self.assertTrue(row["formal_score_publishable"])
        self.assertAlmostEqual(row["net_model_gold"], 0)
        for value in ("true", 1):
            annotations["semantic_audit_passed"] = value
            with self.assertRaisesRegex(ValueError, "JSON boolean"):
                model.run(self.cards, [15], annotations)

    def test_annotation_snapshot_hash_is_verified_before_scoring(self):
        import hashlib
        digest = hashlib.sha256(model.DEFAULT_SNAPSHOT.read_bytes()).hexdigest()
        result = model.run(self.cards, [15], {"annotations": [], "snapshot_sha256": digest})
        self.assertEqual(result["snapshot_sha256"], digest)
        with self.assertRaisesRegex(ValueError, "does not match"):
            model.run(self.cards, [15], {"annotations": [], "snapshot_sha256": "not-the-snapshot"})

    def test_output_records_version_reference_and_blank_partial_headline(self):
        result = model.run(self.cards, [15, 530])
        self.assertEqual(result["parameter_version"], model.PARAMETER_VERSION)
        self.assertEqual(result["reference"]["total"], len(self.reference))
        with tempfile.TemporaryDirectory() as directory:
            path = model.write_outputs(result, Path(directory) / "test.json")
            restored = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsNone(restored["scores"][1]["net_model_gold"])
            self.assertTrue(path.with_suffix(".csv").exists())


if __name__ == "__main__":
    unittest.main()
