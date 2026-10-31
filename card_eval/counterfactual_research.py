"""Paired action-continuation targets, with whole-episode splits and new finals.

Branches share a newly sampled training prefix. Reusing that prefix is a
counterfactual intervention, not an independent game or replay of old evidence.
No engine transition is reimplemented. Agents never receive private state.
"""
from dataclasses import asdict
from pathlib import Path
import argparse, gzip, json, random, time
import numpy as np
from .advantage_model import AdvantageNetwork, encode, head_features
from .catalog import Spec, Effect, semantic_key
from .network import Network
from .game import NativeGame, DecisionBudgetExceeded
from .policies import ReferencePolicy, LearnedPolicy, lethal
from .profiles import training_pool, base_deck, opponents
from .training import dump, commit, decode
from .relational_research import small_result, ValueRecorder, value_metrics, phase_metrics, paired_value_gain
from .statistics import interval

BASELINE = Path('artifacts/card_eval/v4/primary-value.npz')


def prepare(folder):
    if folder.exists(): raise ValueError('Preserve experiment')
    folder.mkdir(parents=True)
    dump(folder / 'design.json', dict(schema=1, source_commit=commit(), baseline=str(BASELINE), rng_seed=2026103105,
        train_seeds=list(range(1040000, 1040384)), diagnostic_seeds=list(range(1140000, 1140096)),
        development_seeds=list(range(1450000, 1450016)), final_seeds=list(range(1610000, 1610064)),
        value_train_seeds=list(range(1050000, 1050384)), value_dev_seeds=list(range(1150000, 1150096)),
        value_final_seeds=list(range(1630000, 1630096)),
        forks_per_episode=2, max_actions=6, continuations=['baseline', 'race'],
        fork_sampling='One random Actor0 multi-action decision in turns2..5 and one in6..12; exclude public32-node immediate lethal; fallback to distinct eligible decisions if stratum absent. No outcome-based sampling.',
        action_sampling='Always end and baseline action, then one per available kind and uniform remaining actions, capped6. Unobserved action outcomes remain missing.',
        deck_distribution='Equal random/pressure/defense/refill semantic weighted 25-card decks, at most3 per source descriptor; both players sampled independently.',
        action_target='Within-fork centered mean terminal win over frozen baseline/race continuation. Opponent held fixed for each sampled episode. Not Q* or value of the new greedy policy.',
        l2=.01, optimizer_iterations=160, margins=[0., .05, .1, .2],
        selection='Highest mean development win over five predeclared contexts; ties choose larger margin. Diagnostic contrast data never selects weights. No final tuning or reselection.',
        decision_seconds=.25, previous_experiments_replayed=0,
        final_cases=['pressure', 'defense', 'refill', 'new_parameters', 'new_composition', 'new_structure', 'delayed_sweep_opponent'],
        final_policies=['primary', 'previous_v4', 'previous_v3', 'race', 'board', 'guard'],
        acceptance='Positive paired95% lower gain against every causal reference and V4 in every final context, zero unresolved slots. Value prediction alone cannot qualify.',
        partial_observation='Public semantic observation only; no deck order, RNG, actual opponent hand/composition or hidden-state online search.',
        limits='One training seed; finite history, no belief learning; mixed-policy continuation target can disagree with resulting greedy policy; simulator rules unchanged.'))


def policy(name, baseline): return LearnedPolicy(baseline) if name == 'baseline' else ReferencePolicy(name)


def draw_deck(rng, pool, role):
    bag = list(pool) * 3; result = []
    for _ in range(25):
        weights = []
        for s in bag:
            draw = sum(e.amount for e in s.effects if e.op == 'draw'); heal = sum(e.amount for e in s.effects if e.op == 'heal')
            score = (0. if role == 'random' else .22 * s.attack - .16 * s.cost - .15 * draw if role == 'pressure' else
                     .15 * s.health + .6 * s.keyword('taunt') + .2 * heal if role == 'defense' else 1.4 * draw + .06 * s.health)
            weights.append(np.exp(min(3., score)))
        index = rng.choices(range(len(bag)), weights=weights)[0]; result.append(bag.pop(index))
    return tuple(result)


def sample_inputs(rng):
    pool = training_pool(); roles = [rng.choice(('random', 'pressure', 'defense', 'refill')) for _ in range(2)]
    decks = tuple(draw_deck(rng, pool, role) for role in roles)
    souls = tuple(rng.choice(('INTEGRITY', 'KINDNESS')) for _ in range(2))
    return decks, souls, roles


