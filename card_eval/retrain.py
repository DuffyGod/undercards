"""Reuse decision-level data, correct teacher labels, then collect new PPO data."""
from pathlib import Path
import argparse, gzip, json, random, time
import numpy as np
from .training import train, dump, commit
from .network import Network, encode
from .policies import ReferencePolicy


def prepare(folder, original):
    if folder.exists(): raise ValueError('Preserve existing runs')
    previous = json.loads((original / 'design.json').read_text())
    design = dict(previous, source_commit=commit(), training_seed_start=1020000,
        warmup_games=0, dagger_rounds=0, ppo_updates=96, rollouts=16,
        offline_source=str(original), offline_sample_capacity=12288,
        development_seeds=list(range(1111000, 1111016)),
        explanation='Reuse recorded observations; consistently label all imitation actions with one causal race teacher. Separate play/attack semantic channels. No previous game is re-simulated.')
    folder.mkdir(parents=True); dump(folder / 'design.json', design)


def offline(folder):
    design = json.loads((folder / 'design.json').read_text()); source = Path(design['offline_source'])
    if (folder / 'offline.npz').exists(): raise ValueError('Do not overwrite offline model')
    rng = random.Random(881); replay = []; seen = 0; teacher = ReferencePolicy('race'); started = time.monotonic()
    files = sorted(source.glob('decisions-warmup-*.jsonl.gz')) + sorted(source.glob('decisions-dagger-*.jsonl.gz'))
    for path in files:
        pending = {}
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            for raw in f:
                row = json.loads(raw); key = row['episode_id']
                if row['record_type'] == 'decision': pending.setdefault(key, []).append(row)
                else:
                    rows = pending.pop(key, [])
                    if not row['terminated']: continue
                    for r in rows:
                        obs = r['observation']; actions = list(map(tuple, r['legal_actions']))
                        label = teacher.choose(obs, actions)['action_index']
                        sample = dict(features=tuple(x.astype('float32') for x in encode(obs, actions)), chosen=label,
                            old_value=r['selection']['value'], behavior_probability=r['selection']['behavior_probability'],
                            **{'return': row['returns'][obs['player']]})
                        seen += 1
                        if len(replay) < design['offline_sample_capacity']: replay.append(sample)
                        else:
                            i = rng.randrange(seen)
                            if i < len(replay): replay[i] = sample
    net = Network(design['seed']); nrng = np.random.default_rng(885); epochs = []
    for epoch in range(10):
        nrng.shuffle(replay); reports = []
        for i in range(0, len(replay), 64): reports.append(net.update(replay[i:i + 64], imitation=True, lr=5e-4, entropy=.003))
        item = dict(epoch=epoch, loss=float(np.mean([r['loss'] for r in reports])), seconds=time.monotonic() - started)
        epochs.append(item); print(json.dumps(item), flush=True)
    net.save(folder / 'offline.npz', dict(source_commit=commit(), training_games=0, training_seed_start=1020000,
                                         training_seed_end=1019999, feature_scope='explicit_decks', generalization_passed=False))
    dump(folder / 'offline.json', dict(source_commit=commit(), input_files=[str(p) for p in files],
        decision_rows_seen=seen, retained_samples=len(replay), teacher='semantic_race', replayed_games=0, epochs=epochs))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('mode', choices=['prepare', 'offline'])
    parser.add_argument('--output', required=True, type=Path); parser.add_argument('--source', type=Path)
    args = parser.parse_args()
    if args.mode == 'prepare': prepare(args.output, args.source)
    else: offline(args.output)
