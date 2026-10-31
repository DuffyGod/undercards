"""V10: order-aware shared action values, with matched learning objectives.

The centered objective estimates within-information-set action differences.
It is not calibrated Q*, a belief model, or a safe-improvement guarantee.
Only visible semantics and owner-known/public-play summaries enter the head.
"""
from pathlib import Path
import hashlib, json
import numpy as np
from .legacy import features
from .relations import state_features, encode as relation_encode
from .knowledge import vector, SUMMARY_DIM
from .advantage_model import AdvantageNetwork
from .relational_model import RelationalNetwork

VERSION = 'ordered-paired-action-value-1'
MAX_EFFECTS = 8
EFFECT = 1 + len(features.TRIGGERS) + len(features.OPS) + len(features.SCOPES) + 2
CARD = 15 + MAX_EFFECTS * EFFECT
COMMON = 74 + 3 * SUMMARY_DIM + 2
INPUT = COMMON + 81 + 2 * CARD


def ordered_card(card, board=False):
    if card is None:
        return np.zeros(CARD)
    spec = card['spec'] if board else card
    effects = spec['effects'] if not (board and card['silenced']) else []
    if len(effects) > MAX_EFFECTS:
        raise ValueError('Effect sequence exceeds model capacity; never truncate or zero unknown effects')
    result = np.zeros((MAX_EFFECTS, EFFECT))
    for i, effect in enumerate(effects):
        row = result[i]; row[0] = 1.; offset = 1
        for field, options in (('trigger', features.TRIGGERS), ('op', features.OPS), ('scope', features.SCOPES)):
            row[offset + options.index(effect[field])] = 1.; offset += len(options)
        row[-2:] = effect['amount'] / 10, effect['health'] / 10
    return np.r_[features.card_features(card, board)[:15], result.ravel()]


def encode(obs, actions):
    state, relation = relation_encode(obs, actions)
    # Hand position is an implementation ordering, not information. Public
    # board positions remain meaningful to callbacks and are retained.
    relation = relation.copy(); relation[:, 27 + 29] = 0.
    common = np.r_[state, vector(obs)[3 * features.CARD_DIM:]]
    hand = {c['uid']: c for c in obs['hand']}
    own = {c['uid']: c for c in obs['own']}; enemy = {c['uid']: c for c in obs['enemy']}
    rows = []
    for i, (kind, uid, side, target) in enumerate(actions):
        source = hand[uid] if kind == 'play' else own[uid] if kind == 'attack' else None
        destination = (own if side == obs['player'] else enemy).get(target) if target != -1 else None
        rows.append(np.r_[common, relation[i], ordered_card(source, kind == 'attack'), ordered_card(destination, True)])
    x = np.asarray(rows, float)
    if x.shape != (len(actions), INPUT) or not np.isfinite(x).all():
        raise ValueError('Invalid public action-value inputs')
    # Frozen V5 needs its original semantic action descriptor, not this head.
    return state, (x, None)


