"""Run the frozen small current-slot experiment; writes only slot-results/."""
from __future__ import annotations

from collections import defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path
import random
import shutil
import time

from slot_value import VERSION, SlotSolver, compare_slot
from value_model import BodyScale


HERE = Path(__file__).resolve().parent
OUT = HERE / "slot-results"
CANDIDATES = [9, 13, 15, 20, 21, 43, 49, 168, 175, 187, 377, 469, 530, 602, 984]
MENUS = {"two_plain": [2, 4], "three_plain": [2, 187, 15],
         "four_plain": [4, 602, 187, 15]}
CASH = (4, 6, 8, 10)
SLOTS = (1, 2, 4)
LAMBDAS = (0., .5, 1.)
REFERENCES = (2, 4)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(name, rows):
    with (OUT / name).open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def deterministic_gzip(name):
    source = OUT / name
    destination = OUT / (name + ".gz")
    # No original filename, path or current timestamp in the gzip header.
    with source.open("rb") as incoming, destination.open("wb") as raw_out:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_out,
                           compresslevel=9, mtime=0) as compressed:
            shutil.copyfileobj(incoming, compressed)
    return {"source": name, "gzip": name + ".gz", "source_sha256": sha(source),
            "gzip_sha256": sha(destination), "source_bytes": source.stat().st_size,
            "gzip_bytes": destination.stat().st_size,
            "gzip_mtime": 0, "gzip_original_filename": ""}


def build_boards(inputs):
    boards = [dict(group="empty", name="empty", enemy=(), weight=1.),
              dict(group="three_3_2", name="three_3_2", enemy=((3, 2),) * 3, weight=1.),
              dict(group="single_6_7", name="single_6_7", enemy=((6, 7),), weight=1.)]
    rng = random.Random(20261018043)
    cohort = inputs["cohorts"]["aggro"]
    for i in range(32):
        draw = rng.choices(cohort, weights=[c["weight"] for c in cohort], k=3)
        boards.append(dict(group="aggro_32", name=f"aggro_{i:02d}",
                           enemy=tuple((c["attack"], c["health"]) for c in draw),
                           source_ids=[c["id"] for c in draw], weight=1 / 32))
    return boards


