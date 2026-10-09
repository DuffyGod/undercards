"""Adapt resource-only draw/payment samples into shared unified profile priors.

Input has exactly one of deck_costs/deck_card_ids (25 entries), an explicit
policy (deploy/reserve/save), explicit future_income_available_fraction, and
optional resource_config. Sampling frequencies are conditional on the stated
resource policy, not observed matches. Board states are never estimated here.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import statistics

import resource_curve as resource
import unified_value as unified

VERSION = "resource-profile-bridge-0.2.0"
PHASES = (3, 5, 8)
BUCKETS = ("deployed", "reserved")
DEFAULT_SEED = 20261008
DEFAULT_SNAPSHOT = Path(__file__).resolve().parents[2] / "skills/undercards/references/snapshot.json"
CONFIG_KEYS = {"opening_hand", "first_turn_draw", "first", "horizon", "trials", "seed",
               "reserve_budget", "key_cost", "trace_trials"}
LIMITATIONS = [
    "Abstract cost lists or snapshot cost lookups; full deck legality/copy caps are not validated.",
    "Frequencies come from resource-only sampling under the declared policy, not real-match frequencies.",
    "Only Gold and hand count are adapted; boards, targets, responses, Soul and card quality are not inferred.",
    "Phase bucket weights are conditional on a nonempty pre-decision hand; empty-hand frequency remains separately visible.",
    "Hand >=4 is called reserved as a resource bucket, not evidence of a player's intent.",
    "All nonempty observed Gold/hand pairs enter the numerical panel; bucket representatives remain diagnostics only.",
    "Future income fraction is supplied explicitly, not inferred from observed spending or quality.",
    "All four roles receive identical resource samples and representatives; other unified priors remain defaults.",
]


def digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def bucket(hand_count):
    return "reserved" if hand_count >= 4 else "deployed"


def summarize_phase(pairs, turn):
    """pairs contains (actual Gold_before, hand_before), including empty hands."""
    trials = len(pairs)
    empty = sum(hand == 0 for _, hand in pairs)
    frequencies = Counter((gold, hand) for gold, hand in pairs if hand > 0)
    nonempty = sum(frequencies.values())
    groups = {}
    for name in BUCKETS:
        observed = {pair: count for pair, count in frequencies.items() if bucket(pair[1]) == name}
        count = sum(observed.values())
        representative = None
        marginal_medians = None
        if count:
            gold_median = statistics.median([gold for (gold, _), n in observed.items() for _ in range(n)])
            hand_median = statistics.median([hand for (_, hand), n in observed.items() for _ in range(n)])
            # Joint representative is always an actual observation. Marginal
            # medians only set the common distance target; never combine them.
            pair = min(observed, key=lambda p: (abs(p[0] - gold_median) + abs(p[1] - hand_median),
                                                -observed[p], p[0], p[1]))
            representative = {"gold_before_play": pair[0], "hand_size_before_play": pair[1],
                              "observed_count": observed[pair],
                              "l1_distance_to_marginal_medians": abs(pair[0] - gold_median) + abs(pair[1] - hand_median)}
            marginal_medians = {"gold_before": gold_median, "hand_before": hand_median}
        groups[name] = {"observations": count,
                        "conditional_nonempty_weight": count / nonempty if nonempty else 0.,
                        "representative": representative, "marginal_medians": marginal_medians}
    rows = [{"gold_before": gold, "hand_before": hand, "count": count, "bucket": bucket(hand),
             "all_trial_frequency": count / trials if trials else 0.,
             "conditional_nonempty_frequency": count / nonempty if nonempty else 0.}
            for (gold, hand), count in sorted(frequencies.items())]
    return {"own_turn": turn, "trials": trials, "nonempty_hand_trials": nonempty,
            "empty_hand_trials": empty, "empty_hand_rate": empty / trials if trials else None,
            "joint_frequencies": rows, "buckets": groups,
            "no_nonempty_samples": nonempty == 0,
            "representative_rule": "closest observed joint pair to two marginal medians by L1; ties prefer count, then lower Gold, then lower hand count"}


def normalize_input(data, snapshot_path=DEFAULT_SNAPSHOT):
    if not isinstance(data, dict):
        raise ValueError("Input must be a JSON object")
    allowed = {"deck_costs", "deck_card_ids", "policy", "resource_config", "future_income_available_fraction", "name"}
    if not set(data) <= allowed:
        raise ValueError("Unknown bridge input fields")
    present = [key for key in ("deck_costs", "deck_card_ids") if key in data]
    if len(present) != 1:
        raise ValueError("Provide exactly one of deck_costs or deck_card_ids")
    values = data[present[0]]
    if not isinstance(values, list) or len(values) != 25:
        raise ValueError("Provide exactly 25 cost entries or card IDs")
    source = {"kind": present[0]}
    if present[0] == "deck_card_ids":
        if any(type(cid) is not int for cid in values):
            raise ValueError("Card IDs must be integers")
        raw = Path(snapshot_path).read_bytes()
        catalog = {card["id"]: card for card in json.loads(raw)["cards"]}
        if any(cid not in catalog for cid in values):
            raise ValueError("Unknown snapshot card ID")
        costs = [catalog[cid]["cost"] for cid in values]
        source.update(card_ids=list(values), snapshot_sha256=digest(raw))
    else:
        # Cost labels/annotations/roles cannot influence the resource policy.
        costs = [value.get("cost") if isinstance(value, dict) else value for value in values]
    policy = data.get("policy")
    if policy not in resource.POLICIES:
        raise ValueError("policy must explicitly be deploy, reserve or save")
    if "future_income_available_fraction" not in data:
        raise ValueError("Explicit future_income_available_fraction is required; it is never inferred from spending")
    fraction = data["future_income_available_fraction"]
    if type(fraction) not in (int, float) or not math.isfinite(fraction) or not 0 <= fraction <= 1:
        raise ValueError("future_income_available_fraction must be finite in [0,1]")
    config = data.get("resource_config", {})
    if not isinstance(config, dict) or not set(config) <= CONFIG_KEYS:
        raise ValueError("Unknown or invalid resource_config")
    config = {"trials": 500, "seed": DEFAULT_SEED, **config}
    cards, config, _ = resource.normalize_input({"deck": costs, "policies": [policy], **config})
    if config["horizon"] < max(PHASES):
        raise ValueError("Resource horizon must include own turns 3,5,8")
    name = data.get("name", "resource_sample_" + policy)
    if not isinstance(name, str):
        raise ValueError("Profile name must be text")
    source["costs"] = [card["cost"] for card in cards]
    return cards, config, policy, fraction, name, source


def build_profile(data, snapshot_path=DEFAULT_SNAPSHOT):
    cards, cfg, policy, fraction, name, source = normalize_input(data, snapshot_path)
    rng = random.Random(cfg["seed"])
    observations = {turn: [] for turn in PHASES}
    for _ in range(cfg["trials"]):
        order = list(cards)
        rng.shuffle(order)
        trace = resource.simulate_trial(order, cfg, policy)
        for turn in PHASES:
            row = trace["turns"][turn - 1]
            observations[turn].append((row["gold_before"], row["hand_before"]))
    summaries = {str(turn): summarize_phase(observations[turn], turn) for turn in PHASES}
    profile = copy.deepcopy(unified.DEFAULT_PROFILE)
    profile.update(name=name, second_player=not cfg["first"],
                   future_income_available_fraction=fraction, context_overrides={}, joint_resource_weights={},
                   resource_joint_samples={})
    for phase, summary in summaries.items():
        profile['resource_joint_samples'][phase]=[
            {'gold_before_play':row['gold_before'], 'hand_size_before_play':row['hand_before'],
             'weight':row['conditional_nonempty_frequency']}
            for row in summary['joint_frequencies']]
        profile["joint_resource_weights"][phase] = {}
        for state_name, stats in summary["buckets"].items():
            profile["joint_resource_weights"][phase][state_name] = stats["conditional_nonempty_weight"]
    ready = all(not summary["no_nonempty_samples"] for summary in summaries.values())
    if ready:
        profile = unified.normalize_profile(profile)
        unified.make_panel(profile)  # Exact resource cap and shared-weight validation.
    return {"bridge_version": VERSION, "profile_ready": ready,
            "unified_profile": profile if ready else None,
            "phase_summaries": summaries, "resource_policy": policy,
            "resource_config": cfg, "source": source,
            "source_costs_sha256": digest(source["costs"]),
            "future_income_fraction_source": "explicit caller value; not sampled expenditure",
            "resource_tool_version": "resource_curve schema 1",
            "unified_version": unified.VERSION,
            "unified_defaults_sha256": digest(unified.DEFAULT_PROFILE),
            "resource_script_sha256": digest(Path(resource.__file__).read_bytes()),
            "bridge_script_sha256": digest(Path(__file__).read_bytes()),
            "limitations": LIMITATIONS,
            "empty_phase_boundary": "No nonempty phase observations => no unified profile, no fabricated normalized weights."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--profile-output", type=Path, help="Optional standalone profile consumable by unified_value --profile")
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    args = parser.parse_args()
    result = build_profile(json.loads(args.input.read_text(encoding="utf-8")), args.snapshot)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    if args.profile_output:
        if not result["profile_ready"]:
            raise ValueError("Cannot export a profile with an empty sampled phase")
        args.profile_output.parent.mkdir(parents=True, exist_ok=True)
        args.profile_output.write_text(json.dumps(result["unified_profile"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
