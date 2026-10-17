"""Four-phase, paid physical combat. This is a declared finite model, not server code."""
from dataclasses import dataclass, replace, asdict
from .rules import Card, Effect, UnknownMechanic, compile_card, compile_observed_card

VERSION = 'finite_physical0.1.0'

CONFIG_INTEGERS = {'own_player_max_hp','enemy_player_max_hp','node_limit',
    'next_own_income','next_own_gold_income','next_enemy_income','next_opponent_gold_income',
    'next_own_draw_count','next_natural_draw_count','next_enemy_draw_count','next_opponent_natural_draw_count',
    'own_player_hp','enemy_player_hp','gold_before_play','opponent_gold_before_response'}
CONFIG_ARRAY_INTEGERS = {'hand_ids','opponent_hand_ids','hand_costs','opponent_hand_costs',
    'own_deck_ids','known_own_deck_ids','enemy_deck_ids','known_enemy_deck_ids','opponent_deck_ids'}
CONFIG_ALLOWED = CONFIG_INTEGERS | CONFIG_ARRAY_INTEGERS | {
    'horizon','income_by_phase','draw_by_phase','hand_generated','opponent_hand_generated',
    'ally_bodies_before_play','enemy_bodies'}


def _require_integer(value, field):
    if type(value) is not int:
        raise UnknownMechanic(f'{field}: exact integer required, received {value!r}')
    return value


@dataclass(frozen=True)
class HandCard:
    key: str
    card_id: int
    cost: int
    generated: bool = False


@dataclass(frozen=True)
class Body:
    key: str
    card_id: int | None
    attack: int
    health: int
    max_health: int
    statuses: tuple = ()
    ready: bool = False
    fresh: bool = False
    silenced: bool = False
    paralyzed_until: int = -1
    attacked: bool = False
    printed_cost: int | None = None
    base_cost: int | None = None
    current_cost: int | None = None
    max_health_known: bool = True

    def status(self, name):
        return dict(self.statuses).get(name, 0)


@dataclass(frozen=True)
class State:
    phase: int
    own_hp: int
    enemy_hp: int
    own_gold: int
    enemy_gold: int
    own_hand: tuple
    enemy_hand: tuple
    own_board: tuple
    enemy_board: tuple
    own_deck: tuple = ()
    enemy_deck: tuple = ()
    own_deployments: int = 0
    enemy_deployments: int = 0
    own_draws: int = 0
    enemy_draws: int = 0
    own_fatigue: int = 0
    enemy_fatigue: int = 0
    own_burned: int = 0
    enemy_burned: int = 0
    pending_delays: tuple = ()
    own_generated: int = 0
    enemy_generated: int = 0


