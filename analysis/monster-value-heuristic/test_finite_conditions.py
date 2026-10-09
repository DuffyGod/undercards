import copy
import unittest

import finite_conditions as f


def card(identity=1, generated=False, card_type="monster", rarity="COMMON"):
    return {"identity": identity, "generated": generated, "card_type": card_type, "rarity": rarity}


class ConditionsTests(unittest.TestCase):
    def evaluate(self, spec, state):
        return f.evaluate_condition(spec, state)["value"]

    def test_free_spells_and_cast_count_are_not_gold_spending(self):
        spec = {"kind": "last_turn_spell_spend_positive"}
        self.assertFalse(self.evaluate(spec, {"last_turn_gold_spent_on_spells": 0, "last_turn_spell_cast_count": 3}))
        self.assertTrue(self.evaluate(spec, {"last_turn_gold_spent_on_spells": 2, "last_turn_spell_cast_count": 1}))
        result = f.evaluate_condition(spec, {"last_turn_spell_cast_count": 7})
        self.assertIsNone(result["value"])
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["required_fields"], ["last_turn_gold_spent_on_spells"])

    def test_duplicates_use_current_deck_kind_identity_and_generated_exclusion(self):
        spec = {"kind": "deck_no_duplicates"}
        self.assertFalse(self.evaluate(spec, {"remaining_deck": [card(1), card(1)]}))
        self.assertTrue(self.evaluate(spec, {"remaining_deck": [card(1), card(1, generated=True)]}))
        self.assertTrue(self.evaluate(spec, {"remaining_deck": [card(1, generated=True), card(1, generated=True)]}))
        initial = [card(1), card(1)]
        self.assertTrue(self.evaluate(spec, {"initial_deck": initial, "remaining_deck": [card(1)]}))
        self.assertIsNone(self.evaluate(spec, {"initial_deck": initial}))

    def test_generated_rare_epic_and_spells_are_excluded(self):
        rarity = {"kind": "deck_no_rarities", "rarities": ["RARE", "EPIC"]}
        spells = {"kind": "deck_no_spells"}
        deck = [card(1, rarity="COMMON"), card(2, True, "spell", "EPIC")]
        self.assertTrue(self.evaluate(rarity, {"remaining_deck": deck}))
        self.assertTrue(self.evaluate(spells, {"remaining_deck": deck}))
        deck[1]["generated"] = False
        self.assertFalse(self.evaluate(rarity, {"remaining_deck": deck}))
        self.assertFalse(self.evaluate(spells, {"remaining_deck": deck}))

    def test_empty_current_deck_satisfies_absence_not_missing_deck(self):
        for spec in ({"kind": "deck_no_duplicates"}, {"kind": "deck_no_spells"},
                     {"kind": "deck_no_rarities", "rarities": ["RARE", "EPIC"]}):
            self.assertTrue(self.evaluate(spec, {"remaining_deck": []}))
            self.assertIsNone(self.evaluate(spec, {"remaining_deck": None}))

    def test_missing_fields_never_prove_true_and_counterexamples_prove_false(self):
        spec = {"kind": "deck_no_spells"}
        deck = [card(1)]
        del deck[0]["generated"]
        self.assertIsNone(self.evaluate(spec, {"remaining_deck": deck}))
        deck.append(card(2, False, "spell"))
        self.assertFalse(self.evaluate(spec, {"remaining_deck": deck}))
        spec = {"kind": "deck_no_duplicates"}
        self.assertIsNone(self.evaluate(spec, {"remaining_deck": [{"generated": False}]}))
        self.assertTrue(self.evaluate(spec, {"remaining_deck": [{"generated": True}]}))

    def test_hand_threshold_at_declared_event_only(self):
        state = {"hand_size": 5, "hand_size_before_play": 6, "hand_size_after_play": 5}
        for op, limit, expected in [("<=", 5, True), (">=", 6, False), ("==", 5, True)]:
            self.assertEqual(self.evaluate({"kind": "hand_size_threshold", "operator": op, "threshold": limit}, state), expected)
        self.assertIsNone(self.evaluate({"kind": "hand_size_threshold", "operator": "<=", "threshold": 5},
                                        {"hand_size_before_play": 6}))

    def test_actor_and_selected_target_survival_never_substitute(self):
        state = {"actor": {"health": 0}, "selected_target": {"health": 1}}
        self.assertFalse(self.evaluate({"kind": "actor_alive"}, state))
        self.assertTrue(self.evaluate({"kind": "selected_target_alive"}, state))
        state = {"actor": {"health": 5}, "selected_target": None}
        self.assertTrue(self.evaluate({"kind": "actor_alive"}, state))
        self.assertFalse(self.evaluate({"kind": "selected_target_alive"}, state))
        self.assertIsNone(self.evaluate({"kind": "selected_target_alive"}, {"actor": {"health": 5}}))

    def test_exact_inventoried_need_parser_and_unknown_clauses(self):
        for clause, spec in f.NEED_CLAUSES.items():
            self.assertEqual(f.parse_need(clause + " Magic: Draw a card."), spec)
            self.assertEqual(f.parse_need("Starwalker. " + clause + " Magic: Draw a card."), spec)
        self.assertIsNone(f.parse_need("Magic: Draw a card."))
        self.assertEqual(f.parse_need("Need: You cast a spell last turn. Magic: Draw a card.")["kind"], "unknown")
        self.assertEqual(f.parse_need("Need:  Your deck has no non-Generated spells.")["kind"], "unknown")
        text = "Need: Your deck has no non-Generated spells. Need: Your deck has no non-Generated duplicates."
        self.assertEqual(f.parse_need(text)["kind"], "unknown")

    def test_invalid_numbers_and_specs_cannot_be_truthy_conditions(self):
        for value in (None, True, float("nan"), -1):
            self.assertIsNone(self.evaluate({"kind": "last_turn_spell_spend_positive"}, {"last_turn_gold_spent_on_spells": value}))
        for value in (None, True, 8):
            self.assertIsNone(self.evaluate({"kind": "hand_size_threshold", "operator": "<=", "threshold": 5}, {"hand_size": value}))
        with self.assertRaises(ValueError):
            self.evaluate({"kind": "hand_size_threshold", "operator": "eval", "threshold": 5}, {})
        with self.assertRaises(ValueError):
            self.evaluate({"kind": "deck_no_duplicates", "initial_deck": True}, {})
        result = f.evaluate_condition({"kind": "unknown", "reason": "Unsupported finite clause"}, {})
        self.assertIsNone(result["value"])

    def test_inputs_are_not_mutated_and_no_pricing_or_probability_output(self):
        spec = {"kind": "deck_no_duplicates"}
        state = {"remaining_deck": [card(1), card(2)]}
        original = copy.deepcopy((spec, state))
        result = f.evaluate_condition(spec, state)
        self.assertEqual((spec, state), original)
        self.assertNotIn("gold_value", result)
        self.assertNotIn("probability", result)


if __name__ == "__main__":
    unittest.main()
