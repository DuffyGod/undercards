"""Joint, public heuristic contexts and accounting primitives; no card prices.

These fixtures are design assumptions, not sampled matches or empirical rates.
They describe a candidate's *conditional legal deployment*. Its unknown paid
cost is bound separately. Future event/usage fixtures never inform current
amount expressions or legal branch enumeration.
"""
from __future__ import annotations

import copy
import itertools
import math

VERSION = "joint-contexts-0.1.1"
ROLES = ("aggro", "control", "combo", "midrange")
PHASES = (3, 5, 8)
STATES = ("deployed", "reserved")
STAGE_TARGET_BODIES = {
    3: ((2, 2), (3, 1), (4, 4)),
    5: ((3, 4), (4, 5), (6, 5)),
    8: ((4, 6), (6, 7), (8, 8)),
}
RESOURCE_STATES = {
    "deployed": {"hand_before": 3, "ally_count_before": 2, "enemy_count": 3,
                 "gold_before": {3: 4, 5: 8, 8: 10},
                 "opponent_gold": {3: 3, 5: 5, 8: 7},
                 "death_hand_costs": [1, 3, 6], "used": [True, True, False]},
    "reserved": {"hand_before": 6, "ally_count_before": 0, "enemy_count": 1,
                 "gold_before": {3: 7, 5: 12, 8: 20},
                 "opponent_gold": {3: 6, 5: 10, 8: 16},
                 "death_hand_costs": [2, 4, 7, 8], "used": [True, False, True, False]},
}
ASSUMPTIONS = (
    "Equal roles, phases and two joint resource fixtures; weights are not actual occurrence frequencies.",
    "First-player base income only, initial 1G; no artifact, Soul or card income.",
    "Before/after fields are immediately before/after paying and placing a candidate, before its Magic.",
    "Target bodies are synthetic shared stage fixtures, not claims about particular opposing cards.",
    "Response descriptions are synthetic effect states with affordable costs; no response probabilities or optimal-play claims.",
    "Death-event hand and future usage masks are paired scenario assumptions, not known future information.",
    "Payment floor 0 is a model accounting assumption, not a newly verified minimum-cost ruling.",
)


def base_income(own_turn, second_player=False):
    if not isinstance(own_turn, int) or isinstance(own_turn, bool) or own_turn < 1:
        raise ValueError("own_turn must be a positive integer")
    return min(own_turn, 10) + int(second_player and own_turn in (1, 3, 5, 7, 9))


def cumulative_base_gold(own_turn, second_player=False):
    return 1 + sum(base_income(n, second_player) for n in range(1, own_turn + 1))


def make_contexts():
    contexts = []
    for role, turn, state in itertools.product(ROLES, PHASES, STATES):
        r = RESOURCE_STATES[state]
        targets = [{"attack": a, "health": h} for a, h in STAGE_TARGET_BODIES[turn]]
        opponent_gold = r["opponent_gold"][turn]
        future_available = base_income(turn + 1) + base_income(turn + 2)
        ctx = {
            "context_id": f"{role}-t{turn}-{state}", "version": VERSION,
            "role": role, "own_turn": turn, "joint_resource_state": state,
            "weight": 1 / 24, "parameters_are_design_assumptions": True,
            "conditional_on_legal_candidate_play": True,
            "hand_size_before_play": r["hand_before"],
            "hand_size_after_play": r["hand_before"] - 1,
            "gold_before_play": r["gold_before"][turn], "gold_after_play": None,
            "candidate_paid_cost": None,
            "cumulative_base_gold_cap": cumulative_base_gold(turn),
            "ally_count_before_play": r["ally_count_before"],
            "ally_count_after_play": r["ally_count_before"] + 1,
            "ally_empty_slots_before_play": 4 - r["ally_count_before"],
            "ally_empty_slots_after_play": 3 - r["ally_count_before"],
            "enemy_count": r["enemy_count"], "enemy_empty_slots": 4 - r["enemy_count"],
            "other_monster_count": r["ally_count_before"] + r["enemy_count"],
            "stage_target_bodies": targets,
            "stage_target_bodies_meaning": "shared target alternatives; not an additional board",
            "ally_bodies_before_play": copy.deepcopy(targets[:r["ally_count_before"]]),
            "enemy_bodies": copy.deepcopy(targets[:r["enemy_count"]]),
            "opponent_gold_before_response": opponent_gold,
            "response_states": [
                {"name": "none", "paid_cost": 0, "affordable": True,
                 "effect_family": "none", "synthetic_fixture": True},
                {"name": "normal", "paid_cost": 2, "affordable": opponent_gold >= 2,
                 "effect_family": "one_damage_instance", "damage": 2, "synthetic_fixture": True},
                {"name": "silence", "paid_cost": 3, "affordable": opponent_gold >= 3,
                 "effect_family": "silence_current_candidate", "synthetic_fixture": True},
            ],
            "death_event_hand_costs": list(r["death_hand_costs"]),
            "actually_used_mask": list(r["used"]),
            "resource_use_window": {
                "death_event_own_turn": turn, "first_own_turn": turn + 1,
                "last_own_turn": turn + 2, "assumed_carry_gold": 0,
                "base_income_in_window": future_available,
                "available_gold_assumption": future_available,
                "paired_usage_plan_fixed": True,
                "not_available_to_current_decisions": True,
            },
            "assumptions": list(ASSUMPTIONS),
        }
        validate_context(ctx)
        contexts.append(ctx)
    return contexts


