"""V12: causal continuation attribution and a predeclared two-head router.

Y[action, continuation] shares the exact original hidden world and prefix.
The actually executed V11/V11 cell is reused, never counted as a new game.
All decisions, expanded inputs, missing roots and unfinished cells survive.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import random
import time
import numpy as np
from .action_value import encode
from .continuation_gate import ContinuationGate, MODES
from .counterfactual_research import PrefixController, PrefixAgent, sample_inputs, run, value_data
from .memory_research import opponent
from .network import Network
from .policies import LearnedPolicy
from .relational_research import small_result, value_metrics, paired_value_gain, phase_metrics
from .relational_model import RelationalNetwork
from .action_research import suppress_sparse
from .statistics import interval
from .suffix_research import cases, BehaviorRecorder
from .training import dump, commit, decode

BASE = Path('artifacts/card_eval/v5/primary-value.npz')
PROPOSER = Path('artifacts/card_eval/v11/regret_mean-selected.npz')
SOURCE = Path('artifacts/card_eval/v11/development-decisions.jsonl.gz')


def prepare(folder):
    if folder.exists():
        raise ValueError('Preserve research run')
    folder.mkdir(parents=True)
    dump(folder / 'design.json', dict(schema=1, source_commit=commit(), baseline=str(BASE), proposer=str(PROPOSER),
        source=str(SOURCE), source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (BASE, PROPOSER, SOURCE)},
        rng_seed=2026110212, primary='robust', modes=MODES,
        train_seeds=list(range(3610000, 3610128)), diagnostic_seeds=list(range(3620000, 3620032)),
        development_seeds=list(range(3630000, 3630012)), final_seeds=list(range(3830000, 3830032)),
        value_train_seeds=list(range(3640000, 3640192)), value_dev_seeds=list(range(3650000, 3650048)),
        value_final_seeds=list(range(3850000, 3850096)),
        source_use='Already-read V11 primary development trajectories only diagnose; never fit/select the router.',
        roots='First Actor0 semantic disagreement; first disagreement at or after turn6, deduplicated. Prefix-only stopping rules; absent roots stay absent, no fallback or winner filter.',
        matrix='Y00=V5 action/V5 continuation; Y10=V11 action/V5 continuation; Y01=V5 action/V11 continuation; Y11=actual V11 action/V11 continuation (reused).',
        targets=['Y10-Y00', 'Y11-Y01'], interaction='(Y11-Y01)-(Y10-Y00)',
        sampling='Fresh V11 roll-in; independently sampled training-pool full decks/souls. Opponent race/board/guard/delayed crossed with seat by i%4 and (i//4)%2.',
        partial_observation='Same original hidden world/order for offline branches; no new posterior/suffix samples. Actor555 public ordered features, no actual opponent hand/order/RNG.',
        hidden=8, l2=.001, lr=.003, epochs=96, batch=32, epoch_candidates=[16, 32, 64, 96],
        fitting='Equal opening weight divided among complete paired roots. Unknown cells retained but not fit as zero. Shared tanh555x8 then2 utility heads; contrast antisymmetric. No hidden-state input.',
        selection='Minimum two-head diagnostic opening-weighted squared contrast error; ties earliest epoch. One fixed training seed; all gate modes share selected weights, primary robust fixed.',
        deployment='Choose V11 proposal iff both predicted contrasts strictly positive (robust); controls use base-only or own-only contrast. Otherwise V5. Common32-node attack-lethal proof outside router.',
        development_gate='Primary lower completed score>=V5 upper score over5 contexts, paired95% lower gain>=-.10, at least1% semantic activation, and no primary unknown. Otherwise stop before own-value fit and large final. No mode reselection.',
        acceptance='If development passes, freeze primary actor and train own critic before fresh383/385 final. Positive paired95% lower against V5 and V11 in every final context, no unresolved primary, required for qualification. Never tune/reselect on final.',
        decision_seconds=.25, limits='Restricted V5/V11 proposals, finite history, realized single-world contrasts; not conditional expected Q*, belief learning, PSRO or safe policy improvement. Mixed deployed continuation differs from both target continuations. Rule scope unchanged.'))


def design(folder):
    d = json.loads((folder / 'design.json').read_text())
    for path, digest in d['source_sha256'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError('Frozen input changed')
    return d


def stopping_roots(rows):
    """A stopping rule: no outcome or later-trajectory information inspected."""
    roots = {}; previous = LearnedPolicy(Network.load(BASE)[0])
    for index, row in enumerate(rows):
        obs = row['observation']
        if obs['player'] != 0:
            continue
        actions = list(map(tuple, row['legal_actions']))
        baseline = row.get('baseline') or previous.choose(obs, actions)
        b = baseline['action_index']; a = row['selection']['action_index']
        if a == b:
            continue
        x = encode(obs, actions)[1][0]
        if np.array_equal(x[a], x[b]):
            continue
        if 'first' not in roots:
            roots['first'] = (index, b, a)
        if obs['turn'] >= 6 and 'late' not in roots:
            roots['late'] = (index, b, a)
        if len(roots) == 2:
            break
    if 'late' in roots and roots.get('late') == roots.get('first'):
        del roots['late']
    return [(name, *entry) for name, entry in roots.items()]


class OnlineRecorder:
    def __init__(self, sink, baseline):
        self.sink = sink; self.baseline = baseline; self.rows = []; self.roots = {}

    def record(self, obs, actions, selection):
        alt = self.baseline.choose(obs, actions) if obs['player'] == 0 else None
        row = dict(record_type='decision', observation=obs, legal_actions=actions, selection=selection, baseline=alt)
        index = len(self.rows); self.rows.append(row)
        if alt is not None and selection['action_index'] != alt['action_index']:
            a = selection['action_index']; b = alt['action_index']; x = encode(obs, actions)[1][0]
            if not np.array_equal(x[a], x[b]):
                if 'first' not in self.roots:
                    self.roots['first'] = (index, b, a)
                if obs['turn'] >= 6 and 'late' not in self.roots:
                    self.roots['late'] = (index, b, a)
        self.sink.write(json.dumps(row, separators=(',', ':')) + '\n')

    def finish(self, result):
        self.sink.write(json.dumps(dict(record_type='outcome', result=small_result(result))) + '\n')


def source_episodes():
    lookup = {g: (a, b, souls, style) for g, a, b, souls, style in cases()}
    rows = []
    with gzip.open(SOURCE, 'rt') as stream:
        for line in stream:
            row = json.loads(line); meta = row['metadata']
            if meta['policy'] != 'regret_mean':
                continue
            if row['record_type'] == 'decision':
                rows.append(row)
            else:
                a, b, souls, style = lookup[meta['group']]
                full = dict(meta, record_type='input', decks=[[asdict(s) for s in ds] for ds in (a, b)],
                            souls=souls, opponent=style, source=str(SOURCE))
                yield full, rows, row['result']
                rows = []
    if rows:
        raise ValueError('Incomplete reused episode boundary')


def cells_for_root(meta, rows, result, root, base, proposer):
    name, index, b, a = root; actions = list(map(tuple, rows[index]['legal_actions']))
    cells = [dict(action=1, continuation=1, reused=True, prefix_checked=True, result=small_result(result))]
    decks = tuple(tuple(map(decode, ds)) for ds in meta['decks'])
    for action, continuation in ((0, 0), (1, 0), (0, 1)):
        actor = LearnedPolicy(base if continuation == 0 else proposer)
        controller = PrefixController(rows, index, actions[b if action == 0 else a], (actor, opponent(meta['opponent'])))
        r = run(decks, meta['seed'], (PrefixAgent(controller), PrefixAgent(controller)), meta['seat'], meta['souls'])
        if not controller.checked:
            raise ValueError('Counterfactual did not reach recorded root')
        cells.append(dict(action=action, continuation=continuation, reused=False, prefix_checked=True, result=small_result(r)))
    return dict(record_type='root', seed=meta['seed'], group=meta.get('group'), seat=meta['seat'],
                root=name, decision=index, observation=rows[index]['observation'], legal_actions=actions,
                baseline_action=b, proposal_action=a, cells=cells)


def read_lines(path):
    with gzip.open(path, 'rt') as stream:
        for line in stream:
            yield json.loads(line)


def collect(folder, stage):
    d = design(folder); base = Network.load(BASE)[0]; proposer = Network.load(PROPOSER)[0]
    if (folder / f'{stage}-collection.json').exists():
        raise ValueError('Preserve completed collection')
    started = time.monotonic(); output = folder / stage; output.mkdir(exist_ok=True)
    rng = random.Random(d['rng_seed'] + (stage == 'diagnostic'))
    if stage == 'source':
        episodes = source_episodes()
    else:
        inputs = []
        for i, seed in enumerate(d[stage + '_seeds']):
            decks, souls, roles = sample_inputs(rng)
            inputs.append(dict(record_type='input', seed=seed, decks=[[asdict(s) for s in ds] for ds in decks],
                souls=souls, roles=roles, seat=(i // 4) % 2, opponent=('race', 'board', 'guard', 'delayed')[i % 4],
                actor_fingerprint=proposer.actor_fingerprint))
        episodes = ((meta, None, None) for meta in inputs)
    for number, (meta, rows, result) in enumerate(episodes):
        target = output / f'episode-{number:04}.jsonl.gz'
        if target.exists():
            continue  # Only atomically completed files; no completed game repeated.
        pending = target.with_suffix('.pending')
        if pending.exists():
            raise ValueError(f'Preserve interrupted attempts before resuming: {pending}')
        with gzip.open(pending, 'wt') as sink:
            sink.write(json.dumps(meta) + '\n')
            if rows is None:
                rec = OnlineRecorder(sink, LearnedPolicy(base))
                decks = tuple(tuple(map(decode, ds)) for ds in meta['decks'])
                result = run(decks, meta['seed'], (LearnedPolicy(proposer), opponent(meta['opponent'])), meta['seat'], meta['souls'], rec)
                rows = rec.rows; roots = [(name, *value) for name, value in rec.roots.items()]
                if rec.roots.get('late') == rec.roots.get('first'):
                    roots = [r for r in roots if r[0] != 'late']
            else:
                roots = stopping_roots(rows)
                # Original decisions/results remain in hashed source; only new interventions stored here.
            sink.write(json.dumps(dict(record_type='root_selection', present=[r[0] for r in roots],
                rollin_unknown=bool(result['unfinished']), rollin_reused=stage == 'source')) + '\n')
            for root in roots:
                sink.write(json.dumps(cells_for_root(meta, rows, result, root, base, proposer), separators=(',', ':')) + '\n')
        pending.rename(target)
        if number % 8 == 7:
            print(json.dumps(dict(stage=stage, completed_openings=number + 1)), flush=True)
    report = attribution(output)
    dump(folder / f'{stage}-collection.json', dict(report, source_commit=commit(), elapsed_seconds=time.monotonic() - started))


def bounds(cell):
    r = cell['result']
    return (0., 1.) if r['unfinished'] else (float(r['won']), float(r['won']))


def gains(root):
    cells = {(c['action'], c['continuation']): bounds(c) for c in root['cells']}
    lo = []; hi = []
    for continuation in (0, 1):
        a = cells[1, continuation]; b = cells[0, continuation]
        lo.append(a[0] - b[1]); hi.append(a[1] - b[0])
    return np.array(lo), np.array(hi)


def attribution(output):
    counts = Counter(); seed_values = defaultdict(list); complete = []; missing = Counter()
    for path in sorted(output.glob('episode-*.jsonl.gz')):
        counts['openings'] += 1
        for row in read_lines(path):
            if row['record_type'] == 'root_selection':
                counts['unfinished_rollins'] += row['rollin_unknown']
                for name in ('first', 'late'):
                    missing[name] += name not in row['present']
            if row['record_type'] != 'root':
                continue
            lo, hi = gains(row); seed_values[row['seed']].append((lo, hi)); counts['roots'] += 1
            counts['new_branches'] += 3; counts['reused_cells'] += 1
            counts['unknown_cells'] += sum(c['result']['unfinished'] for c in row['cells'])
            if not np.array_equal(lo, hi):
                counts['incomplete_roots'] += 1; continue
            a, b = lo; complete.append(lo)
            category = ('target_reversal' if a > 0 and b < 0 else 'both_harmful' if a < 0 and b < 0 else
                        'both_helpful' if a > 0 and b > 0 else 'own_only_helpful' if a <= 0 and b > 0 else
                        'own_only_harmful' if a >= 0 and b < 0 else 'base_only_helpful' if a > 0 else
                        'base_only_harmful' if a < 0 else 'no_effect')
            counts[category] += 1
    if not seed_values:
        raise ValueError('No paired roots')
    lo = np.asarray([np.mean([x[0] for x in values], axis=0) for values in seed_values.values()])
    hi = np.asarray([np.mean([x[1] for x in values], axis=0) for values in seed_values.values()])
    return dict(counts=dict(counts), absent_or_duplicate_roots=dict(missing),
        base_continuation_gain=interval(lo[:, 0], hi[:, 0]), own_continuation_gain=interval(lo[:, 1], hi[:, 1]),
        interaction=interval(lo[:, 1] - hi[:, 0], hi[:, 1] - lo[:, 0]),
        inference='Original-seed clusters, equal observed-root weight within each seed. Root-conditional realized counterfactuals; not full-game policy effect or posterior expected Q. Missing-root openings excluded only from root-conditional estimand; counts retained.')


def dataset(folder, stage):
    rows = []
    for path in sorted((folder / stage).glob('episode-*.jsonl.gz')):
        rows.extend(r for r in read_lines(path) if r['record_type'] == 'root')
    complete = []
    for r in rows:
        lo, hi = gains(r)
        if np.array_equal(lo, hi):
            x = encode(r['observation'], list(map(tuple, r['legal_actions'])))[1][0]
            complete.append((r['seed'], x[[r['baseline_action'], r['proposal_action']]], lo))
    n = Counter(s for s, _, _ in complete)
    return dict(x=np.array([x for _, x, _ in complete]), y=np.array([y for _, _, y in complete]),
                weights=np.array([1 / n[s] for s, _, _ in complete]), seeds=[s for s, _, _ in complete],
                excluded_roots=len(rows) - len(complete))


def prediction_metrics(net, data):
    pred = net.contrasts(data['x']); residual = pred - data['y']; w = data['weights'] / data['weights'].sum()
    return dict(mse=float(w @ np.mean(residual ** 2, axis=1)), head_mse=(w @ residual ** 2).tolist(),
                zero_predictor_mse=float(w @ np.mean(data['y'] ** 2, axis=1)),
                positive_both=int(np.sum(np.min(pred, axis=1) > 0)), roots=len(pred),
                excluded_unknown_roots=data['excluded_roots'])


def fit(folder):
    if (folder / 'fit.json').exists():
        raise ValueError('Preserve fit')
    d = design(folder); train = dataset(folder, 'train'); diagnostic = dataset(folder, 'diagnostic')
    net = ContinuationGate(Network.load(PROPOSER)[0], hidden=d['hidden'], seed=d['rng_seed'])
    rng = np.random.default_rng(d['rng_seed']); m = {k: np.zeros_like(p) for k, p in net.p.items()}; v = deepcopy(m)
    curve = []; step = 0
    for epoch in range(1, d['epochs'] + 1):
        order = rng.permutation(len(train['x']))
        for start in range(0, len(order), d['batch']):
            ix = order[start:start + d['batch']]
            weights = train['weights'][ix] / train['weights'].sum() * len(order) / len(ix)
            _, grads = net.loss_grad(train['x'][ix], train['y'][ix], weights, d['l2']); step += 1
            norm = np.sqrt(sum(np.sum(g * g) for g in grads.values())); scale = min(1., 5 / max(norm, 1e-12))
            for k, g in grads.items():
                g = g * scale; m[k] = .9 * m[k] + .1 * g; v[k] = .999 * v[k] + .001 * g * g
                net.p[k] -= d['lr'] * (m[k] / (1 - .9 ** step)) / (np.sqrt(v[k] / (1 - .999 ** step)) + 1e-8)
        if epoch in d['epoch_candidates']:
            curve.append(dict(epoch=epoch, train=prediction_metrics(net, train), diagnostic=prediction_metrics(net, diagnostic)))
            net.save(folder / f'epoch-{epoch:03}.npz', dict(source_commit=commit(), validation=dict(qualified=False),
                     value_unfitted=True, epoch=epoch))
    chosen = min(curve, key=lambda row: (row['diagnostic']['mse'], row['epoch']))['epoch']
    selected = Network.load(folder / f'epoch-{chosen:03}.npz')[0]
    for mode in MODES:
        selected.mode = mode
        selected.save(folder / f'{mode}-selected.npz', dict(source_commit=commit(), validation=dict(qualified=False),
                      value_unfitted=True, epoch=chosen, selection=d['selection']))
    dump(folder / 'fit.json', dict(source_commit=commit(), selected_epoch=chosen, curve=curve, parameters=net.parameters,
        train_openings=len(set(train['seeds'])), diagnostic_openings=len(set(diagnostic['seeds'])),
        selection=d['selection'], all_modes_share_weights=True))


def development(folder):
    if (folder / 'development.json').exists():
        raise ValueError('Preserve development')
    d = design(folder); base = Network.load(BASE)[0]
    models = {mode: Network.load(folder / f'{mode}-selected.npz')[0] for mode in MODES}
    models.update(v5=base, v11=Network.load(PROPOSER)[0]); results = []; behavior = defaultdict(Counter)
    with gzip.open(folder / 'development-decisions.jsonl.gz', 'wt') as decisions, gzip.open(folder / 'development-games.jsonl.gz', 'wt') as games:
        for group, a, b, souls, style in cases():
            for seed in d['development_seeds']:
                for seat in (0, 1):
                    for name, net in models.items():
                        meta = dict(group=group, seed=seed, seat=seat, policy=name)
                        rec = BehaviorRecorder(decisions, meta, LearnedPolicy(base))
                        r = run((a, b), seed, (LearnedPolicy(net), opponent(style)), seat, souls, rec)
                        games.write(json.dumps(dict(meta, result=small_result(r))) + '\n')
                        results.append(dict(meta, unknown=r['unfinished'], won=r['won']))
                        behavior[name].update(decisions=rec.decisions, changed=rec.changed, raw_changed=rec.raw_changed, unknown=r['unfinished'])
            print(json.dumps(dict(group=group, completed_slots=len(results))), flush=True)
    perseed = {}
    for name in models:
        rows = [[r for r in results if r['policy'] == name and r['seed'] == seed] for seed in d['development_seeds']]
        perseed[name] = (np.array([np.mean([0 if r['unknown'] else int(r['won']) for r in rs]) for rs in rows]),
                         np.array([np.mean([1 if r['unknown'] else int(r['won']) for r in rs]) for rs in rows]))
    a, b = perseed['robust']; metrics = {}
    for name, (lo, hi) in perseed.items():
        metrics[name] = dict(win=interval(lo, hi), primary_gain=interval(a - hi, b - lo), behavior=dict(behavior[name]))
    ratio = behavior['robust']['changed'] / max(1, behavior['robust']['decisions'])
    proceed = bool(a.mean() >= perseed['v5'][1].mean() and metrics['v5']['primary_gain']['low'] >= -.1
                   and ratio >= .01 and not behavior['robust']['unknown'])
    dump(folder / 'development.json', dict(source_commit=commit(), primary='robust', metrics=metrics, activation=ratio,
        proceed_to_final=proceed, gate=d['development_gate'], no_reselection=True))
    if not proceed:
        dump(folder / 'final-status.json', dict(status='not_executed', qualified=False,
             reason='Predeclared development gate failed', final_seeds_unread=True, value_final_unread=True,
             own_value_fitted=False))


def require_gate(folder):
    if not json.loads((folder / 'development.json').read_text())['proceed_to_final']:
        raise ValueError('Development gate failed; final must remain unread')


def value(folder):
    require_gate(folder)
    if (folder / 'value.json').exists() or list(folder.glob('value-*.jsonl.gz')):
        raise ValueError('Preserve own-policy value evidence')
    d = design(folder); net = Network.load(folder / 'robust-selected.npz')[0]
    train = value_data(folder, net, 'train', d['value_train_seeds']); x = []; y = []; w = []
    for e in train:
        if not e['terminal']:
            continue
        x.extend(e['states']); y.extend([int(e['won'])] * len(e['states'])); w.extend([1 / len(e['states'])] * len(e['states']))
    before = net.actor_fingerprint; fitted = net.fit_value(x, y, w, l2=.01, iterations=160)
    assert net.actor_fingerprint == before
    prior = float(np.mean([int(e['won']) for e in train if e['terminal']]))
    net.save(folder / 'primary-value.npz', dict(source_commit=commit(), validation=dict(qualified=False),
        value_unfitted=False, critic_actor_fingerprint=before,
        target='Natural full-game continuation of frozen robust router; sampled semantic decks and race/board/guard mixture'))
    simple = RelationalNetwork(); states = np.asarray(x)
    reduced = np.c_[np.ones(len(states)), states[:, 1] - states[:, 2], states[:, 26] - states[:, 39],
                    states[:, 27] - states[:, 40], states[:, 8] - states[:, 9]]
    simple_fit = simple.fit_value(reduced, y, w, l2=.01, iterations=160)
    beta = simple.critic.copy(); simple.critic = np.zeros(74); simple.critic[0] = beta[0]
    for c, (pos, neg) in zip(beta[1:], ((1, 2), (26, 39), (27, 40), (8, 9))):
        simple.critic[pos] = c; simple.critic[neg] = -c
    simple.save(folder / 'value-simple.npz', dict(validation=dict(qualified=False), critic_actor_fingerprint=before))
    dev = value_data(folder, net, 'dev', d['value_dev_seeds'])
    dump(folder / 'value.json', dict(source_commit=commit(), fit=fitted, simple_fit=simple_fit,
        actor_unchanged=True, actor_fingerprint=before, train_prior=prior, train_openings=len(train), train_states=len(x),
        unknown_train=sum(not e['terminal'] for e in train), development=value_metrics(net, dev, prior),
        simple_development=value_metrics(simple, dev, prior), gain_vs_simple=paired_value_gain(net, simple, dev),
        no_critic_selection=True))


def final(folder):
    require_gate(folder)
    if (folder / 'final-games.jsonl.gz').exists() or list(folder.glob('value-final-*.jsonl.gz')):
        raise ValueError('Final runs once; preserve partial output')
    d = design(folder); primary, meta = Network.load(folder / 'primary-value.npz')
    assert primary.actor_fingerprint == Network.load(folder / 'robust-selected.npz')[0].actor_fingerprint
    assert meta['value_unfitted'] is False and meta['critic_actor_fingerprint'] == primary.actor_fingerprint
    models = dict(robust=primary, v5=Network.load(BASE)[0], v11=Network.load(PROPOSER)[0])
    inputs = cases(True)
    dump(folder / 'final-plan.json', dict(source_commit=commit(), primary_actor=primary.actor_fingerprint,
        models={n: m.fingerprint for n, m in models.items()}, seeds=d['final_seeds'],
        cases=[dict(group=g, decks=[[asdict(s) for s in ds] for ds in (a, b)], souls=souls, opponent=style)
               for g, a, b, souls, style in inputs], no_final_selection=True, acceptance=d['acceptance']))
    groups = []; failures = []; started = time.monotonic()
    with gzip.open(folder / 'final-games.jsonl.gz', 'wt') as sink:
        for group, a, b, souls, style in inputs:
            scores = {n: [] for n in models}; timings = defaultdict(list)
            for seed in d['final_seeds']:
                seats = {n: [] for n in models}
                for seat in (0, 1):
                    for name, model in models.items():
                        enemy = LearnedPolicy(models['v5']) if style == 'learned' else opponent(style)
                        r = run((a, b), seed, (LearnedPolicy(model), enemy), seat, souls)
                        sink.write(json.dumps(dict(group=group, seed=seed, seat=seat, policy=name, result=small_result(r))) + '\n')
                        seats[name].append(None if r['unfinished'] else int(r['won']))
                        timings[name].extend(r['decision_seconds'][0])
                        if r['unfinished']:
                            failures.append(dict(group=group, seed=seed, seat=seat, policy=name, error=r.get('error')))
                for name in models:
                    scores[name].append((np.mean([0 if v is None else v for v in seats[name]]),
                                         np.mean([1 if v is None else v for v in seats[name]])))
            lo, hi = np.asarray(scores['robust']).T; comparisons = []
            for name, values in scores.items():
                a0, b0 = np.asarray(values).T
                comparisons.append(dict(policy=name, win=interval(a0, b0), primary_gain=interval(lo - b0, hi - a0),
                    family_gain=interval(lo - b0, hi - a0, alpha=.05 / (2 * len(inputs)))))
            groups.append(dict(group=group, policies=comparisons, timings={n: dict(decisions=len(t),
                p95=float(np.quantile(t, .95)) if t else None, maximum=max(t) if t else None) for n, t in timings.items()}))
            dump(folder / 'final-progress.json', dict(groups=groups, failures=failures))
            print(json.dumps(dict(group=group, wins={c['policy']: c['win']['completion_range'] for c in comparisons})), flush=True)
    # This reports all frozen cases; no post-result model/mode choice.
    qualified = (not any(f['policy'] == 'robust' for f in failures) and
                 all(c['primary_gain']['low'] > 0 for g in groups for c in g['policies'] if c['policy'] != 'robust'))
    val = value_data(folder, primary, 'final', d['value_final_seeds'])
    prior = json.loads((folder / 'value.json').read_text())['train_prior']; simple = Network.load(folder / 'value-simple.npz')[0]
    dump(folder / 'final.json', dict(source_commit=commit(), qualified=qualified, groups=groups, failures=failures,
        no_final_reselection=True, elapsed_seconds=time.monotonic() - started,
        value_final=value_metrics(primary, val, prior), value_simple=value_metrics(simple, val, prior),
        value_previous_v5=value_metrics(models['v5'], val, prior), value_gain_vs_simple=paired_value_gain(primary, simple, val),
        value_gain_vs_v5=paired_value_gain(primary, models['v5'], val), phases=suppress_sparse(phase_metrics(primary, val, prior))))
    dump(folder / 'validation.json', dict(qualified=qualified, status='qualified' if qualified else 'not_qualified',
        frozen_policy=primary.fingerprint, default_model_replaced=False, source='final.json'))
    dump(folder / 'final-status.json', dict(status='complete', qualified=qualified, final_seeds_unread=False,
        value_final_unread=False, own_value_fitted=True, no_reselection=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'collect', 'fit', 'development', 'value', 'final'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stage', choices=['source', 'train', 'diagnostic'])
    args = parser.parse_args()
    if args.mode == 'collect':
        collect(args.output, args.stage)
    else:
        globals()[args.mode](args.output)