class Game:
    def __init__(self, cards, config):
        if set(config)-CONFIG_ALLOWED:
            raise UnknownMechanic('unsupported configuration fields: '+', '.join(sorted(set(config)-CONFIG_ALLOWED)))
        for key in CONFIG_INTEGERS & set(config): _require_integer(config[key],key)
        for key in CONFIG_ARRAY_INTEGERS & set(config):
            for value in config[key]: _require_integer(value,key)
        for key in ('income_by_phase','draw_by_phase'):
            for phase,value in config.get(key,{}).items():
                if type(phase) is not int and phase not in ('1','2','3'):
                    raise UnknownMechanic(key+': phase key must be 1, 2 or 3')
                _require_integer(value,key)
        for key in ('ally_bodies_before_play','enemy_bodies'):
            for raw in config.get(key,()):
                for field in ('card_id','id','attack','health','max_health','paralyzed_until',
                              'printed_cost','base_cost','current_cost'):
                    if field in raw: _require_integer(raw[field],key+'.'+field)
        self.config = dict(config)
        raw_cards = cards.values() if isinstance(cards, dict) else cards
        self.raw_cards = {int(c['id']): c for c in raw_cards}
        self.cards = {}
        self.own_max_hp = int(config.get('own_player_max_hp', 30))
        self.enemy_max_hp = int(config.get('enemy_player_max_hp', 30))
        self.node_limit = int(config.get('node_limit', 20000))
        if config.get('horizon', 'next_enemy_attack') != 'next_enemy_attack':
            raise UnknownMechanic('only next_enemy_attack four-phase horizon supported')
        self.incomes = {1: 0, 2: int(config.get('next_own_income', config.get('next_own_gold_income', 0))),
                        3: int(config.get('next_enemy_income', config.get('next_opponent_gold_income', 0)))}
        self.draws = {1: 0, 2: int(config.get('next_own_draw_count', config.get('next_natural_draw_count', 0))),
                      3: int(config.get('next_enemy_draw_count', config.get('next_opponent_natural_draw_count', 0)))}
        for k, v in config.get('income_by_phase', {}).items(): self.incomes[int(k)] = int(v)
        for k, v in config.get('draw_by_phase', {}).items(): self.draws[int(k)] = int(v)
        if any(k not in (1, 2, 3) or v < 0 for k, v in self.incomes.items()) or any(k not in (1, 2, 3) or v < 0 for k, v in self.draws.items()):
            raise UnknownMechanic('invalid boundary resources')
        self.own_deck = self._deck(config, 'own')
        self.enemy_deck = self._deck(config, 'enemy')
        oh = self._hand(config.get('hand_ids', ()), 'own', config.get('hand_costs'),config.get('hand_generated'))
        eh = self._hand(config.get('opponent_hand_ids', ()), 'enemy', config.get('opponent_hand_costs'),config.get('opponent_hand_generated'))
        ob = self._board(config.get('ally_bodies_before_play', ()), 'own')
        eb = self._board(config.get('enemy_bodies', ()), 'enemy')
        if len(oh) > 7 or len(eh) > 7 or len(ob) > 4 or len(eb) > 4:
            raise UnknownMechanic('root exceeds seven hand / four body capacity')
        for cid in self.own_deck + self.enemy_deck: self.card(cid)
        self._root = State(0, int(config.get('own_player_hp', 30)),
                           int(config.get('enemy_player_hp', 30)), int(config.get('gold_before_play', 0)),
                           int(config.get('opponent_gold_before_response', 0)), oh, eh, ob, eb,
                           self.own_deck, self.enemy_deck)
        if not (0 <= self._root.own_hp <= self.own_max_hp and 0 <= self._root.enemy_hp <= self.enemy_max_hp):
            raise UnknownMechanic('root HP outside explicit ceiling')
        if min(self._root.own_gold, self._root.enemy_gold) < 0:
            raise UnknownMechanic('negative root gold')
        if len({b.key for b in ob+eb}) != len(ob)+len(eb):
            raise UnknownMechanic('body keys must be globally unique')

    def _deck(self, config, side):
        for key in (side + '_deck_ids', 'known_' + side + '_deck_ids', 'opponent_deck_ids' if side=='enemy' else 'own_deck_ids'):
            if key in config:
                return tuple(int(x) for x in config[key])
        # Missing library is only certified when no draw is requested.
        phases = (2,) if side == 'own' else (1, 3)
        if any(self.draws.get(p, 0) for p in phases):
            raise UnknownMechanic(f'{side}: natural draw requires explicit ordered deck (empty allowed)')
        return ()

    def card(self, cid):
        cid = int(cid)
        if cid not in self.cards:
            if cid not in self.raw_cards: raise UnknownMechanic(f'unknown card id {cid}')
            self.cards[cid] = compile_card(self.raw_cards[cid])
        return self.cards[cid]

    def _hand(self, ids, side, costs=None,generated=None):
        ids = tuple(ids)
        if costs is not None and len(costs)!=len(ids): raise UnknownMechanic('hand costs length mismatch')
        if generated is not None and (len(generated)!=len(ids) or any(type(x) is not bool for x in generated)):
            raise UnknownMechanic('hand Generated flags must be exact boolean array matching physical hand')
        result = []
        for i, cid in enumerate(ids):
            cid = int(cid); card=self.card(cid)
            cost=card.cost if costs is None else int(costs[i])
            if cost<0: raise UnknownMechanic('negative hand cost')
            result.append(HandCard(f'{side}:hand:{i}', cid,cost,False if generated is None else generated[i]))
        return tuple(result)

    def _board(self, raw_bodies, side):
        result = []
        for i, raw in enumerate(raw_bodies):
            cid = raw.get('card_id', raw.get('id'))
            card = compile_observed_card(self.raw_cards[int(cid)]) if cid is not None else None
            attack = int(raw.get('attack', card.attack if card else 0))
            health = int(raw.get('health', card.health if card else 1))
            maximum = int(raw.get('max_health', max(health, card.health if card else health)))
            statuses = raw.get('statuses', card.statuses if card and not raw.get('silenced',False) else ())
            if isinstance(statuses, dict): statuses = tuple(statuses.items())
            if statuses and isinstance(statuses[0], str): statuses = tuple((s, 1) for s in statuses)
            statuses = tuple(sorted(tuple(s) for s in statuses))
            if any(s not in ('Taunt','Haste','Charge','Armor','Dodge','Disarmed') or int(n) <= 0 for s,n in statuses):
                raise UnknownMechanic('unsupported observed status')
            if health <= 0 or attack < 0 or maximum < health: raise UnknownMechanic('invalid observed body')
            result.append(Body(raw.get('key', f'{side}:observed:{i}'), card.id if card else None,
                               attack, health, maximum, statuses, bool(raw.get('ready', side == 'own')),
                               bool(raw.get('fresh', False)), bool(raw.get('silenced', False)),
                               int(raw.get('paralyzed_until', -1)),False,
                               int(raw.get('printed_cost',card.cost)) if card else raw.get('printed_cost'),
                               int(raw['base_cost']) if 'base_cost' in raw else None,
                               int(raw['current_cost']) if 'current_cost' in raw else None,
                               'max_health' in raw))
        keys = [b.key for b in result]
        if len(keys) != len(set(keys)) or any(k in ('own:hero','enemy:hero') for k in keys):
            raise UnknownMechanic('duplicate/reserved body keys')
        return tuple(result)

    def root(self): return self._root
    def owner(self, state): return 'own' if state.phase % 2 == 0 else 'enemy'
    def finished(self, state): return state.phase >= 4 or state.own_hp <= 0 or state.enemy_hp <= 0
    def hp(self, state): return state.own_hp

    def _sides(self, state):
        side = self.owner(state); other = 'enemy' if side == 'own' else 'own'
        return side, other

    def _replace_body(self, state, side, body):
        key = side + '_board'
        return replace(state, **{key: tuple(body if b.key == body.key else b for b in getattr(state, key))})

    def _find(self, state, key):
        for side in ('own','enemy'):
            for b in getattr(state, side + '_board'):
                if b.key == key: return side, b
        raise KeyError(key)

    def _clean(self, state):
        return replace(state, own_board=tuple(b for b in state.own_board if b.health > 0),
                       enemy_board=tuple(b for b in state.enemy_board if b.health > 0),
                       own_hp=max(0, state.own_hp), enemy_hp=max(0, state.enemy_hp))

    def _damage(self, state, target, amount, source_body=None):
        if amount <= 0: return state
        if target.endswith(':hero'):
            side = target.split(':')[0]
            return replace(state, **{side+'_hp': max(0, getattr(state, side+'_hp') - amount)})
        side, b = self._find(state, target)
        if b.status('Dodge'):
            statuses = dict(b.statuses); statuses['Dodge'] -= 1
            if not statuses['Dodge']: del statuses['Dodge']
            return self._replace_body(state, side, replace(b, statuses=tuple(sorted(statuses.items()))))
        reduction=bool(b.status('Armor'))
        if b.card_id is not None and not b.silenced:
            card=compile_observed_card(self.raw_cards[b.card_id])
            if card.damage_cost_limit is not None and source_body is not None:
                costs=(source_body.printed_cost,source_body.base_cost,source_body.current_cost)
                if None in costs: raise UnknownMechanic('cost-conditional defense needs all source COST facts')
                predicates={int(c)<=card.damage_cost_limit for c in costs}
                if len(predicates)!=1: raise UnknownMechanic('printed/base/current COST predicates disagree')
                reduction+=int(next(iter(predicates)))
        return self._replace_body(state, side, replace(b, health=b.health - max(0, amount - reduction)))

    def _targets(self, state, side, source, effect):
        other = 'enemy' if side == 'own' else 'own'
        mine = [b.key for b in getattr(state, side+'_board')]
        theirs = [b.key for b in getattr(state, other+'_board')]
        scope = effect.scope
        if scope == 'self': return [source]
        if scope == 'self_hero': return [side+':hero']
        if scope == 'ally': return [t for t in mine if t != source]
        if scope == 'enemy': return theirs
        if scope == 'monster': return [t for t in mine+theirs if t != source]
        if scope == 'any': return [side+':hero',other+':hero']+[t for t in mine+theirs if t != source]
        if scope.startswith('all_'): return [None]
        raise UnknownMechanic('unknown effect scope')

    def _effect(self, state, side, source, effect, target=None):
        source_body=next((b for b in state.own_board+state.enemy_board if b.key==source),None)
        if effect.scope.startswith('all_'):
            targets = [b.key for b in state.own_board+state.enemy_board]
            if effect.scope == 'all_other': targets = [t for t in targets if t != source]
            if effect.scope == 'all_enemy':
                other = 'enemy' if side == 'own' else 'own'
                targets = [b.key for b in getattr(state, other+'_board')]
            for t in targets: state = self._damage(state, t, effect.amount,source_body)
            return self._clean(state)
        target = target if target is not None else self._targets(state, side, source, effect)[0]
        if effect.kind == 'damage': return self._clean(self._damage(state, target, effect.amount,source_body))
        if target.endswith(':hero'):
            ts = target.split(':')[0]
            maximum = self.own_max_hp if ts == 'own' else self.enemy_max_hp
            return replace(state, **{ts+'_hp': min(maximum, getattr(state, ts+'_hp') + effect.amount)})
        ts, body = self._find(state, target)
        if effect.kind == 'heal':
            if not body.max_health_known: raise UnknownMechanic('body healing needs explicit maximum HP')
            body = replace(body, health=min(body.max_health, body.health+effect.amount))
        elif effect.kind in ('buff','worsening'):
            body = replace(body, attack=max(0,body.attack+effect.amount), health=body.health+effect.second,
                           max_health=max(1,body.max_health+effect.second))
        elif effect.kind == 'kill': body = replace(body, health=0)
        elif effect.kind == 'silence':
            if body.card_id is None:
                raise UnknownMechanic('Silence stat cleanup needs printed identity and known maximum HP')
            raw=self.raw_cards[body.card_id]
            if raw.get('rarity') in ('DT','DETERMINATION'):
                return state
            printed=compile_observed_card(raw)
            if not body.max_health_known or body.attack!=printed.attack or body.max_health!=printed.health:
                raise UnknownMechanic('Silence of modified/unknown stats has unverified cleanup semantics')
            body = replace(body, statuses=(), silenced=True, paralyzed_until=-1)
        elif effect.kind == 'paralyze':
            next_owner_phase = state.phase+2 if ts == self.owner(state) else state.phase+1
            body = replace(body, paralyzed_until=next_owner_phase)
        else: raise UnknownMechanic('unsupported transition '+effect.kind)
        return self._clean(self._replace_body(state, ts, body))

    def _end(self, state):
        side, _ = self._sides(state)
        for source_side,target,cid,generated in state.pending_delays:
            if source_side!=side: raise UnknownMechanic('delay belongs to a different turn')
            still_living=any(b.key==target for b in state.own_board+state.enemy_board)
            if not still_living and not generated:
                hand=getattr(state,side+'_hand')
                if len(hand)>=7:
                    raise UnknownMechanic('full-hand Add rule not established for Worsening')
                count=getattr(state,side+'_generated')
                product=HandCard(f'{side}:generated:{count}',cid,self.card(cid).cost,True)
                state=replace(state,**{side+'_hand':hand+(product,),side+'_generated':count+1})
        state=replace(state,pending_delays=())
        for b in getattr(state, side+'_board'):
            if b.card_id is not None and not b.silenced:
                effect = compile_observed_card(self.raw_cards[b.card_id]).end
                if effect: state = self._effect(state, side, b.key, effect)
        # Charge expires at its owner's turn end; Haste at every turn end.
        for board_side in ('own','enemy'):
            cleaned=tuple(replace(b,statuses=tuple((s,n) for s,n in b.statuses
                          if s!='Haste' and not (s=='Charge' and board_side==side)))
                          for b in getattr(state,board_side+'_board'))
            state=replace(state,**{board_side+'_board':cleaned})
        state = replace(state, phase=state.phase+1)
        if self.finished(state): return state
        side, _ = self._sides(state)
        state = replace(state, **{side+'_gold':getattr(state,side+'_gold')+self.incomes.get(state.phase,0)})
        # Supported start callbacks touch only source ATK or owner's hero HP;
        # neither can interact with draws, so no server ordering is assumed.
        board = tuple(replace(b, ready=True, fresh=False, attacked=False) for b in getattr(state,side+'_board'))
        state = replace(state, **{side+'_board':board})
        for b in board:
            if b.card_id is not None and not b.silenced:
                effect = compile_observed_card(self.raw_cards[b.card_id]).start
                if effect:
                    if effect.kind=='heal' and self.draws.get(state.phase,0)>len(getattr(state,side+'_deck')):
                        raise UnknownMechanic('healing callback/fatigue boundary order undeclared')
                    state = self._effect(state, side, b.key, effect)
        for _ in range(self.draws.get(state.phase,0)):
            if self.finished(state): break
            deck = getattr(state,side+'_deck'); hand = getattr(state,side+'_hand')
            if deck:
                count = getattr(state,side+'_draws')
                changes = {side+'_deck':deck[1:],side+'_draws':count+1}
                if len(hand)<7: changes[side+'_hand']=hand+(HandCard(f'{side}:draw:{count}',deck[0],self.card(deck[0]).cost),)
                else: changes[side+'_burned']=getattr(state,side+'_burned')+1
                state=replace(state,**changes)
            else:
                fatigue=getattr(state,side+'_fatigue')+1
                state=replace(state,**{side+'_fatigue':fatigue,side+'_hp':max(0,getattr(state,side+'_hp')-fatigue)})
        return state

    def actions(self, state):
        if self.finished(state): return []
        side, other = self._sides(state)
        board, targets = getattr(state,side+'_board'), getattr(state,other+'_board')
        result = [(('end',),self._end(state))]
        taunts=[b for b in targets if b.status('Taunt')]
        for b in board:
            if not b.ready or b.attacked or b.attack <= 0 or b.status('Disarmed') or b.paralyzed_until>=state.phase: continue
            if b.fresh and not (b.status('Charge') or b.status('Haste')): continue
            legal=[t.key for t in (taunts or targets)]
            if not taunts and (not b.fresh or b.status('Charge')): legal.append(other+':hero')
            for target in legal:
                child=self._replace_body(state,side,replace(b,ready=False,attacked=True))
                defender=None if target.endswith(':hero') else self._find(state,target)[1]
                retaliation=0 if defender is None else defender.attack
                child=self._damage(child,target,b.attack,b)
                if retaliation: child=self._damage(child,b.key,retaliation,defender)
                result.append((('attack',b.key,target),self._clean(child)))
        for h in getattr(state,side+'_hand'):
            card=self.card(h.card_id)
            if h.cost>getattr(state,side+'_gold') or (card.card_type=='monster' and len(board)>=4): continue
            deployment=getattr(state,side+'_deployments')
            source=f'{side}:deployed:{deployment}' if card.card_type=='monster' else side+':spell'
            base=replace(state,**{side+'_gold':getattr(state,side+'_gold')-h.cost,
                                 side+'_hand':tuple(x for x in getattr(state,side+'_hand') if x.key!=h.key)})
            if card.card_type=='monster':
                b=Body(source,card.id,card.attack,card.health,card.health,card.statuses,True,True,
                       printed_cost=card.cost,base_cost=card.cost,current_cost=h.cost)
                base=replace(base,**{side+'_board':board+(b,),side+'_deployments':deployment+1})
            choices=self._targets(base,side,source,card.magic) if card.magic else [None]
            if card.card_type=='monster' and not choices:
                raise UnknownMechanic('no mandatory Magic target: empty deployment/fizzle rule unverified')
            # A mandatory targeted Magic cannot be silently skipped when no legal target exists.
            for target in choices:
                child=self._effect(base,side,source,card.magic,target) if card.magic else base
                if card.magic and card.magic.kind=='worsening':
                    child=replace(child,pending_delays=child.pending_delays+((side,target,card.id,h.generated),))
                result.append((('play',h.key,target),child))
        return result

    def observation(self, state):
        # No hidden physical hand/deck identity, nor hidden physical index survives.
        public_delays=tuple((side,target,cid,generated if side=='own' else None)
                            for side,target,cid,generated in state.pending_delays)
        return (state.phase,state.own_hp,state.enemy_hp,state.own_gold,state.enemy_gold,
                state.own_hand,len(state.enemy_hand),state.own_board,state.enemy_board,
                state.own_deck,len(state.enemy_deck),state.own_deployments,state.enemy_deployments,
                state.own_draws,state.enemy_draws,state.own_fatigue,state.enemy_fatigue,
                state.own_burned,state.enemy_burned,public_delays,
                state.own_generated,state.enemy_generated)

    def action_observation(self, action, state, child):
        if action[0]!='play': return action
        side=self.owner(state)
        hand=getattr(state,side+'_hand')
        cid=next(h.card_id for h in hand if h.key==action[1])
        return ('play',cid,action[2],getattr(state,side+'_deployments') if self.card(cid).card_type=='monster' else None)

    def describe_action(self, action):
        return {'kind':action[0],'arguments':list(action[1:])}

    def goal(self, state, constraints):
        aliases={'min_own_player_hp':'min_own_hp','max_enemy_player_hp':'max_enemy_hp',
                 'min_own_living_count':'min_own_living','max_enemy_living_count':'max_enemy_living'}
        constraints={aliases.get(k,k):v for k,v in constraints.items()}
        allowed={'min_own_hp','max_enemy_hp','min_own_living','min_enemy_living','max_enemy_living',
                 'min_own_attack','min_own_board_hp','min_own_body_attack','min_own_body_health'}
        if set(constraints)-allowed: raise UnknownMechanic('unsupported goal constraints')
        return (state.own_hp>=constraints.get('min_own_hp',0)
                and state.enemy_hp<=constraints.get('max_enemy_hp',self.enemy_max_hp)
                and len(state.own_board)>=constraints.get('min_own_living',0)
                and len(state.enemy_board)>=constraints.get('min_enemy_living',0)
                and len(state.enemy_board)<=constraints.get('max_enemy_living',4)
                and (not {'min_own_body_attack','min_own_body_health'}.intersection(constraints)
                     or any(b.attack>=constraints.get('min_own_body_attack',0)
                            and b.health>=constraints.get('min_own_body_health',0) for b in state.own_board))
                and sum(b.attack for b in state.own_board)>=constraints.get('min_own_attack',0)
                and sum(b.health for b in state.own_board)>=constraints.get('min_own_board_hp',0))
