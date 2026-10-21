"""Read frozen strategic-role results; does not simulate or optimize real decks."""
from pathlib import Path
import argparse,csv,json
HERE=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment',type=Path,default=HERE/'experiment-v01')
    p.add_argument('--world',default='sweep_integrity_seat0')
    p.add_argument('--structure');p.add_argument('--against',default='immediate')
    p.add_argument('--policies',action='store_true');a=p.parse_args()
    summary=json.loads((a.experiment/'derived/summary.json').read_text())
    world=next((w for w in summary['results'] if w['world']==a.world),None)
    if world is None:raise ValueError('Unknown frozen world; no inferred interpolation')
    if a.policies:
        output={k:v for k,v in world.items() if k not in ('train_matrix','test_matrix')}
    else:
        with (a.experiment/'derived/cells.csv').open() as f:
            rows=[r for r in csv.DictReader(f) if r['world']==a.world and r['column']==a.against and (not a.structure or r['structure']==a.structure)]
        if not rows:raise ValueError('Unknown condition')
        # This is a read-only held-out table, not a new fitted recommendation.
        rows.sort(key=lambda r:float(r['life']),reverse=True)
        output=dict(world=a.world,against=a.against,rows=rows,
            interpretation='Held-out conditional results of abstract role strategies. Use --policies for train-frozen choices; sorting test rows is descriptive, not independent validation or a real card/deck ranking.')
    print(json.dumps(output,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
