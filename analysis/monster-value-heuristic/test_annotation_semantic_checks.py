import copy
import unittest

import annotation_semantic_checks as checks


def fixture(text, **module_changes):
    card = {"id": 1, "name": "Synthetic", "effect_readable": text}
    module = {"kind": "damage", "trigger": "magic", "target": "enemy_monster", "amount": 1,
              "count": 1, "card_ref": None, "condition": "", "evidence": text,
              "amount_basis": "fixed", "stat": "none", "repeat_rule": "none"}
    module.update(module_changes)
    row = {"card_id": 1, "printed_effect": text, "modules": [module], "conditions": [],
           "condition_codes": [], "notes": "", "silence_exposure": "none"}
    return card, row


def codes(row, card, **kwargs):
    return {issue["code"] for issue in checks.check_annotation(row, card, **kwargs)}


class SemanticChecks(unittest.TestCase):
    def test_ordinary_kill_is_not_exact_and_child_bullseye_does_not_exempt(self):
        text = "After this attacks and kills a monster, summon a monster with Bullseye."
        card, row = fixture(text, trigger="attack")
        row["condition_codes"] = ["exact_kill"]
        self.assertIn("ordinary_kill_is_not_exact_kill", codes(row, card))
        row["condition_codes"] = ["target_exists"]
        self.assertNotIn("ordinary_kill_is_not_exact_kill", codes(row, card))

    def test_dodge_per_turn_claim_requires_own_reset(self):
        card, row = fixture("Dodge (1).", kind="combat", trigger="passive", target="self", condition="Dodge每回合可闪避1次")
        self.assertIn("dodge_unfounded_turn_reset", codes(row, card))
        row["modules"][0]["condition"] = "Dodge消耗一次，不会每回合重置"
        self.assertNotIn("dodge_unfounded_turn_reset", codes(row, card))
        card["effect_readable"] = "Dodge (1). Turn start: Gain +1 Dodge."
        row["printed_effect"] = card["effect_readable"]
        row["modules"][0]["condition"] = "每回合获得Dodge"
        self.assertNotIn("dodge_unfounded_turn_reset", codes(row, card))

    def test_dodge_on_another_entity_is_not_caster_dodge(self):
        card, row = fixture("Magic: Give an ally Dodge (1).", kind="combat", target="ally", condition="友军每回合获得Dodge")
        self.assertNotIn("dodge_unfounded_turn_reset", codes(row, card))

    def test_bullseye_zero_damage_vs_zero_hp(self):
        card, row = fixture("Bullseye: Draw a card.", kind="draw", trigger="bullseye", target="self", condition="恰好造成0并击杀")
        self.assertIn("bullseye_not_zero_damage", codes(row, card))
        row["modules"][0]["condition"] = "目标HP恰好归0并死亡，不是造成0伤害"
        self.assertNotIn("bullseye_not_zero_damage", codes(row, card))

    def test_bullseye_on_generated_entity_is_not_own_trigger(self):
        card, row = fixture("Magic: Summon a monster with Bullseye.", kind="summon", condition="生成物Bullseye造成0伤害")
        self.assertNotIn("bullseye_not_zero_damage", codes(row, card))

    def test_dynamic_total_checks_typed_count_and_prose(self):
        card, row = fixture("Magic: Deal 1 DMG to a monster for each other monster.", amount_basis="other_monster_count", condition="伤害次数等于其他怪物数")
        self.assertIn("dynamic_total_prose_claims_multiple_hits", codes(row, card))
        row["modules"][0]["condition"] = "一次总伤害，等于其他怪物数"
        self.assertNotIn("dynamic_total_prose_claims_multiple_hits", codes(row, card))
        row["modules"][0]["count"] = 3
        self.assertIn("dynamic_total_is_one_instance", codes(row, card))

    def test_external_magic_not_undone_by_caster_silence(self):
        card, row = fixture("Magic: Give an ally monster +2 ATK.", kind="buff", target="ally", stat="ATK")
        row["silence_exposure"] = "body"
        self.assertIn("caster_silence_cannot_undo_external_magic", codes(row, card))
        row["silence_exposure"] = "none"
        self.assertNotIn("caster_silence_cannot_undo_external_magic", codes(row, card))
        row["modules"][0]["target"] = "self"
        row["silence_exposure"] = "body"
        self.assertNotIn("caster_silence_cannot_undo_external_magic", codes(row, card))

    def test_reference_existence_and_provided_face_are_distinct(self):
        card, row = fixture("Dust: Summon Child [#2].", kind="summon", trigger="dust", target="self", card_ref=2)
        self.assertIn("nonexistent_reference", codes(row, card, known_card_ids={1}))
        self.assertIn("unprovided_reference_face", codes(row, card, known_card_ids={1, 2}))
        ref = {2: {"id": 2, "name": "Child", "attack": 2, "health": 3}}
        self.assertFalse(codes(row, card, references=ref, known_card_ids={1, 2}))
        row["modules"][0]["card_ref"] = 3
        self.assertIn("unsupported_specific_reference", codes(row, card, references=ref, known_card_ids={1, 2, 3}))

    def test_generated_attributes_without_a_face_or_literal_source(self):
        card, row = fixture("Magic: Summon a random monster.", kind="summon", condition="生成物拥有Taunt和ATK 4")
        self.assertIn("unprovided_generated_attributes", codes(row, card))
        row["modules"][0]["condition"] = "随机召唤，无确定属性"
        self.assertNotIn("unprovided_generated_attributes", codes(row, card))

    def test_exclusive_choice_needs_schema_not_prose(self):
        card, row = fixture("Magic: Deal 2 DMG or give an ally +2 ATK.")
        row["modules"].append(copy.deepcopy(row["modules"][0]))
        row["modules"][1].update(kind="buff", target="ally", stat="ATK")
        row["notes"] = "两个模块互斥"
        self.assertIn("exclusive_choice_requires_schema", codes(row, card))
        for index, module in enumerate(row["modules"]):
            module.update(choice_group="mode1", choice_branch=str(index))
        self.assertNotIn("exclusive_choice_requires_schema", codes(row, card))
        card, row = fixture("Magic: Summon a rare or epic monster.", kind="summon")
        self.assertNotIn("exclusive_choice_requires_schema", codes(row, card))

    def test_optional_schema(self):
        card, row = fixture("Magic: You may draw a card.", kind="draw", target="self")
        self.assertIn("optional_effect_requires_schema", codes(row, card))
        row["modules"][0]["optional"] = True
        self.assertNotIn("optional_effect_requires_schema", codes(row, card))

    def test_bad_evidence_and_no_auto_approval(self):
        card, row = fixture("Magic: Deal 2 DMG.")
        original = copy.deepcopy(row)
        report = checks.check_batch([row], {1: card})
        self.assertTrue(report["semantic_review_required"])
        self.assertNotIn("semantic_audit_passed", report)
        self.assertEqual(row, original)
        row["modules"][0]["evidence"] = "Magic: Deal three DMG."
        self.assertIn("nonliteral_evidence", codes(row, card))


if __name__ == "__main__":
    unittest.main()
