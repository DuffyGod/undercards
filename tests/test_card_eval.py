from dataclasses import asdict, replace
from pathlib import Path
import json, unittest
import numpy as np
from card_eval.catalog import resolve, deck, Spec, Effect, InputError
from card_eval.game import NativeGame
from card_eval.network import Network, encode
from card_eval.policies import ReferencePolicy, LearnedPolicy
from card_eval.profiles import base_deck, opponents


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


if __name__ == '__main__': unittest.main()
