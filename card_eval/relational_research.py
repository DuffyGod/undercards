"""Frozen representation/teacher ablation and policy-specific value experiment.

Run prepare, commit source/design, then fit, development, value and final.
Every phase refuses to replace evidence. Final outcomes cannot select a model.
"""
from dataclasses import asdict
from pathlib import Path
import argparse, gzip, hashlib, json, random, time
import numpy as np
from .catalog import Spec, Effect, semantic_key
from .game import NativeGame, DecisionBudgetExceeded
from .network import Network, encode as mlp_encode
from .policies import ReferencePolicy, LearnedPolicy
from .profiles import training_pool, base_deck, opponents
from .relations import encode, state_features
from .relational_model import RelationalNetwork
from .statistics import interval
from .training import dump, commit

ARMS = ('relational_race', 'relational_guard', 'mlp_race', 'mlp_guard')


def prepare(folder):
    if folder.exists(): raise ValueError('Preserve existing run')
    root = Path('artifacts/card_eval/v2')
    fit_files = sorted(root.glob('decisions-warmup-*.jsonl.gz')) + sorted(root.glob('decisions-dagger-*.jsonl.gz'))
    check_files = sorted(root.glob('decisions-ppo-*.jsonl.gz'))[:8]
    d = dict(schema=1, source_commit=commit(), rng_seed=2026103104,
        fit_files=list(map(str, fit_files)), fidelity_files=list(map(str, check_files)),
        input_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in fit_files + check_files},
        samples=12288, train_filter='Decisions with at least two legal actions; reservoir across old warmup+DAgger observations.',
        arms=ARMS, primary='relational_guard', selection='Primary fixed before training, not selected by development or final outcomes.',
        teacher_basis='guard chosen from v2/development-reference.json, which predates V3 final test; race is the teacher ablation.',
        actor=dict(relational_l2=1e-5, relational_iterations=180, mlp_epochs=10, mlp_lr=.0005,
                   mlp_value_weight=0, entropy=0, seed=2026103104),
        development_seeds=list(range(1112000, 1112016)), final_seeds=list(range(1310000, 1310048)),
        value_train_seeds=list(range(1030000, 1030384)), value_dev_seeds=list(range(1130000, 1130096)),
        value_final_seeds=list(range(1330000, 1330096)), value_l2=.01,
        value_target='Actor0 terminal win probability under frozen deterministic actor, 1/3 race+board+guard opponent mixture and training-pool full decks.',
        value_weight='Equal episode weight, divided among Actor0 decisions; no labels for unresolved episodes.',
        value_select='No hyperparameter/checkpoint selection; development is diagnostic only.',
        final_cases=['pressure', 'defense', 'refill', 'new_parameters', 'new_composition', 'new_structure', 'unseen_reserve_opponent'],
        final_policies=['primary', 'previous_v3', 'race', 'board', 'guard'],
        acceptance='Positive paired 95% lower gain against every causal reference in every case, with zero unresolved slots. Narrower gains cannot promote production.',
        decision_seconds=.25, new_api_calls=0, previous_games_replayed=0,
        limitation='Public finite history, no recurrent belief; model-rule scope unchanged; one training seed; value does not yet improve actor.')
    if not fit_files or len(check_files) != 8: raise ValueError('Missing reusable inputs')
    folder.mkdir(parents=True); dump(folder / 'design.json', d)


def read_decisions(paths):
    for path in paths:
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                if row['record_type'] == 'decision':
                    row['input_file'] = path
                    yield row


