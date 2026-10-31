"""Reproducible shared learning, frozen evaluation and carrying comparisons."""
from dataclasses import asdict
from pathlib import Path
import argparse, gzip, hashlib, json, random, subprocess, time
import numpy as np
from mechanisms import Spec, Effect, compile_text, UnsupportedRule
from environment import LearningGame, Config, bridge, DecisionBudgetExceeded, VERSION as ENGINE_VERSION
from agents import LearnedAgent, FixedAgent
from learner import Network
from records import Recorder, load_episodes

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OPPONENTS = (*bridge.COLS, bridge.Policy('heldout_window_race', order='window', guard=1,
             reserve_cards=2, reserve_gold=4, response_threshold=3, combat='frontier_race', heal_at=23))


def dump(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def source_commit(require_clean=True):
    if require_clean:
        changed = subprocess.check_output(['git', 'status', '--porcelain', '--', str(HERE)], cwd=ROOT, text=True)
        if changed.strip(): raise ValueError('Commit source/protocol before an official run')
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()


def from_dict(d):
    return Spec(**{**d, 'keywords': tuple(tuple(x) for x in d['keywords']),
                   'effects': tuple(Effect(**e) for e in d['effects'])})


def catalog():
    raw = json.loads((ROOT / 'skills/undercards/references/snapshot.json').read_text())['cards']
    mapped, rejected = {}, []
    for card in raw:
        if card['card_type'] != 'monster' or card['pool_category'] != 'ordinary_non_token': continue
        try: mapped[card['name']] = compile_text(card)
        except UnsupportedRule as exc: rejected.append(dict(id=card['id'], name=card['name'], reason=str(exc)))
    return mapped, rejected


def training_specs():
    rng = random.Random(613)
    families = [({}, ()), ({'haste': 1}, ()), ({'taunt': 1}, ()), ({'armor': 1}, ()),
        ({'dodge': 1}, ()), ({'charge': 1}, ()),
        ({}, (Effect('play', 'draw', 'owner', 1),)),
        ({}, (Effect('end', 'draw', 'owner', 1),)),
        ({}, (Effect('start', 'buff', 'self', 1),)),
        ({}, (Effect('end', 'buff', 'self', 1, 1),)),
        ({}, (Effect('play', 'silence', 'enemy'),)),
        ({}, (Effect('play', 'damage', 'all_enemy', 1),))]
    out = []
    for f, (keywords, effects) in enumerate(families):
        for j in range(2):
            # The held-out real-body and composed signatures are checked below.
            out.append(Spec(f'synthetic_train_{f}_{j}', rng.randint(2, 6), rng.randint(1, 6),
                            rng.randint(2, 8), tuple(keywords.items()), effects))
    return out


def prepare(dest, args):
    if dest.exists(): raise ValueError('Never overwrite an existing experiment')
    mapped, rejected = catalog(); train = training_specs()
    # Only training descriptions and predeclared tests, no outcomes are read.
    reserved = Spec('synthetic_haste_plus_draw', train[0].cost, train[0].attack, train[0].health,
                    (('haste', 1),), (Effect('play', 'draw', 'owner', 1),))
    cases = [
        dict(group='in_distribution', structure='wide', spec=asdict(train[0]), opponent=0),
        dict(group='heldout_parameters', structure='wide', spec=asdict(mapped['Aaron']), opponent=0),
        dict(group='heldout_mechanism_composition', structure='wide', spec=asdict(reserved), opponent=0),
        dict(group='heldout_deck_structure', structure='refill', spec=asdict(train[0]), opponent=0),
        dict(group='heldout_opponent', structure='wide', spec=asdict(train[0]), opponent=3),
    ]
    if (mapped['Aaron'].cost, mapped['Aaron'].attack, mapped['Aaron'].health) in {(s.cost, s.attack, s.health) for s in train}:
        raise ValueError('Held-out parameter tuple appeared in training')
    def structure(s):
        d = s.semantic(); return json.dumps([d['keywords'], d['effects']], sort_keys=True)
    if structure(reserved) in {structure(s) for s in train}: raise ValueError('Structural holdout leakage')
    design = dict(schema=1, engine=ENGINE_VERSION, source_commit=source_commit(),
        training_specs=list(map(asdict, train)), training_structures=['wide', 'anchor'],
        fixed_training_opponents=[0, 1], heldout_fixed_opponent=3,
        warmup_games=args.warmup, updates=args.updates, rollouts_per_update=args.rollouts,
        training_seed_start=610000, evaluation_seeds=list(range(710000, 710000 + args.eval_seeds)),
        replacement_seeds=list(range(720000, 720000 + args.eval_seeds)),
        cases=cases, warmup_rows=[0, 1, 2, 3, 4],
        replacement_cards=['Rock Pet', 'Froggit', 'Aaron', 'Spider', 'Bench', 'Fishing Rod', 'Bloody Tree', 'Scarf Mouse'],
        baseline_rows=[asdict(p) for p in bridge.ROWS], opponent_columns=[asdict(p) for p in OPPONENTS],
        decision_seconds=.25, search_nodes=16, value_search_ablation_nodes=8, value_search_ablation_seeds=32, seed=618,
        objectives='MC +/-1 for actual HP terminal in the declared role game. Unfinished is unlabelled.',
        selection='Last checkpoint fixed in advance. No model/hyperparameter selection from evaluation.',
        uncertainty='Paired seed clusters include both seat configurations; groups are experimental conditions, not meta weights.',
        silence_mode='retain', silence_status='Unverified modified-stat cleanup; retain/reset sensitivity is required.',
        full_game_scope='Aggregate roles plus composable ordinary bodies; no artifacts/mulligan/tribes/death effects/current-server certification.',
        old_experiments_rerun=0, new_api_calls=0)
    dest.mkdir(parents=True)
    dump(dest / 'design.json', design)
    dump(dest / 'mechanism-coverage.json', dict(mapped=[asdict(s) for s in mapped.values()],
                                              rejected=rejected, meaning='Strict full-text compilation, not empirical valuation'))
    print(json.dumps(dict(status='prepared', mapped=len(mapped), rejected=len(rejected), directory=str(dest))), flush=True)


def run_game(spec, seed, cfg, structure, agents, recorder=None, **kwargs):
    game = LearningGame(structure, seed, cfg, spec, agents, recorder=recorder, **kwargs)
    result = game.run()
    for p in game.players:
        if p.cash != 1 + p.income + p.bonus_gold - p.total_spent: raise ValueError('Gold accounting')
        if len(p.deck) + len(p.hand) + p.played + p.burned != 25: raise ValueError('Card accounting')
    return result


def train(dest):
    design = json.loads((dest / 'design.json').read_text()); source = source_commit()
    if (dest / 'training.json').exists(): raise ValueError('Never repeat/overwrite an official training run')
    status = dict(status='running', source_commit=source, games=0, terminal_games=0, truncated_games=0,
                  decision_records=0, optimizer_steps=0, seed_start=design['training_seed_start'])
    dump(dest / 'training.json', status)
    rng = random.Random(design['seed']); nrng = np.random.default_rng(design['seed'])
    net = Network(design['seed']); specs = list(map(from_dict, design['training_specs']))
    started = time.monotonic(); episode = 0
    stats = []

    def rollout(agents, sink, tag):
        nonlocal episode
        spec = rng.choice(specs); opponent_spec = rng.choice(specs)
        cfg = Config(rounds=40, seat=episode % 2, soul=rng.choice(('INTEGRITY', 'KINDNESS')),
                     response_kind=rng.choice(('sweep', 'focus')))
        seed = design['training_seed_start'] + episode
        rec = Recorder(f'{tag}-{episode}', sink, dict(seed=seed, spec=asdict(spec), opponent_spec=asdict(opponent_spec),
                       structure=None, stage=tag))
        host = rng.choice(design['training_structures']); rec.metadata['structure'] = host
        result = run_game(spec, seed, cfg, host, agents, rec, opponent_candidate=opponent_spec,
                          silence_mode=design['silence_mode'], decision_seconds=design['decision_seconds'])
        episode += 1; status['games'] += 1; status['decision_records'] += len(rec.rows)
        status['terminal_games'] += not result['unfinished']; status['truncated_games'] += result['unfinished']
        return rec, result

    try:
        warmup = []
        with gzip.open(dest / 'decisions-warmup.jsonl.gz', 'wt', encoding='utf-8') as sink:
            for i in range(design['warmup_games']):
                agents = (FixedAgent(bridge.ROWS[rng.choice(design['warmup_rows'])]), FixedAgent(bridge.COLS[rng.choice((0, 1))]))
                rec, _ = rollout(agents, sink, 'warmup'); warmup.extend(rec.samples(include_search=True))
        for epoch in range(3):
            nrng.shuffle(warmup)
            for i in range(0, len(warmup), 64): net.update(warmup[i:i + 64], imitation=True, lr=7e-4)
        status['warmup_samples'] = len(warmup)
        del warmup
        print(json.dumps(dict(stage='warmup_complete', games=status['games'], samples=status['warmup_samples'],
                              seconds=round(time.monotonic() - started, 1))), flush=True)
        snapshot, _ = None, None
        for update in range(design['updates']):
            samples = []; fp = net.fingerprint; outcomes = []
            with gzip.open(dest / f'decisions-selfplay-{update:03}.jsonl.gz', 'wt', encoding='utf-8') as sink:
                for j in range(design['rollouts_per_update']):
                    a = LearnedAgent(net, 810000 + episode * 2, stochastic=True, search_nodes=design['search_nodes'])
                    if j % 4 < 2:
                        b = LearnedAgent(net, 810001 + episode * 2, stochastic=True, search_nodes=design['search_nodes'])
                    elif j % 4 == 2 and snapshot is not None:
                        b = LearnedAgent(snapshot, 810001 + episode * 2, stochastic=True, search_nodes=design['search_nodes'])
                    else: b = FixedAgent(bridge.COLS[rng.choice((0, 1))])
                    rec, result = rollout((a, b), sink, 'selfplay')
                    samples.extend(rec.samples(learner_policy=fp)); outcomes.append(result['won'])
            losses = []
            for epoch in range(2):
                nrng.shuffle(samples)
                for i in range(0, len(samples), 64): losses.append(net.update(samples[i:i + 64], lr=3e-4))
            report = dict(update=update, games=status['games'], samples=len(samples),
                          sample_win=float(np.mean(outcomes)),
                          loss=float(np.mean([r['loss'] for r in losses])) if losses else None,
                          value_loss=float(np.mean([r['value_loss'] for r in losses])) if losses else None,
                          seconds=round(time.monotonic() - started, 1))
            stats.append(report)
            if update % 8 == 0:
                snapshot = Network(); snapshot.p = {k: v.copy() for k, v in net.p.items()}; snapshot._fingerprint = None
            if (update + 1) % 4 == 0 or update + 1 == design['updates']:
                status['optimizer_steps'] = net.step; dump(dest / 'training.json', dict(status, progress=stats))
                print(json.dumps(report), flush=True)
        status.update(status='complete', optimizer_steps=net.step, progress=stats, elapsed_seconds=time.monotonic() - started,
                      final_fingerprint=net.fingerprint, training_seed_end=design['training_seed_start'] + episode - 1)
        net.save(dest / 'policy.npz', dict(source_commit=source, design_sha256=hashlib.sha256((dest / 'design.json').read_bytes()).hexdigest(),
                                         training_seed_start=status['seed_start'], training_seed_end=status['training_seed_end']))
    except Exception as exc:
        status.update(status='failed', error=repr(exc)); dump(dest / 'training.json', status); raise
    dump(dest / 'training.json', status)


def interval(values, seed=19):
    values = np.asarray(values, dtype=float)
    if not len(values): return dict(mean=None, low=None, high=None, n=0)
    rng = np.random.default_rng(seed)
    boot = values[rng.integers(0, len(values), (4000, len(values)))].mean(axis=1)
    return dict(mean=float(values.mean()), low=float(np.quantile(boot, .025)),
                high=float(np.quantile(boot, .975)), n=len(values))


def bounded_interval(lower, upper):
    """Keep unresolved outcomes in the denominator under both completions."""
    lower, upper = np.asarray(lower), np.asarray(upper)
    lo, hi = interval(lower), interval(upper)
    return dict(mean=float(lower.mean()) if np.array_equal(lower, upper) else None,
                low=lo['low'], high=hi['high'], n=len(lower),
                completion_mean_range=[float(lower.mean()), float(upper.mean())],
                unresolved_seed_clusters=int(np.sum(lower != upper)))


def evaluate(dest, reuse_decisions=None, reuse_evaluation=None):
    source = source_commit(); design = json.loads((dest / 'design.json').read_text())
    training = json.loads((dest / 'training.json').read_text())
    if training['status'] != 'complete': raise ValueError('Incomplete training')
    if (dest / 'evaluation.json').exists(): raise ValueError('Evaluation cannot be overwritten')
    net, meta = Network.load(dest / 'policy.npz')
    if training['training_seed_end'] >= min(design['evaluation_seeds'] + design['replacement_seeds']):
        raise ValueError('Training/evaluation seed overlap')
    cache = {}; cached_records = {}
    if reuse_evaluation is not None:
        prior = json.loads((reuse_evaluation / 'evaluation.json').read_text())
        if prior['frozen_policy'] != net.fingerprint: raise ValueError('Recovery policy mismatch')
        with gzip.open(reuse_evaluation / 'evaluation-records.jsonl.gz', 'rt') as f:
            for r in map(json.loads, f): cached_records[(r['group'], r['seed'], r['seat'], r['policy'])] = r
        if 'common wall-time budget' in prior.get('error', ''):
            keys = [(c['group'], s, seat, name) for c in design['cases'] for s in design['evaluation_seeds']
                    for seat in (0, 1) for name in ['shared_policy_value'] + [p.name for p in bridge.ROWS]]
            failed = next(k for k in keys if k not in cached_records)
            cached_records[failed] = dict(zip(('group', 'seed', 'seat', 'policy'), failed)) | dict(
                won=None, lost=None, unfinished=True, error=prior['error'], error_kind='recovered_decision_budget',
                failure_attribution='Original exception did not record actor/action latency; do not infer it.',
                preserved_failure_source=str(reuse_evaluation / 'evaluation.json'))
        reuse_decisions = reuse_evaluation / 'evaluation-decisions.jsonl.gz'
    if reuse_decisions is not None:
        for rec in load_episodes(reuse_decisions):
            if not rec.result['terminated']: continue
            meta = rec.result['metadata']; key = (meta['group'], meta['seed'], meta['seat'])
            if any(r['policy'] != net.fingerprint for r in rec.rows if r['observation']['player'] == 0):
                raise ValueError('Cached episode used a different frozen learner')
            if rec.result['result']['seed'] != meta['seed']:
                raise ValueError('Cached episode seed mismatch')
            cache[key] = rec
    status = dict(status='running', source_commit=source, frozen_policy=net.fingerprint, records=0,
                  reused_completed_episodes=len(cache), reused_rows=len(cached_records),
                  reused_decision_file=str(reuse_decisions) if reuse_decisions else None)
    dump(dest / 'evaluation.json', status); started = time.monotonic()
    output = []; latencies = []; failures = []; missing_latency_rows = 0
    try:
        with gzip.open(dest / 'evaluation-records.jsonl.gz', 'wt', encoding='utf-8') as sink, \
             gzip.open(dest / 'evaluation-decisions.jsonl.gz', 'wt', encoding='utf-8') as decisions:
            for case in design['cases']:
                lower = [[] for _ in range(7)]; upper = [[] for _ in range(7)]
                for seed in design['evaluation_seeds']:
                    seat_scores = [[] for _ in range(7)]
                    for seat in (0, 1):
                        for row in range(7):
                            agent = LearnedAgent(net, search_nodes=design['search_nodes']) if row == 0 else FixedAgent(bridge.ROWS[row - 1])
                            spec = from_dict(case['spec'])
                            cfg = Config(rounds=40, seat=seat, soul='INTEGRITY', response_kind='sweep')
                            key = case['group'], seed, seat, agent.name
                            cached = cache.get((case['group'], seed, seat)) if row == 0 else None
                            if key in cached_records:
                                result = dict(cached_records[key])
                                result['decision_seconds'] = result.pop('decision_usage', [[], []])
                                if row == 0 and cached is not None:
                                    result['decision_seconds'] = [[r['seconds'] for r in cached.rows if r['observation']['player'] == a] for a in (0, 1)]
                                    for recrow in cached.rows + [cached.result]: decisions.write(json.dumps(recrow, separators=(',', ':')) + '\n')
                                elif row == 0:
                                    rec = Recorder(f"eval-{case['group']}-{seed}-{seat}", decisions, dict(group=case['group'], seed=seed, seat=seat))
                                    rec.finish(result)
                                if not result['decision_seconds'][0] and not result['unfinished']: missing_latency_rows += 1
                            elif cached is not None:
                                result = dict(cached.result['result'])
                                if result['config'] != asdict(cfg) or result['structure'] != case['structure']:
                                    raise ValueError('Cached episode condition mismatch')
                                if any(cached.rows[0]['observation'][k] != v for k, v in {'silence_mode': design['silence_mode']}.items()):
                                    raise ValueError('Cached rule assumption mismatch')
                                result['decision_seconds'] = [[r['seconds'] for r in cached.rows if r['observation']['player'] == a] for a in (0, 1)]
                                for recrow in cached.rows + [cached.result]:
                                    decisions.write(json.dumps(recrow, separators=(',', ':')) + '\n')
                            else:
                                recorder = Recorder(f"eval-{case['group']}-{seed}-{seat}", decisions,
                                    dict(group=case['group'], seed=seed, seat=seat)) if row == 0 else None
                                try:
                                    result = run_game(spec, seed, cfg, case['structure'],
                                        (agent, FixedAgent(OPPONENTS[case['opponent']])), recorder=recorder,
                                        silence_mode=design['silence_mode'], decision_seconds=design['decision_seconds'])
                                except (DecisionBudgetExceeded, UnsupportedRule) as exc:
                                    result = dict(seed=seed, won=None, lost=None, unfinished=True, error=repr(exc),
                                        error_kind=type(exc).__name__, decision_seconds=[[], []],
                                        failure_actor=getattr(exc, 'actor', None), failure_seconds=getattr(exc, 'seconds', None))
                                    if recorder is not None: recorder.finish(result)
                            record = {**{k: v for k, v in result.items() if k not in ('trace', 'snapshots', 'decision_seconds')},
                                      'group': case['group'], 'seed': seed, 'seat': seat, 'policy': agent.name}
                            record['decision_usage'] = result['decision_seconds']
                            sink.write(json.dumps(record, separators=(',', ':')) + '\n'); status['records'] += 1
                            latencies.extend((agent.name, x) for x in result['decision_seconds'][0])
                            if result['unfinished']:
                                failures.append(dict(group=case['group'], seed=seed, seat=seat, policy=agent.name,
                                    reason=result.get('error', 'HP terminal not reached'), error_kind=result.get('error_kind')))
                                seat_scores[row].append(None)
                            else: seat_scores[row].append(float(result['won']))
                    for row in range(7):
                        lower[row].append(float(np.mean([0 if x is None else x for x in seat_scores[row]])))
                        upper[row].append(float(np.mean([1 if x is None else x for x in seat_scores[row]])))
                learned_low, learned_high = np.asarray(lower[0]), np.asarray(upper[0])
                rows = []
                for i, policy in enumerate(bridge.ROWS):
                    rows.append(dict(policy=policy.name, win=bounded_interval(lower[i + 1], upper[i + 1]),
                        learned_gain=bounded_interval(learned_low - np.asarray(upper[i + 1]), learned_high - np.asarray(lower[i + 1]))))
                incomplete = any(np.any(np.asarray(lo) != np.asarray(hi)) for lo, hi in zip(lower, upper))
                output.append(dict(group=case['group'], case=case, incomplete=bool(incomplete),
                    learned_win=bounded_interval(learned_low, learned_high), baselines=rows))
                print(json.dumps(dict(group=case['group'], learned_win=output[-1]['learned_win'],
                                      records=status['records'], seconds=round(time.monotonic() - started, 1))), flush=True)
        summaries = {}
        for name in sorted({p for p, _ in latencies}):
            xs = [x for p, x in latencies if p == name]
            summaries[name] = dict(decisions=len(xs), median=float(np.median(xs)), p95=float(np.quantile(xs, .95)),
                                   maximum=max(xs), over_budget=sum(x > design['decision_seconds'] for x in xs))
        sufficient = len(design['evaluation_seeds']) >= 32
        passed = bool(sufficient and not failures and len(output) == 5 and
            all(not g.get('incomplete') and all(r['learned_gain']['low'] > 0 for r in g['baselines']) for g in output))
        status.update(status='complete', elapsed_seconds=time.monotonic() - started, groups=output,
            unfinished=failures, compute=dict(common_seconds_per_decision=design['decision_seconds'], measured=summaries,
            recovered_successful_rows_without_detailed_timings=missing_latency_rows,
            accounting='Feature extraction, inference and search included. Slow decisions are rejected by the environment.'),
            generalization_gate_passed=passed, gate_requires='At least32 independent seed clusters per group, no unresolved games, positive paired95%lower gain against EACH of six frozen policies in EACH of five groups.',
            real_game_certified=False, frozen_policy_unchanged=net.fingerprint == status['frozen_policy'],
            value_validation='Terminal Monte Carlo training only; independent held-out calibration is reported separately by audit script.')
    except Exception as exc:
        status.update(status='failed', error=repr(exc)); dump(dest / 'evaluation.json', status); raise
    dump(dest / 'evaluation.json', status)


def replacements(dest):
    source = source_commit(); design = json.loads((dest / 'design.json').read_text())
    if (dest / 'replacements.json').exists(): raise ValueError('Replacement evidence cannot be overwritten')
    net, _ = Network.load(dest / 'policy.npz'); fingerprint = net.fingerprint
    mapped, _ = catalog(); all_scores = {}; diagnostic = {}; ruling = []
    with gzip.open(dest / 'replacement-records.jsonl.gz', 'wt', encoding='utf-8') as sink:
        for name in design['replacement_cards']:
            scores = []; rows = []
            for seed in design['replacement_seeds']:
                paired = []
                for seat in (0, 1):
                    result = run_game(mapped[name], seed, Config(rounds=40, seat=seat), 'wide',
                        (LearnedAgent(net, search_nodes=design['search_nodes']), FixedAgent(bridge.COLS[0])),
                        silence_mode=design['silence_mode'], decision_seconds=design['decision_seconds'])
                    if result['unfinished']: raise ValueError('Unfinished replacement stays unresolved')
                    r = {k: v for k, v in result.items() if k not in ('trace', 'snapshots', 'decision_seconds')}
                    r.update(card=name, seat=seat); sink.write(json.dumps(r, separators=(',', ':')) + '\n')
                    rows.append(r); paired.append(float(result['won']))
                scores.append(float(np.mean(paired)))
            all_scores[name] = scores
            diagnostic[name] = dict(win=interval(scores), games=len(rows), never_received=sum(r['candidate_drawn'] == 0 for r in rows),
                received_unplayed=sum(r['candidate_drawn'] > 0 and not r['candidate_played'] for r in rows),
                played=sum(r['candidate_played'] > 0 for r in rows), burned=sum(r['candidate_burned'] for r in rows),
                wait_turns=sum(r['candidate_wait'] for r in rows), unfunded_turns=sum(r['candidate_unfunded_turns'] for r in rows),
                slot_blocked_turns=sum(r['candidate_slot_blocked_turns'] for r in rows),
                first_punished_games=sum(r['first_punished'] > 0 for r in rows))
            print(json.dumps(dict(replacement=name, win=float(np.mean(scores)))), flush=True)
    # A deliberately unresolved ruling gets two explicit worlds, using one
    # frozen policy. No world is advertised as a current-server fact.
    grow = Spec('synthetic_growth', 3, 2, 4, effects=(Effect('end', 'buff', 'self', 1, 1),))
    silence_spec = mapped['Scarf Mouse']
    for mode in ('retain', 'reset'):
        scores = []
        for seed in design['replacement_seeds'][:16]:
            r = run_game(silence_spec, seed + 10000, Config(rounds=40), 'wide',
                (LearnedAgent(net, search_nodes=design['search_nodes']), LearnedAgent(net, search_nodes=design['search_nodes'])),
                opponent_candidate=grow, silence_mode=mode, decision_seconds=design['decision_seconds'])
            scores.append(None if r['unfinished'] else float(r['won']))
        ruling.append(dict(silence_mode=mode, scores=scores, seed_start=design['replacement_seeds'][0] + 10000,
                           win=interval([x for x in scores if x is not None]), unfinished=scores.count(None)))
    if fingerprint != net.fingerprint: raise ValueError('Policy changed across candidate comparisons')
    baseline = np.asarray(all_scores['Rock Pet'])
    dump(dest / 'replacements.json', dict(source_commit=source, frozen_policy=fingerprint, baseline='Rock Pet',
        cards=[dict(card=name, diagnostics=diagnostic[name], carrying_win_difference=interval(np.asarray(scores) - baseline))
               for name, scores in all_scores.items()], silence_sensitivity=ruling,
        estimand='Three predeclared entity slots replaced before shuffle; all shared seeds retained, including no draw/no play. Same frozen policy, no per-card retraining or diagnosis penalties added.',
        scope='Conditional aggregate-role host; primitive interactions only, no tribal synergies or real environment weights.'))


def ablate(dest):
    source = source_commit(); design = json.loads((dest / 'design.json').read_text())
    if (dest / 'value-search-ablation.json').exists(): raise ValueError('Preserve existing ablation')
    net, _ = Network.load(dest / 'policy.npz'); base = {}
    with gzip.open(dest / 'evaluation-records.jsonl.gz', 'rt') as f:
        for r in map(json.loads, f):
            if r['policy'] == 'shared_policy_value': base[(r['group'], r['seed'], r['seat'])] = r
    output = []
    with gzip.open(dest / 'value-search-ablation-records.jsonl.gz', 'wt') as sink:
        for case in design['cases']:
            differences = []; wins = []; maximum = 0.
            for seed in design['evaluation_seeds'][:design['value_search_ablation_seeds']]:
                seat_difference = []; seat_wins = []
                for seat in (0, 1):
                    r = run_game(from_dict(case['spec']), seed, Config(rounds=40, seat=seat), case['structure'],
                        (LearnedAgent(net, search_nodes=design['search_nodes'], value_nodes=design['value_search_ablation_nodes']),
                         FixedAgent(OPPONENTS[case['opponent']])), silence_mode=design['silence_mode'],
                        decision_seconds=design['decision_seconds'])
                    if r['unfinished']: raise ValueError('Unresolved ablation')
                    maximum = max(maximum, max(r['decision_seconds'][0]))
                    row = dict(group=case['group'], seed=seed, seat=seat, won=r['won'], lost=r['lost'],
                               max_seconds=max(r['decision_seconds'][0]), baseline_won=base[case['group'], seed, seat]['won'])
                    sink.write(json.dumps(row) + '\n'); seat_wins.append(float(r['won']))
                    seat_difference.append(float(r['won']) - float(row['baseline_won']))
                differences.append(float(np.mean(seat_difference))); wins.append(float(np.mean(seat_wins)))
            output.append(dict(group=case['group'], win=interval(wins), gain_over_policy_plus_lethal=interval(differences),
                               max_decision_seconds=maximum))
            print(json.dumps(output[-1]), flush=True)
    dump(dest / 'value-search-ablation.json', dict(source_commit=source, frozen_policy=net.fingerprint,
        value_search_nodes=design['value_search_ablation_nodes'], groups=output,
        selection='Predeclared ablation only; no checkpoint, parameter or primary-policy selection from evaluation outcomes.',
        uncertainty='Same held-out seed prefixes as primary evaluation; correlated comparisons, not extra independent validation seeds.'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'train', 'evaluate', 'replacements', 'ablate'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--warmup', type=int, default=96)
    parser.add_argument('--updates', type=int, default=48)
    parser.add_argument('--rollouts', type=int, default=8)
    parser.add_argument('--eval-seeds', type=int, default=64)
    parser.add_argument('--reuse-decisions', type=Path)
    parser.add_argument('--reuse-evaluation', type=Path)
    args = parser.parse_args()
    if args.mode == 'prepare': prepare(args.output, args)
    elif args.mode == 'evaluate': evaluate(args.output, args.reuse_decisions, args.reuse_evaluation)
    else: globals()[args.mode](args.output)


if __name__ == '__main__': main()
