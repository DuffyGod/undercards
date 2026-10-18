"""Finite same-slot payment menus, tail=0 and no opponent response.

This is an explicit current-deadline comparator, not a full card value. Each
background is an actually blank printed body. Only one focal card can have
an effect; prefix/suffix/target choices are committed before random outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
import math

from statistical_value import FEATURES, deployment_plans


VERSION = "fixed-slot-current-menu-0.1"
ALLOWED_CANDIDATES = (2, 4, 9, 13, 15, 20, 21, 43, 49, 168, 175, 187,
                      377, 469, 530, 602, 984)


@dataclass(frozen=True)
class Plan:
    prefix: tuple[int, ...] = ()
    suffix: tuple[int, ...] = ()
    candidate_used: bool = False
    focal_action: str = ""


@dataclass(frozen=True)
class Quote:
    plan: Plan
    paid: float
    asset_value: float
    played_count: int
    summon_failure_weight: float = 0.
    remaining_body_count: float = 0.


@dataclass(frozen=True)
class Choice:
    value: float
    quote: Quote
    no_candidate_value: float


def subsets(indices):
    indices = tuple(indices)
    for count in range(len(indices) + 1):
        yield from combinations(indices, count)


def _finite(value, label, minimum=0):
    if type(value) not in (float, int) or not math.isfinite(value) or value < minimum:
        raise ValueError(label + " must be finite and at least " + str(minimum))


class SlotSolver:
    def __init__(self, cards, scale, face_price=.25):
        _finite(face_price, "face price")
        self.cards = cards
        self.scale = scale
        self.face_price = face_price

    def _backgrounds(self, background_ids):
        if len(background_ids) > 6:
            raise ValueError("At most seven physical cards including the focal slot")
        result = tuple(self.cards[str(cid)] for cid in background_ids)
        if any(c["effect_readable"].strip() or c["card_type"] != "monster"
               or c["health"] <= 0 for c in result):
            raise ValueError("Every physical background must actually have no effect")
        return result

    @lru_cache(maxsize=100000)
    def _focal_plans(self, candidate_id, enemy, hand_after_play, a_delta):
        if candidate_id not in ALLOWED_CANDIDATES:
            raise ValueError("Focal mechanism excluded from this restricted payment study")
        return tuple(deployment_plans(self.cards[str(candidate_id)], self.cards,
                                     enemy, hand_after_play, a_delta=a_delta))

    @lru_cache(maxsize=40000)
    def quotes(self, candidate_id, background_ids, enemy, slots, a_delta=0):
        """All current-deadline endpoints independent of cash and lambda.

        Slots is capacity available to this candidate and background. Other
        board positions contain shared inert occupants whose values cancel;
        selected focal mechanisms do not count or buff those friendly bodies.
        Car/Snowdrake are excluded because they would violate this boundary.
        The only no-room event possible in this focal subset is Archer's extra
        Clover: it explicitly fails to summon; legal Play remains available.
        """
        if type(slots) is not int or not 1 <= slots <= 4:
            raise ValueError("Empty-slot allowance must be an integer from one to four")
        if type(a_delta) is not int or a_delta < 0:
            raise ValueError("Only nonnegative integer printed-ATK interventions")
        backgrounds = self._backgrounds(background_ids)
        indices = tuple(range(len(backgrounds)))
        original_enemy = sum(self.scale.value(a, h) for a, h in enemy)
        body_values = tuple(self.scale.value(c["attack"], c["health"]) for c in backgrounds)
        candidate = self.cards[str(candidate_id)]
        result = []
        # Declining the focal card is always an actual physical option. This
        # branch appears first, so exact ties do not force focal deployment.
        for chosen in subsets(indices):
            if len(chosen) <= slots:
                result.append(Quote(Plan(suffix=chosen),
                                    sum(backgrounds[i]["cost"] for i in chosen),
                                    sum(body_values[i] for i in chosen), len(chosen),
                                    remaining_body_count=len(chosen)))
        for prefix in subsets(indices):
            if len(prefix) >= slots:
                continue  # A legal Play itself needs an initially free slot.
            unchosen = tuple(i for i in indices if i not in prefix)
            hand = len(backgrounds) - len(prefix)
            prefix_paid = sum(backgrounds[i]["cost"] for i in prefix)
            prefix_value = sum(body_values[i] for i in prefix)
            for name, lottery in self._focal_plans(candidate_id, enemy, hand, a_delta):
                if not math.isclose(sum(outcome[0] for outcome in lottery), 1., abs_tol=1e-10):
                    raise ValueError("Focal outcome weights must sum to one")
                fixed_outcomes = []
                for probability, team, remaining_enemy, face, draw, discount in lottery:
                    if draw:
                        raise ValueError("Draw-then-pay is intentionally excluded")
                    room = slots - len(prefix)
                    failed = len(team) > room
                    if failed:
                        if candidate_id != 984 or room < 1 or team[0].root is False:
                            raise ValueError("Unexpected board-capacity event outside declared assumption")
                        team = team[:room]
                    # No future Dust/keyword reserve is assigned. A currently
                    # summoned B child is still a real body, not future reserve.
                    enemy_delta = original_enemy - sum(self.scale.value(a, h) for a, h in remaining_enemy)
                    assets = (sum(self.scale.value(u.a, u.h) for u in team)
                              + enemy_delta
                              + face * self.face_price)
                    fixed_outcomes.append((probability, assets, len(team), failed))
                for suffix in subsets(unchosen):
                    # The SAME suffix is feasible in every random branch; no
                    # re-optimization after inspecting the Piranhas outcome.
                    if any(len(prefix) + count + len(suffix) > slots
                           for _, _, count, _ in fixed_outcomes):
                        continue
                    paid = prefix_paid + candidate["cost"] + sum(backgrounds[i]["cost"] for i in suffix)
                    asset_value = prefix_value + sum(body_values[i] for i in suffix)
                    asset_value += sum(p * value for p, value, _, _ in fixed_outcomes)
                    result.append(Quote(Plan(prefix, suffix, True, name), paid, asset_value,
                                        len(prefix) + len(suffix) + 1,
                                        sum(p * int(failed) for p, _, _, failed in fixed_outcomes),
                                        len(prefix) + len(suffix) + sum(p * n for p, _, n, _ in fixed_outcomes)))
        return tuple(result)

    def best(self, candidate_id, background_ids, enemy, cash, slots, cash_residual=0., a_delta=0):
        _finite(cash, "cash"); _finite(cash_residual, "cash residual coefficient")
        eligible = [q for q in self.quotes(candidate_id, tuple(background_ids), tuple(enemy), slots, a_delta)
                    if q.paid <= cash]
        # Enumeration orders the empty plan first; a stable max uses the
        # first equal-valued plan. This makes all-tie behavior reproducible.
        chosen = eligible[0]
        chosen_value = chosen.asset_value + cash_residual * (cash - chosen.paid)
        for quote in eligible[1:]:
            value = quote.asset_value + cash_residual * (cash - quote.paid)
            if value > chosen_value + 1e-10:
                chosen, chosen_value = quote, value
        no_candidate = max(q.asset_value + cash_residual * (cash - q.paid)
                           for q in eligible if not q.plan.candidate_used)
        return Choice(chosen.asset_value + cash_residual * (cash - chosen.paid), chosen, no_candidate)

    def fixed(self, plan, candidate_id, background_ids, enemy, cash, slots,
              cash_residual=0., a_delta=0):
        """Value the exact previously committed menu and initial target."""
        for quote in self.quotes(candidate_id, tuple(background_ids), tuple(enemy), slots, a_delta):
            if quote.plan == plan and quote.paid <= cash:
                return quote.asset_value + cash_residual * (cash - quote.paid)
        raise ValueError("Fixed physical menu is not feasible after intervention")


def compare_slot(solver, candidate_id, reference_id, background_ids, enemy,
                 cash, slots, cash_residual, with_marginals=True):
    arguments = (tuple(background_ids), tuple(enemy), cash, slots, cash_residual)
    candidate = solver.best(candidate_id, *arguments)
    reference = solver.best(reference_id, *arguments)
    result = {
        "candidate_value": candidate.value, "reference_value": reference.value,
        "slot_delta": candidate.value - reference.value,
        "candidate_used": candidate.quote.plan.candidate_used,
        "candidate_gain_over_background": candidate.value - candidate.no_candidate_value,
        "candidate_strictly_improves_background": candidate.value > candidate.no_candidate_value + 1e-10,
        "candidate_selected_without_strict_gain": candidate.quote.plan.candidate_used and
            candidate.value <= candidate.no_candidate_value + 1e-10,
        "candidate_no_plays": candidate.quote.played_count == 0,
        "reference_used": reference.quote.plan.candidate_used,
        "reference_no_plays": reference.quote.played_count == 0,
        "candidate_paid": candidate.quote.paid, "reference_paid": reference.quote.paid,
        "candidate_summon_failure_weight": candidate.quote.summon_failure_weight,
        "candidate_plan": {"prefix": candidate.quote.plan.prefix,
                           "suffix": candidate.quote.plan.suffix,
                           "candidate_used": candidate.quote.plan.candidate_used,
                           "action": candidate.quote.plan.focal_action},
        "reference_plan": {"prefix": reference.quote.plan.prefix,
                           "suffix": reference.quote.plan.suffix,
                           "candidate_used": reference.quote.plan.candidate_used,
                           "action": reference.quote.plan.focal_action},
    }
    if not with_marginals:
        return result
    upgraded = solver.best(candidate_id, *arguments, a_delta=1)
    fixed = solver.fixed(candidate.quote.plan, candidate_id, *arguments, a_delta=1)
    cash_candidate = solver.best(candidate_id, tuple(background_ids), tuple(enemy), cash + 1, slots, cash_residual)
    cash_reference = solver.best(reference_id, tuple(background_ids), tuple(enemy), cash + 1, slots, cash_residual)
    result.update({
        "plus_attack_reoptimized": upgraded.value - candidate.value,
        "plus_attack_fixed_menu": fixed - candidate.value,
        "plus_cash_candidate": cash_candidate.value - candidate.value,
        "plus_cash_reference": cash_reference.value - reference.value,
        "plus_cash_slot_delta": cash_candidate.value - cash_reference.value - result["slot_delta"],
        "plus_slot_candidate": None, "plus_slot_reference": None, "plus_slot_delta": None,
    })
    if slots < 4:
        more_candidate = solver.best(candidate_id, tuple(background_ids), tuple(enemy), cash, slots + 1, cash_residual)
        more_reference = solver.best(reference_id, tuple(background_ids), tuple(enemy), cash, slots + 1, cash_residual)
        result.update({"plus_slot_candidate": more_candidate.value - candidate.value,
                       "plus_slot_reference": more_reference.value - reference.value,
                       "plus_slot_delta": more_candidate.value - more_reference.value - result["slot_delta"]})
    return result
