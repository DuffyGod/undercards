"""Frozen, matched comparisons; test outcomes cannot choose the checkpoint."""
from dataclasses import asdict
from pathlib import Path
import argparse, gzip, json, time
import numpy as np
from .catalog import Spec, Effect
from .profiles import base_deck, opponents
from .network import Network
from .policies import ReferencePolicy, LearnedPolicy
from .game import NativeGame, DecisionBudgetExceeded
from .statistics import interval
from .training import dump, commit
from .legacy import learner as old_learner, agents as old_agents, ROOT


def qualify(folder):
    d = json.loads((folder / 'design.json').read_text()); selection = json.loads((folder / 'selection.json').read_text())
    if (folder / 'qualification.json').exists() or (folder / 'test-games.jsonl.gz').exists():
        raise ValueError('Never replace final test evidence')
    net, metadata = Network.load(folder / selection['selected']); fp = net.fingerprint
    previous, _ = old_learner.Network.load(ROOT / 'analysis/strategic-model/2026-10-31/experiment-v01/policy.npz')
    others = opponents(); own = base_deck()
    composed = list(own); composed[0] = Spec('heldout_haste_end_draw', 4, 3, 6, (('haste', 1),), (Effect('end', 'draw', 'owner', 1),))
    # Five predeclared contexts. The final two change action composition and
    # complete deck structure, not names or a card-ID embedding.
    cases = [('pressure', own, others['pressure'], ('INTEGRITY', 'INTEGRITY')),
             ('defense', own, others['defense'], ('INTEGRITY', 'KINDNESS')),
             ('refill', own, others['refill'], ('KINDNESS', 'INTEGRITY')),
             ('heldout_composition', tuple(composed), others['pressure'], ('INTEGRITY', 'INTEGRITY')),
             ('heldout_deck_structure', others['refill'], others['defense'], ('KINDNESS', 'INTEGRITY'))]
    def policy(name):
        if name == 'learned': return LearnedPolicy(net)
        if name == 'previous': return old_agents.LearnedAgent(previous, search_nodes=16)
        return ReferencePolicy(name)
    names = ['learned', 'previous', 'race', 'board', 'guard']; output = []; failed = []
    started = time.monotonic()
    status = dict(status='running', source_commit=commit(), frozen_policy=fp, selected_checkpoint=selection['selected'],
                  complete_slots=0, test_seeds=d['test_seeds'])
    dump(folder / 'qualification.json', status)
    with gzip.open(folder / 'test-games.jsonl.gz', 'wt', encoding='utf-8') as sink:
        for group, a_deck, b_deck, souls in cases:
            scores = {name: [] for name in names}; timers = {name: [] for name in names}
            for seed in d['test_seeds']:
                seats = {name: [] for name in names}
                for seat in (0, 1):
                    for name in names:
                        game = NativeGame((a_deck, b_deck), seed, (policy(name), ReferencePolicy('race')),
                                          seats=seat, souls=souls)
                        try: r = game.run()
                        except DecisionBudgetExceeded as exc:
                            r = dict(won=None, lost=None, unfinished=True, error=str(exc), decision_seconds=[[], []])
                        row = {k: v for k, v in r.items() if k not in ('deck_semantics', 'trace', 'snapshots')}
                        row.update(group=group, seed=seed, seat=seat, policy=name)
                        sink.write(json.dumps(row, separators=(',', ':')) + '\n'); status['complete_slots'] += 1
                        timers[name].extend(r['decision_seconds'][0])
                        seats[name].append(None if r['unfinished'] else float(r['won']))
                        if r['unfinished']: failed.append(dict(group=group, seed=seed, seat=seat, policy=name, error=r.get('error')))
                for name in names:
                    scores[name].append((np.mean([0 if x is None else x for x in seats[name]]), np.mean([1 if x is None else x for x in seats[name]])))
            lo, hi = np.asarray(scores['learned']).T
            comparisons = []
            for name in names[1:]:
                old_lo, old_hi = np.asarray(scores[name]).T
                comparisons.append(dict(policy=name, win=interval(old_lo, old_hi),
                                        learned_gain=interval(lo - old_hi, hi - old_lo)))
            output.append(dict(group=group, learned_win=interval(lo, hi), comparisons=comparisons,
                timings={name: dict(decisions=len(xs), p95=float(np.quantile(xs, .95)) if xs else None,
                                     maximum=max(xs, default=None)) for name, xs in timers.items()}))
            print(json.dumps(dict(group=group, learned=output[-1]['learned_win']['completion_range'],
                                  baseline={r['policy']: r['win']['completion_range'] for r in comparisons})), flush=True)
    qualified = bool(not failed and all(all(r['learned_gain']['low'] > 0 for r in group['comparisons'] if r['policy'] != 'previous') for group in output))
    status.update(status='complete', qualified=qualified, groups=output, failures=failed, elapsed_seconds=time.monotonic() - started,
                  decision_seconds=.25, real_server_certified=False,
                  acceptance='Positive paired95%lower gain against each causal reference in all five contexts, no rejected games. Previous failed model is a separate improvement diagnostic.')
    if fp != net.fingerprint: raise ValueError('Frozen model changed')
    dump(folder / 'qualification.json', status)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', required=True, type=Path)
    qualify(parser.parse_args().output)