def fit(folder):
    if (folder / 'fit.json').exists(): raise ValueError('Preserve fitting evidence')
    d = json.loads((folder / 'design.json').read_text()); rng = random.Random(d['rng_seed']); reservoir = []; seen = 0
    for path, digest in d['input_sha256'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest: raise ValueError('Reusable input changed')
    started = time.monotonic(); all_rows = 0
    for row in read_decisions(d['fit_files']):
        all_rows += 1
        if len(row['legal_actions']) < 2: continue
        seen += 1
        if len(reservoir) < d['samples']: reservoir.append(row)
        else:
            j = rng.randrange(seen)
            if j < len(reservoir): reservoir[j] = row
    dump(folder / 'sample-keys.json', [dict(file=r['input_file'], episode=r['episode_id'], decision=r['decision']) for r in reservoir])
    rel = []; mlp = []; labels = {style: [] for style in ('race', 'guard')}
    for row in reservoir:
        obs = row['observation']; actions = list(map(tuple, row['legal_actions']))
        rel.append(encode(obs, actions)[1].astype('float32'))
        mlp.append(tuple(v.astype('float32') for v in mlp_encode(obs, actions)))
        for style in labels: labels[style].append(ReferencePolicy(style).choose(obs, actions)['action_index'])
    result = dict(source_commit=commit(), input_rows=all_rows, multi_action_rows=seen, retained=len(reservoir), arms={})
    for arm in ARMS:
        style = arm.split('_')[-1]
        if arm.startswith('relational'):
            net = RelationalNetwork(); report = net.fit_actor(rel, labels[style], d['actor']['relational_l2'], d['actor']['relational_iterations'])
        else:
            net = Network(d['actor']['seed']); nrng = np.random.default_rng(d['rng_seed']); epochs = []
            samples = [dict(features=f, chosen=y, **{'return': 0.}) for f, y in zip(mlp, labels[style])]
            for epoch in range(d['actor']['mlp_epochs']):
                nrng.shuffle(samples); loss = []
                for j in range(0, len(samples), 64):
                    loss.append(net.update(samples[j:j + 64], imitation=True, lr=d['actor']['mlp_lr'],
                                           value_weight=0, entropy=0)['loss'])
                epochs.append(float(np.mean(loss)))
            report = dict(epoch_loss=epochs)
        net.save(folder / (arm + '.npz'), dict(source_commit=commit(), teacher=style, validation=dict(qualified=False),
                                             purpose='frozen diagnostic actor, no outcome values fitted'))
        correct = []
        for f, y in zip(rel if arm.startswith('relational') else mlp, labels[style]):
            if arm.startswith('relational'): chosen = int((f @ net.actor).argmax())
            else: chosen = int(net.forward(*f)[0].argmax())
            correct.append(chosen == y)
        result['arms'][arm] = dict(report=report, raw_train_accuracy=float(np.mean(correct)), fingerprint=net.fingerprint,
                                   elapsed_seconds=time.monotonic() - started)
        print(json.dumps(dict(arm=arm, **result['arms'][arm])), flush=True)
    dump(folder / 'fit.json', result)


def development(folder):
    if (folder / 'development.json').exists(): raise ValueError('Preserve development evidence')
    d = json.loads((folder / 'design.json').read_text()); nets = {a: Network.load(folder / (a + '.npz'))[0] for a in ARMS}
    nets['previous_v3'] = Network.load('card_eval/models/shared-policy.npz')[0]
    counts = {a: dict(total=0, correct=0, multi=0, multi_correct=0, attack=0, attack_correct=0) for a in nets}
    for row in read_decisions(d['fidelity_files']):
        obs = row['observation']; actions = list(map(tuple, row['legal_actions']))
        teachers = {style: ReferencePolicy(style).choose(obs, actions)['action_index'] for style in ('race', 'guard')}
        for name, net in nets.items():
            y = teachers['guard' if name.endswith('guard') else 'race']; got = LearnedPolicy(net).choose(obs, actions)['action_index']
            c = counts[name]; c['total'] += 1; c['correct'] += got == y
            if len(actions) > 1: c['multi'] += 1; c['multi_correct'] += got == y
            if actions[y][0] == 'attack': c['attack'] += 1; c['attack_correct'] += got == y
    results = []
    with gzip.open(folder / 'development-games.jsonl.gz', 'wt', encoding='utf-8') as stream:
        for name, net in nets.items():
            values = []
            for group, other in opponents().items():
                for seed in d['development_seeds']:
                    r = game((base_deck(), other), seed, LearnedPolicy(net), ReferencePolicy('race'), seed % 2,
                             ('INTEGRITY', 'KINDNESS' if group == 'defense' else 'INTEGRITY'))
                    row = dict(group=group, seed=seed, policy=name, result=small_result(r)); stream.write(json.dumps(row) + '\n')
                    values.append(0 if r['unfinished'] else int(r['won']))
            c = counts[name]; c.update(accuracy=c['correct'] / c['total'], multi_accuracy=c['multi_correct'] / c['multi'],
                                      attack_accuracy=c['attack_correct'] / c['attack'])
            results.append(dict(policy=name, fidelity=c, development_win_lower=float(np.mean(values))))
            print(json.dumps(results[-1]), flush=True)
    dump(folder / 'development.json', dict(source_commit=commit(), results=results,
                                          primary_remains=d['primary'], selection='No reselection; all actors frozen before these diagnostics.'))


def small_result(r): return {k: v for k, v in r.items() if k not in ('deck_semantics', 'trace', 'snapshots')}


def game(decks, seed, a, b, seat, souls, recorder=None):
    try: return NativeGame(decks, seed, (a, b), seats=seat, souls=souls, recorder=recorder).run()
    except DecisionBudgetExceeded as exc:
        r = dict(won=None, lost=None, unfinished=True, error=str(exc), decision_seconds=[[], []])
        if recorder: recorder.finish(r)
        return r


class ValueRecorder:
    def __init__(self, sink, episode, metadata):
        self.sink = sink; self.episode = episode; self.metadata = metadata; self.states = []; self.rows = 0
    def record(self, obs, actions, selected):
        self.sink.write(json.dumps(dict(record_type='decision', episode=self.episode, decision=self.rows,
            observation=obs, legal_actions=actions, selection=selected), separators=(',', ':')) + '\n')
        if obs['player'] == 0: self.states.append(state_features(obs))
        self.rows += 1
    def finish(self, r):
        self.result = r
        self.sink.write(json.dumps(dict(record_type='outcome', episode=self.episode, metadata=self.metadata,
            result=small_result(r)), separators=(',', ':')) + '\n')


def value_data(folder, net, name, seeds):
    rng = random.Random(2026103104 + {'train': 0, 'dev': 1, 'final': 2}[name]); pool = training_pool(); records = []
    for start in range(0, len(seeds), 64):
        with gzip.open(folder / f'value-{name}-{start:04}.jsonl.gz', 'wt', encoding='utf-8') as sink:
            for i, seed in enumerate(seeds[start:start + 64], start):
                decks = tuple(tuple(rng.sample(pool * 3, 25)) for _ in range(2))
                souls = tuple(rng.choice(('INTEGRITY', 'KINDNESS')) for _ in range(2)); style = ('race', 'board', 'guard')[i % 3]
                rec = ValueRecorder(sink, seed, dict(seed=seed, seat=i % 2, souls=souls, opponent=style,
                    decks=[[asdict(s) for s in deck] for deck in decks], actor_fingerprint=net.actor_fingerprint))
                r = game(decks, seed, LearnedPolicy(net), ReferencePolicy(style), i % 2, souls, rec)
                records.append(dict(seed=seed, terminal=not r['unfinished'], won=r['won'], states=rec.states, opponent=style))
    return records


def value_metrics(net, episodes, constant):
    scored = []; calibration = []
    for e in episodes:
        if not e['terminal']: continue
        probs = [net.forward(s, np.zeros((1, len(net.actor))))[1] / 2 + .5 for s in e['states']]
        y = int(e['won']); brier = float(np.mean([(p - y) ** 2 for p in probs]))
        scored.append((brier, (constant - y) ** 2)); calibration.extend((p, y, 1 / len(probs)) for p in probs)
    a = np.asarray(scored); bins = []
    for lo in (0, .2, .4, .6, .8):
        rows = [(p, y, w) for p, y, w in calibration if lo <= p < lo + .2 or lo == .8 and p == 1]
        if rows:
            p, y, w = np.asarray(rows).T
            bins.append(dict(range=[lo, lo + .2], episode_weight=float(w.sum()), prediction=float(np.average(p, weights=w)),
                             outcome=float(np.average(y, weights=w))))
    return dict(terminal_episodes=len(scored), unresolved_episodes=sum(not e['terminal'] for e in episodes),
        brier=interval(a[:, 0]), constant_brier=interval(a[:, 1]), brier_gain=interval(a[:, 1] - a[:, 0]), calibration=bins)


def value(folder):
    if (folder / 'value.json').exists() or list(folder.glob('value-*.jsonl.gz')): raise ValueError('Preserve value evidence')
    d = json.loads((folder / 'design.json').read_text()); net = Network.load(folder / (d['primary'] + '.npz'))[0]
    before = net.actor_fingerprint; train = value_data(folder, net, 'train', d['value_train_seeds'])
    xs = []; ys = []; weights = []
    for e in train:
        if not e['terminal']: continue
        xs.extend(e['states']); ys.extend([int(e['won'])] * len(e['states'])); weights.extend([1 / len(e['states'])] * len(e['states']))
    constant = float(np.mean([int(e['won']) for e in train if e['terminal']]))
    report = net.fit_value(xs, ys, weights, l2=d['value_l2'])
    net.save(folder / 'primary-value.npz', dict(source_commit=commit(), validation=dict(qualified=False), value_opponent_mixture=['race', 'board', 'guard'],
        deterministic_actor=True, actor_fingerprint=before, value_target=d['value_target']))
    dev = value_data(folder, net, 'dev', d['value_dev_seeds'])
    dump(folder / 'value.json', dict(source_commit=commit(), fit=report, frozen_actor=before, actor_unchanged=before == net.actor_fingerprint,
        train_episodes=len(train), train_decisions=len(xs), train_unresolved=sum(not e['terminal'] for e in train), train_prior=constant,
        development=value_metrics(net, dev, constant), selection='No selection or retuning from these diagnostics.'))
    print(json.dumps(json.loads((folder / 'value.json').read_text())), flush=True)


class ReservePolicy:
    """Unseen opponent deliberately waits to afford a visible expensive body."""
    name = 'unseen_public_reserve'
    def choose(self, obs, actions):
        result = ReferencePolicy('guard').choose(obs, actions)
        if result['action'][0] != 'play' or sum(u['a'] for u in obs['enemy']) + 5 >= obs['hp']: return result
        expensive = [h['cost'] for h in obs['hand'] if h['cost'] >= 5 and h['health']]
        if expensive and obs['cash'] < min(expensive):
            result.update(action=actions[0], action_index=0)
        return result


def final(folder):
    if (folder / 'final.json').exists() or (folder / 'final-games.jsonl.gz').exists(): raise ValueError('Final is single use')
    d = json.loads((folder / 'design.json').read_text()); net = Network.load(folder / 'primary-value.npz')[0]
    old = Network.load('card_eval/models/shared-policy.npz')[0]; own = base_deck(); others = opponents()
    param = Spec('unseen_parameter', 5, 8, 3, (('armor', 1),), ())
    composed = Spec('unseen_taunt_end_draw', 5, 2, 7, (('taunt', 1),), (Effect('end', 'draw', 'owner', 1),))
    pool = {semantic_key(s) for s in training_pool()}
    if semantic_key(param) in pool or semantic_key(composed) in pool: raise ValueError('Heldout spec overlaps training')
    params = list(own); params[:3] = [param] * 3
    combo = list(own); combo[:3] = [composed] * 3
    cases = [('pressure', own, others['pressure'], ('INTEGRITY', 'INTEGRITY'), 'race'),
             ('defense', own, others['defense'], ('INTEGRITY', 'KINDNESS'), 'race'),
             ('refill', own, others['refill'], ('KINDNESS', 'INTEGRITY'), 'race'),
             ('new_parameters', tuple(params), others['pressure'], ('INTEGRITY', 'INTEGRITY'), 'race'),
             ('new_composition', tuple(combo), others['pressure'], ('INTEGRITY', 'INTEGRITY'), 'race'),
             ('new_structure', others['pressure'], others['refill'], ('KINDNESS', 'INTEGRITY'), 'guard'),
             ('unseen_reserve_opponent', own, others['defense'], ('INTEGRITY', 'KINDNESS'), 'reserve')]
    # Persist complete final inputs and exact checkpoint fingerprints before reading outcomes.
    plan = dict(source_commit=commit(), primary_fingerprint=net.fingerprint, actor_fingerprint=net.actor_fingerprint,
        previous_fingerprint=old.fingerprint, cases=[dict(name=c[0], decks=[[asdict(s) for s in deck] for deck in c[1:3]],
        souls=c[3], opponent=c[4]) for c in cases], seeds=d['final_seeds'], value_seeds=d['value_final_seeds'],
        selection='All choices fixed before outcomes; final seeds are retired after this run.')
    dump(folder / 'final-plan.json', plan)
    def policy(name):
        if name == 'primary': return LearnedPolicy(net)
        if name == 'previous_v3': return LearnedPolicy(old)
        return ReferencePolicy(name)
    groups = []; failures = []; elapsed = time.monotonic()
    with gzip.open(folder / 'final-games.jsonl.gz', 'wt', encoding='utf-8') as sink:
        for group, a_deck, b_deck, souls, opponent in cases:
            scores = {name: [] for name in d['final_policies']}; times = {name: [] for name in scores}
            for seed in d['final_seeds']:
                seats = {name: [] for name in scores}
                for seat in (0, 1):
                    for name in scores:
                        b = ReservePolicy() if opponent == 'reserve' else ReferencePolicy(opponent)
                        r = game((a_deck, b_deck), seed, policy(name), b, seat, souls)
                        sink.write(json.dumps(dict(group=group, seed=seed, seat=seat, policy=name, result=small_result(r)), separators=(',', ':')) + '\n')
                        seats[name].append(None if r['unfinished'] else int(r['won'])); times[name].extend(r['decision_seconds'][0])
                        if r['unfinished']: failures.append(dict(group=group, seed=seed, seat=seat, policy=name, error=r.get('error')))
                for name in scores:
                    scores[name].append([np.mean([0 if x is None else x for x in seats[name]]), np.mean([1 if x is None else x for x in seats[name]])])
            lower, upper = np.asarray(scores['primary']).T; comparisons = []
            for name in scores:
                lo, hi = np.asarray(scores[name]).T
                comparisons.append(dict(policy=name, win=interval(lo, hi), primary_gain=interval(lower - hi, upper - lo)))
            groups.append(dict(group=group, policies=comparisons, timings={n: dict(decisions=len(t), p95=float(np.quantile(t, .95)), maximum=max(t)) for n, t in times.items()}))
            print(json.dumps(dict(group=group, wins={c['policy']: c['win']['completion_range'] for c in comparisons})), flush=True)
    prior = json.loads((folder / 'value.json').read_text())['train_prior']
    val = value_data(folder, net, 'final', d['value_final_seeds'])
    qualified = not failures and all(c['primary_gain']['low'] > 0 for g in groups for c in g['policies'] if c['policy'] in ('race', 'board', 'guard'))
    result = dict(status='complete', source_commit=commit(), groups=groups, failures=failures,
        qualified=qualified, primary_fingerprint=net.fingerprint, value_final=value_metrics(net, val, prior),
        elapsed_seconds=time.monotonic() - elapsed, no_final_selection=True, real_server_certified=False,
        acceptance=d['acceptance'], limitation=d['limitation'])
    dump(folder / 'final.json', result)
    dump(folder / 'validation.json', dict(qualified=qualified, status='qualified' if qualified else 'not_qualified',
        frozen_policy=net.fingerprint, source='final.json', default_model_replaced=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('mode', choices=['prepare', 'fit', 'development', 'value', 'final'])
    p.add_argument('--output', type=Path, required=True); args = p.parse_args()
    globals()[args.mode](args.output)