class RollinRecorder:
    def __init__(self, sink, seed): self.sink = sink; self.seed = seed; self.rows = []
    def record(self, obs, actions, selected):
        row = dict(record_type='decision', episode=self.seed, decision=len(self.rows), observation=obs,
                   legal_actions=actions, selection=selected)
        self.rows.append(row); self.sink.write(json.dumps(row, separators=(',', ':')) + '\n')
    def finish(self, result):
        self.sink.write(json.dumps(dict(record_type='outcome', episode=self.seed, result=small_result(result)), separators=(',', ':')) + '\n')


def run(decks, seed, agents, seat, souls, recorder=None):
    try: return NativeGame(decks, seed, agents, seats=seat, souls=souls, recorder=recorder).run()
    except DecisionBudgetExceeded as e:
        r = dict(won=None, lost=None, unfinished=True, error=str(e), decision_seconds=[[], []])
        if recorder: recorder.finish(r)
        return r


class PrefixController:
    def __init__(self, rows, fork, action, agents):
        self.rows = rows; self.fork = fork; self.action = tuple(action); self.agents = agents; self.index = 0; self.checked = False
    def choose(self, obs, actions):
        index = self.index; self.index += 1
        if index <= self.fork:
            expected = self.rows[index]
            if json.dumps(obs,sort_keys=True) != json.dumps(expected['observation'],sort_keys=True) or list(map(tuple, expected['legal_actions'])) != actions:
                raise ValueError('Counterfactual common prefix/observation mismatch')
            action = self.action if index == self.fork else tuple(expected['selection']['action'])
            if index == self.fork: self.checked = True
            if action not in actions: raise ValueError('Illegal fork intervention')
            return dict(action=action, action_index=actions.index(action), value=0., behavior_probability=1.,
                        policy='training_prefix_or_intervention', search_override=False, seconds=0.)
        return self.agents[obs['player']].choose(obs, actions)


class PrefixAgent:
    name = 'offline_counterfactual_branch'
    def __init__(self, controller): self.controller = controller
    def choose(self, obs, actions): return self.controller.choose(obs, actions)


def collect(folder, stage):
    d = json.loads((folder / 'design.json').read_text()); seeds = d[stage + '_seeds']
    if (folder / f'{stage}-collection.json').exists() or list(folder.glob(f'{stage}-forks-*.jsonl.gz')): raise ValueError('Preserve collection')
    baseline = Network.load(d['baseline'])[0]; rng = random.Random(d['rng_seed'] + (stage == 'diagnostic'))
    status = dict(source_commit=commit(), stage=stage, episodes=0, forks=0, branches=0, unresolved_branches=0,
                  rejected_rollins=0, prefix_assertions=0, elapsed_seconds=0); start_time = time.monotonic()
    for start in range(0, len(seeds), 32):
        with gzip.open(folder / f'{stage}-rollins-{start:04}.jsonl.gz', 'wt', encoding='utf-8') as rollins, gzip.open(folder / f'{stage}-forks-{start:04}.jsonl.gz', 'wt', encoding='utf-8') as sink:
            for i, seed in enumerate(seeds[start:start + 32], start):
                decks, souls, roles = sample_inputs(rng); opponent = ('race', 'board', 'guard')[i % 3]; behavior = ('baseline', 'race')[i % 2]
                metadata = dict(record_type='input', seed=seed, decks=[[asdict(s) for s in deck] for deck in decks], souls=souls, roles=roles,
                                seat=i % 2, opponent=opponent, behavior=behavior)
                rollins.write(json.dumps(metadata, separators=(',', ':')) + '\n')
                rec = RollinRecorder(rollins, seed); r = run(decks, seed, (policy(behavior, baseline), policy(opponent, baseline)), i % 2, souls, rec)
                status['episodes'] += 1; status['rejected_rollins'] += r['unfinished']
                eligible = [j for j, row in enumerate(rec.rows) if row['observation']['player'] == 0 and len(row['legal_actions']) > 1
                            and not lethal(row['observation'])[0]]
                selected = []
                for lo, hi in ((2, 5), (6, 12)):
                    options = [j for j in eligible if lo <= rec.rows[j]['observation']['turn'] <= hi and j not in selected]
                    if not options: options = [j for j in eligible if j not in selected]
                    if options: selected.append(rng.choice(options))
                for fork in selected:
                    row = rec.rows[fork]; obs = row['observation']; actions = list(map(tuple, row['legal_actions']))
                    base_action = policy('baseline', baseline).choose(obs, actions)['action_index']; indices = {0, base_action}
                    for kind in ('play', 'attack'):
                        candidates = [j for j, a in enumerate(actions) if a[0] == kind]
                        if candidates: indices.add(rng.choice(candidates))
                    candidates = [j for j in range(len(actions)) if j not in indices]; rng.shuffle(candidates)
                    indices.update(candidates[:max(0, d['max_actions'] - len(indices))]); results = []
                    for action_index in sorted(indices):
                        for continuation in d['continuations']:
                            controller = PrefixController(rec.rows, fork, actions[action_index], (policy(continuation, baseline), policy(opponent, baseline)))
                            b = run(decks, seed, (PrefixAgent(controller), PrefixAgent(controller)), i % 2, souls)
                            if not controller.checked: raise ValueError('Branch did not reach intervention')
                            status['branches'] += 1; status['prefix_assertions'] += 1; status['unresolved_branches'] += b['unfinished']
                            results.append(dict(action_index=action_index, continuation=continuation, won=b['won'], lost=b['lost'],
                                                unfinished=b['unfinished'], error=b.get('error'), a_hp=b.get('a_hp'), b_hp=b.get('b_hp'), round=b.get('round')))
                    sink.write(json.dumps(dict(seed=seed, decision=fork, observation=obs, legal_actions=actions,
                        sampled_action_indices=sorted(indices), baseline_action=base_action, branches=results), separators=(',', ':')) + '\n')
                    status['forks'] += 1
        status['elapsed_seconds'] = time.monotonic() - start_time
        print(json.dumps(status), flush=True); dump(folder / f'{stage}-progress.json', status)
    dump(folder / f'{stage}-collection.json', status)


