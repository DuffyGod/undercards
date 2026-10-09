"""Declared damage Magic and keyword actions priced by one common local Phi.

No growth, Dust, Bullseye, other allied defenders, or full-game simulation.
P0 has the printed body and original board, no Magic/keywords. Pmid has the
selected Magic resolved but no keywords. P1 has that same Magic and keywords.
Magic targets and current Haste actions precede the hidden response; next-turn
actions follow its observation. Unchosen lethal routes are not independently
priced: this follows the calling model's chosen-route terminal boundary.
"""
from __future__ import annotations

import copy
import json
import math

import combat_increment as combat
import score_cards as prices

VERSION = "coupled-damage-window-0.1.1"
TARGETS = {"enemy_monster", "enemy_entity", "monster", "wide_entity", "all_enemy_monsters", "opponent"}
STATUS_KEYS = {"haste", "dodge", "armor", "taunt"}
BODY_KEYS = {"attack", "health", "id", "dodge", "armor", "taunt"}
MAX_MAGIC_PLANS = 4096


def evaluate_cached(card, ctx, damage_specs, statuses, reference, weights=None, conditional_haste_limit=None):
    """Memoize equivalent local windows, isolated by reference object.

    Candidate cost, own Gold and unused hand identities do not enter evaluate;
    dynamic amount expressions are already bound in damage_specs. Return a
    copy so a diagnostic consumer cannot poison later quotes.
    """
    cache=getattr(reference,'coupled_window_cache',None)
    if cache is None:
        return evaluate(card,ctx,damage_specs,statuses,reference,weights,conditional_haste_limit)
    relevant={key:ctx.get(key,default) for key,default in (
        ('role',None),('enemy_bodies',None),('ally_bodies_before_play',ctx.get('ally_bodies',[])),
        ('opponent_gold_before_response',ctx.get('enemy_gold',0)),
        ('own_player_hp',30),('enemy_player_hp',30))}
    effective_weights=combat.RESPONSE_WEIGHTS.get(ctx.get('role')) if weights is None else weights
    parameters=prices.role_parameters(ctx['role']) if ctx.get('role') in combat.RESPONSE_WEIGHTS else None
    key=json.dumps([VERSION,card.get('attack'),card.get('health'),relevant,damage_specs,statuses,
                    effective_weights,conditional_haste_limit,parameters,combat.HP_WEIGHTS.get(ctx.get('role')),
                    combat.CASH_WEIGHT],sort_keys=True)
    if key in cache: return copy.deepcopy(cache[key])
    result=evaluate(card,ctx,damage_specs,statuses,reference,weights,conditional_haste_limit)
    if len(cache)<4096: cache[key]=copy.deepcopy(result)
    return result


def _number(value, name, minimum=0):
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum:
        raise ValueError(name + " must be finite and >= " + str(minimum))
    return value


def _statuses(value, allowed=STATUS_KEYS):
    if not isinstance(value, dict) or not set(value) <= allowed:
        raise ValueError("Unsupported status fields")
    if any(type(value[key]) is not bool for key in ("haste", "armor", "taunt") if key in value):
        raise ValueError("Keyword flags must be booleans")
    if "dodge" in value and (type(value["dodge"]) is not int or value["dodge"] < 0):
        raise ValueError("Dodge must be a nonnegative integer")


def _body_list(value, limit, allied=False):
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError("Board must be a list within its slot limit")
    result = copy.deepcopy(value)
    for unit in result:
        if not isinstance(unit, dict) or not {"attack", "health"} <= set(unit) or not set(unit) <= BODY_KEYS:
            raise ValueError("Unsupported or missing body fields")
        _number(unit["attack"], "body attack")
        _number(unit["health"], "body health")
        if unit["health"] == 0:
            raise ValueError("Initial boards must contain live bodies only")
        _statuses({k: v for k, v in unit.items() if k in STATUS_KEYS})
        if allied and unit.get("taunt"):
            raise ValueError("Other allied Taunt defenders are outside this response primitive")
    return result


def _components(state, reference, role):
    result = combat.utility_components(state, reference, role)
    parameters = prices.role_parameters(role)
    result["other_ally_bodies"] = sum(prices.body_value(unit["attack"], max(0, unit["health"]), reference, parameters)
                                       for unit in state["external_allies"])
    return result


def _phi(state, reference, role):
    return sum(_components(state, reference, role).values())


def _plan(state, haste, weights, reference, role):
    # External allies are constant during this candidate-only response window,
    # so their resource value does not change the core's within-window choice.
    result = combat.optimal_declared_plan(state, haste, weights, reference, role)
    result["core_expected_without_external_allies"] = result["expected"]
    for outcome in result["outcomes"].values():
        outcome["components"] = _components(outcome["state"], reference, role)
        outcome["utility"] = sum(outcome["components"].values())
    result["expected"] = sum(weights[event] * outcome["utility"] for event, outcome in result["outcomes"].items())
    result["chosen_terminal_present"] = any(weights[event] > 0 and outcome["terminal"]
                                            for event, outcome in result["outcomes"].items())
    return result


