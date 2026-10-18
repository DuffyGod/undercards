"""Freeze existing card/resource statistics; do not simulate or assign prices.

Run this file to refresh only statistical_inputs.json beside this source.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CARD_IDS = (2, 4, 9, 11, 13, 15, 20, 21, 43, 49, 168, 175, 187,
            243, 292, 377, 469, 470, 530, 602, 649, 984, 375)
COHORT_COSTS = {"aggro": range(1, 5), "midrange": range(4, 8),
                "control": range(5, 9)}
RESOURCE_KEYS = ("lower_cost", "middle_cost", "higher_cost")
PHASES = (3, 5, 8)


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(path):
    return path.relative_to(ROOT).as_posix()


def _unit_weight(rows, label):
    if not rows or any(not math.isfinite(r["weight"]) or r["weight"] < 0
                       for r in rows):
        raise ValueError(f"{label}: nonempty finite nonnegative weights required")
    if not math.isclose(sum(r["weight"] for r in rows), 1., abs_tol=1e-10):
        raise ValueError(f"{label}: weights must sum to one")


def build_inputs():
    snapshot_path = ROOT / "skills/undercards/references/snapshot.json"
    old_inputs_path = HERE / "inputs.json"
    snapshot = _read(snapshot_path)
    old_inputs = _read(old_inputs_path)
    if old_inputs["snapshot_sha256"] != _sha(snapshot_path):
        raise ValueError("Frozen body reference and current card snapshot differ")
    all_cards = snapshot["cards"]
    by_id = {c["id"]: c for c in all_cards}
    if len(by_id) != len(all_cards):
        raise ValueError("Duplicate snapshot card IDs")
    cards = {str(cid): by_id[cid] for cid in CARD_IDS}
    ordinary = [c for c in all_cards if c.get("card_type") == "monster"
                and c.get("pool_category") == "ordinary_non_token"
                and c.get("rarity") != "TOKEN" and c.get("health", 0) > 0]
    cohorts = {}
    cohort_summary = {}
    for name, cost_range in COHORT_COSTS.items():
        layers = {cost: [c for c in ordinary if c.get("cost") == cost]
                  for cost in cost_range}
        effective = {cost: layer for cost, layer in layers.items() if layer}
        if not effective:
            raise ValueError(f"No cards in {name}")
        rows = []
        for cost, layer in sorted(effective.items()):
            for c in sorted(layer, key=lambda c: c["id"]):
                rows.append({"id": c["id"], "attack": c["attack"],
                             "health": c["health"], "cost": cost,
                             "weight": 1. / (len(effective) * len(layer))})
        _unit_weight(rows, name)
        cohorts[name] = rows
        cohort_summary[name] = {
            "cards": len(rows),
            "cards_by_cost": {str(c): len(layer) for c, layer in effective.items()},
            "mean_attack": sum(r["weight"] * r["attack"] for r in rows),
            "mean_health": sum(r["weight"] * r["health"] for r in rows),
            "health_at_least": {str(h): sum(r["weight"] for r in rows
                                             if r["health"] >= h)
                                for h in range(2, 11)},
        }
    reference = old_inputs["reference"]
    _unit_weight(reference, "unchanged reference")
    resources = {}
    resource_summary = {}
    source_hashes = {_relative(snapshot_path): _sha(snapshot_path),
                     _relative(old_inputs_path): _sha(old_inputs_path)}
    folder = ROOT / "analysis/monster-value-heuristic/resource-comparison-v04"
    for key in RESOURCE_KEYS:
        profile_path = folder / f"{key}-profile.json"
        resource_path = folder / f"{key}-resources.json"
        profile, raw = _read(profile_path), _read(resource_path)
        if not raw.get("profile_ready"):
            raise ValueError(f"{key}: existing resource profile is not ready")
        if profile["resource_joint_samples"] != raw["unified_profile"]["resource_joint_samples"]:
            raise ValueError(f"{key}: profile/resource joint frequencies disagree")
        costs = raw["source"]["costs"]
        if len(costs) != 25:
            raise ValueError(f"{key}: expected an existing 25-cost source list")
        records, phase_metadata = [], {}
        for turn in PHASES:
            joint = profile["resource_joint_samples"][str(turn)]
            _unit_weight(joint, f"{key} turn {turn}")
            phase = raw["phase_summaries"][str(turn)]
            raw_pairs = {(r["gold_before"], r["hand_before"]):
                         r["conditional_nonempty_frequency"]
                         for r in phase["joint_frequencies"]}
            for r in joint:
                gold, hand, weight = (r["gold_before_play"],
                                      r["hand_size_before_play"], r["weight"])
                if not 1 <= hand <= 7 or gold < 0:
                    raise ValueError(f"{key}: invalid pre-decision resource state")
                if not math.isclose(weight, raw_pairs[(gold, hand)], abs_tol=1e-12):
                    raise ValueError(f"{key}: raw/profile frequency mismatch")
                records.append({"turn": turn, "gold_before_play": gold,
                                "hand_size_before_play": hand,
                                "weight": weight / len(PHASES)})
            phase_metadata[str(turn)] = {k: phase[k] for k in (
                "trials", "nonempty_hand_trials", "empty_hand_trials", "empty_hand_rate")}
        _unit_weight(records, key)
        hashes = {_relative(profile_path): _sha(profile_path),
                  _relative(resource_path): _sha(resource_path)}
        source_hashes.update(hashes)
        resources[key] = {"records": records, "source_costs": costs,
                          "source_hashes": hashes,
                          "resource_policy": raw["resource_policy"],
                          "resource_config": raw["resource_config"],
                          "source_costs_sha256": raw["source_costs_sha256"],
                          "phase_observation_counts": phase_metadata,
                          "inherited_limitations": raw["limitations"]}
        resource_summary[key] = {
            "joint_records": len(records),
            "hand_after_replacing_and_playing_one_slot_mean": sum(
                r["weight"] * (r["hand_size_before_play"] - 1) for r in records),
            "gold_mean": sum(r["weight"] * r["gold_before_play"] for r in records),
            "payable_rate_by_cost": {
                str(cost): sum(r["weight"] for r in records
                               if r["gold_before_play"] >= cost)
                for cost in range(0, 11)},
            "empty_hand_rate_by_phase": {t: v["empty_hand_rate"]
                                          for t, v in phase_metadata.items()},
        }
    return {
        "schema_version": "fixed-statistical-inputs-0.1",
        "snapshot_sha256": _sha(snapshot_path),
        "source_hashes": source_hashes,
        "reference": reference,
        "cards": cards,
        "cohorts": cohorts,
        "resources": resources,
        "filters": {
            "cohort_card_type": "monster",
            "cohort_pool_category": "ordinary_non_token",
            "cohort_excluded_rarity": "TOKEN",
            "cohort_health": ">0",
            "cohort_cost_ranges_inclusive": {k: [min(v), max(v)]
                                              for k, v in COHORT_COSTS.items()},
            "cohort_weighting": "Equal total weight per nonempty cost stratum; equal weight per card within each stratum.",
            "cohort_names": "aggro/midrange/control are cost-band aliases, not observed opponent archetype frequencies.",
            "reference": "Exact original inputs.json.reference, without filtering or renormalization.",
            "resource_phase_weights": {str(t): 1 / len(PHASES) for t in PHASES},
            "resource_within_phase": "Existing joint Gold/hand frequencies conditional on nonempty pre-decision hand; no marginal factorization.",
            "hand_interpretation": "Hypothetical fixed-slot replacement followed by play removes one card; not the observed distribution conditional on holding any particular candidate.",
            "source_costs_interpretation": "Historical abstract 25-cost deck lists; full deck legality was not validated.",
            "statistics_interpretation": "Card-pool census and historical resource-only Monte Carlo under a declared policy; not live-match frequencies, win rates, or metagame rates.",
            "uncertainty": "Cross-phase observations may share trials; record counts are not independent sample sizes. No price, strength ranking, or sampling confidence interval is assigned here.",
            "replay": "Read and validate stored files only; no API calls and no simulation reruns.",
        },
        "summary": {"reference_cards": len(reference), "frozen_card_ids": list(CARD_IDS),
                    "cohorts": cohort_summary, "resources": resource_summary},
    }


if __name__ == "__main__":
    frozen = build_inputs()
    destination = HERE / "statistical_inputs.json"
    destination.write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps(frozen["summary"], ensure_ascii=False, indent=2))