def groups(folder, stage):
    output = []
    for path in sorted(folder.glob(f'{stage}-forks-*.jsonl.gz')):
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                if any(b['unfinished'] for b in row['branches']): continue
                actions = list(map(tuple, row['legal_actions'])); state, af = encode(row['observation'], actions)
                indices = row['sampled_action_indices']; target = []
                for index in indices:
                    branches = [b for b in row['branches'] if b['action_index'] == index]
                    if len(branches) != 2: raise ValueError('Incomplete paired continuation labels')
                    target.append(np.mean([int(b['won']) for b in branches]))
                output.append((head_features(state, af)[indices], np.asarray(target), row))
    return output


def fit(folder):
    if (folder / 'fit.json').exists(): raise ValueError('Preserve fit')
    d = json.loads((folder / 'design.json').read_text()); baseline = Network.load(d['baseline'])[0]
    data = groups(folder, 'train'); net = AdvantageNetwork(baseline.actor.copy())
    report = net.fit_advantage([(x, y) for x, y, _ in data], d['l2'], d['optimizer_iterations'])
    contrast = int(sum(np.ptp(y) > 0 for _, y, _ in data))
    net.save(folder / 'action-head.npz', dict(source_commit=commit(), validation=dict(qualified=False), target=d['action_target'], value_unfitted=True, fit=report))
    dump(folder / 'fit.json', dict(source_commit=commit(), fit=report, contrast_groups=contrast, flat_groups=len(data) - contrast,
        source_forks=json.loads((folder / 'train-collection.json').read_text())['forks'], frozen_baseline=baseline.fingerprint))


class DelayedSweepPolicy:
    name = 'public_wait_for_two_sweep_kills'
    def choose(self, obs, actions):
        permitted = []
        for a in actions:
            h = next((h for h in obs['hand'] if h['uid'] == a[1]), None) if a[0] == 'play' else None
            sweeps = [e for e in h['effects'] if e['trigger'] == 'play' and e['op'] == 'damage' and e['scope'] == 'all_enemy'] if h else []
            kills = sum(not u['dodge'] and e['amount'] - int(u['armor']) >= u['h'] for e in sweeps for u in obs['enemy'])
            if sweeps and kills < 2 and obs['hp'] > sum(u['a'] for u in obs['enemy']) + 4: continue
            permitted.append(a)
        result = ReferencePolicy('board').choose(obs, permitted); result['action_index'] = actions.index(result['action']); return result


