"""Composable, deliberately restricted rules; no card IDs enter execution.

The silence treatment of modified stats is an explicit model parameter. It is
not a ruling about the live server. Death triggers and generated cards remain
unsupported instead of becoming blank bodies.
"""
from dataclasses import dataclass, asdict, replace
import re

OPS = ('draw', 'heal', 'damage', 'kill', 'silence', 'buff', 'gold')
TRIGGERS = ('play', 'start', 'end')
SCOPES = ('owner', 'opponent', 'self', 'enemy', 'monster', 'all_enemy', 'highest_enemy')
KEYWORDS = ('haste', 'charge', 'taunt', 'armor', 'dodge')


class UnsupportedRule(ValueError):
    pass


@dataclass(frozen=True)
class Effect:
    trigger: str
    op: str
    scope: str
    amount: int = 0
    health: int = 0

    def __post_init__(self):
        if self.trigger not in TRIGGERS or self.op not in OPS or self.scope not in SCOPES:
            raise UnsupportedRule('Unknown trigger, operation or selector')
        if type(self.amount) is not int or type(self.health) is not int:
            raise UnsupportedRule('Effect parameters must be exact integers')
        allowed = {'draw': ('owner',), 'heal': ('owner',), 'gold': ('owner',),
                   'buff': ('self',), 'kill': ('highest_enemy',),
                   'silence': ('enemy', 'monster'),
                   'damage': ('enemy', 'monster', 'opponent', 'all_enemy', 'self')}
        if self.scope not in allowed[self.op]:
            raise UnsupportedRule('Unsupported operation/selector composition')
        if self.op != 'buff' and (self.amount < 0 or self.health):
            raise UnsupportedRule('Unsupported effect parameters')
        if self.trigger != 'play' and self.scope not in ('owner', 'self', 'opponent', 'all_enemy'):
            raise UnsupportedRule('Automatic triggers cannot acquire an undeclared chosen target')


@dataclass(frozen=True)
class Spec:
    name: str
    cost: int
    attack: int = 0
    health: int = 0
    keywords: tuple = ()
    effects: tuple = ()
    card_id: int | None = None

    def __post_init__(self):
        if any(type(x) is not int or x < 0 for x in (self.cost, self.attack, self.health)):
            raise UnsupportedRule('Nonnegative integer cost/body required')
        if any(k not in KEYWORDS or type(n) is not int or n <= 0 for k, n in self.keywords):
            raise UnsupportedRule('Unsupported keyword')
        if len(dict(self.keywords)) != len(self.keywords):
            raise UnsupportedRule('Duplicate keyword')
        if not self.health and self.keywords:
            raise UnsupportedRule('Body keywords on a spell')
        if sum(e.trigger == 'play' and e.scope in ('enemy', 'monster') for e in self.effects) > 1:
            raise UnsupportedRule('Multiple independent choices need an expanded action schema')
        if not self.health and any(e.scope == 'self' for e in self.effects):
            raise UnsupportedRule('Spell has no source body')

    def keyword(self, name):
        return dict(self.keywords).get(name, 0)

    def semantic(self):
        d = asdict(self)
        d.pop('name'); d.pop('card_id')
        return d


def compile_text(card):
    """Consume the WHOLE supported text grammar, never a recognized substring."""
    if card['card_type'] != 'monster' or card['pool_category'] != 'ordinary_non_token':
        raise UnsupportedRule('Only ordinary monster mapping in this compiler')
    if card['rarity'] in ('DT', 'DETERMINATION'):
        raise UnsupportedRule('DT innate immunity is outside this descriptor version')
    text = card['effect_readable'].strip()
    keywords = []
    while True:
        match = re.match(r'^(Haste|Charge|Taunt|Armor|Dodge \((\d+)\))\.(?:\s*|$)', text)
        if not match: break
        key = match[1].split(' ')[0].lower()
        keywords.append((key, int(match[2]) if key == 'dodge' else 1))
        text = text[match.end():]
    effects = []
    patterns = (
        (r'Magic: Draw a card\.', lambda m: Effect('play', 'draw', 'owner', 1)),
        (r'Magic: Draw (\d+) cards\.', lambda m: Effect('play', 'draw', 'owner', int(m[1]))),
        (r'Turn end: Draw a card\.', lambda m: Effect('end', 'draw', 'owner', 1)),
        (r'Magic: Silence (an enemy monster|a monster)\.',
         lambda m: Effect('play', 'silence', 'enemy' if m[1].startswith('an enemy') else 'monster')),
        (r'Turn start: Gain \+(\d+) ATK\.', lambda m: Effect('start', 'buff', 'self', int(m[1]))),
        (r'Turn (start|end): Gain ATK \+(\d+)/HP \+(\d+)\.',
         lambda m: Effect(m[1], 'buff', 'self', int(m[2]), int(m[3]))),
        (r'Turn (start|end): Heal (\d+) HP to you\.',
         lambda m: Effect(m[1], 'heal', 'owner', int(m[2]))),
        (r'Turn end: Earn GOLD (\d+)\.', lambda m: Effect('end', 'gold', 'owner', int(m[1]))),
        (r'Magic: Deal (\d+) DMG to all enemy monsters\.',
         lambda m: Effect('play', 'damage', 'all_enemy', int(m[1]))),
    )
    if text:
        for pattern, build in patterns:
            match = re.fullmatch(pattern, text)
            if match:
                effects.append(build(match)); break
        else:
            raise UnsupportedRule('Unconsumed card text: ' + text)
    serialized = {s['name'].lower(): s.get('counter', 1) for s in card['base_statuses']}
    if serialized != dict(keywords):
        raise UnsupportedRule('Printed text/status metadata disagree')
    return Spec(card['name'], card['cost'], card['attack'], card['health'],
                tuple(keywords), tuple(effects), card['id'])


def hurt(unit, amount):
    """Same per-instance Armor/Dodge primitive as the verified opening model."""
    health, dodge = damage_packet(unit.h, unit.dodge, unit.armor, amount)
    return replace(unit, h=health, dodge=dodge)


def damage_packet(health, dodge, armor, amount):
    if amount <= 0: return health, dodge
    if dodge: return health, dodge - 1
    return health - max(0, amount - int(armor)), dodge


def silence(unit, mode):
    if mode not in ('retain', 'reset', 'reject_modified'):
        raise UnsupportedRule('Unknown silence-stat assumption')
    modified = unit.a != unit.spec.attack or unit.max_h != unit.spec.health
    if modified and mode == 'reject_modified':
        raise UnsupportedRule('Silence of modified stats has no verified cleanup ruling')
    changes = dict(silenced=True, haste=False, charge=False, taunt=False, armor=False, dodge=0)
    if modified and mode == 'reset':
        changes.update(a=unit.spec.attack, max_h=unit.spec.health,
                       h=unit.spec.health - (unit.max_h - unit.h))
    # Fresh units lose immediate-attack permission if the granting keyword goes.
    if unit.fresh: changes['ready'] = False
    return replace(unit, **changes)
