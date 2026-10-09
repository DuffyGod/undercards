"""Small exact resource probes, not a game simulator or empirical match data."""
import hashlib
import json
from collections import Counter
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / 'skills/undercards/references/snapshot.json'


def income(turn, first):
    return min(turn, 10) + int(not first and turn in (1, 3, 5, 7, 9))


def access_probability(deck_size, usable_count, seen):
    if not 0 <= usable_count <= deck_size or not 0 <= seen <= deck_size:
        raise ValueError('Invalid finite-population sample')
    misses = comb(deck_size - usable_count, seen) if seen <= deck_size - usable_count else 0
    return 1 - misses / comb(deck_size, seen)


def main():
    raw = SNAPSHOT.read_bytes()
    cards = json.loads(raw)['cards']
    plain = [c for c in cards if c['card_type'] == 'monster'
             and c['pool_category'] == 'ordinary_non_token'
             and not c['effect_readable'].strip()]
    results = {
        'scope': 'Exact arithmetic under snapshot rules; not observed match statistics.',
        'snapshot_sha256': hashlib.sha256(raw).hexdigest(),
        'plain_cards': [{k: c[k] for k in ('id', 'name', 'cost', 'attack', 'health')} for c in plain],
        'plain_counts_by_cost': dict(sorted(Counter(c['cost'] for c in plain).items())),
        'income': {},
        'access': [],
        'assumptions': [
            'Starting balance 1; no extra income or expenditure in unspent_balance.',
            'Access is a uniform without-replacement sample of n distinct deck positions.',
            'No mulligan, tutor, burn, extra draw or identity-dependent sampling.',
            'Seen n is explicit; no unverified opening draw rule maps n to a turn.',
            'Usable category is defined by the caller; access does not prove legal/useful play.'
        ],
    }
    for first in (True, False):
        incomes = [income(t, first) for t in range(1, 7)]
        results['income']['first' if first else 'second'] = {
            'new_income': incomes,
            'unspent_balance': [1 + sum(incomes[:t]) for t in range(1, 7)],
        }
    for seen in (4, 5, 6):
        for usable in (6, 8, 10):
            results['access'].append({'deck_size': 25, 'usable_count': usable,
                                      'seen': seen, 'p_at_least_one': access_probability(25, usable, seen)})
    out = Path(__file__).with_name('resource-probes.json')
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(out), 'plain_count': len(plain),
                      'plain_4_to_8_count': sum(4 <= c['cost'] <= 8 for c in plain)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
