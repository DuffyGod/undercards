"""Streaming raw decisions with separate applied actions and teacher labels."""
import json
from .network import encode


class Recorder:
    def __init__(self, episode_id, sink=None, teacher=None, metadata=None):
        self.episode_id = episode_id; self.sink = sink; self.teacher = teacher
        self.metadata = metadata or {}; self.rows = []; self.samples = []; self.labels = []

    def write(self, row):
        if self.sink: self.sink.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')

    def record(self, obs, actions, selection):
        expert = self.teacher.choose(obs, actions) if self.teacher else None
        self.write(dict(schema='explicit-deck-trajectories-2', record_type='decision', episode_id=self.episode_id,
                        decision=len(self.rows), observation=obs, legal_actions=actions, selection=selection,
                        expert_action=expert['action'] if expert else None))
        self.rows.append((obs['player'], selection['policy'], selection.get('search_override', False)))
        feats = tuple(x.astype('float32') for x in encode(obs, actions))
        self.samples.append(dict(features=feats, chosen=actions.index(tuple(selection['action'])),
            behavior_probability=selection['behavior_probability'], old_value=selection['value']))
        self.labels.append(actions.index(tuple(expert['action'])) if expert else selection['action_index'])

    def finish(self, result):
        self.terminal = not result['unfinished'] and result['won'] != result['lost']
        returns = [1. if result['won'] else -1., -1. if result['won'] else 1.] if self.terminal else None
        self.write(dict(schema='explicit-deck-trajectories-2', record_type='outcome', episode_id=self.episode_id,
            terminated=self.terminal, returns=returns, metadata=self.metadata,
            result={k: v for k, v in result.items() if k not in ('decision_seconds', 'snapshots', 'trace', 'deck_semantics')}))
        self.returns = returns

    def training_samples(self, policy=None, imitation=False):
        if not self.terminal: return []
        out = []
        for (actor, fp, override), sample, label in zip(self.rows, self.samples, self.labels):
            if not imitation and (override or (policy is not None and fp != policy)): continue
            out.append(dict(sample, chosen=label if imitation else sample['chosen'], **{'return': self.returns[actor]}))
        return out
