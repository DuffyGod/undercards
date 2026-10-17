"""Exact common policies for a finite, nonprobabilistic information set.

Worlds describe possible hidden hands/libraries, never frequencies. Own actions
are chosen once for all states consistent with the public history. Opponent
actions may depend on the actual world. Their public action and outcome update
the belief before the next own decision; a singleton-world oracle is an upper
bound, not a deployable policy when that world is hidden.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

VERSION = 'finite-information-policy-0.1.0'


class ProtocolError(ValueError):
    pass


class SearchBudget(Exception):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def sources():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(__file__).parent.glob('*.py')) if not p.name.startswith('test_')}


def pack(items):
    """A world may have several indistinguishable physical successor states."""
    return tuple(sorted(set(items), key=lambda item: (item[0], repr(item[1]))))


@dataclass(frozen=True)
class Result:
    value: tuple
    policy: dict
    nodes: int
    physical_expansions: int
    policy_audit: dict
    root_action: object
    public_nodes: list


class Solver:
    def __init__(self, games, objective, *, node_limit=50000, audit_limit=200000):
        if type(node_limit) is not int or node_limit < 1 or type(audit_limit) is not int or audit_limit < 1:
            raise ProtocolError('Positive integer search and policy-audit budgets required')
        self.games = games
        self.objective = objective
        self.node_limit = node_limit
        self.audit_limit = audit_limit
        self.cache = {}
        self.policy = {}
        self.transitions = {}
        self.stack = set()
        self.nodes = 0

    def validate(self, belief):
        if not belief:
            raise ProtocolError('An information set cannot be empty')
        observations = {self.games[w].observation(s) for w, s in belief}
        owners = {self.games[w].owner(s) for w, s in belief}
        terminal = {self.games[w].finished(s) for w, s in belief}
        if len(observations) != 1 or len(owners) != 1 or len(terminal) != 1:
            raise ProtocolError('Information set contains differing visible observations, actors or terminal facts')
        owner = next(iter(owners))
        if owner not in ('own', 'enemy'):
            raise ProtocolError('Game owner must be own or enemy')
        return owner, next(iter(terminal))

    def actions(self, world, state):
        key = (world, state)
        if key not in self.transitions:
            if len(self.transitions) >= self.audit_limit:
                raise SearchBudget('Physical transition budget exhausted')
            values = tuple(self.games[world].actions(state))
            seen = {}
            for action, child in values:
                if action in seen and seen[action] != child:
                    raise ProtocolError('A physical action has several deterministic outcomes')
                seen[action] = child
            if not seen:
                raise ProtocolError('Nonterminal physical state has no legal action, including stop')
            self.transitions[key] = tuple(seen.items())
        return self.transitions[key]

    def group(self, transitions):
        groups = defaultdict(list)
        for world, state, action, child in transitions:
            game = self.games[world]
            label = (game.action_observation(action, state, child), game.observation(child))
            groups[label].append((world, child))
        return tuple(pack(values) for _, values in sorted(groups.items(), key=lambda item: repr(item[0])))

    def branches(self, belief, own_action=None):
        edges = []
        for world, state in belief:
            edges.extend((world, state, action, child) for action, child in self.actions(world, state)
                         if own_action is None or action == own_action)
        return self.group(edges)

    def menus(self, belief):
        menus = [{a for a, _ in self.actions(w, s)} for w, s in belief]
        if any(menu != menus[0] for menu in menus[1:]):
            raise ProtocolError('Own legal action menus differ across indistinguishable states; no hidden legality oracle is permitted')
        return sorted(menus[0], key=repr)

    def visit(self, belief):
        belief = pack(belief)
        if belief in self.cache:
            return self.cache[belief]
        if belief in self.stack:
            raise ProtocolError('A physical cycle exceeds this finite-game protocol')
        self.nodes += 1
        if self.nodes > self.node_limit:
            raise SearchBudget('Information-set search budget exhausted')
        owner, terminal = self.validate(belief)
        if terminal:
            value = min(self.objective(self.games[w], s) for w, s in belief)
        else:
            self.stack.add(belief)
            if owner == 'own':
                best = None
                for action in self.menus(belief):
                    # Commit before a hidden-dependent physical outcome is
                    # observed. Only subsequent observable branches may adapt.
                    value = min(self.visit(child) for child in self.branches(belief, action))
                    if best is None or value > best:
                        best, selected = value, action
                value = best
                self.policy[belief] = selected
            else:
                # Opponent may act differently in each real world. Identical
                # visible events merge all compatible successor states.
                value = min(self.visit(child) for child in self.branches(belief))
            self.stack.remove(belief)
        self.cache[belief] = value
        return value

    def audit(self, root):
        """Replay the chosen common policy against EVERY opponent branch.

        No search values or discarded own actions are used to establish its
        attained lower bound. This is a policy replay through the same physical
        engine, not an independent verification of the game rules.
        """
        memo = {}; public = []
        def replay(belief):
            belief = pack(belief)
            if belief in memo:
                return memo[belief]
            if len(memo) >= self.audit_limit:
                raise SearchBudget('Policy replay budget exhausted')
            owner, terminal = self.validate(belief)
            if terminal:
                result = min(self.objective(self.games[w], s) for w, s in belief)
            else:
                selected = self.policy.get(belief) if owner == 'own' else None
                if owner == 'own' and selected not in self.menus(belief):
                    raise ProtocolError('Stored own policy is missing or illegal')
                children = self.branches(belief, selected)
                result = min(replay(child) for child in children)
                if owner == 'own':
                    w, state = belief[0]
                    public.append(dict(node_id=hashlib.sha256(repr(belief).encode()).hexdigest(),
                        possible_worlds=sorted({world for world, _ in belief}),
                        indistinguishable_physical_states=len(belief),
                        observation=repr(self.games[w].observation(state)),
                        action=self.games[w].describe_action(selected)))
            memo[belief] = result
            return result
        value = replay(root)
        return dict(passed=True, attained_value=list(value), replayed_beliefs=len(memo),
                    semantics='Actual shared policy, all enemy choices and all compatible visible branches; not independent engine verification.'), public

    def solve(self, root):
        root = pack(root)
        value = self.visit(root)
        audit, public = self.audit(root)
        if tuple(audit['attained_value']) != value:
            raise ProtocolError('Common policy replay does not attain the search value')
        action = self.policy.get(root)
        description = None if action is None else self.games[root[0][0]].describe_action(action)
        return Result(value, self.policy, self.nodes, len(self.transitions), audit, description, public)


def objective(task):
    if not isinstance(task, dict) or set(task)-{'kind', 'constraints'}:
        raise ProtocolError('Task has kind hp/joint and optional constraints')
    kind = task.get('kind')
    if kind == 'hp':
        if task.get('constraints'):
            raise ProtocolError('Pure HP task has no additional constraints')
        return lambda game, state: (game.hp(state),)
    if kind != 'joint' or not isinstance(task.get('constraints', {}), dict):
        raise ProtocolError('Explicit hp or joint task required')
    constraints = {'min_own_player_hp': 1, **task.get('constraints', {})}
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in constraints.values()):
        raise ProtocolError('Finite numeric constraints required')
    return lambda game, state: (int(game.goal(state, constraints)), game.hp(state))


def cell(value, kind):
    if value is None:
        return dict(value=None, feasible=None, guaranteed_player_hp=None)
    feasible = value[0] > 0 if kind == 'hp' else bool(value[0])
    hp = value[0] if kind == 'hp' else value[1] if feasible else None
    return dict(value=list(value), feasible=feasible, guaranteed_player_hp=hp)


def evaluate(config, cards=None):
    # Lazy import permits protocol tests using tiny independent games even
    # when an optional card-family adapter is unavailable.
    from .engine import Game, UnknownMechanic
    binding = sources()
    allowed = {'scenario', 'worlds', 'task', 'node_limit', 'audit_limit', 'report_oracle', 'include_policy'}
    if not isinstance(config, dict) or set(config)-allowed or not {'scenario', 'worlds'} <= set(config):
        raise ProtocolError('Config requires scenario/worlds and documented task/budgets')
    scene, worlds = config['scenario'], config['worlds']
    if not isinstance(scene, dict) or not isinstance(worlds, list) or not 1 <= len(worlds) <= 16:
        raise ProtocolError('Scenario object and one to sixteen hidden worlds required')
    ids = []
    for world in worlds:
        if not isinstance(world, dict) or set(world)-{'id','opponent_hand_ids','opponent_hand_costs','opponent_hand_generated','opponent_deck_ids'}:
            raise ProtocolError('Only hidden enemy hand, prices and ordered library may vary by world')
        if not isinstance(world.get('id'), str) or not world['id']:
            raise ProtocolError('Nonempty string world IDs required')
        ids.append(world['id'])
    if len(set(ids)) != len(ids):
        raise ProtocolError('Duplicate world IDs')
    if cards is None:
        cards = json.loads((Path(__file__).resolve().parents[3]/'skills/undercards/references/snapshot.json').read_text())['cards']
    card_digest = hashlib.sha256(canonical(cards).encode()).hexdigest()
    task = config.get('task', {'kind':'hp'}); obj = objective(task); kind = task['kind']
    base = dict(version=VERSION, source_hashes=binding, cards_sha256=card_digest,
        input_sha256=hashlib.sha256(canonical(config).encode()).hexdigest(),
        task=task, information_protocol='Own sees only public actions/outcomes and own known state. Enemy knows its actual hidden world.',
        world_ids=ids, declared_world_envelope_complete_for_server=False,
        probabilities_inferred=False, calibrated_win_probability=None,
        scope='Exact only for this finite declared world set, rules and horizon. No claim that these are all real hidden cards.')
    try:
        games = {w['id']: Game(cards, dict(scene, **{k:v for k,v in w.items() if k != 'id'})) for w in worlds}
        root = pack((wid, game.root()) for wid, game in games.items())
        solver = Solver(games, obj, node_limit=config.get('node_limit', 50000), audit_limit=config.get('audit_limit', 200000))
        solver.validate(root)  # Public contradictions are rejected, not unknown scores.
        solved = solver.solve(root)
        common = cell(solved.value, kind)
        oracle = []; upper = None
        if config.get('report_oracle', True):
            for wid in ids:
                singleton = Solver(games, obj, node_limit=config.get('node_limit', 50000), audit_limit=config.get('audit_limit', 200000))
                try:
                    r = singleton.solve(pack(((wid, games[wid].root()),)))
                    oracle.append(dict(world_id=wid, known=True, **cell(r.value, kind), root_action=r.root_action, nodes=r.nodes))
                except (UnknownMechanic, SearchBudget) as error:
                    oracle.append(dict(world_id=wid, known=False, unknown=[str(error)]))
            if all(r['known'] for r in oracle):
                upper = min(tuple(r['value']) for r in oracle)
                if upper < solved.value:
                    raise ProtocolError('An informed-world oracle is below the valid common policy')
        hp_gap = None
        upper_cell = cell(upper, kind)
        if common['guaranteed_player_hp'] is not None and upper_cell['guaranteed_player_hp'] is not None:
            hp_gap = upper_cell['guaranteed_player_hp']-common['guaranteed_player_hp']
        result = dict(base, known=True, status='known', common_policy=common,
            root_action=solved.root_action, policy_audit=solved.policy_audit,
            visited_information_sets=solved.nodes, expanded_physical_states=solved.physical_expansions,
            oracle_worlds=oracle, informed_world_upper_bound=upper_cell,
            information_gap_hp=hp_gap, oracle_is_playable_under_hidden_information=False,
            policy=solved.public_nodes if config.get('include_policy', True) else None, unknown=[])
    except (UnknownMechanic, SearchBudget) as error:
        result = dict(base, known=False, status='unknown', common_policy=cell(None, kind),
                      root_action=None, unknown=[str(error)], policy=None)
    if binding != sources() or card_digest != hashlib.sha256(canonical(cards).encode()).hexdigest():
        raise RuntimeError('Game source or card source changed during evaluation')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--input', required=True); parser.add_argument('--output', required=True)
    args=parser.parse_args(); result=evaluate(json.loads(Path(args.input).read_text()))
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('known','common_policy','root_action','unknown')}, ensure_ascii=False))


if __name__ == '__main__': main()
