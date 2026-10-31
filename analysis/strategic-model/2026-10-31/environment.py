"""Learning actions over the retained resource engine and shared effect rules.

Only this object owns private decks. Agents receive sanitized observations and
legal action tuples. The old October20/30 sources and results stay unchanged.
"""
from dataclasses import dataclass, asdict, replace
from pathlib import Path
import sys, time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / '2026-10-30'))
import engine as bridge
from mechanisms import Spec, Effect, hurt, silence, UnsupportedRule

Config = bridge.Config
Policy = bridge.Policy
Action = tuple  # ('end'|'play'|'attack', source UID, target actor, target UID|-1)
VERSION = 'shared-action-mechanisms-0.1'


@dataclass(frozen=True)
class Unit(bridge.Unit):
    spec: Spec | None = None
    fresh: bool = False
    haste: bool = False
    charge: bool = False
    taunt: bool = False
    armor: bool = False
    dodge: int = 0
    silenced: bool = False


def role_specs(cfg):
    return {
        'small': Spec('small role', cfg.small_cost, cfg.small_attack, cfg.small_health),
        'anchor': Spec('anchor role', cfg.anchor_cost, cfg.anchor_attack, cfg.anchor_health),
        'draw': Spec('draw role', cfg.draw_cost, effects=(Effect('play', 'draw', 'owner', cfg.draw_amount),)),
        'heal': Spec('heal role', cfg.heal_cost, effects=(Effect('play', 'heal', 'owner', cfg.heal_amount),)),
        'response': Spec('response role', cfg.response_cost, effects=(
            Effect('play', 'damage', 'all_enemy', cfg.response_damage) if cfg.response_kind == 'sweep'
            else Effect('play', 'kill', 'highest_enemy'),)),
    }


