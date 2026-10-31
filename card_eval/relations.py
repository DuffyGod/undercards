"""Public semantic relations for a shared action ranker and policy evaluation.

UIDs only join an action to visible entities. Names, card IDs, private decks,
teacher choices and future outcomes never enter these vectors.
"""
import numpy as np

VERSION = 'public-relations-1'


def state_features(obs):
    incoming = sum(u['a'] for u in obs['enemy'])
    ready = sum(u['a'] for u in obs['own'] if u['ready'])
    x = [1., obs['hp'] / 30, obs['enemy_hp'] / 30,
         np.log1p(obs['cash']) / 5, np.log1p(obs['enemy_cash']) / 5,
         obs['turn'] / 30, obs['enemy_turn'] / 30, obs['seat'],
         obs['deck_count'] / 25, obs['enemy_deck_count'] / 25,
         len(obs['hand']) / 7, obs['enemy_hand_count'] / 7,
         obs['fatigue'] / 10, obs['enemy_fatigue'] / 10,
         obs['spent'] / 15, obs['previous_spent'] / 15, obs['enemy_previous_spent'] / 15,
         incoming / 20, ready / 20, incoming >= obs['hp'], ready >= obs['enemy_hp'],
         obs['deck_count'] == 0, obs['enemy_deck_count'] == 0,
         obs.get('own_soul', obs['config']['soul']) == 'KINDNESS', obs.get('enemy_soul') == 'KINDNESS']
    for zone in ('own', 'enemy'):
        units = obs[zone]
        x += [len(units) / 4, sum(u['a'] for u in units) / 30,
              sum(u['h'] for u in units) / 30, sum(u['max_h'] for u in units) / 30]
        x += [sum(bool(u[k]) for u in units) / 4 for k in ('taunt', 'armor', 'dodge', 'ready', 'silenced')]
        for op in ('draw', 'heal', 'damage', 'buff'):
            x.append(sum(e['amount'] for u in units if not u['silenced'] for e in u['spec']['effects']
                         if e['op'] == op and e['trigger'] in ('start', 'end')) / 20)
    for key in ('cost', 'attack', 'health'):
        vals = [h[key] for h in obs['hand']]
        x += [sum(vals) / 50, max(vals, default=0) / 10]
    for op in ('draw', 'heal', 'damage', 'kill', 'silence', 'buff', 'gold'):
        x.append(sum(e['amount'] + (e['op'] in ('kill', 'silence')) for h in obs['hand']
                     for e in h['effects'] if e['op'] == op) / 20)
    # Public history summaries are finite-memory information, not a belief state.
    for kind in ('play', 'attack', 'punishment', 'fatigue', 'effect'):
        for side in (0, 1):
            x.append(sum(e['amount'] for e in obs['history'][-8:]
                         if e['action'] == kind and e['side'] == side) / 30)
    return np.asarray(x, dtype=float)


def encode(obs, actions):
    actor = obs['player']; hand = {u['uid']: u for u in obs['hand']}
    own = {u['uid']: u for u in obs['own']}; enemy = {u['uid']: u for u in obs['enemy']}
    incoming = sum(u['a'] for u in obs['enemy']); danger = incoming >= obs['hp']
    context = [1., danger, obs['hp'] <= 12, not obs['deck_count'], len(obs['hand']) >= 6,
               obs['hp'] / 30, incoming / 20, len(obs['own']) / 4]
    rows = []
    for kind, uid, side, target in actions:
        f = [float(kind == k) for k in ('end', 'play', 'attack')]
        f += list(np.outer(f, context).ravel())
        p = np.zeros(35); a = np.zeros(19)
        if kind == 'play':
            h = hand[uid]; kw = dict(h['keywords']); es = h['effects']
            effects = [e for e in es if e['trigger'] == 'play']
            # Owner healing and drawing only: target effects cannot become hero value.
            heal = sum(e['amount'] for e in effects if e['op'] == 'heal' and e['scope'] == 'owner')
            draw = sum(e['amount'] for e in effects if e['op'] == 'draw' and e['scope'] == 'owner')
            t = enemy.get(target) if side != actor else own.get(target)
            damage_kills = 0; removed = 0
            for e in effects:
                if e['op'] == 'damage':
                    targets = obs['enemy'] if e['scope'] == 'all_enemy' else [t] if t and side != actor else []
                    killed = [u for u in targets if not u['dodge'] and e['amount'] - int(u['armor']) >= u['h']]
                    damage_kills += len(killed); removed += sum(u['a'] for u in killed)
                elif e['op'] == 'kill' and e['scope'] == 'highest_enemy' and enemy:
                    damage_kills += 1; removed += max(u['a'] for u in enemy.values())
            silence = any(e['op'] == 'silence' for e in effects)
            power = (sum(bool(t[k]) for k in ('taunt', 'armor', 'dodge')) +
                     len(t['spec']['effects']) * (not t['silenced'])) if t and silence else 0
            effective = min(30 - obs['hp'], heal)
            urgent = danger or obs['hp'] <= 12 or not obs['deck_count']
            p[:] = [1., h['cost'] / 10, h['attack'] / 10, h['health'] / 10, bool(h['health']),
                    kw.get('haste', 0), kw.get('charge', 0), kw.get('taunt', 0), kw.get('armor', 0), kw.get('dodge', 0) / 3,
                    effective / 10, heal > 0, effective / 10 * urgent, bool(heal) and urgent,
                    draw / 3, min(draw, max(0, 8 - len(obs['hand'])), obs['deck_count']) / 3,
                    bool(draw) and (len(obs['hand']) >= 6 or not obs['deck_count']),
                    damage_kills / 4, removed / 20, bool(removed), bool(removed) and danger,
                    bool(removed) and removed >= incoming, removed >= 2, removed >= 5,
                    silence, bool(silence and side == actor), power / 5,
                    (obs['cash'] - h['cost']) / 20, (4 - len(obs['own'])) / 4,
                    obs['hand'].index(h) / 7, (list(enemy).index(target) / 4 if side != actor and target in enemy else 0),
                    sum(e['amount'] for e in es if e['op'] == 'draw' and e['trigger'] != 'play') / 3,
                    sum(e['amount'] for e in es if e['op'] == 'buff') / 3,
                    bool(not h['health'] and heal > 30 - obs['hp']), bool(not h['health'] and not es)]
        elif kind == 'attack':
            u = own[uid]; t = enemy.get(target)
            killed = bool(t and not t['dodge'] and u['a'] - int(t['armor']) >= t['h'])
            survives = bool(t and (u['dodge'] or u['h'] > max(0, t['a'] - int(u['armor']))))
            a[:] = [1., target == -1, u['a'] / 10, u['h'] / 10, bool(u['armor']), bool(u['dodge']),
                    (t['a'] / 10 if t else 0), (t['h'] / 10 if t else 0), bool(t and t['dodge']),
                    bool(t and t['taunt']), killed, survives, killed and survives,
                    (t['a'] / 10 if killed else 0), u['a'] / 10 * killed,
                    killed and danger, (t['a'] / 10 if killed and danger else 0),
                    obs['own'].index(u) / 4, (obs['enemy'].index(t) / 4 if t else 0)]
        f += list(p) + list(a)
        rows.append(f)
    return state_features(obs), np.asarray(rows, dtype=float)
