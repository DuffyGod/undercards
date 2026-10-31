"""Causal semantic policies and a shared learned policy; no card-ID scores."""
import time
import numpy as np
from .legacy import agents as tactical
from .network import encode


def lethal(obs, nodes=32):
    # This upper bound avoids exploring attacks that cannot possibly be lethal.
    if sum(u['a'] for u in obs['own'] if u['ready']) < obs['enemy_hp']: return (), 0
    return tactical.lethal_plan(obs, nodes)


class ReferencePolicy:
    def __init__(self, style='race'):
        if style not in ('race', 'board', 'guard'): raise ValueError('Unknown reference policy')
        self.style = style; self.name = 'semantic_' + style

    def choose(self, obs, actions):
        start = time.perf_counter(); actor = obs['player']
        plan, nodes = lethal(obs)
        hand = {h['uid']: h for h in obs['hand']}; own = {u['uid']: u for u in obs['own']}; enemy = {u['uid']: u for u in obs['enemy']}
        incoming = sum(u['a'] for u in obs['enemy'])
        plays = [a for a in actions if a[0] == 'play']; attacks = [a for a in actions if a[0] == 'attack']
        selected = plan[0] if plan else None
        def effects(h, op): return [e for e in h['effects'] if e['trigger'] == 'play' and e['op'] == op]
        def heal(h): return sum(e['amount'] for e in effects(h, 'heal'))
        urgent = [a for a in plays if heal(hand[a[1]]) and (obs['hp'] <= incoming or obs['deck_count'] == 0 or obs['hp'] <= 12)]
        if selected is None and urgent:
            selected = max(urgent, key=lambda a: (min(30 - obs['hp'], heal(hand[a[1]])), -hand[a[1]]['cost']))
        removals = []
        for a in plays:
            h = hand[a[1]]; removed = 0
            for e in effects(h, 'damage'):
                targets = obs['enemy'] if e['scope'] == 'all_enemy' else [enemy[a[-1]]] if a[2] != actor and a[-1] in enemy else []
                removed += sum(u['a'] for u in targets if not u['dodge'] and e['amount'] - int(u['armor']) >= u['h'])
            if effects(h, 'kill') and enemy: removed += max(u['a'] for u in enemy.values())
            if removed and (removed >= incoming or incoming >= obs['hp'] or removed >= (5 if self.style == 'race' else 2)):
                removals.append((removed, -h['cost'], a))
        if selected is None and removals: selected = max(removals, key=lambda x: x[:2])[-1]
        if selected is None and attacks:
            trades = []
            for a in attacks:
                if a[-1] == -1: continue
                u, e = own[a[1]], enemy[a[-1]]
                killed = not e['dodge'] and u['a'] - int(e['armor']) >= e['h']
                survives = u['dodge'] or u['h'] > max(0, e['a'] - int(u['armor']))
                if killed and (survives or self.style == 'guard' or incoming >= obs['hp']):
                    trades.append((e['a'], bool(survives), -u['a'], a))
            faces = [a for a in attacks if a[-1] == -1]
            if trades and (self.style != 'race' or incoming >= obs['hp']): selected = max(trades, key=lambda x: x[:3])[-1]
            elif faces: selected = max(faces, key=lambda a: own[a[1]]['a'])
            elif trades: selected = max(trades, key=lambda x: x[:3])[-1]
            else: selected = max(attacks, key=lambda a: (not enemy[a[-1]]['dodge'], enemy[a[-1]]['a'], -own[a[1]]['a']))
        if selected is None and plays:
            choices = []
            for a in plays:
                h = hand[a[1]]
                if effects(h, 'silence') and a[2] == actor: continue
                if not h['health']:
                    if effects(h, 'heal') and 30 - obs['hp'] < heal(h): continue
                    if effects(h, 'draw') and (len(obs['hand']) >= 6 or not obs['deck_count']): continue
                    if not h['effects']: continue
                # Spending priorities are teacher hypotheses, never value labels.
                draw = sum(e['amount'] for e in effects(h, 'draw'))
                if self.style == 'guard': body_order = h['health'] + int(dict(h['keywords']).get('taunt', 0)) * 2
                else: body_order = h['attack'] + int(dict(h['keywords']).get('charge', 0)) * 2
                silence_power = 0
                if effects(h, 'silence') and a[-1] in enemy:
                    t = enemy[a[-1]]
                    silence_power = sum(t[k] for k in ('taunt', 'armor', 'dodge')) + len(t['spec']['effects']) * (not t['silenced'])
                score = (int(h['health'] > 0), -h['cost'] if self.style != 'guard' else body_order,
                         body_order if self.style != 'guard' else -h['cost'], silence_power, draw)
                choices.append((score, a))
            if choices: selected = max(choices, key=lambda x: x[0])[-1]
        selected = selected or actions[0]
        return dict(action=selected, action_index=actions.index(selected), behavior_probability=1., value=0.,
                    policy=self.name, search_override=False, search_nodes=nodes, seconds=time.perf_counter() - start)


class LearnedPolicy:
    def __init__(self, network, seed=0, stochastic=False, search_nodes=32):
        self.network = network; self.rng = np.random.default_rng(seed)
        self.stochastic = stochastic; self.search_nodes = search_nodes; self.name = 'shared_semantic_model'

    def choose(self, obs, actions):
        start = time.perf_counter(); prob, value, _ = self.network.forward(*encode(obs, actions))
        plan, nodes = lethal(obs, self.search_nodes)
        if plan: i = actions.index(plan[0]); bp = 1.
        elif self.stochastic: i = int(self.rng.choice(len(actions), p=prob)); bp = float(prob[i])
        else: i = int(prob.argmax()); bp = 1.
        return dict(action=actions[i], action_index=i, behavior_probability=bp, value=value,
                    policy=self.network.fingerprint, search_override=bool(plan), search_nodes=nodes,
                    seconds=time.perf_counter() - start)
