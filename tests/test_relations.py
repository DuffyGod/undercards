from copy import deepcopy
from pathlib import Path
import tempfile, unittest
import numpy as np
from card_eval.api import evaluate
from card_eval.game import NativeGame
from card_eval.network import Network
from card_eval.policies import ReferencePolicy, LearnedPolicy
from card_eval.profiles import base_deck, opponents
from card_eval.relations import encode
from card_eval.relational_model import RelationalNetwork
from card_eval.relational_research import value_metrics


class RelationalChecks(unittest.TestCase):
    def observation(self):
        game = NativeGame((base_deck(), opponents()['pressure']), 950101, (ReferencePolicy(), ReferencePolicy()))
        game.players[0].cash = 20
        return game.observation(0), game.legal_actions(0)

    def test_names_ids_and_consistently_renamed_uids_cannot_change_features(self):
        obs, actions = self.observation(); s, a = encode(obs, actions); other = deepcopy(obs)
        for zone in ('hand', 'own', 'enemy'):
            for u in other[zone]:
                u.update(uid=u['uid'] + 1000)
                spec = u.get('spec', u); spec.update(name='unseen', card_id=999999)
        renamed = [(kind, uid + 1000 if uid >= 0 else uid, side, target + 1000 if target >= 0 else target)
                   for kind, uid, side, target in actions]
        s2, a2 = encode(other, renamed)
        np.testing.assert_array_equal(s, s2); np.testing.assert_array_equal(a, a2)

    def test_action_permutation_only_permutes_probabilities(self):
        obs, actions = self.observation(); net = RelationalNetwork(np.arange(81) / 20)
        s, a = encode(obs, actions); sr, ar = encode(obs, actions[::-1])
        p, v, _ = net.forward(s, a); pr, vr, _ = net.forward(sr, ar)
        np.testing.assert_allclose(p, pr[::-1]); self.assertEqual(v, vr)

    def test_actor_training_learns_ranking_and_critic_cannot_change_actor(self):
        net = RelationalNetwork(); af = [np.array([[0., 1.], [1., 0.]]), np.array([[2., 0.], [0., 2.]])]
        net.fit_actor(af, [1, 0], iterations=50)
        self.assertEqual([int((a @ net.actor).argmax()) for a in af], [1, 0])
        before = net.actor.copy(); fp = net.actor_fingerprint
        states = np.array([[1., -1.], [1., 1.]]); net.fit_value(states, [0, 1], [1., 1.])
        np.testing.assert_array_equal(before, net.actor); self.assertEqual(fp, net.actor_fingerprint)

    def test_backend_roundtrip_and_product_gate(self):
        obs, actions = self.observation(); net = RelationalNetwork(np.arange(81) / 100)
        with tempfile.TemporaryDirectory(dir='work') as directory:
            path = Path(directory) / 'model.npz'; net.save(path, dict(validation=dict(qualified=False)))
            loaded, _ = Network.load(path); self.assertEqual(net.fingerprint, loaded.fingerprint)
            self.assertEqual(LearnedPolicy(net).choose(obs, actions)['action'], LearnedPolicy(loaded).choose(obs, actions)['action'])
            request = dict(deck=list(base_deck()), slots=[0], candidates=['Fishing Rod'], samples=2,
                policies=['learned'], opponents=[dict(name='pressure', deck=list(opponents()['pressure']))])
            result = evaluate(request, checkpoint=path)
            self.assertEqual(result['status'], 'unqualified_policy'); self.assertIsNone(result['scores'])

    def test_unfinished_value_episode_has_no_training_or_validation_label(self):
        net = RelationalNetwork(); episodes = [dict(terminal=True, won=True, states=[np.zeros(74)]),
                                             dict(terminal=False, won=None, states=[np.ones(74)])]
        metrics = value_metrics(net, episodes, .5)
        self.assertEqual(metrics['terminal_episodes'], 1); self.assertEqual(metrics['unresolved_episodes'], 1)
        self.assertEqual(metrics['brier']['mean'], .25)


if __name__ == '__main__': unittest.main()