class LearningGame(bridge.BridgeGame):
    def __init__(self, structure, seed, cfg, candidate, agents, opponent_candidate=None,
                 silence_mode='retain', trace=False, recorder=None, decision_seconds=.25):
        self.specs = (candidate, opponent_candidate)
        self.roles = role_specs(cfg)
        self.agents = agents
        self.silence_mode = silence_mode
        self.recorder = recorder
        self.public_events = []
        self.decisions = []
        self.usage = [[], []]
        self.actor = 0
        self.decision_seconds = decision_seconds
        body = bridge.Body(candidate.name, candidate.cost, candidate.attack, candidate.health, candidate.card_id)
        super().__init__(structure, seed, cfg, (Policy('agent0'), Policy('agent1')), body, trace=trace)
        if opponent_candidate:
            b = self.players[1]
            conv = lambda h: replace(h, kind='candidate') if h.uid < 3 else h
            b.hand = [conv(h) for h in b.hand]; b.deck = [conv(h) for h in b.deck]

    def event(self, actor, action, **kw):
        super().event(actor, action, **kw)
        # Private draw identity, end-of-turn hand contents and shuffled UIDs are
        # never copied into public history. Burned identities are public here.
        if action in ('play', 'attack', 'punishment', 'fatigue', 'start', 'end', 'effect'):
            self.public_events.append(dict(actor=actor, action=action,
                amount=kw.get('damage', kw.get('attack', kw.get('income', kw.get('amount', 0)))),
                cost=kw.get('cost', 0)))

    def spec(self, actor, card):
        if card.kind == 'candidate':
            if self.specs[actor] is None: raise UnsupportedRule('Missing candidate descriptor')
            return self.specs[actor]
        return self.roles[card.kind]

    def legal_actions(self, actor):
        if min(p.hp for p in self.players) <= 0: return []
        a, b = self.players[actor], self.players[1 - actor]
        out = [('end', -1, -1, -1)]
        taunts = [u for u in b.units if u.taunt]
        for u in a.units:
            if not u.ready or u.a <= 0: continue
            for target in taunts or b.units:
                out.append(('attack', u.uid, 1 - actor, target.uid))
            if not taunts and (not u.fresh or u.charge):
                out.append(('attack', u.uid, 1 - actor, -1))
        for h in a.hand:
            spec = self.spec(actor, h)
            if a.cash < spec.cost or (spec.health and len(a.units) >= self.cfg.slots): continue
            choices = [e for e in spec.effects if e.trigger == 'play' and e.scope in ('enemy', 'monster')]
            if choices:
                sides = (1 - actor,) if choices[0].scope == 'enemy' else (actor, 1 - actor)
                targets = [(s, u.uid) for s in sides for u in self.players[s].units]
                # Explicit domain assumption: no-target Magic fizzles; the body
                # can still enter. The new source cannot choose itself.
                if not targets: targets = [(-1, -1)]
                out.extend(('play', h.uid, s, uid) for s, uid in targets)
            else:
                out.append(('play', h.uid, -1, -1))
        return out

    def _effects(self, actor, source, spec, trigger, chosen=(-1, -1)):
        if trigger != 'play':
            living = next((u for u in self.players[actor].units if u.uid == source), None)
            if living is None or living.silenced: return
        for e in spec.effects:
            if e.trigger != trigger or min(p.hp for p in self.players) <= 0: continue
            a, b = self.players[actor], self.players[1 - actor]
            if e.op == 'draw':
                for _ in range(e.amount):
                    if a.hp <= 0: break
                    self.draw(actor)
            elif e.op == 'heal':
                n = min(e.amount, 30 - a.hp); a.hp += n; a.healing += n
            elif e.op == 'gold':
                a.cash += e.amount; a.bonus_gold += e.amount
            elif e.op == 'damage' and e.scope == 'opponent':
                b.hp -= e.amount; a.damage += e.amount
            else:
                if e.scope == 'self': targets = [(actor, source)]
                elif e.scope == 'all_enemy': targets = [(1 - actor, u.uid) for u in b.units]
                elif e.scope == 'highest_enemy':
                    targets = [(1 - actor, max(b.units, key=lambda u: (u.a, u.h, -u.uid)).uid)] if b.units else []
                else: targets = [chosen] if chosen[0] != -1 else []
                for side, uid in targets:
                    p = self.players[side]
                    u = next((u for u in p.units if u.uid == uid), None)
                    if u is None: continue
                    if e.op == 'damage': new = hurt(u, e.amount)
                    elif e.op == 'kill': new = replace(u, h=0)
                    elif e.op == 'silence': new = silence(u, self.silence_mode)
                    elif e.op == 'buff':
                        new = replace(u, a=max(0, u.a + e.amount), h=u.h + e.health,
                                      max_h=max(1, u.max_h + e.health))
                    else: raise UnsupportedRule('No implementation for effect')
                    p.units = [new if x.uid == uid else x for x in p.units]
                    p.units = [x for x in p.units if x.h > 0]
            self.event(actor, 'effect', op=e.op, trigger=trigger, amount=e.amount)

    def play_action(self, actor, uid, target_side=-1, target=-1):
        a, b = self.players[actor], self.players[1 - actor]
        h = next(h for h in a.hand if h.uid == uid); spec = self.spec(actor, h)
        a.hand.remove(h); a.cash -= spec.cost; a.spent += spec.cost
        a.total_spent += spec.cost; a.played += 1
        if spec.health:
            a.units.append(Unit(uid, h.kind, spec.attack, spec.health, spec.health,
                ready=bool(spec.keyword('haste') or spec.keyword('charge')), spec=spec, fresh=True,
                haste=bool(spec.keyword('haste')), charge=bool(spec.keyword('charge')),
                taunt=bool(spec.keyword('taunt')), armor=bool(spec.keyword('armor')), dodge=spec.keyword('dodge')))
            if a.first_effective_penalty_turn:
                a.post_penalty_uids.add(uid)
                if not a.rebuilt_deploy_turn: a.rebuilt_deploy_turn = a.turn
        if actor == 0 and h.kind == 'candidate':
            self.candidate_played += 1
            if not self.candidate_first_turn: self.candidate_first_turn = a.turn
        if h.kind == 'response':
            a.response_public += 1; a.penalties += 1
        before = len(b.units)
        self.event(actor, 'play', card=asdict(h), cost=spec.cost, cash_after=a.cash)
        self._effects(actor, uid, spec, 'play', (target_side, target))
        killed = before - len(b.units)
        if h.kind == 'response' and killed and not b.first_effective_penalty_turn:
            b.first_effective_penalty_turn = b.turn; b.first_penalty_killed = killed
            b.first_penalty_wiped = not b.units

    def attack(self, actor, uid, target):
        a, b = self.players[actor], self.players[1 - actor]
        u = next(u for u in a.units if u.uid == uid)
        if target == -1:
            b.hp -= u.a; a.damage += u.a
            new = replace(u, ready=False, haste=False, charge=False)
            a.units = [new if x.uid == uid else x for x in a.units]
        else:
            enemy = next(x for x in b.units if x.uid == target)
            new = replace(hurt(u, enemy.a), ready=False, haste=False, charge=False)
            defender = hurt(enemy, u.a)
            a.units = [new if x.uid == uid else x for x in a.units]
            b.units = [defender if x.uid == target else x for x in b.units]
            a.units = [x for x in a.units if x.h > 0]; b.units = [x for x in b.units if x.h > 0]
        if uid in a.post_penalty_uids and not a.rebuilt_attack_turn: a.rebuilt_attack_turn = a.turn
        self.event(actor, 'attack', unit=uid, target=target, attack=u.a)

    def apply(self, actor, action):
        if action not in self.legal_actions(actor): raise ValueError('Illegal action')
        kind, uid, side, target = action
        if kind == 'play': self.play_action(actor, uid, side, target)
        elif kind == 'attack': self.attack(actor, uid, target)

    def observation(self, actor):
        a, b = self.players[actor], self.players[1 - actor]
        def held(h):
            return dict(uid=h.uid, role=h.kind, candidate=h.kind == 'candidate', **asdict(self.spec(actor, h)))
        def unit(u):
            d = asdict(u); d['spec'] = asdict(u.spec); return d
        return dict(player=actor, hp=a.hp, enemy_hp=b.hp, cash=a.cash, enemy_cash=b.cash,
            turn=a.turn, enemy_turn=b.turn, seat=self.cfg.seat if actor == 0 else 1 - self.cfg.seat,
            deck_count=len(a.deck), enemy_deck_count=len(b.deck), enemy_hand_count=len(b.hand),
            fatigue=a.fatigue, enemy_fatigue=b.fatigue, spent=a.spent, previous_spent=a.previous_spent,
            enemy_previous_spent=b.previous_spent, hand=[held(h) for h in a.hand],
            own=[unit(u) for u in a.units], enemy=[unit(u) for u in b.units],
            enemy_response_unseen=self.view(actor).enemy_response_unseen,
            config=asdict(self.cfg), silence_mode=self.silence_mode,
            history=[dict(side=int(e['actor'] != actor), action=e['action'], amount=e['amount'], cost=e['cost'])
                     for e in self.public_events[-8:]])

    def act_turn(self, actor):
        self.actor = actor
        a, b = self.players[actor], self.players[1 - actor]; c = self.cfg
        a.turn += 1; a.spent = 0
        grant = bridge.income(a.turn, c.seat if actor == 0 else 1 - c.seat, c.soul)
        a.cash += grant; a.income += grant
        a.units = [replace(u, ready=True, fresh=False, haste=False, charge=False) for u in a.units]
        self.event(actor, 'start', income=grant, cash=a.cash)
        if c.first_draw or a.turn > 1: self.draw(actor)
        if min(a.hp, b.hp) <= 0: return
        for u in list(a.units):
            if not u.silenced: self._effects(actor, u.uid, u.spec, 'start')
        if actor == 0 and any(h.kind == 'candidate' for h in a.hand):
            self.candidate_wait += 1
            self.candidate_unfunded_turns += a.cash < self.specs[0].cost
            self.candidate_slot_blocked_turns += len(a.units) == c.slots
        for _ in range(100):
            if min(a.hp, b.hp) <= 0: return
            obs = self.observation(actor); actions = self.legal_actions(actor)
            started = time.perf_counter()
            selection = self.agents[actor].choose(obs, actions)
            selection['seconds'] = time.perf_counter() - started
            if selection['seconds'] > self.decision_seconds:
                raise RuntimeError('Decision exceeded the common wall-time budget')
            action = tuple(selection['action'])
            if action not in actions: raise ValueError('Agent selected an illegal action')
            self.usage[actor].append(selection.get('seconds', 0.0))
            if self.recorder is not None:
                self.recorder.record(obs, actions, selection)
            if action[0] == 'end': break
            self.apply(actor, action)
        else: raise ValueError('Action loop exceeded its declared bound')
        a.held_opportunities += int(any(h.kind == 'response' for h in a.hand) and a.cash >= c.response_cost and bool(b.units))
        for u in list(a.units):
            if not u.silenced: self._effects(actor, u.uid, u.spec, 'end')
        if min(a.hp, b.hp) <= 0: return
        if c.soul == 'INTEGRITY' and a.turn > 1 and a.spent > a.previous_spent:
            a.cash += 1; a.bonus_gold += 1
        if c.soul == 'KINDNESS' and a.turn >= 3:
            n = min(1, 30 - a.hp); a.hp += n; a.healing += n
            if any(u.h < u.max_h for u in a.units):
                a.units = [replace(u, h=min(u.max_h, u.h + 1)) for u in a.units]
            elif a.units:
                a.units[-1] = replace(a.units[-1], h=a.units[-1].h + 1, max_h=a.units[-1].max_h + 1)
        for side, player in enumerate(self.players):
            player.units = [replace(u, haste=False, charge=False if side == actor else u.charge) for u in player.units]
        a.previous_spent = a.spent
        for p in self.players:
            if p.cash != 1 + p.income + p.bonus_gold - p.total_spent:
                raise ValueError('Gold conservation failed')
            if len(p.deck) + len(p.hand) + p.played + p.burned != 25:
                raise ValueError('Physical card conservation failed')
            if len(p.hand) > c.hand_cap or len(p.units) > c.slots:
                raise ValueError('Capacity violation')
        self.event(actor, 'end', hp=a.hp, enemy_hp=b.hp, cash=a.cash)

    def run(self):
        result = super().run()
        result['decision_seconds'] = self.usage
        if self.recorder is not None: self.recorder.finish(result)
        return result


def legacy_view(obs):
    """Reconstruct ONLY observed fields for the retained fixed policies."""
    cfg = Config(**obs['config'])
    def unit(u): return bridge.Unit(u['uid'], u['kind'], u['a'], u['h'], u['max_h'], u['ready'])
    hand = tuple(bridge.Card(h['uid'], 'candidate' if h.get('candidate') else h['role']) for h in obs['hand'])
    return bridge.View(hand, tuple(map(unit, obs['own'])), tuple(map(unit, obs['enemy'])),
        obs['hp'], obs['enemy_hp'], obs['cash'], obs['enemy_cash'], obs['turn'], obs['enemy_turn'],
        obs['seat'], obs['deck_count'], obs['enemy_response_unseen'], cfg)
