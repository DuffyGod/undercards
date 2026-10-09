import copy
import unittest

import coupled_magic as magic
import score_cards as prices


class CoupledDamageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference, _ = prices.make_reference(prices.load_cards())

    def evaluate(self, attack=4, health=5, enemies=None, allies=None, specs=None, statuses=None, **kwargs):
        ctx = {"role": "aggro", "enemy_bodies": enemies or [], "ally_bodies_before_play": allies or [],
               "opponent_gold_before_response": kwargs.pop("gold", 0)}
        ctx.update(kwargs.pop("ctx_changes", {}))
        return magic.evaluate({"attack": attack, "health": health}, ctx, specs or [], statuses or {},
                              self.reference, weights=kwargs.pop("weights", {"none": 1}), **kwargs)

    def test_no_magic_or_keyword_preserves_phi_and_inputs(self):
        card = {"attack": 4, "health": 5}
        ctx = {"role": "aggro", "enemy_bodies": [{"attack": 3, "health": 3}],
               "ally_bodies_before_play": [{"attack": 2, "health": 2}], "opponent_gold_before_response": 3}
        original = copy.deepcopy(ctx)
        result = magic.evaluate(card, ctx, [], {}, self.reference, weights={"none": .5, "chip": .5})
        self.assertAlmostEqual(result["total_increment_model_gold"], 0)
        self.assertAlmostEqual(result["keyword_delta_model_gold"], 0)
        self.assertEqual(result["ordinary"]["expected"], result["special"]["expected"])
        self.assertEqual(ctx, original)

    def test_cache_matches_uncached_quote_and_cannot_be_poisoned(self):
        card={'attack':4,'health':5}
        ctx={'role':'aggro','enemy_bodies':[{'attack':4,'health':5},{'attack':1,'health':1}],
             'ally_bodies_before_play':[],'opponent_gold_before_response':3}
        specs=[{'amount':1,'target':'enemy_monster'}]
        status={'haste':True}
        raw=magic.evaluate(card,ctx,specs,status,self.reference)
        cached=magic.evaluate_cached(card,ctx,specs,status,self.reference)
        self.assertEqual(raw,cached)
        cached['magic_initial_state']['actor']['health']=-99
        cached['total_delta_model_gold']=-999
        again=magic.evaluate_cached(card,ctx,specs,status,self.reference)
        self.assertEqual(raw,again)
        changed=copy.deepcopy(ctx)
        changed['own_player_hp']=1
        self.assertEqual(magic.evaluate_cached(card,changed,specs,status,self.reference),
                         magic.evaluate(card,changed,specs,status,self.reference))

    def test_dead_magic_target_cannot_reply_and_no_keyword_is_pmid(self):
        result = self.evaluate(enemies=[{"attack": 5, "health": 1}],
                               specs=[{"amount": 1, "target": "enemy_monster"}], weights={"enemy_face": 1})
        self.assertEqual(result["magic_initial_state"]["enemies"][0]["health"], 0)
        self.assertFalse(any(row["event"] == "enemy_face" for row in result["special"]["outcomes"]["enemy_face"]["state"]["log"]))
        self.assertAlmostEqual(result["keyword_delta_model_gold"], 0)
        self.assertAlmostEqual(sum(result["component_deltas"].values()), result["total_increment_model_gold"])
        self.assertAlmostEqual(result["decomposition_residual"], 0)

    def test_target_permutation_and_single_target_do_not_become_aoe(self):
        enemies = [{"attack": 2, "health": 1}, {"attack": 5, "health": 1}]
        specs = [{"amount": 1, "target": "enemy_monster"}]
        a = self.evaluate(enemies=enemies, specs=specs)
        b = self.evaluate(enemies=list(reversed(enemies)), specs=specs)
        self.assertAlmostEqual(a["total_increment_model_gold"], b["total_increment_model_gold"])
        self.assertEqual(len(a["magic_selection"][0]["targets"]), 1)
        self.assertEqual(sum(unit["health"] <= 0 for unit in a["magic_initial_state"]["enemies"]), 1)
        empty = self.evaluate(specs=specs)
        self.assertTrue(empty["magic_selection"][0]["fizzle"])
        self.assertAlmostEqual(empty["total_increment_model_gold"], 0)

    def test_aoe_is_one_plan_and_immediate_damage_is_not_added_twice(self):
        enemies = [{"attack": 3, "health": 1}, {"attack": 3, "health": 3}]
        result = self.evaluate(enemies=enemies, specs=[{"amount": 1, "target": "all_enemy_monsters"}])
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual([unit["health"] for unit in result["magic_initial_state"]["enemies"]], [0, 2])
        body = lambda hp: prices.body_value(3, hp, self.reference, prices.role_parameters("aggro"))
        direct = body(1) + body(3) - body(2)
        self.assertAlmostEqual(result["immediate_damage_only_diagnostic"]["delta_phi"], direct)
        self.assertAlmostEqual(result["total_increment_model_gold"], result["magic_window_delta_model_gold"] + result["keyword_delta_model_gold"])
        self.assertAlmostEqual(result["magic_window_delta_model_gold"], direct + result["interaction_model_gold"])
        self.assertAlmostEqual(result["total_delta_model_gold"], result["direct_damage_model_gold"] + result["magic_interaction_model_gold"] + result["keyword_delta_model_gold"])
        self.assertEqual(result["post_magic_ordinary"], result["intermediate"])
        self.assertEqual(result["keyword_bundle"], result["special"])

    def test_magic_target_is_jointly_chosen_with_haste_not_greedy_direct(self):
        result = self.evaluate(enemies=[{"attack": 4, "health": 5}, {"attack": 1, "health": 1}],
                               specs=[{"amount": 1, "target": "enemy_monster"}], statuses={"haste": True})
        greedy = max(result["candidates"], key=lambda row: row["immediate_damage_only_diagnostic"]["delta_phi"])
        self.assertEqual(greedy["magic_selection"][0]["targets"][0]["index"], 1)
        self.assertEqual(result["magic_selection"][0]["targets"][0]["index"], 0)
        self.assertGreater(result["special"]["expected"], greedy["special"]["expected"])

    def test_friendly_damage_and_wide_entity_exclude_caster(self):
        result = self.evaluate(attack=0, allies=[{"attack": 5, "health": 1}],
                               specs=[{"amount": 1, "target": "monster"}])
        self.assertEqual(result["magic_selection"][0]["targets"][0]["side"], "ally")
        loss = prices.body_value(5, 1, self.reference, prices.role_parameters("aggro"))
        self.assertAlmostEqual(result["component_deltas"]["other_ally_bodies"], -loss)
        self.assertAlmostEqual(result["total_increment_model_gold"], -loss)
        wide = self.evaluate(attack=0, specs=[{"amount": 1, "target": "wide_entity"}])
        self.assertEqual({row["magic_selection"][0]["targets"][0]["side"] for row in wide["candidates"]}, {"owner", "opponent"})
        self.assertEqual(wide["magic_selection"][0]["targets"][0]["side"], "opponent")

    def test_conditional_haste_mitigation_and_invalid_inputs_fail_explicitly(self):
        plain = self.evaluate(enemies=[{"attack": 1, "health": 4}], specs=[{"amount": 3, "target": "monster"}], conditional_haste_limit=3)
        self.assertTrue(plain["effective_statuses"]["haste"])
        for shield in ({"armor": True}, {"dodge": 1}):
            with self.assertRaises(ValueError):
                self.evaluate(enemies=[{"attack": 1, "health": 4, **shield}],
                              specs=[{"amount": 3, "target": "monster"}], conditional_haste_limit=3)
        for kwargs in ({"statuses": {"charge": True}}, {"statuses": {"haste": "false"}},
                       {"specs": [{"amount": True, "target": "monster"}]},
                       {"specs": [{"amount": 1, "target": "growth"}]},
                       {"weights": {"none": float("nan")}}):
            with self.assertRaises(ValueError):
                self.evaluate(**kwargs)

    def test_enemy_entity_domain_contains_only_enemy_monsters_and_opponent(self):
        result = self.evaluate(attack=0, enemies=[{"attack": 2, "health": 2}, {"attack": 1, "health": 3}],
                               allies=[{"attack": 5, "health": 1}],
                               specs=[{"amount": 1, "target": "enemy_entity"}])
        targets = [row["magic_selection"][0]["targets"] for row in result["candidates"]]
        self.assertTrue(all(len(target) == 1 for target in targets))
        self.assertEqual({(target[0]["side"], target[0]["index"]) for target in targets},
                         {("enemy", 0), ("enemy", 1), ("opponent", None)})
        for row in result["candidates"]:
            self.assertEqual(row["magic_initial_state"]["external_allies"][0]["health"], 1)
            self.assertEqual(row["magic_initial_state"]["own_player_hp"], 30)
            self.assertEqual(row["magic_initial_state"]["actor"]["health"], 5)
        empty_board = self.evaluate(attack=0, specs=[{"amount": 1, "target": "enemy_entity"}])
        self.assertEqual(len(empty_board["candidates"]), 1)
        self.assertFalse(empty_board["magic_selection"][0]["fizzle"])
        self.assertEqual(empty_board["magic_selection"][0]["targets"][0]["side"], "opponent")
        self.assertEqual(empty_board["magic_initial_state"]["enemy_player_hp"], 29)

    def test_unaffordable_response_and_chosen_terminal_are_not_cash_profits(self):
        result = self.evaluate(gold=1, statuses={"dodge": 1}, weights={"chip": 1})
        for plan in (result["ordinary"], result["intermediate"], result["special"]):
            state = plan["outcomes"]["chip"]["state"]
            self.assertEqual(state["enemy_gold"], 1)
            self.assertFalse(any(row["event"] == "synthetic_paid_chip" for row in state["log"]))
        self.assertAlmostEqual(result["component_deltas"]["opponent_cash_utility"], 0)
        terminal = self.evaluate(attack=2, specs=[{"amount": 30, "target": "opponent"}])
        self.assertTrue(terminal["terminal_requires_separate_outcome_evaluation"])
        self.assertIsNone(terminal["total_increment_model_gold"])
        self.assertIsNone(terminal["component_deltas"])


if __name__ == "__main__":
    unittest.main()