def _choices(state, target):
    enemies = [{"side": "enemy", "index": i} for i, unit in enumerate(state["enemies"]) if unit["health"] > 0]
    allies = [{"side": "ally", "index": i} for i, unit in enumerate(state["external_allies"]) if unit["health"] > 0]
    if target == "all_enemy_monsters":
        return [enemies]  # One forced AoE, never one whole AoE per enemy.
    if target == "opponent":
        return [[{"side": "opponent", "index": None}]]
    options = enemies
    if target in ("monster", "wide_entity"):
        options += allies
    if target == "wide_entity":
        options += [{"side": "owner", "index": None}, {"side": "opponent", "index": None}]
    elif target == "enemy_entity":
        options += [{"side": "opponent", "index": None}]
    return [[option] for option in options] or [[]]


def _hit(state, target, amount):
    side, index = target["side"], target["index"]
    if side in ("enemy", "ally"):
        unit = state["enemies" if side == "enemy" else "external_allies"][index]
        before = unit["health"]
        dealt = combat.hurt(unit, amount)
        hp_removed = min(before, dealt)
    else:
        field, delta = (("own_player_hp", "hp_delta") if side == "owner" else ("enemy_player_hp", "enemy_hp_delta"))
        dealt = min(state[field], amount)
        state[field] -= dealt
        state[delta] -= dealt
        hp_removed = dealt
    return {**target, "nominal_damage": amount, "received_damage": dealt, "hp_removed": hp_removed}


def _magic_candidates(initial, specs, conditional_limit):
    candidates = [{"state": copy.deepcopy(initial), "selection": [], "conditional_dealt": None}]
    for spec_index, spec in enumerate(specs):
        next_candidates = []
        for prior in candidates:
            if combat.terminal(prior["state"]):
                child = copy.deepcopy(prior)
                child["selection"].append({"spec_index": spec_index, "target_kind": spec["target"],
                                            "targets": [], "fizzle": False, "skipped_after_terminal": True})
                next_candidates.append(child)
                continue
            for targets in _choices(prior["state"], spec["target"]):
                child = copy.deepcopy(prior)
                hits = [_hit(child["state"], target, spec["amount"]) for target in targets]
                record = {"spec_index": spec_index, "target_kind": spec["target"],
                          "targets": hits, "fizzle": not targets, "skipped_after_terminal": False}
                child["selection"].append(record)
                child["state"]["log"].append({"event": "magic_damage", **record})
                if conditional_limit is not None:
                    if not targets:
                        raise ValueError("Conditional Haste after fizzle is not a verified ruling")
                    dealt = hits[0]["received_damage"]
                    if dealt != spec["amount"]:
                        raise ValueError("Conditional Haste with mitigated/ambiguous received damage is not verified")
                    child["conditional_dealt"] = dealt
                next_candidates.append(child)
        if len(next_candidates) > MAX_MAGIC_PLANS:
            raise ValueError("Declared Magic target combinations exceed the local plan bound")
        candidates = next_candidates
    return candidates


def _difference(left, right, weights):
    keys = next(iter(left["outcomes"].values()))["components"]
    return {key: sum(weights[event] * (left["outcomes"][event]["components"][key] - right["outcomes"][event]["components"][key])
                     for event in weights) for key in keys}