class ActionValueNetwork(RelationalNetwork):
    feature_version = VERSION
    max_effects = MAX_EFFECTS

    def __init__(self, base=None, objective='centered', seed=2026103110, hidden=32, margin=.1):
        if objective not in ('centered', 'pointwise'):
            raise ValueError('Unknown action objective')
        self.base = base if base is not None else AdvantageNetwork()
        self.objective = objective; self.hidden = hidden; self.margin = float(margin)
        self.critic = self.base.critic.copy()
        rng = np.random.default_rng(seed)
        self.p = dict(W=rng.normal(0, 1 / np.sqrt(INPUT), (INPUT, hidden)), b=np.zeros(hidden),
                      w=rng.normal(0, 1 / np.sqrt(hidden), hidden), c=np.zeros(1))

    @property
    def actor_fingerprint(self):
        return hashlib.sha256((VERSION + self.objective + self.base.actor_fingerprint).encode() +
            np.float64(self.margin).tobytes() + b''.join(self.p[k].tobytes() for k in sorted(self.p))).hexdigest()

    @property
    def fingerprint(self):
        return hashlib.sha256(self.actor_fingerprint.encode() + self.critic.tobytes()).hexdigest()

    @property
    def parameters(self):
        return sum(v.size for v in self.p.values())

    def encode(self, obs, actions):
        state, (x, _) = encode(obs, actions)
        return state, (x, self.base.encode(obs, actions)[1])

    def batch(self, x):
        x = np.asarray(x, float)
        h = np.tanh(x @ self.p['W'] + self.p['b'])
        z = h @ self.p['w'] + self.p['c'][0]
        q = 1 / (1 + np.exp(-np.clip(z, -40, 40)))
        return q, (x, h, z)

    def action_scores(self, state, actions):
        return self.batch(actions[0])[0]

    def forward(self, state, actions):
        x, base_actions = actions
        previous = int(self.base.forward(state, base_actions)[0].argmax())
        q = self.batch(x)[0]; best = int(q.argmax())
        selected = best if q[best] - q[previous] > self.margin else previous
        prob = np.zeros(len(q)); prob[selected] = 1.
        return prob, self.predict_value(state), dict(base=previous, chosen=selected,
            predicted_gain=float(q[selected] - q[previous]), action_target='One action then frozen V5 continuation')

    def loss_grad(self, x, y, groups, weights, l2=.001):
        y = np.asarray(y, float); groups = np.asarray(groups, int); weights = np.asarray(weights, float)
        if not np.isin(y, (0, 1)).all() or np.any(weights <= 0) or not np.isfinite(weights).all():
            raise ValueError('Only complete binary rollout targets and positive weights')
        weights = weights / weights.sum(); q, (x, h, z) = self.batch(x)
        if self.objective == 'pointwise':
            loss = weights @ (np.logaddexp(0, z) - y * z); dz = weights * (q - y)
        else:
            residual = q - y
            for group in np.unique(groups):
                mask = groups == group
                # Within-fork weights are constant; unequal opening weights
                # across forks do not change this centering operation.
                if not np.allclose(weights[mask], weights[mask][0]):
                    raise ValueError('Centered group requires equal action weights')
                residual[mask] -= residual[mask].mean()
            loss = 2 * (weights @ residual ** 2)
            dz = 4 * weights * residual * q * (1 - q)
        dh = dz[:, None] * self.p['w'] * (1 - h ** 2)
        grads = dict(W=x.T @ dh, b=dh.sum(0), w=h.T @ dz, c=np.array([dz.sum()]))
        for k in ('W', 'w'):
            loss += l2 / 2 * np.sum(self.p[k] ** 2); grads[k] += l2 * self.p[k]
        return float(loss), grads

    def fit_value(self, *args, **kwargs):
        # Reuse checked, policy-specific logistic value fitting. No actor is
        # available for mutation in this method, and its fingerprint is checked.
        before = self.actor_fingerprint
        helper = RelationalNetwork()
        report = helper.fit_value(*args, **kwargs); self.critic = helper.critic.copy()
        if self.actor_fingerprint != before:
            raise ValueError('Value fitting changed actor')
        return dict(report, actor_fingerprint=before)

    def save(self, path, metadata):
        path = Path(path)
        if path.exists() or path.suffix != '.npz':
            raise ValueError('Preserve checkpoints; use a new .npz')
        np.savez_compressed(path, **self.p, critic=self.critic, base_actor=self.base.actor,
            base_advantage=self.base.advantage, base_critic=self.base.critic,
            metadata=json.dumps(dict(metadata, model_kind='ordered_action_value', feature_version=VERSION,
                objective=self.objective, hidden=self.hidden, margin=self.margin, base_margin=self.base.margin,
                fingerprint=self.fingerprint, actor_fingerprint=self.actor_fingerprint, parameters=self.parameters)))

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as data:
            meta = json.loads(str(data['metadata']))
            if meta['feature_version'] != VERSION:
                raise ValueError('Incompatible action-value schema')
            base = AdvantageNetwork(data['base_actor'].copy(), data['base_critic'].copy(), data['base_advantage'].copy(), meta['base_margin'])
            net = cls(base, meta['objective'], hidden=meta['hidden'], margin=meta['margin'])
            for k in net.p:
                if data[k].shape != net.p[k].shape:
                    raise ValueError('Action-value checkpoint shape mismatch')
                net.p[k] = data[k].copy()
            net.critic = data['critic'].copy()
        if net.critic.shape != (74,) or net.fingerprint != meta['fingerprint']:
            raise ValueError('Action-value checkpoint checksum mismatch')
        return net, meta
