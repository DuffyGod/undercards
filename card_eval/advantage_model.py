"""Shared action differences from paired terminal continuations, public inputs.

The head predicts relative terminal win under a declared continuation mixture,
not optimal Q or a calibrated probability. A margin gates changes to the frozen
baseline. It is an empirical safeguard, not a safe-policy-improvement theorem.
"""
from pathlib import Path
import hashlib, json
import numpy as np
from .legacy import features
from .relations import encode as relations_encode
from .relational_model import RelationalNetwork

VERSION = 'paired-continuation-1'
CONTEXT = (1, 2, 3, 5, 8, 9, 17, 26, 34, 39, 47, 53)
ACTION_DIM = 81 + 2 * features.CARD_DIM
HEAD_DIM = ACTION_DIM * (1 + len(CONTEXT))


def encode(obs, actions):
    state, relations = relations_encode(obs, actions); rows = []
    for action in actions:
        kind, uid, _, _ = action
        zone = obs['hand'] if kind == 'play' else obs['own']
        source = next((u for u in zone if u['uid'] == uid), None) if kind != 'end' else None
        card = features.card_features(source, kind == 'attack') if source else np.zeros(features.CARD_DIM)
        rows.append(np.r_[card if kind == 'play' else np.zeros_like(card), card if kind == 'attack' else np.zeros_like(card)])
    return state, np.c_[relations, np.asarray(rows)]


def head_features(state, actions):
    context = np.r_[1., np.clip(state[list(CONTEXT)], -3, 3)]
    return (actions[:, :, None] * context[None, None, :]).reshape(len(actions), HEAD_DIM)


class AdvantageNetwork(RelationalNetwork):
    feature_version = VERSION

    def __init__(self, actor=None, critic=None, advantage=None, margin=.1):
        super().__init__(actor, critic)
        self.advantage = np.asarray(advantage if advantage is not None else np.zeros(HEAD_DIM), float)
        self.margin = float(margin)

    def encode(self, obs, actions): return encode(obs, actions)

    @property
    def actor_fingerprint(self):
        return hashlib.sha256(VERSION.encode() + self.actor.tobytes() + self.advantage.tobytes() + np.float64(self.margin).tobytes()).hexdigest()

    def action_scores(self, state, actions): return head_features(state, actions) @ self.advantage

    def forward(self, state, actions):
        scores = self.action_scores(state, actions); base = int((actions[:, :81] @ self.actor).argmax())
        best = int(scores.argmax()); chosen = best if scores[best] - scores[base] > self.margin else base
        # Deterministic action distribution; no PPO/importance-sampling claim.
        prob = np.zeros(len(actions)); prob[chosen] = 1.
        value = self.predict_value(state)
        return prob, value, dict(base=base, chosen=chosen, predicted_gain=float(scores[chosen] - scores[base]))

    def fit_advantage(self, groups, l2=.01, iterations=160):
        from scipy.optimize import minimize
        xs = []; ys = []; weights = []
        for matrix, outcomes in groups:
            matrix = np.asarray(matrix); outcomes = np.asarray(outcomes, float)
            if not len(outcomes) or len(matrix) != len(outcomes) or not np.isfinite(outcomes).all():
                raise ValueError('Only complete paired outcomes, never unresolved imputations')
            xs.extend(matrix - matrix.mean(axis=0)); ys.extend(outcomes - outcomes.mean())
            weights.extend([1 / len(outcomes)] * len(outcomes))
        x = np.asarray(xs); y = np.asarray(ys); w = np.asarray(weights); w /= w.sum()
        if x.shape[1:] != self.advantage.shape: raise ValueError('Action head feature mismatch')
        def objective(beta):
            residual = x @ beta - y
            return float(.5 * w @ (residual ** 2) + .5 * l2 * (beta @ beta)), x.T @ (w * residual) + l2 * beta
        result = minimize(objective, np.zeros_like(self.advantage), jac=True, method='L-BFGS-B',
                          options=dict(maxiter=iterations, ftol=1e-10, gtol=1e-7))
        self.advantage = result.x
        return dict(loss=float(result.fun), iterations=int(result.nit), converged=bool(result.success), message=str(result.message),
                    paired_groups=len(groups), action_labels=len(y), head_parameters=len(self.advantage))

    def save(self, path, metadata):
        path = Path(path)
        if path.exists() or path.suffix != '.npz': raise ValueError('Use a new .npz checkpoint')
        np.savez_compressed(path, actor=self.actor, critic=self.critic, advantage=self.advantage,
            metadata=json.dumps(dict(metadata, margin=self.margin, model_kind='paired_advantage', feature_version=VERSION,
                                     fingerprint=self.fingerprint, actor_fingerprint=self.actor_fingerprint)))

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as data:
            meta = json.loads(str(data['metadata']))
            if meta['feature_version'] != VERSION: raise ValueError('Feature version mismatch')
            net = cls(data['actor'].copy(), data['critic'].copy(), data['advantage'].copy(), meta['margin'])
        if net.actor.shape != (81,) or net.critic.shape != (74,) or net.advantage.shape != (HEAD_DIM,): raise ValueError('Checkpoint shape mismatch')
        if net.fingerprint != meta['fingerprint']: raise ValueError('Checkpoint checksum mismatch')
        return net, meta
