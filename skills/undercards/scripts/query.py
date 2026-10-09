"""Read-only Undercards snapshot lookup; Python 3 standard library only."""
import argparse
import json
import sys
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parents[1] / 'references' / 'snapshot.json'


def normalized(value):
    return str(value or '').casefold().replace('_', '-').replace(' ', '-')


def gold_model(turn, integrity=False):
    base = min(turn, 10)
    first_total = 1 + (turn * (turn + 1) // 2 if turn <= 10 else 55 + 10 * (turn - 10))
    second_total = first_total + min(5, (turn + 1) // 2)
    if integrity and turn > 10:
        base = 11
        first_total += turn - 10
        second_total += turn - 10
    return {'own_turn': turn, 'initial_gold_each': 1,
            'first_income': base,
            'second_income': base + int(turn <= 9 and turn % 2 == 1),
            'first_unspent_balance': first_total, 'second_unspent_balance': second_total,
            'scope': 'No spending, card/artifact income or expenses, or conditional Integrity end-turn reward.',
            'evidence': ('Integrity 11G after turn 10 is a textual interpretation, not currently tested.'
                         if integrity else 'Local income tutorial + Wiki and 2025 community starting-bank example; no current server test.')}


def matches(record, args):
    if args.id is not None and record.get('id') not in args.id:
        return False
    if args.name:
        names = (record.get('name'), record.get('metadata_name'), record.get('key'), record.get('soul'))
        if not any(normalized(args.name) in normalized(v) for v in names):
            return False
    if args.text:
        effect = record.get('effect_readable', record.get('readable', record.get('effect', '')))
        if args.text.casefold() not in str(effect).casefold():
            return False
    if args.soul and normalized(record.get('soul')) != normalized(args.soul):
        return False
    if args.rarity and normalized(record.get('rarity')) != normalized(args.rarity):
        return False
    if args.type and record.get('card_type') != args.type:
        return False
    if args.pool and record.get('pool_category') != args.pool:
        return False
    if args.tribe and normalized(args.tribe) not in [normalized(v) for v in record.get('tribes') or []]:
        return False
    if args.cost_min is not None and (record.get('cost') is None or record['cost'] < args.cost_min):
        return False
    if args.cost_max is not None and (record.get('cost') is None or record['cost'] > args.cost_max):
        return False
    if args.selectable and record.get('selectable_by_observed_flags') is not True:
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=['card', 'artifact', 'keyword', 'status', 'enchant', 'soul', 'deck', 'gold'])
    parser.add_argument('--id', type=int, nargs='+')
    parser.add_argument('--name', help='Case-insensitive name/key substring; card aliases included')
    parser.add_argument('--text', help='Case-insensitive effect substring')
    parser.add_argument('--soul')
    parser.add_argument('--rarity')
    parser.add_argument('--tribe')
    parser.add_argument('--type', choices=['monster', 'spell'])
    parser.add_argument('--pool', choices=['ordinary_non_token', 'token', 'text_only'])
    parser.add_argument('--cost-min', type=int)
    parser.add_argument('--cost-max', type=int)
    parser.add_argument('--selectable', action='store_true', help='Artifact observed initial-selection flags')
    parser.add_argument('--full', action='store_true')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--turn', type=int)
    parser.add_argument('--integrity', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.limit <= 200:
        parser.error('--limit must be between 1 and 200')
    filters = [args.id, args.name, args.text, args.soul, args.rarity, args.tribe,
               args.type, args.pool, args.cost_min, args.cost_max, args.selectable]
    if args.kind == 'gold':
        if args.turn is None or args.turn < 1:
            parser.error('gold requires --turn >= 1')
        if any(v is not None and v is not False for v in filters):
            parser.error('gold accepts --turn and optional --integrity, not record filters')
        output = gold_model(args.turn, args.integrity)
    else:
        if args.turn is not None or args.integrity:
            parser.error('--turn and --integrity only apply to gold')
        if args.kind != 'card' and any(v is not None for v in [args.soul, args.rarity, args.tribe, args.type, args.pool, args.cost_min, args.cost_max]):
            parser.error('--soul/rarity/tribe/type/pool/cost filters apply only to card')
        if args.selectable and args.kind != 'artifact':
            parser.error('--selectable applies only to artifact')
        if args.id is not None and args.kind not in {'card', 'artifact'}:
            parser.error('--id applies only to card or artifact')
        snapshot = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
        records = snapshot[{'card': 'cards', 'artifact': 'artifacts', 'deck': 'decks'}.get(args.kind, 'mechanics')]
        if args.kind not in {'card', 'artifact', 'deck'}:
            records = records[args.kind]
        hits = [r for r in records if matches(r, args)]
        shown = hits[:args.limit]
        if args.kind == 'card' and not args.full:
            fields = ['id', 'name', 'metadata_name', 'cost', 'attack', 'health', 'rarity',
                      'card_type', 'soul', 'set', 'tribes', 'pool_category', 'effect_readable']
            shown = [{k: r.get(k) for k in fields} for r in shown]
        output = {'snapshot_compiled': snapshot['provenance']['compiled_date'],
                  'version': snapshot['provenance']['game_version'],
                  'matched': len(hits), 'returned': len(shown),
                  'truncated': len(hits) > len(shown), 'records': shown}
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