def cases(final=False):
    own = base_deck(); others = opponents()
    if not final:
        return [('pressure', own, others['pressure'], ('INTEGRITY', 'INTEGRITY'), 'race'),
                ('defense', own, others['defense'], ('INTEGRITY', 'KINDNESS'), 'race'),
                ('refill', own, others['refill'], ('KINDNESS', 'INTEGRITY'), 'race'),
                ('role_pressure', others['pressure'], others['defense'], ('KINDNESS', 'INTEGRITY'), 'guard'),
                ('role_refill', others['refill'], others['pressure'], ('INTEGRITY', 'KINDNESS'), 'board')]
    param = Spec('unseen_6G_9_4_dodge', 6, 9, 4, (('dodge', 1),), ())
    combo = Spec('unseen_charge_end_growth', 5, 4, 5, (('charge', 1),), (Effect('end', 'buff', 'self', 1, 1),))
    pool = {semantic_key(s) for s in training_pool()}
    if semantic_key(param) in pool or semantic_key(combo) in pool: raise ValueError('Final card overlaps training pool')
    params = list(own); params[:3] = [param] * 3; combos = list(own); combos[:3] = [combo] * 3
    sweep = Spec('synthetic_delayed_sweeper', 5, 0, 5, (), (Effect('play', 'damage', 'all_enemy', 3),))
    counter = list(others['defense']); counter[:3] = [sweep] * 3
    return cases()[:3] + [('new_parameters', tuple(params), others['pressure'], ('INTEGRITY', 'INTEGRITY'), 'race'),
        ('new_composition', tuple(combos), others['pressure'], ('INTEGRITY', 'INTEGRITY'), 'race'),
        ('new_structure', others['refill'], others['pressure'], ('KINDNESS', 'KINDNESS'), 'guard'),
        ('delayed_sweep_opponent', own, tuple(counter), ('INTEGRITY', 'KINDNESS'), 'delayed')]


def development(folder):
    if (folder / 'selection.json').exists(): raise ValueError('Preserve selection')
    d = json.loads((folder / 'design.json').read_text()); net = Network.load(folder / 'action-head.npz')[0]; output = []
    with gzip.open(folder / 'development-games.jsonl.gz', 'wt', encoding='utf-8') as sink:
        for margin in d['margins']:
            net.margin = margin; scores = []
            for name, own, other, souls, opponent in cases():
                for seed in d['development_seeds']:
                    r = run((own, other), seed, (LearnedPolicy(net), ReferencePolicy(opponent)), seed % 2, souls)
                    scores.append(0 if r['unfinished'] else int(r['won']))
                    sink.write(json.dumps(dict(group=name, margin=margin, seed=seed, result=small_result(r)), separators=(',', ':')) + '\n')
            output.append(dict(margin=margin, mean_win_lower=float(np.mean(scores)), scores=scores)); print(json.dumps(output[-1]), flush=True)
    chosen = max(output, key=lambda r: (r['mean_win_lower'], r['margin']))['margin']; net.margin = chosen
    net.save(folder / 'selected-actor.npz', dict(source_commit=commit(), validation=dict(qualified=False), value_unfitted=True))
    dump(folder / 'selection.json', dict(source_commit=commit(), selected_margin=chosen, candidates=output, selection=d['selection'], actor_fingerprint=net.actor_fingerprint))


