"""Shared paired utilities conditioned on two fixed continuation policies.

The two heads estimate terminal contrasts, not Q* or the value of the mixed
router. Deployment uses visible information only; hidden worlds are offline
counterfactual labels. A router is deliberately a restricted action policy.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
from .action_value import ActionValueNetwork, INPUT, encode
from .advantage_model import AdvantageNetwork
from .regret_model import RegretNetwork

VERSION = 'paired-continuation-router-1'
MODES = ('robust', 'base_target', 'own_target')


class ContinuationGate(ActionValueNetwork):
    feature_version = VERSION

    def __init__(self, proposer=None, mode='robust', seed=2026110212, hidden=8):
        if mode not in MODES:
            raise ValueError('Unknown continuation router')
        self.proposer = proposer if proposer is not None else RegretNetwork()
        self.base = self.proposer.base
        self.mode = mode
        self.hidden = hidden
        self.critic = self.base.critic.copy()
        rng = np.random.default_rng(seed)
        self.p = dict(W=rng.normal(0, 1 / np.sqrt(INPUT), (INPUT, hidden)),
                      b=np.zeros(hidden), w=rng.normal(0, 1 / np.sqrt(hidden), (hidden, 2)))

    @property
    def actor_fingerprint(self):
        return hashlib.sha256((VERSION + self.mode + self.proposer.actor_fingerprint).encode() +
                              b''.join(self.p[k].tobytes() for k in sorted(self.p))).hexdigest()

    def utilities(self, x):
        return np.tanh(np.asarray(x) @ self.p['W'] + self.p['b']) @ self.p['w']

    def contrasts(self, pairs):
        pairs = np.asarray(pairs, float)
        return self.utilities(pairs[:, 1]) - self.utilities(pairs[:, 0])

    def encode(self, obs, actions):
        state, (x, _) = encode(obs, actions)
        b = int(self.base.forward(*self.base.encode(obs, actions))[0].argmax())
        a = int(self.proposer.forward(state, (x, None))[0].argmax())
        return state, (x, b, a)

    def forward(self, state, actions):
        x, b, a = actions
        delta = self.utilities(x[[a]])[0] - self.utilities(x[[b]])[0]
        take = bool(np.min(delta) > 0) if self.mode == 'robust' else bool(delta[0 if self.mode == 'base_target' else 1] > 0)
        chosen = a if take else b
        prob = np.zeros(len(x)); prob[chosen] = 1.
        return prob, self.predict_value(state), dict(base=b, proposal=a, chosen=chosen,
            continuation_contrasts=delta.tolist(), scores_are_calibrated_q=False,
            target='fixed V5 / V11 continuations; deployment mixture differs')

    def action_scores(self, state, actions):
        # Ranking only, never presented as calibrated action values.
        return self.forward(state, actions)[0]

    def loss_grad(self, pairs, targets, weights, l2=.001):
        pairs = np.asarray(pairs, float); targets = np.asarray(targets, float)
        weights = np.asarray(weights, float)
        if (pairs.ndim != 3 or pairs.shape[1:] != (2, INPUT) or targets.shape != (len(pairs), 2)
                or weights.shape != (len(pairs),) or not np.isfinite(targets).all()
                or np.any(abs(targets) > 1) or not np.isfinite(weights).all()
                or np.any(weights <= 0)):
            raise ValueError('Known paired terminal contrasts and positive weights required')
        # Caller supplies opening-normalized weights. For minibatches it also
        # supplies the inverse sampling probability; do not renormalize here.
        h = np.tanh(pairs @ self.p['W'] + self.p['b'])
        difference = h[:, 1] - h[:, 0]
        residual = difference @ self.p['w'] - targets
        loss = np.sum(weights[:, None] * residual ** 2) / 2
        dz = weights[:, None] * residual
        dh = (dz @ self.p['w'].T)[:, None, :] * np.array([-1., 1.])[None, :, None] * (1 - h * h)
        grads = dict(W=pairs.reshape(-1, INPUT).T @ dh.reshape(-1, self.hidden),
                     b=dh.sum((0, 1)), w=difference.T @ dz)
        for name in ('W', 'w'):
            loss += l2 / 2 * np.sum(self.p[name] ** 2)
            grads[name] += l2 * self.p[name]
        return float(loss), grads

    def save(self, path, metadata):
        path = Path(path)
        if path.exists() or path.suffix != '.npz':
            raise ValueError('Preserve router checkpoint')
        prior = self.proposer
        np.savez_compressed(path, **self.p, **{'proposal_' + k: v for k, v in prior.p.items()},
            critic=self.critic, proposal_critic=prior.critic, base_actor=self.base.actor,
            base_critic=self.base.critic, base_advantage=self.base.advantage,
            metadata=json.dumps(dict(metadata, model_kind='continuation_gate', feature_version=VERSION,
                hidden=self.hidden, mode=self.mode, base_margin=self.base.margin,
                proposal_hidden=prior.hidden, proposal_objective=prior.objective,
                proposal_baseline_weight=prior.baseline_weight, proposal_actor=prior.actor_fingerprint,
                actor_fingerprint=self.actor_fingerprint, fingerprint=self.fingerprint, parameters=self.parameters)))

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as data:
            meta = json.loads(str(data['metadata']))
            if meta['feature_version'] != VERSION:
                raise ValueError('Incompatible router schema')
            base = AdvantageNetwork(data['base_actor'].copy(), data['base_critic'].copy(),
                                    data['base_advantage'].copy(), meta['base_margin'])
            prior = RegretNetwork(base, meta['proposal_objective'], hidden=meta['proposal_hidden'],
                                 baseline_weight=meta['proposal_baseline_weight'])
            for name in prior.p:
                if data['proposal_' + name].shape != prior.p[name].shape:
                    raise ValueError('Proposer parameter shape mismatch')
                prior.p[name] = data['proposal_' + name].copy()
            prior.critic = data['proposal_critic'].copy()
            if prior.actor_fingerprint != meta['proposal_actor']:
                raise ValueError('Proposer checksum mismatch')
            net = cls(prior, meta['mode'], hidden=meta['hidden'])
            for name in net.p:
                if data[name].shape != net.p[name].shape:
                    raise ValueError('Router parameter shape mismatch')
                net.p[name] = data[name].copy()
            net.critic = data['critic'].copy()
        if net.critic.shape != (74,) or net.fingerprint != meta['fingerprint']:
            raise ValueError('Router checksum mismatch')
        return net, meta
