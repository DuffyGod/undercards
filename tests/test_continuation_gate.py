from copy import deepcopy
from pathlib import Path
import io
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from card_eval.action_value import INPUT
from card_eval.continuation_gate import ContinuationGate
from card_eval.continuation_research import gains, stopping_roots, OnlineRecorder
from card_eval.game import NativeGame
from card_eval.network import Network
from card_eval.policies import ReferencePolicy
from card_eval.profiles import base_deck
from card_eval.regret_model import RegretNetwork


class ContinuationChecks(unittest.TestCase):
    def test_two_head_gradient_and_antisymmetry(self):
        rng = np.random.default_rng(92); pairs = rng.normal(0, .2, (5, 2, INPUT))
        net = ContinuationGate(hidden=3); targets = rng.integers(-1, 2, (5, 2)); weights = np.arange(1., 6.)
        _, grad = net.loss_grad(pairs, targets, weights)
        for name, p in net.p.items():
            for index in rng.choice(p.size, min(p.size, 7), replace=False):
                old = p.flat[index]; eps = 1e-5
                p.flat[index] = old + eps; plus = net.loss_grad(pairs, targets, weights)[0]
                p.flat[index] = old - eps; minus = net.loss_grad(pairs, targets, weights)[0]; p.flat[index] = old
                self.assertAlmostEqual(float(grad[name].flat[index]), (plus - minus) / (2 * eps), places=7)
        np.testing.assert_allclose(net.contrasts(pairs), -net.contrasts(pairs[:, ::-1]), atol=1e-14)
        same = pairs.copy(); same[:, 1] = same[:, 0]
        np.testing.assert_array_equal(net.contrasts(same), np.zeros((5, 2)))
        targets = targets.astype(float); targets[0, 0] = np.nan
        with self.assertRaisesRegex(ValueError, 'Known'):
            net.loss_grad(pairs, targets, weights)

    def test_counterfactual_unknown_is_a_completion_interval(self):
        cells = [dict(action=a, continuation=c, result=dict(unfinished=False, won=(a == c)))
                 for a in (0, 1) for c in (0, 1)]
        lo, hi = gains(dict(cells=cells)); np.testing.assert_array_equal(lo, [-1, 1]); np.testing.assert_array_equal(lo, hi)
        cells[3]['result'] = dict(unfinished=True, won=None)
        lo, hi = gains(dict(cells=cells)); np.testing.assert_array_equal(lo, [-1, 0]); np.testing.assert_array_equal(hi, [-1, 1])

    def test_stopping_roots_prefix_invariance_and_missing(self):
        fake = [dict(observation=dict(player=0, turn=t), legal_actions=[('end', -1, -1, -1), ('play', 1, -1, -1)],
                     selection=dict(action_index=1), baseline=dict(action_index=0)) for t in (2, 4, 6, 9)]
        with patch('card_eval.continuation_research.encode', return_value=(None, (np.array([[0], [1]]), None))):
            roots = stopping_roots(fake)
            self.assertEqual(roots, [('first', 0, 0, 1), ('late', 2, 0, 1)])
            self.assertEqual(stopping_roots(fake[:3]), roots)
            late = deepcopy(fake[:1]); late[0]['observation']['turn'] = 8
            self.assertEqual(stopping_roots(late), [('first', 0, 0, 1)])
            self.assertEqual(stopping_roots([]), [])
            baseline = unittest.mock.Mock(); baseline.choose.return_value = dict(action_index=0)
            rec = OnlineRecorder(io.StringIO(), baseline)
            for r in fake:
                rec.record(r['observation'], r['legal_actions'], r['selection'])
            self.assertEqual(rec.roots, dict(first=(0, 0, 1), late=(2, 0, 1)))

    def test_self_contained_model_roundtrip_and_value_separation(self):
        base = Network.load('card_eval/models/paired-v5.npz')[0]; net = ContinuationGate(RegretNetwork(base))
        g = NativeGame((base_deck(), base_deck()), 3609901, (ReferencePolicy(), ReferencePolicy()))
        obs = g.observation(0); actions = g.legal_actions(0); state, af = net.encode(obs, actions)
        before = net.actor_fingerprint; prob = net.forward(state, af)[0]
        net.fit_value([state, state], [0, 1], [1, 1], iterations=8)
        self.assertEqual(before, net.actor_fingerprint); np.testing.assert_array_equal(prob, net.forward(state, af)[0])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'router.npz'; net.save(path, dict(value_unfitted=True, validation=dict(qualified=False)))
            loaded, meta = Network.load(path)
            self.assertTrue(meta['value_unfitted']); self.assertEqual(net.fingerprint, loaded.fingerprint)
            np.testing.assert_array_equal(prob, loaded.forward(*loaded.encode(obs, actions))[0])


if __name__ == '__main__':
    unittest.main()
