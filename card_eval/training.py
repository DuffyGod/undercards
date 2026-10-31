"""Second-generation learning with DAgger, normalized PPO and a fresh test split."""
from dataclasses import asdict
from pathlib import Path
import argparse, gzip, json, random, subprocess, time
import numpy as np
from .catalog import Spec, Effect, semantic_key
from .profiles import training_pool, base_deck, opponents
from .game import NativeGame, DecisionBudgetExceeded
from .network import Network, encode
from .policies import ReferencePolicy, LearnedPolicy
from .trajectory import Recorder

ROOT = Path(__file__).resolve().parents[1]


def dump(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def commit(): return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()


def prepare(folder, warmup=512, dagger=4, updates=96, rollouts=16):
    if folder.exists(): raise ValueError('Preserve existing run')
    pool = training_pool()
    design = dict(schema=2, seed=2026103102, source_commit=commit(),
        pool=[asdict(s) for s in pool], warmup_games=warmup, dagger_rounds=dagger, dagger_games=96,
        ppo_updates=updates, rollouts=rollouts, training_seed_start=1010000,
        development_seeds=list(range(1110000, 1110016)), test_seeds=list(range(1210000, 1210064)),
        replay_capacity=8192, teacher='semantic_race', checkpoint_every=16,
        selection='Choose among predeclared checkpoints using development mean win only. Test never selects or retrains.',
        objective='Only model HP-terminal +/-1. No labels for deadline/budget failures.',
        scope='Two explicit25-card semantic decks, no role-host substitution. Supported rule grammar only.',
        decision_seconds=.25, new_api_calls=0, previous_experiments_rerun=0)
    folder.mkdir(parents=True); dump(folder / 'design.json', design)


def decode(d):
    return Spec(d['name'], d['cost'], d['attack'], d['health'], tuple(tuple(x) for x in d['keywords']),
                tuple(Effect(**e) for e in d['effects']), d.get('card_id'))


def train(folder):
    d = json.loads((folder / 'design.json').read_text()); pool = list(map(decode, d['pool']))
    if (folder / 'training.json').exists(): raise ValueError('Training cannot overwrite previous evidence')
    if subprocess.check_output(['git', 'status', '--porcelain', '--', 'card_eval', str(folder)], cwd=ROOT, text=True).strip():
        raise ValueError('Commit source and design first')
    rng = random.Random(d['seed']); nrng = np.random.default_rng(d['seed']); net = Network(d['seed'])
    status = dict(status='running', source_commit=commit(), games=0, terminal=0, rejected=0, decisions=0,
                  phases=[], checkpoints=[])
    dump(folder / 'training.json', status); replay = []; seen = 0; started = time.monotonic()

    def add(samples):
        nonlocal seen
        for s in samples:
            seen += 1
            if len(replay) < d['replay_capacity']: replay.append(s)
            else:
                index = rng.randrange(seen)
                if index < len(replay): replay[index] = s

    def rollout(agents, sink, stage, teacher=None):
        # Random full decks from shared parameter/mechanism pool, legal at most3.
        lists = [tuple(rng.sample(pool * 3, 25)) for _ in range(2)]
        # Sampling repeated references can exceed3 only when the source pool
        # itself contains duplicate semantic objects; it is unique by name.
        episode = status['games']; seed = d['training_seed_start'] + episode
        souls = (rng.choice(('INTEGRITY', 'KINDNESS')), rng.choice(('INTEGRITY', 'KINDNESS')))
        rec = Recorder(f'{stage}-{episode}', sink, teacher=teacher,
                       metadata=dict(stage=stage, seed=seed, souls=souls, decks=[[s.name for s in deck] for deck in lists]))
        g = NativeGame(lists, seed, agents, seats=episode % 2, souls=souls, recorder=rec)
        try: result = g.run()
        except DecisionBudgetExceeded as exc:
            result = dict(unfinished=True, won=None, lost=None, error=str(exc)); rec.finish(result)
        status['games'] += 1; status['decisions'] += len(rec.rows)
        status['terminal'] += not result['unfinished']; status['rejected'] += result['unfinished']
        return rec, result

    def fit(samples, epochs, imitation, lr):
        losses = []
        for _ in range(epochs):
            nrng.shuffle(samples)
            for i in range(0, len(samples), 64):
                losses.append(net.update(samples[i:i + 64], imitation=imitation, lr=lr, entropy=.005))
        return float(np.mean([x['loss'] for x in losses])) if losses else None

    def checkpoint(name):
        net.save(folder / (name + '.npz'), dict(source_commit=status['source_commit'], training_games=status['games'],
                 training_seed_start=d['training_seed_start'], training_seed_end=d['training_seed_start'] + status['games'] - 1,
                 feature_scope='explicit_decks', generalization_passed=False))
        status['checkpoints'].append(name + '.npz')

    try:
        for start in range(0, d['warmup_games'], 64):
            with gzip.open(folder / f'decisions-warmup-{start:04}.jsonl.gz', 'wt', encoding='utf-8') as sink:
                for _ in range(min(64, d['warmup_games'] - start)):
                    rec, _ = rollout((ReferencePolicy('race'), ReferencePolicy(rng.choice(('race', 'board', 'guard')))), sink, 'warmup')
                    add(rec.training_samples(imitation=True))
            print(json.dumps(dict(stage='warmup', games=status['games'], replay=len(replay), seconds=round(time.monotonic() - started, 1))), flush=True)
        fit(replay, 5, True, 7e-4); checkpoint('warmup')
        for step in range(d['dagger_rounds']):
            fresh = []
            with gzip.open(folder / f'decisions-dagger-{step:02}.jsonl.gz', 'wt', encoding='utf-8') as sink:
                for j in range(d['dagger_games']):
                    rec, _ = rollout((LearnedPolicy(net), ReferencePolicy(rng.choice(('race', 'board', 'guard')))),
                                     sink, 'dagger', teacher=ReferencePolicy('race'))
                    fresh.extend(rec.training_samples(imitation=True))
            add(fresh); loss = fit(replay, 2, True, 4e-4)
            checkpoint(f'dagger-{step:02}')
            print(json.dumps(dict(stage='dagger', step=step, games=status['games'], loss=loss,
                                  seconds=round(time.monotonic() - started, 1))), flush=True)
        snapshot = None
        for update in range(d['ppo_updates']):
            samples = []; fp = net.fingerprint
            with gzip.open(folder / f'decisions-ppo-{update:03}.jsonl.gz', 'wt', encoding='utf-8') as sink:
                for j in range(d['rollouts']):
                    a = LearnedPolicy(net, seed=2010000 + status['games'], stochastic=True)
                    if j % 4 < 2: b = LearnedPolicy(net, seed=3010000 + status['games'], stochastic=True)
                    elif j % 4 == 2 and snapshot is not None: b = LearnedPolicy(snapshot, seed=3010000 + status['games'], stochastic=True)
                    else: b = ReferencePolicy(rng.choice(('race', 'board', 'guard')))
                    rec, _ = rollout((a, b), sink, 'ppo'); samples.extend(rec.training_samples(policy=fp))
            if samples:
                advantages = np.asarray([s['return'] - s['old_value'] for s in samples])
                normalized = (advantages - advantages.mean()) / max(advantages.std(), .1)
                for s, adv in zip(samples, normalized): s['advantage'] = float(np.clip(adv, -3, 3))
            loss = fit(samples, 2, False, 2e-4)
            if update % 8 == 0:
                snapshot = Network(); snapshot.p = {k: v.copy() for k, v in net.p.items()}; snapshot._fingerprint = None
            if (update + 1) % d['checkpoint_every'] == 0: checkpoint(f'ppo-{update + 1:03}')
            if (update + 1) % 4 == 0:
                status['phases'].append(dict(stage='ppo', update=update, games=status['games'], samples=len(samples),
                                            loss=loss, seconds=round(time.monotonic() - started, 1)))
                dump(folder / 'training.json', status); print(json.dumps(status['phases'][-1]), flush=True)
        if not status['checkpoints'][-1].startswith('ppo'): checkpoint('final')
        status.update(status='complete', seconds=time.monotonic() - started, optimizer_steps=net.step)
    except Exception as exc:
        status.update(status='failed', error=repr(exc)); dump(folder / 'training.json', status); raise
    dump(folder / 'training.json', status)


def development(folder):
    d = json.loads((folder / 'design.json').read_text()); status = json.loads((folder / 'training.json').read_text())
    if status['status'] != 'complete': raise ValueError('Incomplete training')
    if (folder / 'selection.json').exists(): raise ValueError('Do not replace development selection')
    groups = opponents(); results = []
    for checkpoint in status['checkpoints']:
        net, _ = Network.load(folder / checkpoint); wins = []; raw = []
        for name, other in groups.items():
            for seed in d['development_seeds']:
                seat = seed % 2
                r = NativeGame((base_deck(), other), seed, (LearnedPolicy(net), ReferencePolicy('race')),
                               seats=seat, souls=('INTEGRITY', 'KINDNESS' if name == 'defense' else 'INTEGRITY')).run()
                wins.append(float(r['won']) if not r['unfinished'] else 0.)
                raw.append(dict(profile=name, seed=seed, seat=seat, won=r['won'], lost=r['lost'], unfinished=r['unfinished']))
        score = float(np.mean(wins)); results.append(dict(checkpoint=checkpoint, development_score=score, records=raw))
        print(json.dumps(dict(checkpoint=checkpoint, development_score=score)), flush=True)
    chosen = max(results, key=lambda r: r['development_score'])['checkpoint']
    dump(folder / 'selection.json', dict(source_commit=commit(), selected=chosen, candidates=results,
         selection='Development only, ties retain earlier checkpoint. Test outcome has not been read.'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('mode', choices=['prepare', 'train', 'development'])
    parser.add_argument('--output', required=True, type=Path); args = parser.parse_args()
    globals()[args.mode](args.output)