def diagnostic(folder):
    if (folder / 'diagnostic.json').exists(): raise ValueError('Preserve diagnostic')
    net = Network.load(folder / 'selected-actor.npz')[0]; data = groups(folder, 'diagnostic'); errors = []; zero_errors = []
    advantages = {}; oracle = {}; agreements = []; baseline_agreements = []; changed = 0
    for x, y, row in data:
        pred = x @ net.advantage; errors.append(float(np.mean(((pred - pred.mean()) - (y - y.mean())) ** 2)))
        zero_errors.append(float(np.mean((y-y.mean())**2)))
        base = row['sampled_action_indices'].index(row['baseline_action']); best = int(pred.argmax())
        selected = best if pred[best] - pred[base] > net.margin else base
        advantages.setdefault(row['seed'], []).append(float(y[selected] - y[base])); changed += selected != base
        oracle.setdefault(row['seed'], []).append(float(y.max()-y[base]))
        if np.ptp(y) > 0:
            agreements.append(y[selected] == y.max()); baseline_agreements.append(y[base] == y.max())
    dump(folder / 'diagnostic.json', dict(source_commit=commit(), groups=len(data), centered_mse=float(np.mean(errors)),
        zero_centered_mse=float(np.mean(zero_errors)), changed=changed, contrast_groups=len(agreements),
        sampled_best_accuracy=float(np.mean(agreements)) if agreements else None,
        baseline_sampled_best_accuracy=float(np.mean(baseline_agreements)) if baseline_agreements else None,
        sampled_terminal_oracle_gain=interval([np.mean(v) for v in oracle.values()]),
        paired_continuation_gain=interval([np.mean(v) for v in advantages.values()]), limitation='Sampled actions only; forks clustered by seed. This is a continuation-target diagnostic, not closed-loop win or policy qualification.'))


def value_data(folder, net, stage, seeds):
    rng = random.Random(20261031050 + {'train': 0, 'dev': 1, 'final': 2}[stage]); output = []
    for start in range(0, len(seeds), 64):
        with gzip.open(folder / f'value-{stage}-{start:04}.jsonl.gz', 'wt', encoding='utf-8') as sink:
            for i, seed in enumerate(seeds[start:start + 64], start):
                decks, souls, roles = sample_inputs(rng); opponent = ('race', 'board', 'guard')[i % 3]
                rec = ValueRecorder(sink, seed, dict(seed=seed, decks=[[asdict(s) for s in deck] for deck in decks], souls=souls,
                    roles=roles, seat=i % 2, opponent=opponent, actor_fingerprint=net.actor_fingerprint))
                r = run(decks, seed, (LearnedPolicy(net), ReferencePolicy(opponent)), i % 2, souls, rec)
                output.append(dict(seed=seed, terminal=not r['unfinished'], won=r['won'], states=rec.states))
    return output


def value(folder):
    if (folder / 'value.json').exists() or list(folder.glob('value-*.jsonl.gz')): raise ValueError('Preserve value data')
    d = json.loads((folder / 'design.json').read_text()); net = Network.load(folder / 'selected-actor.npz')[0]
    train = value_data(folder, net, 'train', d['value_train_seeds']); xs = []; ys = []; weights = []
    for e in train:
        if not e['terminal']: continue
        xs.extend(e['states']); ys.extend([int(e['won'])] * len(e['states'])); weights.extend([1 / len(e['states'])] * len(e['states']))
    before = net.actor_fingerprint; report = net.fit_value(xs, ys, weights, l2=.01)
    if before != net.actor_fingerprint: raise ValueError('Value fit changed action model')
    prior = float(np.mean([int(e['won']) for e in train if e['terminal']]))
    net.save(folder / 'primary-value.npz', dict(source_commit=commit(), validation=dict(qualified=False),
        target='Own frozen greedy gated actor under equal race/board/guard and structured-deck training distribution.', value_unfitted=False))
    simple = AdvantageNetwork(net.actor.copy(), advantage=net.advantage.copy(), margin=net.margin)
    states = np.asarray(xs)
    reduced = np.c_[np.ones(len(states)),states[:,1]-states[:,2],states[:,26]-states[:,39],states[:,27]-states[:,40],states[:,8]-states[:,9]]
    simple_report = simple.fit_value(reduced,ys,weights,l2=.01); coefficients=simple.critic.copy(); simple.critic=np.zeros(74); simple.critic[0]=coefficients[0]
    for coefficient,(pos,neg) in zip(coefficients[1:],((1,2),(26,39),(27,40),(8,9))):
        simple.critic[pos]=coefficient; simple.critic[neg]=-coefficient
    simple.save(folder/'value-hp-board.npz',dict(source_commit=commit(),validation=dict(qualified=False),purpose='Fixed five-parameter value baseline for the same frozen actor.'))
    dev = value_data(folder, net, 'dev', d['value_dev_seeds'])
    dump(folder / 'value.json', dict(source_commit=commit(), fit=report, train_prior=prior, actor_unchanged=True, actor_fingerprint=before,
        train_episodes=len(train), train_decisions=len(xs), train_unresolved=sum(not e['terminal'] for e in train), development=value_metrics(net, dev, prior),
        simple_fit=simple_report, simple_development=value_metrics(simple,dev,prior), primary_gain_vs_simple=paired_value_gain(net,simple,dev)))


