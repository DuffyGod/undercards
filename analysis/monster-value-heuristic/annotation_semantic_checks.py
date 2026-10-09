"""Conservative issue detectors for semantic-annotations-v3, never auto approval.

Only literal source text and explicitly supplied card faces are evidence.
Issue absence means no implemented detector fired, not semantic correctness.
CLI is read-only: --annotations FILE --snapshot FILE [--manifest FILE].
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

VERSION = "semantic-issue-detectors-v1"
OWN_BULLSEYE = re.compile(r"(?:^|[.;]\s*)Bullseye\s*:", re.I)
OWN_DODGE = re.compile(r"(?:^|[.;]\s*)Dodge\s*\(\s*\d+\s*\)", re.I)
RESET_DODGE = re.compile(r"(?:^|[.;]\s*)Turn start\s*:\s*(?:This\s+)?Gain\b[^.;]*Dodge", re.I)
NEGATION = re.compile(r"不能|不可|不是|不会|不应|不得|并非|不要|无依据|没有.*依据|\b(?:not|never|cannot|don't|doesn't)\b", re.I)
ZERO_DAMAGE = re.compile(r"造成\s*0\s*(?:点)?\s*(?:伤害)?|\b(?:deal|deals|dealing)\s+(?:0|zero)\s+(?:DMG|damage)\b", re.I)
PER_TURN = re.compile(r"每(?:个)?回合|每轮|\beach turn\b|\bevery turn\b|\bper turn\b", re.I)
DODGE_WORD = re.compile(r"Dodge|闪避|抵消.*伤害实例", re.I)
INSTANCE_PROSE = re.compile(r"伤害次数|次数(?:等于|取决于|为)|多次|多个\s*1\s*(?:点)?|N\s*个.*伤害|\bmultiple\s+(?:1|one)[ -](?:point|damage)|\bnumber of (?:hits|instances)\b", re.I)
CHOICE_OR = re.compile(r"\bor\s+(?:deal|give|gain|draw|summon|add|return|kill|choose|erase|attack|send)\b", re.I)
OPTIONAL = re.compile(r"(?:^|[.;]\s*)(?:Optional\s*:|(?:Magic\s*:\s*)?(?:You\s+)?may\s+(?:deal|give|gain|draw|summon|add|return|kill|choose|erase|attack|send)\b)", re.I)
ATTRIBUTES = re.compile(r"\b(?:ATK|HP|COST)\s*[+-]?\s*\d+|\b\d+\s*/\s*\d+\b|Taunt|Charge|Haste|Dodge|Armor|嘲讽|闪避|护甲", re.I)
CHILD_SUBJECT = re.compile(r"召唤物|生成物|召唤的|生成的|\b(?:summoned|generated|token)\b", re.I)


def _sentences(value):
    return [s.strip() for s in re.split(r"[。；;\n]", value or "") if s.strip()]


def _assertions(values):
    """Do not mistake explicitly negated warnings for asserted mechanics."""
    return [s for value in values if isinstance(value, str) for s in _sentences(value) if not NEGATION.search(s)]


def check_annotation(row, card, references=None, known_card_ids=None):
    """Return issues only. references are faces actually provided to the annotator.

    known_card_ids may come from the catalog and are used only for existence,
    never as permission to infer unseen attributes.
    """
    references = references or {}
    known = set(known_card_ids) if known_card_ids is not None else {card.get("id"), *references}
    cid = row.get("card_id")
    text = card.get("effect_readable", "")
    issues = []

    def issue(code, message, index=None, source="", observed=None, severity="contradiction"):
        issues.append({"card_id": cid, "module_index": index, "code": code,
                       "severity": severity, "source_evidence": source,
                       "observed": observed, "message": message})

    if row.get("printed_effect") != text:
        issue("altered_card_text", "Annotation card text does not match the supplied card face.", source=text, observed=row.get("printed_effect"))
    modules = row.get("modules")
    if not isinstance(modules, list):
        issue("invalid_modules", "Cannot perform semantic checks without a module list.", severity="structure")
        return issues
    valid = []
    for index, module in enumerate(modules):
        if not isinstance(module, dict):
            issue("invalid_module", "Module is not an object.", index, severity="structure")
            continue
        evidence = module.get("evidence")
        if not isinstance(evidence, str) or not evidence or evidence not in text:
            issue("nonliteral_evidence", "Module evidence must be an exact, nonempty source substring.", index, text, evidence, "structure")
            continue
        valid.append((index, module))

    own_bullseye = any(m.get("trigger") == "bullseye" and OWN_BULLSEYE.search(m["evidence"]) for _, m in valid)
    ordinary_kill = [(i, m) for i, m in valid if m.get("trigger") == "attack" and re.search(r"\bthis attacks and kills\b", m["evidence"], re.I)]
    if ordinary_kill and "exact_kill" in (row.get("condition_codes") or []) and not own_bullseye and not re.search(r"\bexact(?:ly)?\b", text, re.I):
        i, m = ordinary_kill[0]
        issue("ordinary_kill_is_not_exact_kill", "Ordinary attack-and-kill permits overkill; a Bullseye mentioned on another entity does not change this trigger.", i, m["evidence"], "exact_kill")

    for index, module in valid:
        evidence = module["evidence"]
        condition = module.get("condition") or ""
        if module.get("kind") == "combat" and module.get("target") == "self" and OWN_DODGE.search(evidence):
            prose = _assertions([condition, row.get("notes", ""), *(row.get("conditions") or [])])
            claims = [s for s in prose if PER_TURN.search(s) and DODGE_WORD.search(s)]
            if claims and not RESET_DODGE.search(text):
                issue("dodge_unfounded_turn_reset", "Dodge consumes damage instances; no own Turn start: Gain Dodge clause supports this per-turn claim.", index, evidence, claims)

        if module.get("trigger") == "bullseye" and OWN_BULLSEYE.search(evidence):
            claims = [s for s in _assertions([condition, row.get("notes", ""), *(row.get("conditions") or [])]) if ZERO_DAMAGE.search(s)]
            if claims:
                issue("bullseye_not_zero_damage", "Bullseye requires the victim to reach exactly 0 HP and die, not the damage dealt to be zero.", index, evidence, claims)

        dynamic_damage = module.get("kind") == "damage" and re.search(r"\bDeal\b[^.;]*\bDMG\b[^.;]*\bfor each other monster\b", evidence, re.I)
        if dynamic_damage:
            if module.get("amount_basis") != "other_monster_count":
                issue("dynamic_damage_wrong_basis", "The source specifies a total damage amount scaled by other monster count.", index, evidence, module.get("amount_basis"))
            if module.get("count") != 1 or module.get("repeat_rule") not in ("none", None):
                issue("dynamic_total_is_one_instance", "The dynamic amount is one damage instance; count cannot stand for the number of other monsters.", index, evidence, {"count": module.get("count"), "repeat_rule": module.get("repeat_rule")})
            # Only this module and explicitly damage-related row conditions.
            # A separate attack repeat module must not be mistaken for this hit.
            prose = _assertions([condition, *(row.get("conditions") or [])])
            claims = [s for s in prose if INSTANCE_PROSE.search(s)]
            if claims:
                issue("dynamic_total_prose_claims_multiple_hits", "Typed single-instance total conflicts with prose describing a varying number of damage instances.", index, evidence, claims)

        ref = module.get("card_ref")
        if ref is not None:
            if type(ref) is not int or ref not in known:
                issue("nonexistent_reference", "Referenced card ID does not exist in the supplied catalog IDs.", index, evidence, ref)
            elif ref not in references:
                issue("unprovided_reference_face", "Referenced card face was not provided; generated-body properties cannot be certified from memory.", index, evidence, ref, "dependency_gap")
            if type(ref) is int:
                name = references.get(ref, {}).get("name", "")
                if f"[#{ref}]" not in evidence and not (name and name in evidence):
                    issue("unsupported_specific_reference", "The module assigns a specific generated/reference identity not present in its source evidence.", index, evidence, ref)
        elif module.get("kind") in ("summon", "draw"):
            for claim in _assertions([condition]):
                if CHILD_SUBJECT.search(claim):
                    unsupported = [value for value in ATTRIBUTES.findall(claim) if value.lower() not in evidence.lower()]
                    if unsupported:
                        issue("unprovided_generated_attributes", "Generated-object attributes are asserted without an identified supplied face or literal source support.", index, evidence, unsupported, "dependency_gap")

    pure_external_magic = bool(valid) and len(valid) == len(modules) and all(
        m.get("trigger") == "magic" and m.get("target") in ("ally", "enemy", "enemy_monster", "all_enemy_monsters", "opponent", "hand")
        and m.get("kind") in ("buff", "discount", "tax") for _, m in valid)
    if pure_external_magic and row.get("silence_exposure") in ("body", "body_and_future"):
        issue("caster_silence_cannot_undo_external_magic", "Later silence of the caster does not erase stat/cost modifiers already applied to other entities.", source=text, observed=row.get("silence_exposure"))

    # Use clauses containing actual choice verbs, not 'rare or epic' or keyword
    # descriptions of another card. V3 has no machine-readable choice groups.
    choice_modules = [(i, m) for i, m in valid if m.get("trigger") == "magic" and CHOICE_OR.search(m["evidence"])]
    if choice_modules:
        groups = [m.get("choice_group") for _, m in choice_modules]
        branches = [m.get("choice_branch") for _, m in choice_modules]
        if not all(groups) or len(set(groups)) != 1 or not all(branches) or len(set(branches)) != len(branches):
            issue("exclusive_choice_requires_schema", "Source alternatives need an explicit shared choice group and distinct branches; prose-only mutual exclusion is insufficient for additive scoring.", source=choice_modules[0][1]["evidence"], severity="schema_gap")
    optional_modules = [(i, m) for i, m in valid if OPTIONAL.search(m["evidence"]) and m.get("trigger") == "magic"]
    for index, module in optional_modules:
        if module.get("optional") is not True:
            issue("optional_effect_requires_schema", "Source permission requires a typed optional flag; it cannot be treated as mandatory output.", index, module["evidence"], severity="schema_gap")
    return issues


def check_batch(rows, cards, references=None):
    issues = []
    for row in rows:
        if not isinstance(row, dict) or row.get("card_id") not in cards:
            issues.append({"card_id": row.get("card_id") if isinstance(row, dict) else None,
                           "code": "missing_source_card", "severity": "structure",
                           "message": "No supplied original card face exists for this annotation."})
            continue
        issues.extend(check_annotation(row, cards[row["card_id"]], references, cards.keys()))
    return {"checker_version": VERSION, "annotations_checked": len(rows), "issues": issues,
            "semantic_review_required": True,
            "interpretation": "Issue absence is not semantic approval. Checks neither modify annotations nor estimate numerical values."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, default=Path(__file__).resolve().parents[2] / "skills/undercards/references/snapshot.json")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    data = json.loads(args.annotations.read_text(encoding="utf-8"))
    rows = data.get("data", data).get("annotations", [])
    cards = {c["id"]: c for c in json.loads(args.snapshot.read_text(encoding="utf-8"))["cards"]}
    references = {}
    if args.manifest:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        for task in manifest["tasks"]:
            for card in task["context"].get("references", []) + task["context"].get("cards", []):
                references[card["id"]] = card
    print(json.dumps(check_batch(rows, cards, references), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
