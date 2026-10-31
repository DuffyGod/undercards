"""Small shared semantic ranker with an independently fitted MC critic.

Inference needs NumPy only. SciPy is an optional training dependency. The
critic is conditional on the frozen deterministic actor AND opponent mixture.
It is not a card score or an action-value estimate.
"""
from pathlib import Path
import hashlib, json
import numpy as np
from .relations import encode, VERSION


class RelationalNetwork:
    feature_version = VERSION

    def __init__(self, actor=None, critic=None):
        self.actor = np.asarray(actor if actor is not None else np.zeros(81), dtype=float)
        self.critic = np.asarray(critic if critic is not None else np.zeros(74), dtype=float)

    def encode(self, obs, actions): return encode(obs, actions)

    @property
    def actor_fingerprint(self):
        return hashlib.sha256(VERSION.encode() + self.actor.tobytes()).hexdigest()

    @property
    def fingerprint(self):
        return hashlib.sha256(self.actor_fingerprint.encode() + self.critic.tobytes()).hexdigest()

    def forward(self, state, actions):
        z = actions @ self.actor; p = np.exp(z - z.max()); p /= p.sum()
        value = self.predict_value(state)
        return p, value, None

    def predict_value(self, state):
        return float(2 / (1 + np.exp(-np.clip(state @ self.critic, -40, 40))) - 1)

    def fit_actor(self, features, labels, l2=1e-5, iterations=180):
        from scipy.optimize import minimize
        sizes = np.asarray([len(a) for a in features]); starts = np.r_[0, sizes.cumsum()[:-1]]
        matrix = np.concatenate(features); chosen = starts + np.asarray(labels); n = len(sizes)
        def objective(w):
            z = matrix @ w; maximum = np.maximum.reduceat(z, starts)
            ex = np.exp(z - np.repeat(maximum, sizes)); sums = np.add.reduceat(ex, starts)
            p = ex / np.repeat(sums, sizes); residual = p.copy(); residual[chosen] -= 1
            loss = np.mean(maximum + np.log(sums) - z[chosen]) + l2 * np.dot(w, w) / 2
            return float(loss), matrix.T @ residual / n + l2 * w
        fit = minimize(objective, np.zeros(matrix.shape[1]), jac=True, method='L-BFGS-B',
                       options=dict(maxiter=iterations, ftol=1e-10, gtol=1e-6))
        self.actor = fit.x
        return dict(loss=float(fit.fun), iterations=int(fit.nit), converged=bool(fit.success), message=str(fit.message))

    def fit_value(self, states, outcomes, weights, l2=.01, iterations=160):
        from scipy.optimize import minimize
        x = np.asarray(states, dtype=float); y = np.asarray(outcomes, dtype=float); weights = np.asarray(weights, dtype=float)
        if not len(y) or x.ndim != 2 or len(x) != len(y) or weights.shape != y.shape:
            raise ValueError('Aligned nonempty policy-specific value targets required')
        if not np.isfinite(x).all() or not np.isfinite(weights).all() or not np.isin(y, (0, 1)).all() or np.any(weights <= 0):
            raise ValueError('Only finite states, positive episode weights and terminal binary outcomes are value targets')
        weights = weights / weights.sum()
        actor_before = self.actor_fingerprint
        def objective(w):
            z = x @ w; p = 1 / (1 + np.exp(-np.clip(z, -40, 40)))
            loss = weights @ (np.logaddexp(0, z) - y * z) + l2 * np.dot(w[1:], w[1:]) / 2
            grad = x.T @ (weights * (p - y)); grad[1:] += l2 * w[1:]
            return float(loss), grad
        fit = minimize(objective, np.zeros(x.shape[1]), jac=True, method='L-BFGS-B',
                       options=dict(maxiter=iterations, ftol=1e-10))
        self.critic = fit.x
        if self.actor_fingerprint != actor_before: raise ValueError('Critic fitting changed actor')
        return dict(loss=float(fit.fun), iterations=int(fit.nit), converged=bool(fit.success),
                    message=str(fit.message), actor_fingerprint=actor_before, episode_weighted=True)

    def save(self, path, metadata):
        path = Path(path)
        if path.exists() or path.suffix != '.npz': raise ValueError('Use a new .npz checkpoint')
        np.savez_compressed(path, actor=self.actor, critic=self.critic,
            metadata=json.dumps(dict(metadata, model_kind='relational_linear', feature_version=VERSION,
                                     fingerprint=self.fingerprint, actor_fingerprint=self.actor_fingerprint)))

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as data:
            meta = json.loads(str(data['metadata']))
            if meta['feature_version'] != VERSION: raise ValueError('Feature version mismatch')
            net = cls(data['actor'].copy(), data['critic'].copy())
        if net.fingerprint != meta['fingerprint']: raise ValueError('Checkpoint checksum mismatch')
        if net.actor.shape != (81,) or net.critic.shape != (74,): raise ValueError('Checkpoint shape mismatch')
        return net, meta
