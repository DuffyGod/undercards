"""Agents only consume observations. Search never receives a hidden game clone."""
import copy, time, heapq
from dataclasses import asdict
import numpy as np
from environment import bridge, legacy_view
from features import encode
from mechanisms import damage_packet


def attack_actions(obs):
    if min(obs['hp'], obs['enemy_hp']) <= 0: return []
    actor = obs['player']; targets = [u for u in obs['enemy'] if u['taunt']] or obs['enemy']
    taunt = any(u['taunt'] for u in obs['enemy'])
    out = []
    for u in obs['own']:
        if not u['ready'] or u['a'] <= 0: continue
        out += [('attack', u['uid'], 1 - actor, e['uid']) for e in targets]
        if not taunt and (not u['fresh'] or u['charge']): out.append(('attack', u['uid'], 1 - actor, -1))
    return out


def public_attack(obs, action):
    if action not in attack_actions(obs): raise ValueError('Illegal public attack')
    child = copy.deepcopy(obs)
    _, uid, _, target = action
    u = next(u for u in child['own'] if u['uid'] == uid)
    u['ready'] = False; u['haste'] = False; u['charge'] = False
    if target == -1: child['enemy_hp'] -= u['a']
    else:
        e = next(e for e in child['enemy'] if e['uid'] == target)
        u['h'], u['dodge'] = damage_packet(u['h'], u['dodge'], u['armor'], e['a'])
        e['h'], e['dodge'] = damage_packet(e['h'], e['dodge'], e['armor'], u['a'])
        child['own'] = [x for x in child['own'] if x['h'] > 0]
        child['enemy'] = [x for x in child['enemy'] if x['h'] > 0]
    child['history'] = (child['history'] + [dict(side=0, action='attack', amount=u['a'], cost=0)])[-8:]
    return child


def lethal_plan(obs, node_limit=64):
    """Bounded attack coordination. An incomplete search never certifies safety."""
    stack = [(obs, ())]; nodes = 0
    while stack and nodes < node_limit:
        state, plan = stack.pop(); nodes += 1
        if state['enemy_hp'] <= 0: return plan, nodes
        options = attack_actions(state)
        # Explore face routes first; all branches use only the public board.
        for action in sorted(options, key=lambda a: a[-1] == -1):
            stack.append((public_attack(state, action), plan + (action,)))
    return (), nodes


def value_guided_attacks(obs, network, node_limit=8):
    """Best-first public attack search, neural priorities and neural leaf value.

    Unknown draw/deployment outcomes are deliberately not determinized from the
    real hidden deck. This is an optional frozen ablation, not a win guarantee.
    """
    queue = [(0., 0, obs, ())]; serial = 0; nodes = 0
    best = None; best_score = -float('inf'); root_value = None
    while queue and nodes < node_limit:
        priority, _, state, plan = heapq.heappop(queue); nodes += 1
        actions = [('end', -1, -1, -1)] + attack_actions(state)
        prob, value, _ = network.forward(*encode(state, actions))
        if root_value is None: root_value = value
        if state['enemy_hp'] <= 0: return plan, nodes
        if plan and value > best_score:
            best, best_score = plan, value
        if len(plan) >= 4: continue
        for index in np.argsort(prob)[::-1]:
            action = actions[int(index)]
            if action[0] != 'attack': continue
            child = public_attack(state, action); serial += 1
            # Exact terminal outcomes always outrank uncertain value estimates.
            if child['enemy_hp'] <= 0: return plan + (action,), nodes
            heapq.heappush(queue, (priority - float(np.log(max(prob[index], 1e-15))), serial,
                                  child, plan + (action,)))
    return (best if best is not None and best_score > root_value else ()), nodes


class LearnedAgent:
    def __init__(self, network, seed=0, stochastic=False, search_nodes=64, value_nodes=0):
        self.network = network; self.rng = np.random.default_rng(seed)
        self.stochastic = stochastic; self.search_nodes = search_nodes
        self.name = 'shared_policy_value'
        self.value_nodes = value_nodes

    def choose(self, obs, actions):
        start = time.perf_counter(); features = encode(obs, actions)
        prob, value, _ = self.network.forward(*features)
        plan, nodes = lethal_plan(obs, self.search_nodes) if self.search_nodes else ((), 0)
        if not plan and self.value_nodes:
            plan, extra = value_guided_attacks(obs, self.network, self.value_nodes); nodes += extra
        if plan:
            index = actions.index(plan[0]); behavior_probability = 1.
        elif self.stochastic:
            index = int(self.rng.choice(len(actions), p=prob)); behavior_probability = float(prob[index])
        else:
            index = int(prob.argmax()); behavior_probability = 1.
        return dict(action=actions[index], behavior_probability=behavior_probability, value=value,
                    policy=self.network.fingerprint, action_index=index, search_override=bool(plan),
                    search_nodes=nodes, seconds=time.perf_counter() - start)


class FixedAgent:
    def __init__(self, policy):
        self.policy = policy; self.name = policy.name

    def choose(self, obs, actions):
        start = time.perf_counter()
        view = legacy_view(obs)
        held = next((h for h in obs['hand'] if h['candidate']), None)
        candidate = bridge.Body(held['name'], held['cost'], held['attack'], held['health']) if held else None
        kind, uid, target = bridge.decision(view, self.policy, candidate)
        choices = [a for a in actions if a[0] == kind and a[1] == uid and (kind != 'attack' or a[-1] == target)]
        # The six retained policies were designed without new keywords. This
        # wrapper obeys new legality and openly labels its mechanical fallback.
        fallback = False
        if not choices:
            fallback = True
            if kind == 'attack': choices = [a for a in actions if a[0] == 'attack']
            if not choices: choices = [actions[0]]
        if len(choices) > 1:
            enemies = {u['uid']: u for u in obs['enemy']}
            choices.sort(key=lambda a: (a[2] != obs['player'], enemies.get(a[-1], {}).get('a', 0)), reverse=True)
        action = choices[0]
        return dict(action=action, behavior_probability=1., value=0., policy='fixed:' + self.policy.name,
                    action_index=actions.index(action), search_override=False, legality_fallback=fallback,
                    search_nodes=None, seconds=time.perf_counter() - start)
