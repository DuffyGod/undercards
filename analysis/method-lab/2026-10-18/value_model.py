"""Small heuristic value experiment. No card engine, battle search or API.

Profiles specify endpoint assets and already realized effects. Card names do
not enter formulas. Model-G is a normative unit, not measured win probability.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math

VERSION = "endpoint-risk-option-0.1"


def finite(value, name, lower=None):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(name + " must be finite")
    if lower is not None and value < lower:
        raise ValueError(name + " is below its allowed minimum")
    return value


class BodyScale:
    """Retain the old capped-attack body hypothesis, frozen reference input.

    The reference contains printed bodies, not card quality or metagame rates.
    Its cost-stratum weights and all price coefficients are design assumptions.
    """
    def __init__(self, reference, face_share=.2, threshold_weight=.4):
        if not 0 <= finite(face_share, "face_share") <= 1:
            raise ValueError("face_share must be in [0,1]")
        finite(threshold_weight, "threshold_weight", 0)
        self.rows = tuple((r["attack"], r["health"], r["weight"]) for r in reference)
        if not self.rows or not math.isclose(sum(r[2] for r in self.rows), 1., abs_tol=1e-10):
            raise ValueError("Body reference must have total design weight 1")
        for a, h, w in self.rows:
            finite(a, "reference attack", 0); finite(h, "reference health", 0)
            finite(w, "reference weight", 0)
        self.face_share, self.threshold_weight = face_share, threshold_weight
        continuous, threshold = self.features(6, 5)
        self.alpha = (5 - threshold_weight * threshold) / continuous
        if self.alpha <= 0:
            raise ValueError("Threshold weight exhausts the body scale anchor")

    @lru_cache(maxsize=None)
    def effective_attack(self, attack):
        finite(attack, "attack", 0)
        return self.face_share * attack + (1-self.face_share) * sum(
            w * min(attack, h) for _, h, w in self.rows)

    def features(self, attack, health):
        if health <= 0:
            return 0., 0.
        attack = max(0, attack)
        continuous = math.sqrt((self.effective_attack(attack)+.5)*health)
        threshold = sum(w*(int(attack >= h)+int(health > a)+
                          int(attack >= h and health > a)) for a,h,w in self.rows)
        return continuous, threshold

    @lru_cache(maxsize=None)
    def value(self, attack, health):
        finite(attack, "attack", 0); finite(health, "health")
        c, t = self.features(attack, health)
        return self.alpha*c + self.threshold_weight*t


@dataclass(frozen=True)
class Asset:
    attack: float
    health: float
    base_attack: float
    base_health: float
    damage_taken: float = 0
    armor: bool = False
    dodge: int = 0

    def __post_init__(self):
        for k in ("attack", "base_attack", "base_health", "damage_taken"):
            finite(getattr(self, k), k, 0)
        finite(self.health, "health")
        if type(self.armor) is not bool or type(self.dodge) is not int or self.dodge < 0:
            raise ValueError("Explicit armor and nonnegative integer Dodge required")
        if self.armor and self.dodge:
            raise ValueError("Combined Armor/Dodge order is outside this experiment")


def after_packets(asset, packets):
    """A conditional exposure sketch, not an enemy-turn action simulator."""
    if not isinstance(packets, (tuple, list)):
        raise ValueError("Ordered nonnegative damage packets required")
    health, dodge = asset.health, asset.dodge
    for amount in packets:
        finite(amount, "damage packet", 0)
        if health <= 0:
            break
        if amount > 0 and dodge:
            dodge -= 1
        else:
            health -= max(0, amount - int(asset.armor))
    return Asset(asset.attack, health, asset.base_attack, asset.base_health,
                 asset.damage_taken + max(0, asset.health-health), asset.armor, dodge)


def after_silence(asset):
    # Only fresh endpoint growth is supported. No injured HP-buff reset ruling.
    if asset.damage_taken and asset.health + asset.damage_taken != asset.base_health:
        raise ValueError("Injured HP-modifier silence reset is unresolved")
    if asset.health <= 0:
        return asset
    return Asset(asset.base_attack, asset.base_health-asset.damage_taken,
                 asset.base_attack, asset.base_health, asset.damage_taken)


def endpoint(scale, asset, realized=0.):
    """Realized value + ONE remaining-body stock. No attack/kill bonus."""
    finite(realized, "realized value")
    return realized + scale.value(asset.attack, asset.health)


def response_curve(scale, asset, *, realized=0., kind="silence", packets=(),
                   response_cost=0, enemy_cash=0, response_access=True):
    finite(response_cost, "response cost", 0); finite(enemy_cash, "enemy cash", 0)
    if kind not in ("silence", "damage", "silence_kill"):
        raise ValueError("Unknown conditional response")
    no_reply = endpoint(scale, asset, realized)
    if type(response_access) is not bool:
        raise ValueError("Response access must be explicitly boolean")
    available = response_access and enemy_cash >= response_cost
    if not available:
        answered = no_reply
    elif kind == "silence":
        answered = endpoint(scale, after_silence(asset), realized)
    elif kind == "damage":
        answered = endpoint(scale, after_packets(asset, packets), realized)
    else:
        answered = realized
    loss = no_reply-answered
    return dict(no_reply=no_reply, answered=answered, loss=loss,
                response_available=available, response_cost=response_cost,
                enemy_cash=enemy_cash,response_target="candidate_body",
                response_access_assumed=response_access,
                value_at_p={str(p):no_reply-p*loss for p in (0., .1, .25, .5, 1.)},
                numeric_meaning="conditional recovered asset model-G; opponent resources excluded")


def crossing(left, right):
    """A(p)-B(p) intercept/slope; None if no crossing on [0,1]."""
    intercept = left["no_reply"]-right["no_reply"]
    slope = left["loss"]-right["loss"]
    if abs(slope) < 1e-12:
        return None
    p = intercept/slope
    return p if 0 <= p <= 1 else None


def common_plan(plans, probabilities):
    """Choose before response. Outcome columns are explicit design worlds."""
    if not plans or not probabilities or any(not isinstance(p,(int,float)) or
            not math.isfinite(p) or p < 0 for p in probabilities):
        raise ValueError("Plans and nonnegative finite world weights required")
    if not math.isclose(sum(probabilities),1.,abs_tol=1e-10):
        raise ValueError("World weights must sum to one")
    for row in plans:
        if len(row) != len(probabilities):
            raise ValueError("Every committed plan must contain every world")
        for v in row: finite(v, "plan outcome")
    means = [sum(p*v for p,v in zip(probabilities,row)) for row in plans]
    oracle = sum(p*max(row[i] for row in plans) for i,p in enumerate(probabilities))
    index = max(range(len(means)),key=means.__getitem__)
    return dict(value=means[index],plan_index=index,oracle_diagnostic=oracle,
                oracle_gap=oracle-means[index])


def fixed_deadline_option(now, future_net_values, probabilities, waiting_cost=0.):
    """One hold decision, then observe and deploy/decline at a fixed deadline.

    Endpoint values are already net of actual payment if deployed. No rolling
    window, no cost charged for declining, no secret future information now.
    Waiting cost is an EXOGENOUS foregone-value assumption, not measured tempo.
    """
    finite(now,"now net value"); finite(waiting_cost,"waiting cost",0)
    if len(future_net_values) != len(probabilities):
        raise ValueError("Future values and probabilities must match")
    validated = common_plan([future_net_values], probabilities)
    del validated
    wait = sum(p*max(0.,v) for p,v in zip(probabilities,future_net_values))-waiting_cost
    choices = {"deploy_now":now,"wait_once":wait,"decline":0.}
    choice = max(choices,key=choices.get)
    return dict(value=choices[choice],choice=choice,choices=choices,
                future_deploy=[v > 0 for v in future_net_values],
                world_weights_are_design_assumptions=True)


def hand_budget_value(cards, cash):
    """Tiny same-deadline payment menu, using declared additive net gains.

    No board, combos, generated cards, or conjectured full-match opportunities.
    """
    finite(cash,"cash",0)
    if len(cards)>7: raise ValueError("At most seven physical hand copies")
    for cost,net in cards:
        finite(cost,"cost",0); finite(net,"declared net gain")
    best,chosen = 0.,[]
    for mask in range(1<<len(cards)):
        ids=[i for i in range(len(cards)) if mask>>i&1]
        paid=sum(cards[i][0] for i in ids)
        gain=sum(cards[i][1] for i in ids)
        if paid <= cash and gain > best:best,chosen=gain,ids
    return dict(value=best,chosen_copies=chosen,paid=sum(cards[i][0] for i in chosen))
