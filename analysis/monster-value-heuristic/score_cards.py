"""Shared, deliberately narrow heuristic ledger; no API or battle simulation.

Model-G is a normative scale anchored to the printed Aaron body, not measured
Gold equivalence. Unimplemented text makes the headline score null. Annotation
models can audit support, never supply prices, scores, or parameter overrides.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SNAPSHOT = ROOT / "skills/undercards/references/snapshot.json"
PARAMETER_VERSION = "heuristic-ledger-0.1.0"
ANCHOR = {"card_id": 15, "name": "Aaron", "attack": 6, "health": 5,
          "model_gold": 5, "meaning": "printed-body scale anchor, not a strength label"}
ROLE_PARAMETERS = {
    "aggro": {"face_share": .12, "enemy_presence": .90, "enemy_count": 1.8,
              "ally_presence": .60, "draw_value": .65, "face_damage_value": .18},
    "control": {"face_share": .20, "enemy_presence": .65, "enemy_count": 1.2,
                "ally_presence": .70, "draw_value": .90, "face_damage_value": .25},
    "combo": {"face_share": .35, "enemy_presence": .45, "enemy_count": 1.0,
              "ally_presence": .65, "draw_value": .60, "face_damage_value": .40},
    "midrange": {"face_share": .20, "enemy_presence": .80, "enemy_count": 1.5,
                 "ally_presence": .75, "draw_value": .80, "face_damage_value": .25},
}
COMMON_PARAMETERS = {"joint_threshold_weight": .40, "hand_room": .75,
                     "future_draw_use": .75}
CONTEXT_PARAMETERS = {
    "low_context": {"presence_multiplier": .75, "count_multiplier": .75,
                    "draw_multiplier": .60, "face_multiplier": .60,
                    "threshold_weight": .20, "face_share_shift": -.08},
    "central": {"presence_multiplier": 1., "count_multiplier": 1.,
                "draw_multiplier": 1., "face_multiplier": 1.,
                "threshold_weight": .40, "face_share_shift": 0.},
    "high_context": {"presence_multiplier": 1.15, "count_multiplier": 1.25,
                     "draw_multiplier": 1.40, "face_multiplier": 1.40,
                     "threshold_weight": .60, "face_share_shift": .08},
}


class BodyReference(list):
    """Immutable-by-convention reference with a per-run evaluation cache."""
    def __init__(self, rows):
        super().__init__(rows)
        self.body_cache = {}
        self.coupled_window_cache = {}


def load_cards(path=DEFAULT_SNAPSHOT):
    return json.loads(Path(path).read_text(encoding="utf-8"))["cards"]


def make_reference(cards):
    """Equal cost strata, equal ordinary printed bodies within each stratum.

    Reference text is intentionally excluded: these are target-body situations,
    never claims that all printed cards have the quality of a vanilla monster.
    """
    rows = []
    counts = {}
    for cost in range(4, 8):
        group = [c for c in cards if c.get("card_type") == "monster"
                 and c.get("pool_category") == "ordinary_non_token"
                 and c.get("cost") == cost and c.get("health", 0) > 0]
        if not group:
            raise ValueError(f"Reference cost stratum {cost} is empty")
        counts[str(cost)] = len(group)
        rows.extend({"card_id": c["id"], "attack": c["attack"],
                     "health": c["health"], "weight": 1 / (4 * len(group))}
                    for c in group)
    return BodyReference(rows), counts


def role_parameters(role, context="central"):
    p = dict(ROLE_PARAMETERS[role])
    c = CONTEXT_PARAMETERS[context]
    p.update(COMMON_PARAMETERS)
    p["face_share"] = min(1, max(0, p["face_share"] + c["face_share_shift"]))
    p["joint_threshold_weight"] = c["threshold_weight"]
    for key in ("enemy_presence", "ally_presence"):
        p[key] = min(1, p[key] * c["presence_multiplier"])
    p["enemy_count"] = min(4, p["enemy_count"] * c["count_multiplier"])
    p["draw_value"] *= c["draw_multiplier"]
    p["face_damage_value"] *= c["face_multiplier"]
    return p


def _body_features(attack, health, reference, parameters):
    if health <= 0:
        return 0., 0.
    attack = max(0, attack)
    share = parameters["face_share"]
    effective_attack = share * attack + (1 - share) * sum(
        r["weight"] * min(attack, r["health"]) for r in reference)
    # Includes non-damaging defensive bodies; avoids valuing all zero-ATK as 0.
    continuous = math.sqrt((effective_attack + .5) * health)
    thresholds = sum(r["weight"] * (
        int(attack >= r["health"]) + int(health > r["attack"])
        + int(attack >= r["health"] and health > r["attack"])) for r in reference)
    return continuous, thresholds


def body_value(attack, health, reference, parameters):
    cache = getattr(reference, "body_cache", None)
    key = (attack, health, parameters["face_share"], parameters["joint_threshold_weight"])
    if cache is not None and key in cache:
        return cache[key]
    c0, t0 = _body_features(ANCHOR["attack"], ANCHOR["health"], reference, parameters)
    threshold = parameters["joint_threshold_weight"]
    alpha = (ANCHOR["model_gold"] - threshold * t0) / c0
    c, t = _body_features(attack, health, reference, parameters)
    value = alpha * c + threshold * t
    if cache is not None:
        cache[key] = value
    return value


def _module(kind, evidence, amount, target):
    return {"kind": kind, "trigger": "magic", "amount": amount,
            "target": target, "evidence": evidence}


def parse_effect(card):
    """Only complete, unambiguous text templates enter a numeric module.

    No keyword scanning that mistakes a referenced card's status for this card's
    status. No prefix parsing before an 'instead', conditional, or continuation.
    """
    text = card.get("effect_readable", "").strip()
    unknown = []
    # Prefixes still receive no price; stripping permits independent Magic audit.
    while True:
        m = re.match(r"^(Haste|Dodge \(\d+\))\.\s*", text)
        if not m:
            break
        unknown.append("combat bundle unsupported: " + m.group(0).strip())
        text = text[m.end():]
    if not text:
        return [], unknown
    patterns = [
        (r"Magic: Give all enemy monsters -(\d+) ATK\.", "debuff", "all_enemy_monsters"),
        (r"Magic: Give an ally monster \+(\d+) ATK\.", "buff_attack", "ally"),
        (r"Magic: Give an ally monster \+(\d+) HP\.", "buff_health", "ally"),
        (r"Magic: Deal (\d+) DMG to an enemy monster\.", "damage", "enemy_monster"),
        (r"Magic: Deal (\d+) DMG to all enemy monsters\.", "damage", "all_enemy_monsters"),
        (r"Magic: Deal (\d+) DMG to the opponent\.", "face_damage", "opponent"),
        (r"Magic: Draw (\d+) cards\.", "draw", "hand"),
    ]
    for pattern, kind, target in patterns:
        m = re.fullmatch(pattern, text)
        if m:
            return [_module(kind, text, int(m.group(1)), target)], unknown
    if text == "Magic: Draw a card.":
        return [_module("draw", text, 1, "hand")], unknown
    m = re.fullmatch(r"Magic: Deal DMG (\d+)\.", text)
    if m and card.get("target") == "ALL":
        return [_module("damage_choice", text, int(m.group(1)), "enemy")], unknown
    m = re.fullmatch(r"Magic: Deal (\d+) DMG to all enemy monsters and (\d+) DMG to the opponent\.", text)
    if m:
        return [_module("damage", text, int(m.group(1)), "all_enemy_monsters"),
                _module("face_damage", text, int(m.group(2)), "opponent")], unknown
    unknown.append("unimplemented text: " + text)
    return [], unknown


def annotation_audit(card, annotation):
    if annotation is None:
        return [], {"provided": False, "status": "unreviewed", "gate_only": True}
    problems = []
    if annotation.get("printed_effect") != card.get("effect_readable", ""):
        problems.append("annotation printed_effect does not match snapshot exactly")
    for m in annotation.get("modules", []):
        evidence = m.get("evidence", "")
        if not evidence or evidence not in card.get("effect_readable", ""):
            problems.append("annotation module has invalid exact-text evidence")
        if m.get("kind") not in {"damage", "buff", "draw", "summon", "discount",
                                  "combat", "growth", "tax"}:
            problems.append("annotation marks an unknown or invalid effect kind: " + str(m.get("kind")))
        for code in m.get("condition_codes", []):
            if code != "target_exists":
                problems.append("unimplemented or unknown annotation condition_code: " + str(code))
    # Free text is explanatory, not an executable predicate. Ordinary target
    # existence is already represented by ally_presence/enemy_presence.
    known_conditions = {"target_exists"}
    template_modules, _ = parse_effect(card)
    if any(m["target"] == "all_enemy_monsters" for m in template_modules):
        known_conditions.add("enemy_count")
    for code in annotation.get("condition_codes", []):
        if code not in known_conditions:
            problems.append("unimplemented or unknown annotation condition_code: " + str(code))
    for value in annotation.get("unresolved", []):
        if value:
            problems.append("annotation unresolved: " + str(value))
    return problems, {"provided": True, "gate_only": True,
                      "status": "needs_review" if problems else "evidence_checked",
                      "notes": annotation.get("notes", ""),
                      "conditions_text": annotation.get("conditions", []),
                      "condition_codes": annotation.get("condition_codes", []),
                      "module_conditions_text": [m.get("condition", "") for m in annotation.get("modules", [])],
                      "problems": problems}


def effect_value(module, reference, p):
    kind, amount, target = module["kind"], module["amount"], module["target"]
    body = lambda a, h: body_value(a, h, reference, p)
    if kind in ("damage", "damage_choice"):
        raw = sum(r["weight"] * (body(r["attack"], r["health"])
                  - body(r["attack"], max(0, r["health"] - amount))) for r in reference)
        if kind == "damage_choice":
            # One chosen target, not simultaneous full monster + face reward.
            value = p["enemy_presence"] * raw + (1 - p["enemy_presence"]) * amount * p["face_damage_value"]
            reason = "monster-target availability mixture; otherwise opponent damage"
        elif target == "all_enemy_monsters":
            value = p["enemy_presence"] * p["enemy_count"] * raw
            reason = "conditional enemy count times mean damaged-body difference"
        else:
            value = p["enemy_presence"] * raw
            reason = "available enemy target times mean damaged-body difference"
    elif kind == "debuff":
        raw = sum(r["weight"] * (body(r["attack"], r["health"])
                  - body(max(0, r["attack"] - amount), r["health"])) for r in reference)
        value = p["enemy_presence"] * p["enemy_count"] * raw
        reason = "enemy count times body difference, attack floored at zero"
    elif kind in ("buff_attack", "buff_health"):
        raw = sum(r["weight"] * (body(r["attack"] + (amount if kind == "buff_attack" else 0),
                  r["health"] + (amount if kind == "buff_health" else 0))
                  - body(r["attack"], r["health"])) for r in reference)
        value = p["ally_presence"] * raw
        reason = "available ally target times mean before/after body difference"
    elif kind == "draw":
        raw = amount * p["draw_value"]
        value = raw * p["hand_room"] * p["future_draw_use"]
        reason = "normative information/card-access value; not entire drawn body; hand room and future use gated"
    elif kind == "face_damage":
        raw = amount * p["face_damage_value"]
        value = raw
        reason = "normative nonlethal player-health exchange; no lethal thresholds represented"
    else:
        raise ValueError("Unsupported numeric module " + kind)
    return {"term": kind, "evidence": module["evidence"], "raw_model_gold": raw,
            "value_model_gold": value, "reason": reason, "target": target,
            "amount": amount}


def evaluate_terms(card, reference, modules, attack=None, health=None, cost=None, context="central"):
    attack = card["attack"] if attack is None else attack
    health = card["health"] if health is None else health
    cost = card["cost"] if cost is None else cost
    profiles = {}
    for role in ROLE_PARAMETERS:
        p = role_parameters(role, context)
        b = body_value(attack, health, reference, p)
        ledger = [{"term": "printed_body", "value_model_gold": b,
                   "reason": "joint ATK/HP body model; includes normal hand and board commitment"}]
        ledger += [effect_value(m, reference, p) for m in modules]
        gross = sum(row["value_model_gold"] for row in ledger)
        profiles[role] = {"gross_model_gold": gross, "paid_cost": cost,
                          "net_model_gold": gross - cost, "ledger": ledger,
                          "parameters": p}
    return {"gross_model_gold": sum(r["gross_model_gold"] for r in profiles.values()) / 4,
            "paid_cost": cost,
            "net_model_gold": sum(r["net_model_gold"] for r in profiles.values()) / 4,
            "roles": profiles}


def score_card(card, reference, annotation=None, batch_consistency_passed=None,
               semantic_review_required=False, semantic_audit_passed=None):
    modules, unknown = parse_effect(card)
    issues, audit = annotation_audit(card, annotation)
    unknown += issues
    if batch_consistency_passed is False:
        unknown.append("annotation batch consistency_passed=false: formal score publication blocked")
        audit["status"] = "batch_rejected"
    audit["batch_consistency_passed"] = batch_consistency_passed
    semantic_blocked = semantic_review_required and semantic_audit_passed is not True
    if semantic_blocked:
        unknown.append("semantic review required but semantic_audit_passed is not true: formal score publication blocked")
        audit["status"] = "semantic_review_pending"
    audit["semantic_review_required"] = semantic_review_required
    audit["semantic_audit_passed"] = semantic_audit_passed
    if card.get("card_type") != "monster":
        raise ValueError("Only monsters are supported")
    complete = not unknown
    central = evaluate_terms(card, reference, modules)
    status = "supported" if complete else "partial"
    contexts = {name: evaluate_terms(card, reference, modules, context=name)
                for name in CONTEXT_PARAMETERS}
    sensitivity = {}
    for label, field, delta in [("attack_minus_1", "attack", -1), ("attack_plus_1", "attack", 1),
                               ("health_minus_1", "health", -1), ("health_plus_1", "health", 1),
                               ("cost_minus_1", "cost", -1), ("cost_plus_1", "cost", 1)]:
        val = max(0, card[field] + delta)
        probe = evaluate_terms(card, reference, modules, **{field: val})
        sensitivity[label] = {"supported_terms_delta_model_gold": probe["net_model_gold"] - central["net_model_gold"],
                              "complete_card_delta_model_gold": (probe["net_model_gold"] - central["net_model_gold"]) if complete else None,
                              "note": "unchanged text and context; complex interactions excluded"}
    roles = {}
    for role, row in central["roles"].items():
        row = dict(row)
        row["supported_terms_gross_model_gold"] = row["gross_model_gold"]
        row["supported_terms_net_model_gold"] = row["net_model_gold"]
        if not complete:
            row["gross_model_gold"] = row["net_model_gold"] = None
        roles[role] = row
    subtotal = [r["net_model_gold"] for r in contexts.values()]
    return {"card_id": card["id"], "name": card["name"], "attack": card["attack"],
            "health": card["health"], "printed_effect": card.get("effect_readable", ""),
            "support_status": status, "complete_score_available": complete,
            "gross_model_gold": central["gross_model_gold"] if complete else None,
            "paid_cost": central["paid_cost"], "net_model_gold": central["net_model_gold"] if complete else None,
            "supported_terms_gross_model_gold": central["gross_model_gold"],
            "supported_terms_net_model_gold": central["net_model_gold"],
            "unsupported_effects": unknown, "parsed_modules": modules,
            "score_scope": "shared heuristic, not win rate or measured Gold equivalence" if complete else "supported subtotal only, neither lower nor upper bound",
            "roles": roles, "parameters": {"version": PARAMETER_VERSION,
                                          "aggregate_weights": {r: .25 for r in ROLE_PARAMETERS}},
            "ledger": {r: row["ledger"] for r, row in roles.items()},
            "sensitivity": sensitivity, "annotation_audit": audit,
            "audit_status": audit["status"],
            "formal_score_publishable": complete and annotation is not None and batch_consistency_passed is True,
            "parameter_sensitivity": {"supported_net_envelope": [min(subtotal), max(subtotal)],
                                      "complete_net_envelope": [min(subtotal), max(subtotal)] if complete else None,
                                      "context_values": {n: r["net_model_gold"] for n, r in contexts.items()},
                                      "meaning": "three published normative profiles, not confidence interval or exhaustive bounds"}}


def run(cards, ids=None, annotations=None, snapshot_path=DEFAULT_SNAPSHOT):
    digest = hashlib.sha256(Path(snapshot_path).read_bytes()).hexdigest() if Path(snapshot_path).exists() else None
    declared_hash = (annotations or {}).get("snapshot_sha256")
    if declared_hash is not None and declared_hash != digest:
        raise ValueError("Annotation snapshot_sha256 does not match current snapshot")
    reference, counts = make_reference(cards)
    annot = {}
    for row in (annotations or {}).get("annotations", []):
        cid = int(row["card_id"])
        if cid in annot:
            raise ValueError(f"Duplicate annotation card_id {cid}")
        annot[cid] = row
    by_id = {c["id"]: c for c in cards}
    selected = sorted(annot) if ids is None and annot else ids
    if selected is None:
        selected = [c["id"] for c in cards if c.get("card_type") == "monster"
                    and c.get("pool_category") == "ordinary_non_token"]
    missing = set(selected) - set(by_id)
    if missing:
        raise ValueError("Unknown card ids: " + str(sorted(missing)))
    batch_pass = (annotations or {}).get("consistency_passed")
    if batch_pass is not None and not isinstance(batch_pass, bool):
        raise ValueError("consistency_passed must be a JSON boolean")
    semantic_required = (annotations or {}).get("semantic_review_required", False)
    semantic_pass = (annotations or {}).get("semantic_audit_passed")
    if not isinstance(semantic_required, bool):
        raise ValueError("semantic_review_required must be a JSON boolean")
    if semantic_pass is not None and not isinstance(semantic_pass, bool):
        raise ValueError("semantic_audit_passed must be a JSON boolean")
    scores = [score_card(by_id[cid], reference, annot.get(cid), batch_pass,
                         semantic_required, semantic_pass) for cid in selected]
    return {"parameter_version": PARAMETER_VERSION, "snapshot": str(snapshot_path),
            "snapshot_sha256": digest, "anchor": ANCHOR,
            "assumptions": ["No actual matchup or deck distribution is estimated.",
                            "Equal four roles and equal 4-7G cost strata are normative assumptions.",
                            "Reference consists of printed bodies with all text excluded.",
                            "A supported score covers printed template only; timing, opponent responses, Soul, artifacts, lethal and full deck plans remain outside this first version.",
                            "No fixed extra one-card or one-board-slot tax: normal commitment is already in the body anchor.",
                            "Partial subtotals are not bounds; omitted text can add value or impose costs.",
                            "Annotations are evidence/review gates, never parameter or score sources."],
            "reference": {"cost_stratum_counts": counts, "total": len(reference),
                          "sampling": "uniform cost stratum, then uniform printed monster body",
                          "card_ids": [r["card_id"] for r in reference]},
            "annotation_batch_consistency_passed": batch_pass,
            "semantic_review_required": semantic_required, "semantic_audit_passed": semantic_pass,
            "publication_status": "batch_rejected" if batch_pass is False else "semantic_review_pending" if semantic_required and semantic_pass is not True else "batch_consistency_passed" if batch_pass is True else "engineering_diagnostic_only",
            "formal_score_count": sum(row["formal_score_publishable"] for row in scores),
            "role_meaning": {"aggro": "opponent aggro; evaluate defensive exchanges",
                             "control": "opponent control; evaluate advancing our plan",
                             "combo": "opponent combo; evaluate shortening its setup window",
                             "midrange": "opponent ordinary body-quality plan"},
            "normative_parameters": {"roles": ROLE_PARAMETERS, "common": COMMON_PARAMETERS,
                                     "context_profiles": CONTEXT_PARAMETERS}, "scores": scores}


def write_outputs(result, output):
    path = Path(output)
    if path.suffix.lower() != ".json":
        path = path.with_suffix(".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = ["card_id", "name", "paid_cost", "attack", "health", "support_status", "audit_status", "formal_score_publishable",
              "gross_model_gold", "net_model_gold", "supported_terms_gross_model_gold",
              "supported_terms_net_model_gold", "unsupported_effects"]
    with path.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in result["scores"]:
            flat = {k: row[k] for k in fields}
            flat["unsupported_effects"] = " | ".join(row["unsupported_effects"])
            writer.writerow(flat)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument("--annotations", help="Machine annotations only audit evidence and flag unknown conditions")
    parser.add_argument("--cards", nargs="+", type=int, help="IDs; defaults to annotation IDs or ordinary monsters")
    parser.add_argument("--output", required=True, help="JSON path; sibling CSV also written")
    args = parser.parse_args()
    annotations = json.loads(Path(args.annotations).read_text(encoding="utf-8")) if args.annotations else None
    result = run(load_cards(args.snapshot), args.cards, annotations, args.snapshot)
    write_outputs(result, args.output)
    count = sum(row["support_status"] == "supported" for row in result["scores"])
    print(json.dumps({"cards": len(result["scores"]), "supported_templates": count,
                      "partial": len(result["scores"]) - count, "output": args.output}))


if __name__ == "__main__":
    main()
