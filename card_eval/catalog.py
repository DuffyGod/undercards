"""Card/deck preflight. Unknown text remains unknown, not a blank body."""
from dataclasses import asdict
from collections import Counter
from functools import lru_cache
from pathlib import Path
import json, hashlib
from .legacy import ROOT, rules

Spec, Effect, UnsupportedRule = rules.Spec, rules.Effect, rules.UnsupportedRule


@lru_cache(maxsize=1)
def snapshot():
    bundled = Path(__file__).resolve().parent / 'data/snapshot.json'
    source = bundled if bundled.exists() else ROOT / 'skills/undercards/references/snapshot.json'
    data = json.loads(source.read_text())
    return {c['id']: c for c in data['cards']}


def semantic_key(spec):
    return hashlib.sha256(json.dumps(spec.semantic(), sort_keys=True).encode()).hexdigest()


class InputError(ValueError):
    def __init__(self, issues):
        self.issues = issues
        super().__init__('; '.join(i['message'] for i in issues))


def resolve(value):
    if isinstance(value, Spec): return value
    if isinstance(value, str) and value.isdecimal(): value = int(value)
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        cards = snapshot()
        card = cards.get(value) if type(value) is int else next((c for c in cards.values() if c['name'].casefold() == value.casefold()), None)
        if card is None: raise ValueError('Unknown card: ' + str(value))
        return rules.compile_text(card)
    if not isinstance(value, dict): raise ValueError('Use a card name, numeric ID, or a semantic descriptor')
    required = {'name', 'cost', 'attack', 'health'}
    if not required <= value.keys(): raise ValueError('Semantic card needs name, cost, attack and health')
    if set(value) - (required | {'keywords', 'effects'}):
        raise ValueError('Unknown semantic card fields; real IDs must be looked up rather than overridden')
    if not isinstance(value['name'], str) or not value['name'].strip(): raise ValueError('Nonempty card name required')
    return Spec(value['name'], value['cost'], value['attack'], value['health'],
                tuple(tuple(x) for x in value.get('keywords', [])), tuple(Effect(**e) for e in value.get('effects', [])))


def deck(values, path='deck'):
    issues = []; output = []
    if not isinstance(values, list) or len(values) != 25:
        raise InputError([dict(path=path, code='deck_size', message='A deck must contain exactly25 explicit cards')])
    for i, value in enumerate(values):
        try: output.append(resolve(value))
        except (ValueError, TypeError, KeyError) as exc:
            issues.append(dict(path=f'{path}[{i}]', card=value if isinstance(value, (str, int)) else value.get('name') if isinstance(value, dict) else None,
                               code='unsupported_or_invalid_card', message=str(exc)))
    if issues: raise InputError(issues)
    count = Counter(s.card_id if s.card_id is not None else s.name for s in output)
    for spec in output:
        limit = {'BASE': 3, 'COMMON': 3, 'RARE': 3, 'EPIC': 2, 'LEGENDARY': 1}.get(snapshot()[spec.card_id]['rarity'], 1) if spec.card_id is not None else 3
        key = spec.card_id if spec.card_id is not None else spec.name
        if count[key] > limit:
            issues.append(dict(path=path, code='copy_limit', message=f'{spec.name}: {count[key]} copies exceeds {limit}'))
            count[key] = 0
    if issues: raise InputError(issues)
    return tuple(output)


def coverage():
    mapped = []; rejected = []
    for card in snapshot().values():
        if card['pool_category'] != 'ordinary_non_token': continue
        try: mapped.append(asdict(resolve(card['id'])))
        except (ValueError, TypeError) as exc:
            rejected.append(dict(id=card['id'], name=card['name'], reason=str(exc)))
    return dict(snapshot_date='2026-10-05', supported=mapped, unsupported=rejected,
                meaning='Whole supported text grammar; not a claim of current-server completeness')