def evaluate(card, ctx, damage_specs, statuses, reference, weights=None, conditional_haste_limit=None):
    """Evaluate only declared damage and supported keywords, not all card text."""
    if not isinstance(card, dict) or not {"attack", "health"} <= set(card):
        raise ValueError("Card attack/health are required")
    attack = _number(card["attack"], "card attack")
    health = _number(card["health"], "card health")
    if health == 0:
        raise ValueError("Printed candidate must be alive")
    if not isinstance(ctx, dict) or ctx.get("role") not in combat.RESPONSE_WEIGHTS:
        raise ValueError("A supported context role is required")
    role = ctx["role"]
    enemies = _body_list(ctx.get("enemy_bodies"), 4)
    allies = _body_list(ctx.get("ally_bodies_before_play", ctx.get("ally_bodies", [])), 3, allied=True)
    gold = _number(ctx.get("opponent_gold_before_response", ctx.get("enemy_gold", 0)), "opponent Gold")
    own_hp = _number(ctx.get("own_player_hp", 30), "own player HP")
    enemy_hp = _number(ctx.get("enemy_player_hp", 30), "enemy player HP")
    _statuses(statuses)
    weights = dict(combat.RESPONSE_WEIGHTS[role] if weights is None else weights)
    if not weights or not set(weights) <= set(combat.RESPONSE_WEIGHTS[role]):
        raise ValueError("Unknown or empty response events")
    if any(type(v) not in (float, int) or not math.isfinite(v) or v < 0 for v in weights.values()) or abs(sum(weights.values()) - 1) > 1e-10:
        raise ValueError("Response weights must be finite, nonnegative and sum to one")
    if not isinstance(damage_specs, list):
        raise ValueError("damage_specs must be a list")
    for spec in damage_specs:
        if not isinstance(spec, dict) or set(spec) != {"amount", "target"} or spec["target"] not in TARGETS:
            raise ValueError("Only amount/declared damage target specs are supported")
        if type(spec["amount"]) is not int or spec["amount"] < 0:
            raise ValueError("Damage amount must be a nonnegative integer")
    if conditional_haste_limit is not None:
        if type(conditional_haste_limit) is not int or conditional_haste_limit < 0:
            raise ValueError("Conditional Haste limit must be a nonnegative integer")
        if len(damage_specs) != 1 or damage_specs[0]["target"] not in ("enemy_monster", "monster"):
            raise ValueError("Conditional Haste supports one targeted monster damage instance only")

    initial = combat.state(attack, health, enemies, {}, gold, own_hp, enemy_hp)
    initial["external_allies"] = allies
    ordinary = _plan(initial, False, weights, reference, role)
    candidates = []
    for candidate in _magic_candidates(initial, damage_specs, conditional_haste_limit):
        mid_initial = candidate["state"]
        effective = copy.deepcopy(statuses)
        if conditional_haste_limit is not None and candidate["conditional_dealt"] is not None and candidate["conditional_dealt"] <= conditional_haste_limit:
            effective["haste"] = True
        special_initial = copy.deepcopy(mid_initial)
        special_initial["actor"].update(dodge=effective.get("dodge", 0), armor=effective.get("armor", False), taunt=effective.get("taunt", False))
        mid = _plan(mid_initial, False, weights, reference, role)
        special = _plan(special_initial, effective.get("haste", False), weights, reference, role)
        direct_components = {key: _components(mid_initial, reference, role)[key] - _components(initial, reference, role)[key]
                             for key in _components(initial, reference, role)}
        direct = sum(direct_components.values())
        candidates.append({"magic_selection": candidate["selection"], "effective_statuses": effective,
                           "magic_initial_state": copy.deepcopy(mid_initial), "intermediate": mid, "special": special,
                           "immediate_damage_only_diagnostic": {"delta_phi": None if combat.terminal(mid_initial) else direct,
                                                                 "component_deltas": direct_components,
                                                                 "scope": "instant resource changes only; never added again to total"}})
    best = max(candidates, key=lambda value: value["special"]["expected"])
    mid, special = best["intermediate"], best["special"]
    terminal = any(plan["chosen_terminal_present"] for plan in (ordinary, mid, special))
    raw_total = special["expected"] - ordinary["expected"]
    raw_magic = mid["expected"] - ordinary["expected"]
    raw_keyword = special["expected"] - mid["expected"]
    total_deltas = _difference(special, ordinary, weights)
    magic_deltas = _difference(mid, ordinary, weights)
    keyword_deltas = _difference(special, mid, weights)
    direct = best["immediate_damage_only_diagnostic"]["delta_phi"]
    return {"version": VERSION,
            "total_delta_model_gold": None if terminal else raw_total,
            "direct_damage_model_gold": None if terminal else direct,
            "magic_interaction_model_gold": None if terminal or direct is None else raw_magic - direct,
            "total_increment_model_gold": None if terminal else raw_total,
            "magic_window_delta_model_gold": None if terminal else raw_magic,
            "keyword_delta_model_gold": None if terminal else raw_keyword,
            "component_deltas": None if terminal else total_deltas,
            "magic_component_deltas": None if terminal else magic_deltas,
            "keyword_component_deltas": None if terminal else keyword_deltas,
            "immediate_damage_only_diagnostic": best["immediate_damage_only_diagnostic"],
            "interaction_model_gold": None if terminal or direct is None else raw_magic - direct,
            "decomposition_residual": None if terminal else raw_total - raw_magic - raw_keyword,
            "ordinary": ordinary, "post_magic_ordinary": mid, "keyword_bundle": special,
            "intermediate": mid, "special": special,
            "magic_selection": best["magic_selection"], "effective_statuses": best["effective_statuses"],
            "magic_initial_state": best["magic_initial_state"], "candidates": candidates,
            "response_weights": weights, "terminal_requires_separate_outcome_evaluation": terminal,
            "scope": "P1-P0 only; Pmid shares selected Magic; no extra removal, keyword or ally-body bonus added",
            "limitations": ["Other allied bodies are external resources, not active defenders; allied Taunt is rejected.",
                            "Only declared damage and supported keywords are covered; no growth, Dust or Bullseye.",
                            "At most one current monster attack and one common next-turn attack.",
                            "Chosen terminal outcomes block resource pricing; unchosen lethal actions are not separately scanned.",
                            "Synthetic keyword silence does not implement general modifier reset or a full opponent deck."]}