def final(folder):
    if (folder / 'final.json').exists() or (folder / 'final-games.jsonl.gz').exists(): raise ValueError('Final is used once')
    d = json.loads((folder / 'design.json').read_text()); net = Network.load(folder / 'primary-value.npz')[0]
    previous = Network.load(BASELINE)[0]; v3 = Network.load('card_eval/models/shared-policy.npz')[0]
    simple = Network.load(folder/'value-hp-board.npz')[0]
    inputs = cases(True); dump(folder / 'final-plan.json', dict(source_commit=commit(), primary_fingerprint=net.fingerprint,
        actor_fingerprint=net.actor_fingerprint, selected_margin=net.margin, seeds=d['final_seeds'], cases=[dict(group=n,
        decks=[[asdict(s) for s in deck] for deck in (a, b)], souls=s, opponent=p) for n, a, b, s, p in inputs]))
    def agent(name):
        if name == 'primary': return LearnedPolicy(net)
        if name == 'previous_v4': return LearnedPolicy(previous)
        if name == 'previous_v3': return LearnedPolicy(v3)
        return ReferencePolicy(name)
    groups_out = []; failures = []; elapsed = time.monotonic()
    with gzip.open(folder / 'final-games.jsonl.gz', 'wt', encoding='utf-8') as sink:
        for group, own, other, souls, opponent in inputs:
            scores = {name: [] for name in d['final_policies']}; times = {name: [] for name in scores}
            for seed in d['final_seeds']:
                seats = {name: [] for name in scores}
                for seat in (0, 1):
                    for name in scores:
                        b = DelayedSweepPolicy() if opponent == 'delayed' else ReferencePolicy(opponent)
                        r = run((own, other), seed, (agent(name), b), seat, souls)
                        sink.write(json.dumps(dict(group=group, seed=seed, seat=seat, policy=name, result=small_result(r)), separators=(',', ':')) + '\n')
                        seats[name].append(None if r['unfinished'] else int(r['won'])); times[name].extend(r['decision_seconds'][0])
                        if r['unfinished']: failures.append(dict(group=group, seed=seed, seat=seat, policy=name, error=r.get('error')))
                for name in scores:
                    scores[name].append((np.mean([0 if v is None else v for v in seats[name]]), np.mean([1 if v is None else v for v in seats[name]])))
            lo, hi = np.asarray(scores['primary']).T; comparisons = []
            for name, rows in scores.items():
                a, b = np.asarray(rows).T
                comparisons.append(dict(policy=name, win=interval(a, b), primary_gain=interval(lo - b, hi - a)))
            groups_out.append(dict(group=group, policies=comparisons, timings={n:dict(decisions=len(t),p95=float(np.quantile(t,.95)),maximum=max(t)) for n,t in times.items()}))
            print(json.dumps(dict(group=group, wins={c['policy']:c['win']['completion_range'] for c in comparisons})), flush=True)
    val = value_data(folder, net, 'final', d['value_final_seeds']); prior = json.loads((folder / 'value.json').read_text())['train_prior']
    qualified = not failures and all(c['primary_gain']['low'] > 0 for g in groups_out for c in g['policies'] if c['policy'] in ('previous_v4','race','board','guard'))
    result = dict(status='complete', source_commit=commit(), qualified=qualified, groups=groups_out, failures=failures,
        primary_fingerprint=net.fingerprint, value_final=value_metrics(net,val,prior), value_phases_final=phase_metrics(net,val,prior),
        value_simple_final=value_metrics(simple,val,prior), value_gain_vs_simple=paired_value_gain(net,simple,val),
        no_final_selection=True, elapsed_seconds=time.monotonic()-elapsed, acceptance=d['acceptance'], real_server_certified=False)
    dump(folder / 'final.json', result); dump(folder / 'validation.json',dict(qualified=qualified,status='qualified' if qualified else 'not_qualified',
        frozen_policy=net.fingerprint,default_model_replaced=False,source='final.json'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('mode', choices=['prepare','collect','fit','development','diagnostic','value','final'])
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--stage',choices=['train','diagnostic']); args=parser.parse_args()
    if args.mode == 'collect': collect(args.output,args.stage)
    else: globals()[args.mode](args.output)
