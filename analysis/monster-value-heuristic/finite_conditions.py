"""Finite, three-valued conditions on caller-provided *current* known state.

No probabilities, prices, approvals, initial-deck fallback or arbitrary eval.
remaining_deck contains current card records with current card-kind identity
(copies share identity), generated:bool and relevant card_type/rarity. Neither
an initial pre-transformation identity nor a unique physical slot ID should
replace the current duplicate-comparison identity.

hand_size is the current count at the caller's stated evaluation event; this
module never silently substitutes pre-play or post-play counts. actor and
selected_target are separate current object records with health, or explicit
null for known absence. Missing an object key means unknown, not dead/alive.
"""
from __future__ import annotations

import copy
import math

VERSION = "finite-current-conditions-0.1.0"
RARITIES = {"BASE", "COMMON", "RARE", "EPIC", "LEGENDARY", "DT", "TOKEN"}
KINDS = {"last_turn_spell_spend_positive", "deck_no_duplicates", "deck_no_rarities",
         "deck_no_spells", "hand_size_threshold", "actor_alive", "selected_target_alive", "unknown"}
NEED_CLAUSES = {
    "Need: You spent GOLD on spells last turn.": {"kind": "last_turn_spell_spend_positive"},
    "Need: Your deck has no non-Generated duplicates.": {"kind": "deck_no_duplicates"},
    "Need: Your deck has no non-Generated RARE or EPIC cards.": {"kind": "deck_no_rarities", "rarities": ["RARE", "EPIC"]},
    "Need: Your deck has no non-Generated spells.": {"kind": "deck_no_spells"},
    "Need: Your deck has no non-Generated COMMON cards.": {"kind": "deck_no_rarities", "rarities": ["COMMON"]},
}


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _result(spec, value, required, reason, missing=None):
    return {"value": value, "status": "unknown" if value is None else "known",
            "required_fields": list(required), "missing_fields": list(missing or []),
            "reason": reason, "predicate": copy.deepcopy(spec),
            "scope": "current known-state condition only; not probability, pricing or card approval"}


def parse_need(effect_text):
    """Return a finite spec, unknown spec for unhandled Need, or None if absent.

    Match exact catalogued clauses at the start or after a sentence boundary.
    No fuzzy matching of wording or new hand/tribe thresholds. Multiple Need
    clauses are unsupported; no one favorable clause is selected.
    """
    if not isinstance(effect_text, str):
        raise ValueError("effect_text must be text")
    text = effect_text.strip()
    if "Need:" not in text:
        return None
    found = []
    for clause, spec in NEED_CLAUSES.items():
        start = 0
        while True:
            index = text.find(clause, start)
            if index < 0:
                break
            before_ok = index == 0 or text[max(0, index - 2):index] == ". "
            end = index + len(clause)
            after_ok = end == len(text) or text[end].isspace()
            if before_ok and after_ok:
                found.append(copy.deepcopy(spec))
            start = end
    if len(found) == 1 and text.count("Need:") == 1:
        return found[0]
    return {"kind": "unknown", "reason": "Need clause is outside the exact inventoried finite registry, or multiple clauses require a conjunction"}


def _validate_spec(spec):
    if not isinstance(spec, dict) or not isinstance(spec.get("kind"), str) or spec["kind"] not in KINDS:
        raise ValueError("Unknown finite predicate kind")
    kind = spec["kind"]
    if kind == "deck_no_rarities":
        if set(spec) != {"kind", "rarities"} or not isinstance(spec["rarities"], list) or not spec["rarities"]:
            raise ValueError("deck_no_rarities requires a nonempty rarity list")
        if any(not isinstance(x, str) or x not in RARITIES for x in spec["rarities"]):
            raise ValueError("Unknown forbidden rarity")
    elif kind == "hand_size_threshold":
        if set(spec) != {"kind", "operator", "threshold"} or spec["operator"] not in ("<=", ">=", "=="):
            raise ValueError("Hand threshold uses only <=, >= or ==")
        if type(spec["threshold"]) is not int or not 0 <= spec["threshold"] <= 7:
            raise ValueError("Hand threshold must be an integer 0..7")
    elif kind == "unknown":
        if not set(spec) <= {"kind", "reason"} or ("reason" in spec and not isinstance(spec["reason"], str)):
            raise ValueError("Unknown predicate permits only a textual reason")
    elif set(spec) != {"kind"}:
        raise ValueError("Unexpected finite predicate fields")
    return kind


