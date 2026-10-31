from dataclasses import asdict, replace
from pathlib import Path
import json, unittest, tempfile, hashlib
import numpy as np
from card_eval.catalog import resolve, deck, Spec, Effect, InputError
from card_eval.game import NativeGame
from card_eval.network import Network, encode
from card_eval.policies import ReferencePolicy, LearnedPolicy
from card_eval.profiles import base_deck, opponents
from card_eval.api import evaluate, validate, default_request
from card_eval.legacy import features, rules, BUNDLED


class ProductChecks(unittest.TestCase):
    def game(self, **kwargs):
        return NativeGame((base_deck(), opponents()['pressure']), 950001,
                          (ReferencePolicy(), ReferencePolicy()), **kwargs)

    def test_actual_twenty_five_specs_retained_at_shuffled_entity_positions(self):
        g = self.game()
        for actor, p in enumerate(g.players):
            self.assertEqual(sorted(h.uid for h in p.deck + p.hand), list(range(25)))
            for h in p.deck + p.hand: self.assertEqual(g.spec(actor, h), g.native_decks[actor][h.uid])

    def test_hidden_enemy_identity_and_deck_order_do_not_enter_observation(self):
        g = self.game(); before = g.observation(0)
        g.players[1].deck.reverse(); g.players[0].deck.reverse()
        g.native_decks = (g.native_decks[0], tuple(resolve('Aaron') for _ in range(25)))
        self.assertEqual(before, g.observation(0))

    def test_mixed_souls_observed_and_executed_per_owner(self):
        g = self.game(souls=('INTEGRITY', 'KINDNESS'))
        self.assertEqual((g.observation(0)['enemy_soul'], g.observation(1)['config']['soul']), ('KINDNESS', 'KINDNESS'))
        g.players[1].hp = 20; g.players[1].turn = 2
        g.act_turn(1)
        self.assertGreaterEqual(g.players[1].healing, 1)
        self.assertEqual(g.cfg.soul, 'INTEGRITY')

    def test_real_copy_limits_and_unsupported_text_fail_preflight(self):
        with self.assertRaises(InputError): deck(['Aaron'] * 25)
        with self.assertRaises(InputError) as caught: deck(['Glyde'] + ['Rock Pet'] * 24)
        self.assertEqual(caught.exception.issues[0]['code'], 'unsupported_or_invalid_card')

    def test_model_sees_card_semantics_not_names_or_ids(self):
        g = self.game(); g.players[0].cash = 20
        obs = g.observation(0); actions = g.legal_actions(0)
        state, af = encode(obs, actions)
        for h in obs['hand']: h.update(name='unseen name', card_id=999)
        s2, a2 = encode(obs, actions)
        np.testing.assert_array_equal(state, s2); np.testing.assert_array_equal(af, a2)

    def test_complete_native_match_uses_conserved_cards_and_money(self):
        g = self.game(); r = g.run(); self.assertFalse(r['unfinished'])
        for p in g.players:
            self.assertEqual(len(p.deck) + len(p.hand) + p.played + p.burned, 25)
            self.assertEqual(p.cash, 1 + p.income + p.bonus_gold - p.total_spent)

    def test_native_policy_model_chooses_legal_action(self):
        g = self.game(); obs = g.observation(0); actions = g.legal_actions(0)
        self.assertIn(LearnedPolicy(Network(4)).choose(obs, actions)['action'], actions)

    def test_default_benchmarks_respect_copy_limits_for_each_copy_option(self):
        for copies in (1, 2, 3):
            plan = validate(default_request(['Bench', 'Fishing Rod'], copies=copies, samples=2))
            self.assertEqual(len(plan['own']), 25); self.assertFalse(plan['blocked'])

    def test_unknown_candidate_has_no_numeric_score_and_needs_no_model(self):
        req = default_request(['Glyde'], samples=2)
        r = evaluate(req)
        self.assertEqual(r['status'], 'unsupported_input'); self.assertIsNone(r['scores'])
        self.assertIsNone(r['unsupported'][0]['score'])

    def test_complete_denom_and_identical_semantic_negative_control(self):
        request = dict(deck=list(base_deck()), slots=[0], soul='INTEGRITY',
            opponents=[dict(name='pressure', deck=list(opponents()['pressure']))], samples=2,
            policies=['race'], candidates=[dict(name='same semantics', cost=2, attack=3, health=3)])
        r = evaluate(request)
        row = r['comparisons'][0]; cell = row['conditions'][0]
        self.assertEqual(r['games'], 8); self.assertEqual(cell['difference']['mean'], 0)
        self.assertEqual(row['recommendation'], 'equivalent_in_supported_rules')
        self.assertEqual(sum(cell['opportunities'].get(k, 0) for k in ('not_received', 'received_unplayed', 'played', 'unknown')), 4)

    def test_bundled_verified_sources_are_byte_identical(self):
        manifest = json.loads((BUNDLED / 'manifest.json').read_text())
        for name, info in manifest['files'].items():
            self.assertEqual(hashlib.sha256((BUNDLED / name).read_bytes()).hexdigest(), info['sha256'])

    def test_action_type_channels_and_new_gradient_are_consistent(self):
        g = self.game(); g.players[0].cash = 20
        obs = g.observation(0); actions = g.legal_actions(0); s, af = encode(obs, actions)
        for action, row in zip(actions, af):
            block = row[features.ACTION_DIM:features.ACTION_DIM + features.CARD_DIM]
            if action[0] != 'play': self.assertFalse(block.any())
        net = Network(9, hidden=4); p, _, _ = net.forward(s, af)
        sample = dict(features=(s, af), chosen=1, old_value=0., behavior_probability=float(p[1]), **{'return': 1.})
        _, grad = net.loss_grad([sample], imitation=True)
        index = (4 + features.ACTION_DIM, 1); original = net.p['Wa'][index]; eps = 1e-5
        net.p['Wa'][index] = original + eps; plus = net.loss_grad([sample], imitation=True)[0]['loss']
        net.p['Wa'][index] = original - eps; minus = net.loss_grad([sample], imitation=True)[0]['loss']
        net.p['Wa'][index] = original
        self.assertAlmostEqual(grad['Wa'][index], (plus - minus) / (2 * eps), places=7)

    def test_healing_stall_finishes_by_fatigue_without_a_guessed_deadline_winner(self):
        class Staller:
            name = 'only_play_start_healers'
            def choose(self, obs, actions):
                healers = {h['uid'] for h in obs['hand'] if any(e['trigger'] == 'start' and e['op'] == 'heal' for e in h['effects'])}
                action = next((a for a in actions if a[0] == 'play' and a[1] in healers), actions[0])
                return dict(action=action, action_index=actions.index(action), behavior_probability=1., value=0.,
                            policy=self.name, search_override=False, seconds=0.)
        cards = opponents()['defense']
        game = NativeGame((cards, cards), 950050, (Staller(), Staller()), souls=('KINDNESS', 'KINDNESS'))
        # A declared legal opening with all3 healers in hand isolates the long
        # stall. A random full hand can otherwise burn late-drawn healers.
        for actor, player in enumerate(game.players):
            all_cards = player.hand + player.deck
            player.hand = [h for h in all_cards if any(e.trigger == 'start' and e.op == 'heal' for e in game.spec(actor, h).effects)]
            held = {h.uid for h in player.hand}
            player.deck = [h for h in all_cards if h.uid not in held]
        game.candidate_drawn = 0
        result = game.run()
        self.assertFalse(result['unfinished']); self.assertGreater(result['round'], 40); self.assertLessEqual(result['round'], 60)


if __name__ == '__main__': unittest.main()
