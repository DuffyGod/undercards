"""Shared actor/critic reusing verified gradients with public opponent SOUL."""
from pathlib import Path
import json
import numpy as np
from .legacy import learner, features

VERSION = 'explicit-decks-policy-value-3'
OLD_VERSION = 'explicit-decks-policy-value-2'
STATE_DIM = features.STATE_DIM + 2
ACTION_DIM = features.ACTION_DIM + 2 * features.CARD_DIM


def encode(obs, actions, version=VERSION):
    state, af = features.encode(obs, actions)
    soul = obs.get('enemy_soul', obs['config']['soul'])
    if version == VERSION:
        source = af[:, 3:3 + features.CARD_DIM]
        af = np.concatenate((af, source * af[:, 1:2], source * af[:, 2:3]), axis=1)
    return np.concatenate((state, [soul == 'INTEGRITY', soul == 'KINDNESS'])), af


class Network(learner.Network):
    def __init__(self, seed=0, hidden=32, feature_version=VERSION):
        super().__init__(seed, hidden)
        self.feature_version = feature_version
        self.p['Ws'] = np.random.default_rng(seed + 199).normal(0, 1 / np.sqrt(STATE_DIM), (STATE_DIM, hidden))
        self.m['Ws'] = np.zeros_like(self.p['Ws']); self.v['Ws'] = np.zeros_like(self.p['Ws'])
        if feature_version == VERSION:
            self.p['Wa'] = np.random.default_rng(seed + 299).normal(0, 1 / np.sqrt(hidden + ACTION_DIM), (hidden + ACTION_DIM, hidden))
            self.m['Wa'] = np.zeros_like(self.p['Wa']); self.v['Wa'] = np.zeros_like(self.p['Wa'])

    def encode(self, obs, actions): return encode(obs, actions, self.feature_version)

    def loss_grad(self, samples, imitation=False, **kwargs):
        # Reuse the numerically checked PPO derivative; the old implementation
        # represents advantage as return-old_value. Preserve logged old values
        # while allowing batch-standardized advantages in optimizer inputs.
        if not imitation:
            samples = [dict(s, old_value=s['return'] - s.get('advantage', s['return'] - s['old_value'])) for s in samples]
        return super().loss_grad(samples, imitation=imitation, **kwargs)

    def save(self, path, metadata):
        path = Path(path)
        if path.suffix != '.npz' or path.exists(): raise ValueError('Use a new .npz checkpoint path')
        np.savez_compressed(path, **self.p, **{'adam_m_' + k: v for k, v in self.m.items()},
            **{'adam_v_' + k: v for k, v in self.v.items()}, metadata=json.dumps(dict(metadata,
                hidden=self.hidden, step=self.step, feature_version=self.feature_version, fingerprint=self.fingerprint)))

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as data:
            meta = json.loads(str(data['metadata']))
            if meta.get('model_kind') == 'ordered_action_value':
                from .action_value import ActionValueNetwork
                return ActionValueNetwork.load(path)
            if meta.get('model_kind') == 'entity_continuation':
                from .entity_value import EntityValueNetwork
                return EntityValueNetwork.load(path)
            if meta.get('model_kind') == 'known_seen_improvement':
                from .memory_model import MemoryNetwork
                return MemoryNetwork.load(path)
            if meta.get('model_kind') == 'paired_advantage':
                from .advantage_model import AdvantageNetwork
                return AdvantageNetwork.load(path)
            if meta.get('model_kind') == 'relational_linear':
                from .relational_model import RelationalNetwork
                return RelationalNetwork.load(path)
            if meta['feature_version'] not in (VERSION, OLD_VERSION): raise ValueError('Incompatible policy feature version')
            net = cls(hidden=meta['hidden'], feature_version=meta['feature_version']); net.step = meta['step']
            for k in net.p:
                if data[k].shape != net.p[k].shape: raise ValueError('Checkpoint shape mismatch')
                net.p[k] = data[k].copy(); net.m[k] = data['adam_m_' + k].copy(); net.v[k] = data['adam_v_' + k].copy()
        if net.fingerprint != meta['fingerprint']: raise ValueError('Checkpoint checksum mismatch')
        return net, meta
