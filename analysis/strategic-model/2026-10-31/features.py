"""Shared semantic features. Names, IDs, UIDs and hidden state are not inputs."""
import numpy as np
from mechanisms import OPS, TRIGGERS, SCOPES, KEYWORDS

CARD_DIM = 15 + len(TRIGGERS) * len(OPS) * 3 + len(OPS) * len(SCOPES)
HISTORY = ('play', 'attack', 'punishment', 'fatigue', 'start', 'end', 'effect')
GLOBAL_DIM = 24
STATE_DIM = GLOBAL_DIM + 10 * CARD_DIM + 8 * (len(HISTORY) + 3)
ACTION_DIM = 3 + 2 * CARD_DIM + 10
VERSION = 'semantic-observation-0.1'


def card_features(card, board=False):
    if board:
        spec = card['spec']; a, h, maximum = card['a'], card['h'], card['max_h']
        flags = [card['ready'], card['fresh'], card['silenced'], True]
        keywords = [card[k] for k in KEYWORDS]
    else:
        spec = card; a, h, maximum = spec['attack'], spec['health'], spec['health']
        flags = [False, False, False, bool(h)]
        kw = dict(spec['keywords']); keywords = [kw.get(k, 0) for k in KEYWORDS]
    values = [spec['cost'] / 10, a / 10, h / 10, maximum / 10,
              spec['attack'] / 10, spec['health'] / 10]
    values += [float(x) / (3 if k == 'dodge' else 1) for k, x in zip(KEYWORDS, keywords)] + list(map(float, flags))
    effects = np.zeros((len(TRIGGERS), len(OPS), 3))
    selectors = np.zeros((len(OPS), len(SCOPES)))
    if not (board and card['silenced']):
        for e in spec['effects']:
            t, op, scope = TRIGGERS.index(e['trigger']), OPS.index(e['op']), SCOPES.index(e['scope'])
            effects[t, op] += [1, e['amount'] / 10, e['health'] / 10]
            selectors[op, scope] += 1
    result = np.concatenate((values, effects.ravel(), selectors.ravel()))
    if result.shape != (CARD_DIM,) or not np.isfinite(result).all():
        raise ValueError('Invalid semantic card vector')
    return result


def encode(obs, actions):
    c = obs['config']
    g = [obs['hp'] / 30, obs['enemy_hp'] / 30, np.log1p(obs['cash']) / 5,
         np.log1p(obs['enemy_cash']) / 5, obs['turn'] / 30, obs['enemy_turn'] / 30,
         obs['seat'], obs['deck_count'] / 25, obs['enemy_deck_count'] / 25,
         obs['enemy_hand_count'] / 7, obs['fatigue'] / 10, obs['enemy_fatigue'] / 10,
         obs['spent'] / 15, obs['previous_spent'] / 15, obs['enemy_previous_spent'] / 15,
         obs['enemy_response_unseen'] / 3, c['soul'] == 'INTEGRITY', c['soul'] == 'KINDNESS',
         c['response_kind'] == 'sweep', c['response_damage'] / 10, c['response_cost'] / 10,
         obs['silence_mode'] == 'retain', obs['silence_mode'] == 'reset', len(obs['hand']) / 7]
    zones = []
    for name in ('own', 'enemy'):
        if len(obs[name]) > 4: raise ValueError('Board capacity exceeded')
        rows = [card_features(u, True) for u in obs[name]]
        zones.extend(rows + [np.zeros(CARD_DIM)] * (4 - len(rows)))
    hand = [card_features(h) for h in obs['hand']]
    if len(hand) > 7: raise ValueError('Hand capacity exceeded')
    zones += [sum(hand, np.zeros(CARD_DIM)) / 7, np.max(hand, axis=0) if hand else np.zeros(CARD_DIM)]
    history = np.zeros((8, len(HISTORY) + 3))
    for i, e in enumerate(obs['history'][-8:]):
        history[i, HISTORY.index(e['action'])] = 1
        history[i, -3:] = [e['side'], e['amount'] / 10, e['cost'] / 10]
    state = np.concatenate((g, *zones, history.ravel()))
    rows = []
    for kind, uid, side, target in actions:
        source_zone = obs['hand'] if kind == 'play' else obs['own']
        src_index = next((i for i, u in enumerate(source_zone) if u['uid'] == uid), -1) if kind != 'end' else -1
        source = source_zone[src_index] if src_index >= 0 else None
        sf = card_features(source, kind == 'attack') if source else np.zeros(CARD_DIM)
        targets = obs['own'] if side == obs['player'] else obs['enemy']
        dst_index = next((i for i, u in enumerate(targets) if u['uid'] == target), -1) if side != -1 and target != -1 else -1
        dst = targets[dst_index] if dst_index >= 0 else None
        tf = card_features(dst, True) if dst else np.zeros(CARD_DIM)
        attack = source['a'] if kind == 'attack' else 0
        cross = [src_index / 7, dst_index / 4, side == obs['player'], side != -1 and target == -1,
                 bool(dst and attack >= dst['h']), bool(dst and source and kind == 'attack' and source['h'] > dst['a']),
                 bool(kind == 'attack' and target == -1 and attack >= obs['enemy_hp']),
                 (obs['cash'] - (source['cost'] if kind == 'play' else 0)) / 20,
                 (4 - len(obs['own'])) / 4, len(obs['hand']) / 7]
        rows.append(np.concatenate(([kind == 'end', kind == 'play', kind == 'attack'], sf, tf, cross)))
    af = np.asarray(rows, dtype=float)
    if state.shape != (STATE_DIM,) or af.shape != (len(actions), ACTION_DIM):
        raise ValueError('Observation/action shape mismatch')
    if not np.isfinite(state).all() or not np.isfinite(af).all(): raise ValueError('Nonfinite features')
    return state, af
