"""Decision-before-action records plus an explicit HP-terminal result record."""
import copy, gzip, json
from pathlib import Path
from features import encode

SCHEMA = 'decision-trajectories-1'


class Recorder:
    def __init__(self, episode_id, sink=None, metadata=None):
        self.episode_id = episode_id; self.sink = sink; self.rows = []; self.metadata = metadata or {}

    def _write(self, row):
        if self.sink is not None:
            self.sink.write(json.dumps(row, separators=(',', ':'), ensure_ascii=False) + '\n')

    def record(self, observation, actions, selection):
        row = dict(schema=SCHEMA, record_type='decision', episode_id=self.episode_id,
                   decision=len(self.rows), observation=copy.deepcopy(observation),
                   legal_actions=copy.deepcopy(actions), **copy.deepcopy(selection))
        self.rows.append(row); self._write(row)

    def finish(self, result):
        terminal = not result['unfinished'] and result['won'] != result['lost']
        returns = [1. if result['won'] else -1., -1. if result['won'] else 1.] if terminal else None
        summary = {k: v for k, v in result.items() if k not in ('trace', 'decision_seconds', 'snapshots')}
        self.result = dict(schema=SCHEMA, record_type='outcome', episode_id=self.episode_id,
            terminated=terminal, truncated=not terminal, returns=returns,
            scope='declared_role_game_with_composable_mechanisms', metadata=self.metadata, result=summary)
        self._write(self.result)

    def samples(self, learner_policy=None, include_search=False):
        if not hasattr(self, 'result') or not self.result['terminated']: return []
        out = []
        for row in self.rows:
            if learner_policy is not None and row['policy'] != learner_policy: continue
            if row['search_override'] and not include_search: continue
            actions = list(map(tuple, row['legal_actions'])); chosen = tuple(row['action'])
            if chosen not in actions or len(set(actions)) != len(actions): raise ValueError('Invalid action log')
            p = row['behavior_probability']
            if not 0 < p <= 1: raise ValueError('Invalid behavior probability')
            out.append(dict(features=encode(row['observation'], actions), chosen=actions.index(chosen),
                old_value=row['value'], behavior_probability=p,
                return_=self.result['returns'][row['observation']['player']]))
        for sample in out: sample['return'] = sample.pop('return_')
        return out


def load_episodes(path):
    """Old terminal-summary archives fail closed instead of masquerading as data."""
    opener = gzip.open if str(path).endswith('.gz') else open
    pending = {}; completed = set()
    with opener(path, 'rt', encoding='utf-8') as f:
        for line in f:
            row = json.loads(line)
            if row.get('schema') != SCHEMA: raise ValueError('Not decision-level training data')
            key = row['episode_id']
            if key in completed: raise ValueError('Records after completed episode')
            rec = pending.setdefault(key, Recorder(key))
            if row['record_type'] == 'decision':
                if row['decision'] != len(rec.rows): raise ValueError('Missing/duplicate decision')
                rec.rows.append(row)
            elif row['record_type'] == 'outcome':
                rec.result = row
                if row['terminated']:
                    if row['truncated'] or row['returns'] not in ([1., -1.], [-1., 1.]):
                        raise ValueError('Invalid terminal labels')
                elif row['returns'] is not None: raise ValueError('Truncation has no terminal label')
                completed.add(key); pending.pop(key); yield rec
            else: raise ValueError('Unknown record kind')
    # Interrupted episodes stay unlabelled, never assigned zero return.
