"""Small NumPy shared policy/value network; PPO and optional imitation warmup.

Monte Carlo targets are HP-terminal outcomes. There is no fixed Gold, HP or
card-quality target. Truncated games cannot become draws or training labels.
"""
from pathlib import Path
import hashlib, json
import numpy as np
from features import STATE_DIM, ACTION_DIM, VERSION as FEATURE_VERSION


class Network:
    def __init__(self, seed=0, hidden=32):
        rng = np.random.default_rng(seed)
        self.hidden = hidden; self.step = 0; self._fingerprint = None
        self.p = dict(Ws=rng.normal(0, 1 / np.sqrt(STATE_DIM), (STATE_DIM, hidden)),
            bs=np.zeros(hidden), Wa=rng.normal(0, 1 / np.sqrt(hidden + ACTION_DIM), (hidden + ACTION_DIM, hidden)),
            ba=np.zeros(hidden), wp=rng.normal(0, .01, hidden), bp=np.zeros(1),
            wv=rng.normal(0, .01, hidden), bv=np.zeros(1))
        self.m = {k: np.zeros_like(v) for k, v in self.p.items()}
        self.v = {k: np.zeros_like(v) for k, v in self.p.items()}

    @property
    def fingerprint(self):
        if self._fingerprint is None:
            self._fingerprint = hashlib.sha256(b''.join(self.p[k].tobytes() for k in sorted(self.p))).hexdigest()
        return self._fingerprint

    def forward(self, state, actions):
        p = self.p
        h = np.tanh(state @ p['Ws'] + p['bs'])
        x = np.concatenate((np.broadcast_to(h, (len(actions), self.hidden)), actions), axis=1)
        z = np.tanh(x @ p['Wa'] + p['ba'])
        logits = z @ p['wp'] + p['bp'][0]
        ex = np.exp(logits - logits.max()); prob = ex / ex.sum()
        value = float(np.tanh(h @ p['wv'] + p['bv'][0]))
        return prob, value, (h, x, z)

    def loss_grad(self, samples, imitation=False, entropy=.01, value_weight=.5, clip=.2):
        grads = {k: np.zeros_like(v) for k, v in self.p.items()}
        loss = 0.; policy_loss = 0.; value_loss = 0.
        for sample in samples:
            s, a = sample['features']; chosen = sample['chosen']
            target = sample['return']; advantage = target - sample.get('old_value', 0.)
            prob, value, (h, x, z) = self.forward(s, a)
            logs = np.log(np.maximum(prob, 1e-15)); H = -float(prob @ logs)
            if imitation:
                pl = -logs[chosen]; coefficient = -1.
            else:
                old = sample['behavior_probability']
                if not 0 < old <= 1: raise ValueError('Missing/invalid behavior probability')
                ratio = prob[chosen] / old
                pl = -min(ratio * advantage, np.clip(ratio, 1 - clip, 1 + clip) * advantage)
                clipped = (advantage >= 0 and ratio > 1 + clip) or (advantage < 0 and ratio < 1 - clip)
                coefficient = 0. if clipped else -advantage * ratio
            dl = -coefficient * prob
            dl[chosen] += coefficient
            dl += entropy * prob * (logs + H)
            dv = value_weight * (value - target) * (1 - value * value)
            vl = .5 * value_weight * (value - target) ** 2
            grads['wp'] += z.T @ dl; grads['bp'][0] += dl.sum()
            dz = np.outer(dl, self.p['wp']) * (1 - z * z)
            grads['Wa'] += x.T @ dz; grads['ba'] += dz.sum(axis=0)
            dh = (dz @ self.p['Wa'][:self.hidden].T).sum(axis=0) + dv * self.p['wv']
            dh *= 1 - h * h
            grads['Ws'] += np.outer(s, dh); grads['bs'] += dh
            grads['wv'] += dv * h; grads['bv'][0] += dv
            loss += pl + vl - entropy * H; policy_loss += pl; value_loss += vl
        n = max(1, len(samples))
        return dict(loss=float(loss / n), policy_loss=float(policy_loss / n), value_loss=float(value_loss / n)), {k: v / n for k, v in grads.items()}

    def update(self, samples, lr=3e-4, imitation=False, **kwargs):
        report, gradients = self.loss_grad(samples, imitation=imitation, **kwargs)
        norm = np.sqrt(sum(float((g * g).sum()) for g in gradients.values()))
        if not np.isfinite(norm): raise ValueError('Nonfinite gradient')
        self.step += 1; self._fingerprint = None
        for k, grad in gradients.items():
            grad *= min(1., 1. / max(norm, 1e-12))
            self.m[k] = .9 * self.m[k] + .1 * grad
            self.v[k] = .999 * self.v[k] + .001 * grad * grad
            m = self.m[k] / (1 - .9 ** self.step); v = self.v[k] / (1 - .999 ** self.step)
            self.p[k] -= lr * m / (np.sqrt(v) + 1e-8)
        report['gradient_norm'] = float(norm)
        return report

    def save(self, path, metadata):
        path = Path(path)
        if path.exists(): raise ValueError('Refuse to overwrite a frozen checkpoint')
        np.savez_compressed(path, **self.p, **{'adam_m_' + k: v for k, v in self.m.items()},
                            **{'adam_v_' + k: v for k, v in self.v.items()},
                            metadata=json.dumps(dict(metadata, hidden=self.hidden, step=self.step,
                                feature_version=FEATURE_VERSION, fingerprint=self.fingerprint)))

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as data:
            meta = json.loads(str(data['metadata']))
            if meta['feature_version'] != FEATURE_VERSION: raise ValueError('Feature version mismatch')
            net = cls(hidden=meta['hidden']); net.step = meta['step']
            for k in net.p:
                if data[k].shape != net.p[k].shape: raise ValueError('Checkpoint shape mismatch')
                net.p[k] = data[k].copy()
                net.m[k] = data['adam_m_' + k].copy(); net.v[k] = data['adam_v_' + k].copy()
        if net.fingerprint != meta['fingerprint']: raise ValueError('Checkpoint integrity mismatch')
        return net, meta
