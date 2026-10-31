"""Discriminative rule, information, optimizer and experiment-contract checks."""
from dataclasses import asdict, replace
from pathlib import Path
import copy, gzip, json, tempfile, unittest
import numpy as np
from mechanisms import Spec, Effect, compile_text, silence, UnsupportedRule
from environment import LearningGame, Unit, Config, bridge
from agents import LearnedAgent, FixedAgent, public_attack, lethal_plan, value_guided_attacks
from features import encode, STATE_DIM, ACTION_DIM
from learner import Network
from records import Recorder, load_episodes
from study import catalog, training_specs, interval, bounded_interval, guarded_game

WORK = Path(__file__).resolve().parents[3] / 'work' / 'ml-route'
WORK.mkdir(parents=True, exist_ok=True)


def unit(uid, a, h, ready=True, **kw):
    keywords = tuple((k, int(v)) for k, v in kw.items() if k in ('taunt', 'armor', 'dodge', 'haste', 'charge') and v)
    spec = Spec('fixture', 2, a, h, keywords)
    return Unit(uid, 'small', a, h, h, ready, spec, **kw)


class LearningChecks(unittest.TestCase):
    def game(self, spec=None, **kw):
        return LearningGame('wide', 930001, Config(), spec or Spec('blank', 2, 2, 2),
                            (FixedAgent(bridge.ROWS[0]), FixedAgent(bridge.COLS[0])), **kw)

    def test_retained_no_ability_rules_match_full_new_seed_results(self):
        for seat, soul, kind in ((0, 'INTEGRITY', 'sweep'), (1, 'INTEGRITY', 'focus'), (0, 'KINDNESS', 'sweep')):
            cfg = Config(rounds=40, seat=seat, soul=soul, response_kind=kind)
            for seed in (930010, 930011):
                old = bridge.BridgeGame('wide', seed, cfg, (bridge.ROWS[0], bridge.COLS[0]), bridge.bodies()['role_2_2']).run()
                new = LearningGame('wide', seed, cfg, Spec('blank', 2, 2, 2),
                    (FixedAgent(bridge.ROWS[0]), FixedAgent(bridge.COLS[0]))).run()
                for key in ('won', 'lost', 'unfinished', 'round', 'a_hp', 'b_hp', 'a_cash', 'b_cash', 'a_played',
                            'a_burned', 'a_income', 'a_total_spent', 'candidate_drawn', 'candidate_played', 'first_punished'):
                    self.assertEqual(old[key], new[key], (seat, soul, kind, seed, key))

    def test_haste_can_attack_monster_but_not_face(self):
        g = self.game(Spec('synthetic', 2, 3, 3, (('haste', 1),)))
        a, b = g.players; a.hand = [bridge.Card(0, 'candidate')]; a.cash = 2
        b.units = [unit(9, 1, 2)]
        g.apply(0, ('play', 0, -1, -1))
        self.assertIn(('attack', 0, 1, 9), g.legal_actions(0))
        self.assertNotIn(('attack', 0, 1, -1), g.legal_actions(0))

    def test_taunt_and_charge_legality_is_shared(self):
        g = self.game(); a, b = g.players
        a.units = [unit(1, 4, 5, charge=True, fresh=True)]
        b.units = [unit(2, 1, 2, taunt=True), unit(3, 3, 3)]
        self.assertEqual([x for x in g.legal_actions(0) if x[0] == 'attack'], [('attack', 1, 1, 2)])
        g.apply(0, ('attack', 1, 1, 2))
        self.assertFalse(a.units[0].charge)

    def test_draw_and_haste_compose_on_one_body(self):
        spec = Spec('combo fixture', 2, 3, 3, (('haste', 1),), (Effect('play', 'draw', 'owner', 2),))
        g = self.game(spec); a = g.players[0]
        a.hand = [bridge.Card(0, 'candidate')]; a.cash = 2; before = len(a.deck)
        g.apply(0, ('play', 0, -1, -1))
        self.assertEqual((a.cash, len(a.hand), len(a.deck), a.units[0].ready), (0, 2, before - 2, True))

    def test_draw_burn_and_fatigue_not_ignored(self):
        g = self.game(); a = g.players[0]
        a.hand = [bridge.Card(i + 30, 'small') for i in range(7)]; a.deck = [bridge.Card(99, 'small')]
        g.draw(0); self.assertEqual((a.burned, len(a.hand)), (1, 7))
        g.draw(0); g.draw(0); self.assertEqual((a.fatigue, a.hp), (2, 27))

    def test_growth_callback_and_silence_assumptions_are_explicit(self):
        spec = Spec('grow', 2, 2, 4, effects=(Effect('end', 'buff', 'self', 1, 1),))
        g = self.game(spec); a = g.players[0]; a.hand = [bridge.Card(0, 'candidate')]; a.cash = 2
        g.apply(0, ('play', 0, -1, -1)); g._effects(0, 0, spec, 'end')
        grown = replace(a.units[0], h=3)
        self.assertEqual((grown.a, grown.max_h), (3, 5))
        with self.assertRaises(UnsupportedRule): silence(grown, 'reject_modified')
        retained = silence(grown, 'retain'); reset = silence(grown, 'reset')
        self.assertEqual((retained.a, retained.h, retained.max_h), (3, 3, 5))
        self.assertEqual((reset.a, reset.h, reset.max_h), (2, 2, 4))
        a.units = [retained]; g._effects(0, 0, spec, 'end')
        self.assertEqual(a.units, [retained])

    def test_magic_cannot_choose_its_new_caster(self):
        spec = Spec('silencer', 2, 3, 3, effects=(Effect('play', 'silence', 'monster'),))
        g = self.game(spec); a, b = g.players; a.hand = [bridge.Card(0, 'candidate')]; a.cash = 2
        a.units = [unit(5, 2, 2)]; b.units = [unit(6, 3, 4)]
        choices = [x for x in g.legal_actions(0) if x[0] == 'play']
        self.assertEqual(set(choices), {('play', 0, 0, 5), ('play', 0, 1, 6)})

    def test_armor_dodge_independent_numeric_witness(self):
        g = self.game(); a, b = g.players
        a.units = [unit(1, 3, 5, dodge=1)]; b.units = [unit(2, 4, 6, armor=True)]
        g.apply(0, ('attack', 1, 1, 2))
        self.assertEqual((a.units[0].h, a.units[0].dodge, b.units[0].h), (5, 0, 4))

    def test_coordinated_lethal_replays_in_physical_engine(self):
        g = self.game(); a, b = g.players
        a.units = [unit(1, 2, 5), unit(2, 4, 5)]; b.units = [unit(9, 1, 2, taunt=True)]; b.hp = 4
        obs = g.observation(0); plan, nodes = lethal_plan(obs, 64)
        self.assertTrue(plan); self.assertLessEqual(nodes, 64)
        expected = obs
        for action in plan:
            expected = public_attack(expected, action); g.apply(0, action)
        self.assertEqual(b.hp, expected['enemy_hp']); self.assertLessEqual(b.hp, 0)

    def test_hidden_hands_decks_and_seed_cannot_change_features_or_choice(self):
        g = self.game(); before = g.observation(0); actions = g.legal_actions(0)
        agent = LearnedAgent(Network(3), search_nodes=0); chosen = agent.choose(before, actions)['action']
        g.players[0].deck.reverse(); g.players[1].deck.reverse(); g.seed = 999
        g.players[1].hand = [bridge.Card(88 + i, 'response') for i in range(len(g.players[1].hand))]
        after = g.observation(0)
        self.assertEqual(before, after)
        for x, y in zip(encode(before, actions), encode(after, actions)): np.testing.assert_array_equal(x, y)
        self.assertEqual(chosen, agent.choose(after, actions)['action'])

    def test_card_names_and_ids_are_not_neural_features(self):
        g = self.game(); obs = g.observation(0); actions = g.legal_actions(0); changed = copy.deepcopy(obs)
        for h in changed['hand']: h.update(name='arbitrary unseen name', card_id=999999)
        for x, y in zip(encode(obs, actions), encode(changed, actions)): np.testing.assert_array_equal(x, y)

    def test_action_permutation_equivariance(self):
        g = self.game(); g.players[0].cash = 20
        obs = g.observation(0); actions = g.legal_actions(0); net = Network(4)
        p, v, _ = net.forward(*encode(obs, actions)); q, w, _ = net.forward(*encode(obs, actions[::-1]))
        np.testing.assert_allclose(p, q[::-1]); self.assertEqual(v, w)

    def test_optimizer_gradients_against_finite_difference(self):
        rng = np.random.default_rng(3); net = Network(4, hidden=4)
        s = rng.normal(0, .1, STATE_DIM); a = rng.normal(0, .1, (3, ACTION_DIM))
        p, _, _ = net.forward(s, a)
        sample = dict(features=(s, a), chosen=1, old_value=.2, behavior_probability=float(p[1]), **{'return': 1.})
        for imitation in (True, False):
            report, grad = net.loss_grad([sample], imitation=imitation)
            for name, index in [('Ws', (10, 1)), ('bs', (2,)), ('Wa', (4, 2)), ('wp', (1,)), ('wv', (2,)), ('bv', (0,))]:
                original = net.p[name][index]; eps = 1e-5
                net.p[name][index] = original + eps; plus = net.loss_grad([sample], imitation=imitation)[0]['loss']
                net.p[name][index] = original - eps; minus = net.loss_grad([sample], imitation=imitation)[0]['loss']
                net.p[name][index] = original
                self.assertAlmostEqual(grad[name][index], (plus - minus) / (2 * eps), places=7, msg=(imitation, name))

    def test_ppo_clips_a_large_positive_importance_ratio(self):
        net = Network(2, hidden=4); features = (np.zeros(STATE_DIM), np.zeros((2, ACTION_DIM)))
        sample = dict(features=features, chosen=0, old_value=0., behavior_probability=.1, **{'return': 1.})
        _, grad = net.loss_grad([sample], entropy=0., value_weight=0.)
        self.assertTrue(all(np.all(g == 0) for g in grad.values()))

    def test_checkpoint_roundtrip_is_exact_and_no_overwrite(self):
        net = Network(4)
        with tempfile.TemporaryDirectory(dir=WORK) as folder:
            path = Path(folder) / 'model.npz'; net.save(path, dict(purpose='test'))
            new, metadata = Network.load(path)
            self.assertEqual(net.fingerprint, new.fingerprint)
            with self.assertRaises(ValueError): net.save(path, {})

    def test_recorded_observation_is_before_action_and_truncation_has_no_label(self):
        g = self.game(); g.players[0].cash = 20
        obs = g.observation(0); actions = g.legal_actions(0); selection = FixedAgent(bridge.ROWS[0]).choose(obs, actions)
        rec = Recorder('fixture'); rec.record(obs, actions, selection)
        g.apply(0, selection['action'])
        self.assertEqual(rec.rows[0]['observation'], obs)
        rec.finish(dict(unfinished=True, won=False, lost=False))
        self.assertIsNone(rec.result['returns']); self.assertEqual(rec.samples(), [])

    def test_old_summary_is_not_training_data(self):
        with tempfile.TemporaryDirectory(dir=WORK) as folder:
            path = Path(folder) / 'old.jsonl'; path.write_text('{"won":true,"seed":1}\n')
            with self.assertRaises(ValueError): list(load_episodes(path))

    def test_parser_consumes_whole_text_and_uses_semantic_templates(self):
        mapped, rejected = catalog()
        self.assertTrue(mapped['Spider'].keyword('haste'))
        self.assertEqual(mapped['Bench'].effects, (Effect('play', 'draw', 'owner', 1),))
        self.assertEqual(mapped['Bloody Tree'].effects, (Effect('start', 'buff', 'self', 1),))
        self.assertTrue(any(r['name'] == 'Glyde' for r in rejected))
        with self.assertRaises(UnsupportedRule): Effect('death', 'draw', 'owner', 1)

    def test_common_compute_cap_rejects_over_budget_decisions(self):
        g = self.game(decision_seconds=0.)
        with self.assertRaisesRegex(RuntimeError, 'wall-time budget'): g.act_turn(0)

    def test_pairing_preserves_no_draw_outcomes_in_denominator(self):
        result = interval([0., 0., 1., 0.])
        self.assertEqual((result['n'], result['mean']), (4, .25))

    def test_unresolved_game_has_completion_bounds_not_a_draw(self):
        result = bounded_interval([0., .5, 1.], [0., 1., 1.])
        self.assertIsNone(result['mean']); self.assertEqual(result['n'], 3)
        self.assertEqual(result['completion_mean_range'], [.5, 2 / 3])

    def test_guarded_budget_failure_is_unlabelled(self):
        r = guarded_game(Spec('fixture', 2, 2, 2), 930050, Config(), 'wide',
                         (FixedAgent(bridge.ROWS[0]), FixedAgent(bridge.COLS[0])), decision_seconds=0.)
        self.assertTrue(r['unfinished']); self.assertIsNone(r['won']); self.assertIsNone(r['lost'])
        self.assertGreater(r['failure_seconds'], 0)

    def test_value_guided_search_uses_neural_prior_and_respects_bound(self):
        g = self.game(); a, b = g.players
        a.units = [unit(1, 2, 5), unit(2, 4, 5)]; b.units = [unit(9, 1, 2, taunt=True)]; b.hp = 4
        class FakeNetwork:
            calls = 0
            def forward(self, state, actions):
                self.calls += 1
                p = np.arange(1, len(actions) + 1, dtype=float); p /= p.sum()
                return p, float(1 - state[1]), None
        model = FakeNetwork(); obs = g.observation(0)
        plan, nodes = value_guided_attacks(obs, model, 8)
        self.assertTrue(plan); self.assertLessEqual(nodes, 8); self.assertEqual(nodes, model.calls)
        for action in plan: g.apply(0, action)
        self.assertLessEqual(b.hp, 0)

    def test_public_search_observation_equals_physical_next_observation(self):
        g = self.game(); a, b = g.players
        a.units = [unit(1, 3, 5, dodge=1), unit(2, 2, 4)]; b.units = [unit(9, 2, 4, armor=True)]
        for action in (('attack', 1, 1, 9), ('attack', 2, 1, -1)):
            predicted = public_attack(g.observation(0), action)
            g.apply(0, action)
            self.assertEqual(predicted, g.observation(0))


if __name__ == '__main__': unittest.main(verbosity=2)