def _deck_condition(spec, state):
    kind = spec["kind"]
    field = "identity" if kind == "deck_no_duplicates" else "rarity" if kind == "deck_no_rarities" else "card_type"
    required = ["remaining_deck", "remaining_deck[*].generated", "remaining_deck[non-generated]." + field]
    if "remaining_deck" not in state or not isinstance(state["remaining_deck"], list):
        return _result(spec, None, required, "Current remaining_deck is missing or not a known card list; initial_deck is never substituted", ["remaining_deck"])
    missing, seen = [], set()
    for index, card in enumerate(state["remaining_deck"]):
        path = f"remaining_deck[{index}]"
        if not isinstance(card, dict):
            missing.append(path)
            continue
        generated = card.get("generated")
        if type(generated) is not bool:
            missing.append(path + ".generated")
            continue
        if generated:
            continue
        value = card.get(field)
        if kind == "deck_no_duplicates":
            if type(value) not in (str, int) or (isinstance(value, str) and not value):
                missing.append(path + ".identity")
                continue
            if value in seen:
                return _result(spec, False, required, "A known non-Generated identity occurs at least twice in the current remaining deck", missing)
            seen.add(value)
        elif kind == "deck_no_rarities":
            if not isinstance(value, str) or value not in RARITIES:
                missing.append(path + ".rarity")
                continue
            if value in spec["rarities"]:
                return _result(spec, False, required, "A known non-Generated card has a forbidden rarity in the current remaining deck", missing)
        else:
            if value not in ("monster", "spell"):
                missing.append(path + ".card_type")
                continue
            if value == "spell":
                return _result(spec, False, required, "A known non-Generated spell remains in the current deck", missing)
    if missing:
        return _result(spec, None, required, "No known violating card, but missing current-card fields prevent proving the condition", missing)
    return _result(spec, True, required, "All known non-Generated current deck cards satisfy the condition; an explicitly empty remaining deck also satisfies it")


def evaluate_condition(spec, known_state):
    kind = _validate_spec(spec)
    if not isinstance(known_state, dict):
        raise ValueError("known_state must be a dictionary")
    if kind == "unknown":
        return _result(spec, None, [], spec.get("reason", "Explicitly unsupported finite condition"))
    if kind in {"deck_no_duplicates", "deck_no_rarities", "deck_no_spells"}:
        return _deck_condition(spec, known_state)
    if kind == "last_turn_spell_spend_positive":
        field = "last_turn_gold_spent_on_spells"
        value = known_state.get(field)
        if not _finite(value) or value < 0:
            return _result(spec, None, [field], "Actual last-turn Gold paid for spells is unknown; spell cast count is not a substitute", [field])
        return _result(spec, value > 0, [field], "Compare actual Gold paid on spells last turn with zero; free spells alone do not satisfy it")
    if kind == "hand_size_threshold":
        field = "hand_size"
        value = known_state.get(field)
        if type(value) is not int or not 0 <= value <= 7:
            return _result(spec, None, [field], "Current hand size at this evaluation event is missing or invalid", [field])
        op, target = spec["operator"], spec["threshold"]
        result = value <= target if op == "<=" else value >= target if op == ">=" else value == target
        return _result(spec, result, [field], "Compare only the declared current hand size; no pre/post-play inference")
    field = "actor" if kind == "actor_alive" else "selected_target"
    required = [field, field + ".health"]
    if field not in known_state:
        return _result(spec, None, required, f"{field} is not observed; the other object cannot substitute", [field])
    obj = known_state[field]
    if obj is None:
        return _result(spec, False, required, f"{field}=null explicitly denotes known absence from the current observed object state")
    if not isinstance(obj, dict) or not _finite(obj.get("health")):
        return _result(spec, None, required, f"{field} current health is unknown", [field + ".health"])
    return _result(spec, obj["health"] > 0, required, f"{field} current health, evaluated independently of the other object")


def evaluate(spec, known_state):
    return evaluate_condition(spec, known_state)
