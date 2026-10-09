"""Exact, small resource-payment frontier for an already known hand.

Gross model-G quotes come from the caller. No card pricing, random draws,
combat, deck inference, future observations or strategic policy are modeled.
Two/three income windows, seven cards and an explicit play cap keep exhaustive
enumeration small. Payment floor zero is an accounting assumption.
"""
from __future__ import annotations

import copy
import itertools
import math

VERSION = "known-hand-payment-frontier-0.1.0"
EPSILON = 1e-9
SCOPE = {
    "tool": "finite known-hand resource planning only",
    "gross_quotes": "caller-provided priors, not fitted prices or measured card quality",
    "excluded": ["random future draws", "combat", "board space", "target availability",
                 "trigger frequency", "opponent responses", "full-game optimal decisions"],
    "payment_floor": 0,
    "payment_floor_is_model_assumption": True,
    "income_windows_are_caller_scenarios": True,
    "unspent_gold_has_no_penalty": True,
    "known_hand_at_event_only": True,
    "future_gross_values_are_not_new_information": True,
}


def _number(value, field):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{field} must be a finite number")
    return value


class PaymentFrontier:
    def __init__(self, hand, incomes, initial_gold=0, max_plays=2):
        if not isinstance(hand, (list, tuple)) or len(hand) > 7:
            raise ValueError("Known hand must have at most seven cards")
        if not isinstance(incomes, (list, tuple)) or len(incomes) not in (2, 3):
            raise ValueError("Exactly two or three income windows are supported")
        self.hand = copy.deepcopy(list(hand))
        for row in self.hand:
            if not isinstance(row, dict) or "cost" not in row or "gross_model_gold" not in row:
                raise ValueError("Each known card needs cost and caller-provided gross_model_gold")
            _number(row["cost"], "cost")
            _number(row["gross_model_gold"], "gross_model_gold")
        self.incomes = [_number(v, "income") for v in incomes]
        self.initial_gold = _number(initial_gold, "initial_gold")
        if self.initial_gold < 0 or any(v < 0 for v in self.incomes):
            raise ValueError("Gold balance and income cannot be negative")
        caps = [max_plays] * len(incomes) if type(max_plays) is int else max_plays
        if not isinstance(caps, (list, tuple)) or len(caps) != len(incomes):
            raise ValueError("Play caps must be an integer or one cap per income window")
        if any(type(v) is not int or not 0 <= v <= 7 for v in caps):
            raise ValueError("Each play cap must be an integer between zero and seven")
        self.max_plays = list(caps)

    def evaluate_plan(self, assignment):
        """0 means unused; 1..T means one use in that future window."""
        if not isinstance(assignment, (tuple, list)) or len(assignment) != len(self.hand):
            raise ValueError("Assignment must have one use time per known card")
        if any(type(v) is not int or not 0 <= v <= len(self.incomes) for v in assignment):
            raise ValueError("Invalid card use time; no card may be used more than once")
        gold = self.initial_gold
        total_gross = total_paid = 0
        windows = []
        for turn, (income, cap) in enumerate(zip(self.incomes, self.max_plays), 1):
            indexes = [i for i, use in enumerate(assignment) if use == turn]
            if len(indexes) > cap:
                raise ValueError("Plan exceeds the common per-window play cap")
            opening = gold
            available = opening + income
            paid = sum(max(0, self.hand[i]["cost"]) for i in indexes)
            if paid > available + EPSILON:
                raise ValueError("Plan overdraws Gold before the next income window")
            gross = sum(self.hand[i]["gross_model_gold"] for i in indexes)
            gold = max(0, available - paid)
            total_gross += gross
            total_paid += paid
            windows.append({"window": turn, "opening_gold": opening, "income": income,
                            "available_gold": available, "max_plays": cap,
                            "played_indexes": indexes,
                            "plays": [{"card_index": i, "cost": self.hand[i]["cost"],
                                       "paid_cost": max(0, self.hand[i]["cost"]),
                                       "gross_model_gold": self.hand[i]["gross_model_gold"]}
                                      for i in indexes],
                            "paid_cost": paid, "gross_model_gold": gross,
                            "closing_gold": gold})
        return {"assignment": list(assignment), "used_indexes": [i for i, v in enumerate(assignment) if v],
                "unused_indexes": [i for i, v in enumerate(assignment) if not v],
                "gross_model_gold": total_gross, "paid_cost": total_paid,
                "net_model_gold": total_gross - total_paid, "closing_gold": gold,
                "windows": windows, "feasible": True}

    @staticmethod
    def _tie_key(plan):
        # Never deploy a zero-net card merely to make an apparent discount gain.
        # Equal net: fewer uses, then earlier use times, then stable card indexes.
        used = plan["used_indexes"]
        return (len(used), sum(plan["assignment"]), tuple(plan["assignment"]))

    def optimize(self):
        best = self.evaluate_plan([0] * len(self.hand))
        feasible = considered = 0
        for assignment in itertools.product(range(len(self.incomes) + 1), repeat=len(self.hand)):
            considered += 1
            try:
                plan = self.evaluate_plan(assignment)
            except ValueError:
                continue
            feasible += 1
            delta = plan["net_model_gold"] - best["net_model_gold"]
            if delta > EPSILON or (abs(delta) <= EPSILON and self._tie_key(plan) < self._tie_key(best)):
                best = plan
        return {"version": VERSION, "scope": copy.deepcopy(SCOPE),
                "inputs": {"hand": copy.deepcopy(self.hand), "incomes": list(self.incomes),
                           "initial_gold": self.initial_gold, "max_plays": list(self.max_plays)},
                "optimal_plan": best, "max_net_model_gold": best["net_model_gold"],
                "enumerated_assignments": considered, "feasible_assignments": feasible,
                "tie_rule": "maximum net; then fewer uses, earlier total use time, stable assignment"}

    def compare_discount(self, cost_delta):
        """Re-optimize lower costs and separately replay the old optimal plan.

        Only a nonpositive signed cost change is accepted: this guarantees that
        the old plan remains feasible. Direct savings concern its used cards
        only. The extra unlocking term may also include rescheduling/replacement,
        not solely new card indexes. No full-hand cash or extra body bonus.
        """
        _number(cost_delta, "cost_delta")
        if cost_delta > 0:
            raise ValueError("compare_discount requires a nonpositive signed cost_delta")
        old_result = self.optimize()
        discounted = copy.deepcopy(self.hand)
        for row in discounted:
            row["cost"] += cost_delta
        new_frontier = PaymentFrontier(discounted, self.incomes, self.initial_gold, self.max_plays)
        new_result = new_frontier.optimize()
        old_plan = old_result["optimal_plan"]
        replay = new_frontier.evaluate_plan(old_plan["assignment"])
        direct = old_plan["paid_cost"] - replay["paid_cost"]
        unlocking = new_result["max_net_model_gold"] - replay["net_model_gold"]
        total = new_result["max_net_model_gold"] - old_result["max_net_model_gold"]
        if abs((direct + unlocking) - total) > EPSILON or unlocking < -EPSILON:
            raise RuntimeError("Payment decomposition failed")
        return {"version": VERSION, "scope": copy.deepcopy(SCOPE), "cost_delta": cost_delta,
                "old": old_result, "new": new_result, "old_plan_at_new_cost": replay,
                "direct_paid_savings_gold": direct,
                "additional_unlocked_net_model_gold": unlocking,
                "total_net_improvement_model_gold": total,
                "decomposition": "total = direct paid savings on old plan + new optimum minus old-plan replay",
                "decomposition_residual": total - direct - unlocking,
                "newly_used_indexes": sorted(set(new_result["optimal_plan"]["used_indexes"]) - set(old_plan["used_indexes"])),
                "scope_note": "Only caller-quoted known-hand spending options; no extra body value or full-hand discount cash is added."}


def optimize_payments(hand, incomes, initial_gold=0, max_plays=2):
    return PaymentFrontier(hand, incomes, initial_gold, max_plays).optimize()


def compare_discount(hand, incomes, initial_gold=0, max_plays=2, cost_delta=-1):
    return PaymentFrontier(hand, incomes, initial_gold, max_plays).compare_discount(cost_delta)
