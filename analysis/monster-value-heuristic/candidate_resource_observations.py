"""Physical-copy availability under public resource-only spending proxies.

This produces observations, never card prices or candidate-specific unified
weights. Decisions come from resource_curve; its ID trace is sufficient to
reconstruct the hand before each decision without inspecting future cards.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random

import resource_curve as resource

VERSION = "candidate-resource-observations-0.1.0"
DEFAULT_SEED = 20261008
DEFAULT_SNAPSHOT = Path(__file__).resolve().parents[2] / "skills/undercards/references/snapshot.json"
CONFIG_KEYS = {"opening_hand", "first_turn_draw", "first", "horizon", "trials", "seed",
               "reserve_budget", "key_cost", "trace_trials"}
COPY_STATES = ("in_hand", "not_yet_drawn", "burned", "used_before_decision")
GROUP_STATES = ("in_hand", "not_in_hand_with_unseen", "all_copies_used_or_burned")
LIMITATIONS = [
    "Resource-only samples under an explicit public spending proxy, not real-match frequencies or a card-quality policy.",
    "Physical IDs are original deck indexes, so equal-cost and equal-card-ID copies remain distinguishable.",
    "Samples are after current income/draw and before the current own-turn decision; current proxy plays are later events.",
    "Gold affordability is an upper bound: combat, board slots, targets, Soul, artifacts and effects are not modeled.",
    "Opening hand acquisition is recorded at turn 0 separately from subsequent deck draws; no mulligan is simulated.",
    "Previously used copies have unknown realized card value, not zero value; no score or candidate profile is emitted.",
    "A candidate set can contain heterogeneous abstract costs; its group observations describe at least one selected copy.",
    "Full deck legality, copy caps and current card rules are not validated by snapshot cost lookup.",
    "No public resource profile or unified state weights are modified or reinterpreted.",
]


def digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def normalize_input(data, snapshot_path=DEFAULT_SNAPSHOT):
    if not isinstance(data, dict):
        raise ValueError("Input must be a JSON object")
    allowed = {"deck_costs", "deck_card_ids", "candidate_indexes", "candidate_card_id",
               "policy", "resource_config", "phases"}
    if not set(data) <= allowed:
        raise ValueError("Unknown observation input fields")
    kinds = [key for key in ("deck_costs", "deck_card_ids") if key in data]
    if len(kinds) != 1:
        raise ValueError("Provide exactly one of deck_costs/deck_card_ids")
    values = data[kinds[0]]
    if not isinstance(values, list) or len(values) != 25:
        raise ValueError("Provide exactly 25 deck entries")
    source = {"kind": kinds[0]}
    if kinds[0] == "deck_card_ids":
        if any(type(cid) is not int for cid in values):
            raise ValueError("Card IDs must be integers")
        raw = Path(snapshot_path).read_bytes()
        catalog = {card["id"]: card for card in json.loads(raw)["cards"]}
        if any(cid not in catalog for cid in values):
            raise ValueError("Unknown snapshot card ID")
        costs = [catalog[cid]["cost"] for cid in values]
        source.update(card_ids=list(values), snapshot_sha256=digest(raw))
    else:
        costs = [value.get("cost") if isinstance(value, dict) else value for value in values]
    selectors = [key for key in ("candidate_indexes", "candidate_card_id") if key in data]
    if len(selectors) != 1:
        raise ValueError("Provide one explicit candidate selector")
    if selectors[0] == "candidate_card_id":
        cid = data["candidate_card_id"]
        if kinds[0] != "deck_card_ids" or type(cid) is not int:
            raise ValueError("candidate_card_id requires deck_card_ids and an integer ID")
        indexes = [index for index, card_id in enumerate(values) if card_id == cid]
        if not indexes:
            raise ValueError("Candidate card ID does not occur in this deck")
        source["candidate_card_id"] = cid
    else:
        indexes = data["candidate_indexes"]
        if not isinstance(indexes, list) or not indexes or any(type(index) is not int or not 0 <= index < 25 for index in indexes):
            raise ValueError("candidate_indexes must be a nonempty list of physical indexes 0..24")
        if len(set(indexes)) != len(indexes):
            raise ValueError("candidate_indexes must not contain duplicates")
        indexes = sorted(indexes)
    policy = data.get("policy")
    if policy not in resource.POLICIES:
        raise ValueError("Explicit deploy/reserve/save policy is required")
    config = data.get("resource_config", {})
    if not isinstance(config, dict) or not set(config) <= CONFIG_KEYS:
        raise ValueError("Unknown resource configuration")
    cards, cfg, _ = resource.normalize_input({"deck": costs, "policies": [policy],
                                             "trials": 500, "seed": DEFAULT_SEED, **config})
    phases = data.get("phases", [3, 5, 8])
    if not isinstance(phases, list) or not phases or any(type(turn) is not int or not 1 <= turn <= cfg["horizon"] for turn in phases):
        raise ValueError("phases must contain own turns within the declared horizon")
    if len(set(phases)) != len(phases):
        raise ValueError("Duplicate phases")
    source.update(costs=[card["cost"] for card in cards], candidate_indexes=list(indexes))
    return cards, cfg, policy, tuple(indexes), tuple(sorted(phases)), source


def reconstruct_trial(order, cfg, policy, candidate_indexes, phases):
    """Use only initial hand and already-emitted trace events for each sample.

    Full timings are retrospective diagnostics. Future timing fields never
    inform the phase snapshot or resource_curve.choose_subset.
    """
    trace = resource.simulate_trial(order, cfg, policy)
    costs = {card["id"]: card["cost"] for card in order}
    opening = [card["id"] for card in order[:cfg["opening_hand"]]]
    hand = list(opening)
    states = {card["id"]: "not_yet_drawn" for card in order}
    timings = {index: {"opening_hand": index in hand,
                       "drawn_turn": None, "first_in_hand_turn": 0 if index in hand else None,
                       "burned_turn": None, "first_resource_payable_turn": None,
                       "proxy_played_turn": None} for index in candidate_indexes}
    for index in hand:
        states[index] = "in_hand"
    snapshots = {}
    group_first_payable = None
    group_first_played = None
    for row in trace["turns"]:
        turn = row["turn"]
        drawn, burned = row["drawn_id"], row["burned_id"]
        if drawn is not None:
            assert states[drawn] == "not_yet_drawn"
            if drawn in timings:
                timings[drawn]["drawn_turn"] = turn
            if burned is not None:
                assert burned == drawn and len(hand) == 7
                states[drawn] = "burned"
                if drawn in timings:
                    timings[drawn]["burned_turn"] = turn
            else:
                hand.append(drawn)
                states[drawn] = "in_hand"
                if drawn in timings:
                    timings[drawn]["first_in_hand_turn"] = turn
        assert len(hand) == row["hand_before"] <= 7
        hand_candidates = [index for index in candidate_indexes if states[index] == "in_hand"]
        payable = [index for index in hand_candidates if costs[index] <= row["gold_before"]]
        for index in payable:
            if timings[index]["first_resource_payable_turn"] is None:
                timings[index]["first_resource_payable_turn"] = turn
        if payable and group_first_payable is None:
            group_first_payable = turn
        if turn in phases:
            copy_states = {str(index): states[index] for index in candidate_indexes}
            group_state = ("in_hand" if hand_candidates else "not_in_hand_with_unseen"
                           if "not_yet_drawn" in copy_states.values() else "all_copies_used_or_burned")
            snapshots[str(turn)] = {
                "own_turn": turn, "gold_before": row["gold_before"], "hand_before": len(hand),
                "hand_ids_before_decision": list(hand), "candidate_copy_states": copy_states,
                "candidate_deck_drawn_by_decision": {str(index): timings[index]["drawn_turn"] is not None
                                                     for index in candidate_indexes},
                "group_state": group_state, "candidate_copies_in_hand": len(hand_candidates),
                "resource_payable_in_hand": bool(payable),
                "any_candidate_opening_or_drawn": any(state != "not_yet_drawn" for state in copy_states.values()),
                "any_candidate_burned": "burned" in copy_states.values(),
                "any_candidate_used_before_decision": "used_before_decision" in copy_states.values(),
            }
        # This turn's choice occurs AFTER the phase snapshot. Do not classify
        # a copy that will now be used as already used before the decision.
        for index in row["played_ids"]:
            assert index in hand and states[index] == "in_hand"
            hand.remove(index)
            states[index] = "used_before_decision"
            if index in timings:
                timings[index]["proxy_played_turn"] = turn
                if group_first_played is None:
                    group_first_played = turn
        assert len(hand) == row["hand_after"]
        if turn in phases:
            snapshots[str(turn)]["candidate_proxy_played_on_this_turn"] = [
                index for index in row["played_ids"] if index in timings]
    return {"phase_snapshots": snapshots, "copy_timings": {str(index): value for index, value in timings.items()},
            "group_first_resource_payable_turn": group_first_payable,
            "group_first_proxy_played_turn": group_first_played,
            "resource_trace": trace}


def _distribution(values, trials):
    counts = Counter(values)
    return {"turns": [{"own_turn": turn, "count": count, "frequency": count / trials}
                      for turn, count in sorted(counts.items(), key=lambda item: (-1 if item[0] is None else item[0]))
                      if turn is not None],
            "not_observed_by_horizon_count": counts[None],
            "not_observed_by_horizon_rate": counts[None] / trials}


def _joint(rows, trials):
    frequencies = Counter((row["gold_before"], row["hand_before"]) for row in rows)
    count = len(rows)
    return {"conditioning_observations": count, "conditioning_rate": count / trials,
            "no_conditioning_samples": not count,
            "joint_frequencies": [{"gold_before": gold, "hand_before": hand, "count": n,
                                   "all_trial_frequency": n / trials, "conditional_frequency": n / count}
                                  for (gold, hand), n in sorted(frequencies.items())]}


def analyze(data, snapshot_path=DEFAULT_SNAPSHOT):
    cards, cfg, policy, indexes, phases, source = normalize_input(data, snapshot_path)
    rng = random.Random(cfg["seed"])
    observations = []
    for _ in range(cfg["trials"]):
        order = list(cards)
        rng.shuffle(order)
        observations.append(reconstruct_trial(order, cfg, policy, indexes, phases))
    trials = cfg["trials"]
    summaries = {}
    for turn in phases:
        rows = [trial["phase_snapshots"][str(turn)] for trial in observations]
        group_counts = Counter(row["group_state"] for row in rows)
        copies = {}
        for index in indexes:
            state_counts = Counter(row["candidate_copy_states"][str(index)] for row in rows)
            copies[str(index)] = {
                "state_counts": {state: state_counts[state] for state in COPY_STATES},
                "state_rates": {state: state_counts[state] / trials for state in COPY_STATES},
                "opening_or_drawn_rate": 1 - state_counts["not_yet_drawn"] / trials,
                "deck_drawn_by_decision_rate": sum(row["candidate_deck_drawn_by_decision"][str(index)] for row in rows) / trials,
                "joint_resources_given_in_hand": _joint([
                    row for row in rows if row["candidate_copy_states"][str(index)] == "in_hand"], trials),
                "proxy_played_on_current_turn_rate": sum(index in row["candidate_proxy_played_on_this_turn"] for row in rows) / trials,
            }
        summaries[str(turn)] = {
            "own_turn": turn, "trials": trials,
            "group_state_counts": {state: group_counts[state] for state in GROUP_STATES},
            "group_state_rates": {state: group_counts[state] / trials for state in GROUP_STATES},
            "joint_resources_given_candidate_in_hand": _joint([row for row in rows if row["candidate_copies_in_hand"]], trials),
            "candidate_in_hand_count_distribution": dict(sorted(Counter(row["candidate_copies_in_hand"] for row in rows).items())),
            "group_event_rates": {key: sum(bool(row[key]) for row in rows) / trials for key in (
                "resource_payable_in_hand", "any_candidate_opening_or_drawn", "any_candidate_burned",
                "any_candidate_used_before_decision", "candidate_proxy_played_on_this_turn")},
            "physical_copies": copies,
        }
    timing_fields = ("drawn_turn", "first_in_hand_turn", "burned_turn", "first_resource_payable_turn", "proxy_played_turn")
    timing_summaries = {
        str(index): {"opening_hand_rate": sum(trial["copy_timings"][str(index)]["opening_hand"] for trial in observations) / trials,
                     **{field: _distribution([trial["copy_timings"][str(index)][field] for trial in observations], trials)
                        for field in timing_fields}}
        for index in indexes}
    return {"version": VERSION, "resource_policy": policy, "resource_config": cfg,
            "phases": list(phases), "source": source, "phase_summaries": summaries,
            "copy_timing_summaries": timing_summaries,
            "group_first_resource_payable_turn": _distribution([trial["group_first_resource_payable_turn"] for trial in observations], trials),
            "group_first_proxy_played_turn": _distribution([trial["group_first_proxy_played_turn"] for trial in observations], trials),
            "traces": observations[:cfg["trace_trials"]],
            "source_costs_sha256": digest(source["costs"]),
            "resource_script_sha256": digest(Path(resource.__file__).read_bytes()),
            "observation_script_sha256": digest(Path(__file__).read_bytes()),
            "sampling_boundary": "after income and current draw; before current spending-proxy decision",
            "prior_use_value_boundary": "used_before_decision is a physical state; its realized quality/value is unestimated, never assigned zero",
            "scope": "availability and resource observations only; no price, profile conversion or automatic weights",
            "limitations": LIMITATIONS + resource.LIMITATIONS}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    args = parser.parse_args()
    result = analyze(json.loads(args.input.read_text(encoding="utf-8")), args.snapshot)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