def main():
    OUT.mkdir(exist_ok=True)
    started = time.monotonic()
    input_path = HERE / "statistical_inputs.json"
    source_names = ("slot_value.py", "run_slot_study.py", "test_slot_value.py",
                    "statistical_value.py", "value_model.py")
    source_hashes_before = {name: sha(HERE / name) for name in source_names}
    inputs = json.loads(input_path.read_text(encoding="utf-8"))
    solver = SlotSolver(inputs["cards"], BodyScale(inputs["reference"]))
    boards = build_boards(inputs)
    primary_rows, alternate_rows = [], []
    accumulators = {}
    metric_keys = ("slot_delta", "candidate_value", "reference_value", "candidate_used",
                   "candidate_gain_over_background", "candidate_strictly_improves_background",
                   "candidate_selected_without_strict_gain", "candidate_no_plays", "reference_used",
                   "reference_no_plays", "candidate_paid", "reference_paid", "candidate_summon_failure_weight",
                   "plus_attack_reoptimized", "plus_attack_fixed_menu", "plus_cash_candidate",
                   "plus_cash_reference", "plus_cash_slot_delta", "plus_slot_candidate",
                   "plus_slot_reference", "plus_slot_delta")
    invariants = {"fixed_attack_exceeds_reoptimization": [], "negative_attack_gain": [],
                  "negative_cash_gain": [], "negative_slot_gain": [], "identity_failure": []}
    for menu_name, background in MENUS.items():
        relevant_boards = [b for b in boards if b["group"] != "aggro_32" or menu_name == "three_plain"]
        for board in relevant_boards:
            for cash in CASH:
                for slots in SLOTS:
                    for lam in LAMBDAS:
                        for cid in CANDIDATES:
                            for reference in REFERENCES:
                                result = compare_slot(solver, cid, reference, background, board["enemy"],
                                                      cash, slots, lam, with_marginals=reference == 2)
                                row = dict(menu=menu_name, board_group=board["group"], board=board["name"],
                                           candidate_id=cid, candidate_name=inputs["cards"][str(cid)]["name"],
                                           reference_id=reference, cash=cash, empty_slots=slots,
                                           cash_residual=lam,
                                           **{k: v for k, v in result.items() if k not in ("candidate_plan", "reference_plan")},
                                           candidate_plan=json.dumps(result["candidate_plan"], separators=(",", ":")),
                                           reference_plan=json.dumps(result["reference_plan"], separators=(",", ":")))
                                (primary_rows if reference == 2 else alternate_rows).append(row)
                                key = (menu_name, board["group"], lam, cid, reference)
                                if key not in accumulators:
                                    accumulators[key] = {"sums": defaultdict(float), "weights": defaultdict(float)}
                                acc = accumulators[key]
                                weight = board["weight"] / (len(CASH) * len(SLOTS))
                                for metric in metric_keys:
                                    value = result.get(metric)
                                    if value is not None:
                                        acc["sums"][metric] += weight * value
                                        acc["weights"][metric] += weight
                                if reference == 2:
                                    label = [menu_name, board["name"], cash, slots, lam, cid]
                                    if result["plus_attack_fixed_menu"] > result["plus_attack_reoptimized"] + 1e-9:
                                        invariants["fixed_attack_exceeds_reoptimization"].append(label)
                                    if result["plus_attack_reoptimized"] < -1e-9:
                                        invariants["negative_attack_gain"].append(label)
                                    if min(result["plus_cash_candidate"], result["plus_cash_reference"]) < -1e-9:
                                        invariants["negative_cash_gain"].append(label)
                                    if result["plus_slot_candidate"] is not None and min(
                                            result["plus_slot_candidate"], result["plus_slot_reference"]) < -1e-9:
                                        invariants["negative_slot_gain"].append(label)
            print(json.dumps({"menu": menu_name, "completed_board": board["name"],
                              "primary_rows": len(primary_rows)}), flush=True)
        # Clear the large quote cache between backgrounds; keep the same F.
        solver.quotes.cache_clear()
    summaries = []
    for (menu, board_group, lam, cid, reference), acc in accumulators.items():
        summaries.append(dict(menu=menu, board_group=board_group, cash_residual=lam,
                              candidate_id=cid, candidate_name=inputs["cards"][str(cid)]["name"],
                              reference_id=reference,
                              **{metric: acc["sums"][metric] / acc["weights"][metric]
                                 for metric in metric_keys if acc["weights"][metric]}))
    # Identity at representative cases validates true same-slot replacement.
    for cash in CASH:
        for slots in SLOTS:
            for lam in LAMBDAS:
                identity = compare_slot(solver, 2, 2, MENUS["three_plain"], ((6, 7),), cash, slots, lam,
                                        with_marginals=False)
                if abs(identity["slot_delta"]) > 1e-10:
                    invariants["identity_failure"].append([cash, slots, lam])
    source_hashes_after = {name: sha(HERE / name) for name in source_names}
    if source_hashes_before != source_hashes_after:
        raise RuntimeError("A source changed during this experiment; refusing mixed-version output")
    write_csv("slot-primary.csv", primary_rows)
    write_csv("slot-reference-sensitivity.csv", alternate_rows)
    compressed_exports = [deterministic_gzip(name) for name in
                          ("slot-primary.csv", "slot-reference-sensitivity.csv")]
    write_csv("slot-summary.csv", summaries)
    dump("slot-summary.json", summaries)
    dump("slot-design.json", {
        "version": VERSION, "candidate_ids": CANDIDATES, "background_menus": MENUS,
        "primary_reference_id": 2, "alternate_reference_id": 4,
        "cash": CASH, "initial_empty_slots": SLOTS, "cash_residual_coefficients": LAMBDAS,
        "boards": boards, "random_board_scope": "three_plain only; same frozen 32 probes for every candidate/reference",
        "face_damage_price": .25, "future_tail": 0, "opponent_reply": "none",
        "physical_own_board": "Slots are available to the focal/background cards; other positions contain shared inert occupants whose body values cancel. Selected mechanisms do not count/buff those friendly occupants; Car/Snowdrake are excluded.",
        "hand": "Exactly the physical background copies plus the replacement slot; prefix play removes copies before focal hand count.",
        "summon_capacity": "If Archer's extra Clover has no room it fails; legal source Play is retained. B's child replaces its dead source.",
        "tie_rule": "First menu within1e-10 numerical tie tolerance; no-focal menus precede focal menus. Selected-use rates are convention-dependent at ties.",
        "candidate_usage_fields": {
            "candidate_used": "Whether the canonical maximizing menu deployed the focal copy.",
            "candidate_gain_over_background": "M_candidate minus M_background_only, same cash/board/slots/lambda.",
            "candidate_strictly_improves_background": "Necessary-for-gain mass: M_candidate-M_background_only>1e-10; independent of arbitrary zero-gain deployment ties.",
            "candidate_selected_without_strict_gain": "Canonical deployment with no strictly positive gain; exposes tie-selected use if present.",
        },
        "summary_weights": "Each cash and slot level equal weight; named boards separate, sampled boards 1/32; no empirical match frequencies.",
        "no_future_values": "Unused held cards, future ordinary attacks beyond F, Dust discounts, Dodge/Armor/Taunt/Bullseye/chain continuation reserves excluded.",
        "limitations": ["Current finite payment menu marginal, not full card quality or match value.",
                        "Enemy probes have no abilities or reactions; no player terminal or Soul effects.",
                        "ATK intervention changes only the focal physical copy's printed ATK, not duplicate background copies.",
                        "lambda=0 discards cash at this deadline; lambda=1 prices retained Gold but may favor no development.",
                        "Only initial target, prefix and suffix commitment policies are considered; no re-optimization after random chain.",
                        "At slot cap4, slot+1 is null rather than inventing a fifth board slot."],
        "input_sha256": sha(input_path),
        "source_sha256": source_hashes_before,
        "source_sha256_unchanged_during_run": True,
        "deterministic_compressed_exports": compressed_exports,
    })
    dump("slot-verification.json", {
        "primary_rows": len(primary_rows), "alternate_reference_rows": len(alternate_rows),
        "summary_rows": len(summaries), "elapsed_seconds": time.monotonic() - started,
        "invariant_failure_counts": {k: len(v) for k, v in invariants.items()},
        "invariant_failures": invariants,
        "same_slot_identity_cases": len(CASH) * len(SLOTS) * len(LAMBDAS),
        "not_external_calibration": True,
    })
    print(json.dumps({"finished": True, "primary_rows": len(primary_rows),
                      "alternate_reference_rows": len(alternate_rows),
                      "invariant_failure_counts": {k: len(v) for k, v in invariants.items()},
                      "elapsed_seconds": time.monotonic() - started}), flush=True)


if __name__ == "__main__":
    main()
