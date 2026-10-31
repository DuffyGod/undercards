"""Compare arbitrary supported semantic cards with ONE frozen policy.

This is a conditional evaluation interface, not a learned card-ID lookup or a
claim that the present checkpoint passed its generalization gate.
"""
from dataclasses import asdict
from pathlib import Path
import argparse, gzip, hashlib, json
import numpy as np
from study import from_dict, catalog, guarded_game, bounded_interval, dump, source_commit
from environment import Config, Policy
from agents import LearnedAgent, FixedAgent
from learner import Network


def normalize(data):
    mapped, _ = catalog()
    def spec(raw):
        if isinstance(raw, str):
            if raw not in mapped: raise ValueError('Card has no strict complete mapping: ' + raw)
            return mapped[raw]
        return from_dict(dict(name='anonymous candidate', cost=0, attack=0, health=0,
                              keywords=[], effects=[], card_id=None) | raw)
    reference = spec(data['reference'])
    candidates = list(map(spec, data['candidates']))
    if not candidates or len({s.name for s in candidates + [reference]}) != len(candidates) + 1:
        raise ValueError('Use nonempty candidates with unique diagnostic names, distinct from reference')
    seeds = data['seeds']
    if not seeds or len(set(seeds)) != len(seeds) or any(type(s) is not int or s < 0 for s in seeds):
        raise ValueError('Explicit unique nonnegative seed list required')
    structure = data.get('structure', 'wide')
    if structure not in ('wide', 'anchor', 'refill', 'recovery'): raise ValueError('Unknown role-host structure')
    config = dict(rounds=40) | data.get('config', {})
    if 'seat' in config: raise ValueError('Both seats are paired by the interface')
    cfg = Config(**config)
    if cfg.soul not in ('INTEGRITY', 'KINDNESS') or cfg.response_kind not in ('sweep', 'focus'):
        raise ValueError('Unsupported SOUL or response rule')
    if cfg.slots != 4 or cfg.hand_cap != 7: raise ValueError('Feature schema requires board4/hand7')
    opponent = Policy(**(dict(name='declared_opponent', response_threshold=2) | data.get('opponent', {})))
    if opponent.order not in ('cheap', 'durable', 'window') or opponent.combat not in (
            'trade', 'face', 'attack_frontier', 'frontier_board', 'frontier_race') or opponent.response_threshold not in (1, 2, 3):
        raise ValueError('Unsupported fixed-policy parameters')
    mode = data.get('silence_mode', 'retain')
    if mode not in ('retain', 'reset', 'reject_modified'): raise ValueError('Unknown silence mode')
    return reference, candidates, seeds, structure, config, opponent, mode


def compare(checkpoint, input_path, output):
    if output.exists(): raise ValueError('Preserve existing comparison; choose a new output directory')
    data = json.loads(input_path.read_text(encoding='utf-8'))
    reference, candidates, seeds, structure, config, opponent, mode = normalize(data)
    net, metadata = Network.load(checkpoint); frozen = net.fingerprint
    output.mkdir(parents=True)
    dump(output / 'input.json', data)
    receipt = dict(status='running', source_commit=source_commit(require_clean=False),
        checkpoint_source_commit=metadata['source_commit'], frozen_policy=frozen,
        input_sha256=hashlib.sha256(input_path.read_bytes()).hexdigest(),
        rule_assumption=mode, completed_conditions=0,
        scope='Three entity slots in declared abstract role host; no full actual-deck certification.')
    dump(output / 'receipt.json', receipt)
    scores = {}; diagnostics = {}
    try:
        with gzip.open(output / 'records.jsonl.gz', 'wt', encoding='utf-8') as sink:
            for spec in [reference] + candidates:
                values = []; rows = []
                for seed in seeds:
                    pair = []
                    for seat in (0, 1):
                        result = guarded_game(spec, seed, Config(**(config | dict(seat=seat))), structure,
                            (LearnedAgent(net, search_nodes=16), FixedAgent(opponent)), silence_mode=mode,
                            decision_seconds=data.get('decision_seconds', .25))
                        row = {k: v for k, v in result.items() if k not in ('trace', 'snapshots', 'decision_seconds')}
                        row.update(card=spec.name, seat=seat)
                        sink.write(json.dumps(row, separators=(',', ':')) + '\n')
                        rows.append(row); pair.append(None if result['unfinished'] else float(result['won']))
                    values.append((np.mean([0 if x is None else x for x in pair]), np.mean([1 if x is None else x for x in pair])))
                scores[spec.name] = np.asarray(values)
                diagnostics[spec.name] = dict(games=len(rows), unfinished=sum(r['unfinished'] for r in rows),
                    unknown_opportunity=sum('candidate_drawn' not in r for r in rows),
                    not_received=sum(r.get('candidate_drawn') == 0 for r in rows),
                    received_unplayed=sum(r.get('candidate_drawn', 0) > 0 and not r.get('candidate_played', 0) for r in rows),
                    played=sum(r.get('candidate_played', 0) > 0 for r in rows))
                receipt['completed_conditions'] += len(rows); dump(output / 'receipt.json', receipt)
        if frozen != net.fingerprint: raise ValueError('Checkpoint changed across candidates')
        baseline = scores[reference.name]
        result = dict(frozen_policy=frozen, reference=asdict(reference),
            comparisons=[dict(candidate=asdict(s), win=bounded_interval(*scores[s.name].T),
                difference=bounded_interval(scores[s.name][:, 0] - baseline[:, 1], scores[s.name][:, 1] - baseline[:, 0]),
                opportunities=diagnostics[s.name]) for s in [reference] + candidates],
            independent_seed_clusters=len(seeds), equal_weight_seat_pairing=True,
            meaning='All seeds retained; unknown outcomes use completion bounds, no hand-conditioned filtering or extra diagnosis deductions.',
            checkpoint_generalization_certified=False)
        dump(output / 'comparison.json', result); receipt['status'] = 'complete'
    except Exception as exc:
        receipt.update(status='failed', error=repr(exc)); dump(output / 'receipt.json', receipt); raise
    dump(output / 'receipt.json', receipt)
    print(json.dumps(dict(status='complete', conditions=receipt['completed_conditions'], frozen_policy=frozen)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); compare(args.checkpoint, args.input, args.output)
