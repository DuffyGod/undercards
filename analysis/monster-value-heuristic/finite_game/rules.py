"""Strict, deliberately small full-text compiler. No unsupported-text body fallback."""
from dataclasses import dataclass
import re


class UnknownMechanic(ValueError):
    """A transition cannot be certified from the explicit supported rules."""


@dataclass(frozen=True)
class Effect:
    kind: str
    scope: str
    amount: int = 0
    second: int = 0


@dataclass(frozen=True)
class Card:
    id: int
    name: str
    cost: int
    attack: int
    health: int
    card_type: str
    statuses: tuple
    magic: Effect | None = None
    start: Effect | None = None
    end: Effect | None = None
    damage_cost_limit: int | None = None


STATUSES = {'Taunt', 'Haste', 'Charge', 'Armor', 'Dodge', 'Disarmed'}
TARGETS = {'ALL': 'any', 'MONSTER': 'monster', 'ALLY_MONSTER': 'ally',
           'ENEMY_MONSTER': 'enemy'}


def _effect(text, metadata_target=None):
    m = re.fullmatch(r'Deal (\d+) DMG to a monster or you\.', text)
    if m:
        return Effect('damage', 'monster_or_owner', int(m[1]))
    if text == "Give a monster ATK -1/HP -2. Delay: If it's dead and this is non-Generated, add a Worsening [#86] to your hand.":
        return Effect('worsening', 'monster', -1, -2)
    for pattern in (r'Deal (\d+) DMG\.', r'Deal DMG (\d+)\.'):
        m = re.fullmatch(pattern, text)
        if m and metadata_target in TARGETS:
            return Effect('damage', TARGETS[metadata_target], int(m[1]))
    m = re.fullmatch(r'Heal (\d+) HP\.', text)
    if m and metadata_target in TARGETS:
        return Effect('heal', TARGETS[metadata_target], int(m[1]))
    m = re.fullmatch(r'Heal (\d+) HP to you\.', text)
    if m:
        return Effect('heal', 'self_hero', int(m[1]))
    m = re.fullmatch(r'Gain \+(\d+) ATK\.', text)
    if m:
        return Effect('buff', 'self', int(m[1]), 0)
    m = re.fullmatch(r'Give (a monster|an ally monster|an enemy monster) ([+-]\d+) (ATK|HP)\.', text)
    if m:
        scope = {'a monster': 'monster', 'an ally monster': 'ally', 'an enemy monster': 'enemy'}[m[1]]
        return Effect('buff', scope, int(m[2]) if m[3] == 'ATK' else 0,
                      int(m[2]) if m[3] == 'HP' else 0)
    m = re.fullmatch(r'Give (a monster|an ally monster|an enemy monster) ATK ([+-]\d+)/HP ([+-]\d+)\.', text)
    if m:
        return Effect('buff', {'a monster':'monster','an ally monster':'ally','an enemy monster':'enemy'}[m[1]], int(m[2]), int(m[3]))
    m = re.fullmatch(r'(Silence|Paralyze|Kill) (a monster|an ally monster|an enemy monster)\.', text)
    if m:
        return Effect(m[1].lower(), {'a monster':'monster','an ally monster':'ally','an enemy monster':'enemy'}[m[2]])
    m = re.fullmatch(r'Deal (\d+) DMG to all (other monsters|enemy monsters|monsters)\.', text)
    if m:
        return Effect('damage', {'other monsters':'all_other','enemy monsters':'all_enemy','monsters':'all_monsters'}[m[2]], int(m[1]))
    raise UnknownMechanic('unsupported effect: ' + repr(text))


def compile_card(raw):
    cid = int(raw['id'])
    raw_type = raw.get('card_type', 'monster')
    if not isinstance(raw_type, str):
        raise UnknownMechanic(f'card {cid}: missing card type')
    ctype = raw_type.lower()
    if ctype not in ('monster', 'spell'):
        raise UnknownMechanic(f'card {cid}: unsupported card type {ctype}')
    text = raw.get('effect_readable', raw.get('effect', ''))
    if not isinstance(text, str):
        raise UnknownMechanic(f'card {cid}: no readable complete effect')
    statuses = []
    while True:
        m = re.match(r'^(Taunt|Haste|Charge|Armor|Dodge|Disarmed)(?: \((\d+)\))?\.\s*', text)
        if not m:
            break
        if m[1] != 'Dodge' and m[2] is not None:
            raise UnknownMechanic('unsupported counted status ' + m[0])
        statuses.append((m[1], int(m[2] or 1)))
        text = text[m.end():]
    # Metadata is a consistency constraint, never a substitute for complete text.
    metadata = tuple(sorted((s['name'], int(s.get('counter', 1))) for s in raw.get('base_statuses', ())))
    if metadata and metadata != tuple(sorted(statuses)):
        raise UnknownMechanic(f'card {cid}: status text/metadata mismatch')
    magic = start = end = None
    damage_cost_limit = None
    if text:
        m = re.fullmatch(r'This takes 1 less DMG from monsters costing (\d+) or less GOLD\.', text)
        if m:
            damage_cost_limit = int(m[1])
        elif text.startswith('Magic: '):
            magic = _effect(text[7:], raw.get('target'))
        elif text.startswith('Turn start: '):
            start = _effect(text[12:], raw.get('target'))
            if start.scope not in ('self', 'self_hero'):
                raise UnknownMechanic('only deterministic self start callbacks are supported')
        elif text.startswith('Turn end: '):
            end = _effect(text[10:], raw.get('target'))
            if end.scope != 'self_hero' or end.kind != 'heal':
                raise UnknownMechanic('only deterministic hero healing end callback supported')
        elif ctype == 'spell':
            magic = _effect(text, raw.get('target'))
        else:
            raise UnknownMechanic(f'card {cid}: unsupported full text {text!r}')
    if ctype == 'spell' and (statuses or magic is None):
        raise UnknownMechanic(f'card {cid}: spell lacks certified effect')
    cost = int(raw['cost'])
    attack, health = int(raw.get('attack') or 0), int(raw.get('health') or 0)
    if cost < 0 or attack < 0 or (ctype == 'monster' and health <= 0):
        raise UnknownMechanic(f'card {cid}: invalid printed stats')
    return Card(cid, raw.get('name', str(cid)), cost, attack, health, ctype,
                tuple(sorted(statuses)), magic, start, end, damage_cost_limit)


def compile_observed_card(raw):
    """Completed Magic is historical, but only this explicit no-pending template is excused."""
    try:
        return compile_card(raw)
    except UnknownMechanic:
        text = raw.get('effect_readable', '')
        if re.fullmatch(r'Magic: Look at \d+ random monsters and choose one\. Add it to your hand\.', text):
            clone = dict(raw, effect_readable='')
            return compile_card(clone)
        raise
