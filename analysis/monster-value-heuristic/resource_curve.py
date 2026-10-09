"""Resource-only Undercards curve probes; no combat, targets, slots or win rates.

Input: {"deck": [cost or {"cost": cost, "role": "label"}, ...25],
        "opening_hand": 3, "first_turn_draw": true, "first": true,
        "horizon": 8, "trials": 2000, "seed": 20261007,
        "reserve_budget": 3, "key_cost": 6, "trace_trials": 0}

Policies inspect the current hand only. deploy maximizes sum(cost)+0.25*count
over affordable subsets. This is a spending proxy, not card quality. reserve
uses the same proxy after withholding a fixed response budget. save behaves
like deploy until a key-cost card is actually in hand; then saves everything
until one is affordable and prioritizes a subset containing one such card.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

POLICIES = ("deploy", "reserve", "save")
LIMITATIONS = [
    "Abstract 25-card cost lists; no actual deck legality, Soul or artifact validation.",
    "No mulligan, extra income/draw, discount, combat, targets, slots, health or fatigue.",
    "Initial Gold is 1; Gold carries over; own-turn income is min(turn,10).",
    "Second player receives +1 on own turns 1,3,5,7,9 only.",
    "At hand size 7 the next drawn card is burned; a draw with an empty deck does nothing here.",
    "Opening hand and first-turn draw are explicit inputs, not inferred game rulings.",
    "Spending-proxy policies are illustrative resource plans, not optimal play or win-rate estimates.",
    "No target/slot restrictions: affordable action rates are resource upper bounds.",
]


def income(turn: int, first: bool = True) -> int:
    return min(turn, 10) + int(not first and turn <= 9 and turn % 2 == 1)


def _integer(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def normalize_input(data):
    deck = data.get("deck")
    if not isinstance(deck, list) or len(deck) != 25:
        raise ValueError("deck must contain exactly 25 costs or cost objects")
    cards = []
    for index, item in enumerate(deck):
        cost = item.get("cost") if isinstance(item, dict) else item
        cost = _integer(cost, f"deck[{index}].cost")
        # Annotations and text are never interpreted as policy signals.
        role = item.get("role", "") if isinstance(item, dict) else ""
        if not isinstance(role, str):
            raise ValueError("role must be a string when supplied")
        cards.append({"id": index, "cost": cost, "role": role})
    cfg = {"opening_hand": 3, "first_turn_draw": True, "first": True,
           "horizon": 8, "trials": 2000, "seed": 20261007,
           "reserve_budget": 3, "key_cost": 6, "trace_trials": 0}
    for key in cfg:
        if key in data:
            cfg[key] = data[key]
    for key in ("opening_hand", "horizon", "trials", "seed", "reserve_budget", "key_cost", "trace_trials"):
        _integer(cfg[key], key, 1 if key in ("horizon", "trials") else 0)
    if cfg["opening_hand"] > 7:
        raise ValueError("opening_hand cannot exceed the seven-card hand limit")
    for key in ("first", "first_turn_draw"):
        if not isinstance(cfg[key], bool):
            raise ValueError(f"{key} must be a boolean")
    policies = data.get("policies", list(POLICIES))
    if not isinstance(policies, list) or not policies or len(set(policies)) != len(policies):
        raise ValueError("policies must be a nonempty list without duplicates")
    if any(policy not in POLICIES for policy in policies):
        raise ValueError(f"policies must be selected from {POLICIES}")
    return cards, cfg, policies


def choose_subset(hand, gold, policy, cfg):
    """No access to deck order or future cards; returns current-hand indices."""
    if len(hand) > 7:
        raise ValueError("subset enumeration assumes hand size <= 7")
    if policy not in POLICIES:
        raise ValueError("unknown policy")
    budget = gold
    key_indices = {i for i, card in enumerate(hand) if card["cost"] == cfg["key_cost"]}
    require_key = False
    intentional_reason = None
    if policy == "reserve":
        budget = max(0, gold - cfg["reserve_budget"])
        intentional_reason = "reserve_budget"
    elif policy == "save" and key_indices:
        if gold < cfg["key_cost"]:
            return [], 0, "save_for_known_key"
        require_key = True
    best = (0, 0, 0)
    chosen = []
    # Enumerate masks in ascending order; identical spending/count keeps the
    # earliest mask, independent of card labels and unseen cards.
    for mask in range(1 << len(hand)):
        indices = [i for i in range(len(hand)) if mask & (1 << i)]
        if require_key and not key_indices.intersection(indices):
            continue
        spend = sum(hand[i]["cost"] for i in indices)
        if spend > budget:
            continue
        objective = (4 * spend + len(indices), spend, len(indices))
        if objective > best:
            best, chosen = objective, indices
    return chosen, budget, intentional_reason


def simulate_trial(order, cfg, policy):
    """Simulate one fixed shuffled order, enabling paired policy comparisons."""
    hand = list(order[:cfg["opening_hand"]])
    cursor = cfg["opening_hand"]
    gold = 1
    burns = 0
    first_key_payment = None
    records = []
    for turn in range(1, cfg["horizon"] + 1):
        prior_gold = gold
        received = income(turn, cfg["first"])
        gold += received
        burned = None
        draw = None
        if (turn > 1 or cfg["first_turn_draw"]) and cursor < len(order):
            draw = order[cursor]
            cursor += 1
            if len(hand) == 7:
                burned = draw["id"]
                burns += 1
            else:
                hand.append(draw)
        hand_before = list(hand)
        gold_before = gold
        payable = sum(card["cost"] <= gold for card in hand)
        selected, budget, intentional_reason = choose_subset(hand, gold, policy, cfg)
        chosen = [hand[i] for i in selected]
        spend = sum(card["cost"] for card in chosen)
        assert spend <= gold
        gold -= spend
        if first_key_payment is None and any(card["cost"] == cfg["key_cost"] for card in chosen):
            first_key_payment = turn
        selected_set = set(selected)
        hand = [card for i, card in enumerate(hand) if i not in selected_set]
        reasons = Counter()
        for card in hand:
            if card["cost"] > gold_before:
                reasons["insufficient_gold_at_decision"] += 1
            elif intentional_reason and card["cost"] > budget:
                reasons[intentional_reason] += 1
            else:
                reasons["budget_allocated_to_other_cards"] += 1
        records.append({
            "turn": turn, "prior_gold": prior_gold, "income": received,
            "gold_before": gold_before, "spend": spend, "gold_after": gold,
            "hand_before": len(hand_before), "hand_after": len(hand),
            "resource_payable_cards": payable, "played_count": len(chosen),
            "multi_card_spend": len(chosen) >= 2, "empty_hand": not hand,
            "full_hand": len(hand) == 7,
            "no_play_despite_resource_payable": not chosen and payable > 0,
            "unplayed_reasons": dict(reasons),
            "drawn_id": None if draw is None else draw["id"], "burned_id": burned,
            "played_ids": [card["id"] for card in chosen],
            "played_costs": [card["cost"] for card in chosen],
        })
    return {"turns": records, "first_key_payment": first_key_payment,
            "burns": burns, "cards_remaining_in_deck": len(order) - cursor}


def _summarize(traces, cfg):
    count = len(traces)
    turns = []
    means = ("prior_gold", "income", "gold_before", "spend", "gold_after",
             "hand_before", "hand_after", "resource_payable_cards", "played_count")
    for index in range(cfg["horizon"]):
        rows = [trace["turns"][index] for trace in traces]
        row = {"turn": index + 1}
        row.update({f"mean_{key}": sum(item[key] for item in rows) / count for key in means})
        for key in ("multi_card_spend", "empty_hand", "full_hand", "no_play_despite_resource_payable"):
            row[f"rate_{key}"] = sum(bool(item[key]) for item in rows) / count
        row["rate_resource_payable_action"] = sum(item["resource_payable_cards"] > 0 for item in rows) / count
        row["rate_played_any"] = sum(item["played_count"] > 0 for item in rows) / count
        row["rate_burn"] = sum(item["burned_id"] is not None for item in rows) / count
        reasons = Counter()
        for item in rows:
            reasons.update(item["unplayed_reasons"])
        row["mean_unplayed_cards_by_reason"] = {key: value / count for key, value in sorted(reasons.items())}
        turns.append(row)
    payments = Counter(trace["first_key_payment"] for trace in traces)
    paid_turns = [trace["first_key_payment"] for trace in traces if trace["first_key_payment"] is not None]
    return {"turns": turns, "first_key_payment_turn_probabilities": {
        str(turn): payments[turn] / count for turn in range(1, cfg["horizon"] + 1)},
        "probability_key_never_paid_by_horizon": payments[None] / count,
        "mean_first_key_payment_turn_conditional_on_paid": sum(paid_turns) / len(paid_turns) if paid_turns else None,
        "mean_burns": sum(trace["burns"] for trace in traces) / count,
        "traces": traces[:cfg["trace_trials"]]}


def analyze(data):
    cards, cfg, policies = normalize_input(data)
    rng = random.Random(cfg["seed"])
    traces = {policy: [] for policy in policies}
    for _ in range(cfg["trials"]):
        order = list(cards)
        rng.shuffle(order)
        for policy in policies:
            traces[policy].append(simulate_trial(order, cfg, policy))
    return {"schema_version": 1, "model": "resource_only_spending_proxy",
            "config": cfg, "cost_histogram": dict(sorted(Counter(card["cost"] for card in cards).items())),
            "limitations": LIMITATIONS, "paired_shuffled_orders": True,
            "sampling_note": "Monte Carlo fractions under stated draw and spending assumptions; not actual-match statistics.",
            "policies": {policy: _summarize(values, cfg) for policy, values in traces.items()}}


def demo_data():
    decks = {"low_cost": [1] * 6 + [2] * 8 + [3] * 5 + [4] * 4 + [6] * 2,
             "middle_cost": [1] * 2 + [2] * 4 + [3] * 4 + [4] * 5 + [5] * 4 + [6] * 4 + [8] * 2,
             "high_cost": [2] * 3 + [3] * 3 + [4] * 3 + [5] * 4 + [6] * 5 + [8] * 4 + [10] * 3}
    return {"demo_notice": "Three abstract 25-card cost lists, not actual decks and not recommendations.",
            "decks": {name: analyze({"deck": deck}) for name, deck in decks.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path)
    source.add_argument("--demo", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = demo_data() if args.demo else analyze(json.loads(args.input.read_text(encoding="utf-8")))
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