def _number(value, name):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return value


def validate_context(ctx):
    pre = ctx["hand_size_before_play"]
    post = ctx["hand_size_after_play"]
    if not isinstance(pre, int) or isinstance(pre, bool) or not isinstance(post, int) or isinstance(post, bool) or not 1 <= pre <= 7 or post != pre - 1:
        raise ValueError("Invalid before/after candidate hand counts")
    ally = ctx["ally_count_before_play"]
    enemy = ctx["enemy_count"]
    if not isinstance(ally, int) or isinstance(ally, bool) or not 0 <= ally <= 3:
        raise ValueError("Candidate needs a free allied board slot")
    if not isinstance(enemy, int) or isinstance(enemy, bool) or not 0 <= enemy <= 4:
        raise ValueError("Invalid enemy board count")
    if ctx["ally_count_after_play"] != ally + 1:
        raise ValueError("Candidate must be included after play")
    if ctx["other_monster_count"] != ally + enemy:
        raise ValueError("Other monsters includes both boards, excluding candidate")
    if ctx["ally_empty_slots_before_play"] != 4 - ally or ctx["ally_empty_slots_after_play"] != 3 - ally:
        raise ValueError("Inconsistent allied empty slots")
    if ctx["enemy_empty_slots"] != 4 - enemy:
        raise ValueError("Inconsistent enemy empty slots")
    second=ctx.get('second_player',False)
    if type(second) is not bool: raise ValueError('second_player must be boolean')
    cap = cumulative_base_gold(ctx["own_turn"],second)
    if ctx["cumulative_base_gold_cap"] != cap or not 0 <= ctx["gold_before_play"] <= cap:
        raise ValueError("Gold exceeds cumulative base-income budget")
    if not 0 <= ctx["opponent_gold_before_response"] <= cap:
        raise ValueError("Opponent gold exceeds declared base-income budget")
    if ctx["candidate_paid_cost"] is not None:
        if ctx["gold_after_play"] != ctx["gold_before_play"] - ctx["candidate_paid_cost"] or ctx["gold_after_play"] < 0:
            raise ValueError("Invalid actual post-payment balance")
    elif ctx["gold_after_play"] is not None:
        raise ValueError("Unbound candidate has no actual post-payment balance")
    costs, used = ctx["death_event_hand_costs"], ctx["actually_used_mask"]
    if len(costs) != len(used) or len(costs) > 7 or any(not isinstance(x, bool) for x in used):
        raise ValueError("Invalid death-event hand or usage mask")
    if any(_number(cost, "death-event cost") < 0 for cost in costs):
        raise ValueError("Death-event costs must be nonnegative")
    if sum(c for c, u in zip(costs, used) if u) > ctx["resource_use_window"]["available_gold_assumption"]:
        raise ValueError("Paired usage mask is not affordable in its resource window")
    return True


def bind_candidate(ctx, paid_cost):
    """Bind an actual paid amount, rejecting unaffordable deployment fixtures."""
    _number(paid_cost, "paid_cost")
    if paid_cost < 0:
        raise ValueError("Paid cost must be nonnegative")
    if paid_cost > ctx["gold_before_play"]:
        raise ValueError("Candidate is unaffordable in this context; no deployment occurred")
    bound = copy.deepcopy(ctx)
    bound["candidate_paid_cost"] = paid_cost
    bound["gold_after_play"] = ctx["gold_before_play"] - paid_cost
    validate_context(bound)
    return bound


def evaluate_amount(module, ctx):
    """Evaluate the V4 amount multiplier from current public fields only.

    count/repeat_rule define separate event multiplicity and are NOT silently
    multiplied into amount. An unknown basis or absent multiplier is rejected.
    """
    basis = module.get("amount_basis", "fixed")
    amount = _number(module.get("amount"), "module amount")
    fields = {
        "hand_size_after_play": "hand_size_after_play",
        "hand_empty_after_play": None,
        "other_monster_count": "other_monster_count",
        "enemy_monster_count": "enemy_count", "enemy_count": "enemy_count",
        "ally_monster_count": "ally_count_after_play", "ally_count": "ally_count_after_play",
        "other_ally_monster_count": "ally_count_before_play",
    }
    if basis == "fixed":
        return amount
    if basis not in fields:
        raise ValueError("Unknown or unsupported amount_basis: " + str(basis))
    if basis == "hand_empty_after_play":
        multiplier = 7 - ctx["hand_size_after_play"]
    else:
        multiplier = ctx[fields[basis]]
    return amount * _number(multiplier, "observable amount multiplier")


def enumerate_choice_branches(modules):
    """Return index selections: common modules plus one branch per group.

    This supplies legal alternatives only. It performs no optimization, assigns
    no per-card weights and observes no future data or outcomes.
    """
    common, groups = [], {}
    for index, module in enumerate(modules):
        group = module.get("choice_group")
        if group is None:
            common.append(index)
        elif not isinstance(group, str) or not group:
            raise ValueError("choice_group must be a nonempty string or null")
        else:
            branch = module.get('choice_branch', str(index))
            if not isinstance(branch, str) or not branch:
                raise ValueError('Grouped modules need a nonempty choice_branch')
            groups.setdefault(group, {}).setdefault(branch, []).append(index)
    names = list(groups)
    return [{"selected_module_indexes": sorted(common + [index for group,branch in zip(names,selection) for index in groups[group][branch]]),
             "choice_selection": dict(zip(names, selection))}
            for selection in itertools.product(*(groups[g] for g in names))]


def paid_cost_discount(old_cost, new_cost, actually_used=True):
    """Actual payment difference with assumed 0 payment floor.

    An unused card saves zero. A cost increase yields a negative saving. This
    is cash accounting only, not a Gold-equivalent quality valuation.
    """
    _number(old_cost, "old_cost")
    _number(new_cost, "new_cost")
    if not isinstance(actually_used, bool):
        raise ValueError("actually_used must be a boolean")
    return max(0, old_cost) - max(0, new_cost) if actually_used else 0


def discount_payment_ledger(ctx, cost_change):
    """Pair the identical future usage mask before/after a signed cost change."""
    _number(cost_change, "cost_change")
    costs, used_mask = ctx["death_event_hand_costs"], ctx["actually_used_mask"]
    if len(costs) != len(used_mask) or len(costs) > 7:
        raise ValueError("Death-event hand and usage mask must match and fit seven cards")
    rows = []
    for old, used in zip(costs, used_mask):
        _number(old, "old_cost")
        new = old + cost_change
        rows.append({"old_cost": old, "new_cost": new, "actually_used": used,
                     "old_paid": max(0, old) if used else 0,
                     "new_paid": max(0, new) if used else 0,
                     "saved_paid_gold": paid_cost_discount(old, new, used)})
    available = ctx.get("resource_use_window", {}).get("available_gold_assumption")
    if available is not None and (sum(r["old_paid"] for r in rows) > available
                                  or sum(r["new_paid"] for r in rows) > available):
        raise ValueError("Actual paired payment plan exceeds its declared resource window")
    return {"rows": rows, "total_old_paid": sum(r["old_paid"] for r in rows),
            "total_new_paid": sum(r["new_paid"] for r in rows),
            "total_saved_paid_gold": sum(r["saved_paid_gold"] for r in rows),
            "usage_mask_is_a_future_scenario_assumption": True,
            "payment_floor": 0, "payment_floor_is_model_assumption": True,
            "scope": "paired cash payments only; no value assigned to unused discounts or earlier deployment"}
