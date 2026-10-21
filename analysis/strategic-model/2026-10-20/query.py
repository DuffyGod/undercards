"""Read frozen strategic-role results; does not simulate or optimize real decks."""
from pathlib import Path
import argparse,csv,json
HERE=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment',type=Path,default=HERE/'experiment-v01')
    p.add_argument('--world',default='sweep_integrity_seat0')
    p.add_argument('--structure');p.add_argument('--against',default='immediate')
    p.add_argument('--goal',choices=['profile','win_by_deadline','survive_deadline','deadline_life','eventual_bounds','final_outcomes'],default='profile')
    p.add_argument('--policies',action='store_true');a=p.parse_args()
    summary=json.loads((a.experiment/'derived/summary.json').read_text())
    world=next((w for w in summary['results'] if w['world']==a.world),None)
    if world is None:raise ValueError('Unknown frozen world; no inferred interpolation')
    if a.policies:
        output={k:v for k,v in world.items() if k not in ('train_matrix','test_matrix')}
        output['objective_warning']='Original deadline-life fit only; not a generic strength recommendation. See --goal final_outcomes and eventual_bounds.'
    elif a.goal=='eventual_bounds':
        bounds=json.loads((a.experiment/'derived/completion-bounds.json').read_text())
        output=next(w for w in bounds['findings'] if w['world']==a.world)
    elif a.goal=='final_outcomes':
        final=json.loads((HERE/'objective-validation-v01/continuation/summary.json').read_text())
        output=next((w for w in final['results'] if w['world']==a.world),None)
        if output is None:raise ValueError('No frozen objective continuation for this world')
        output=dict(output,scope=final['interpretation'])
    else:
        with (a.experiment/'derived/cells.csv').open() as f:
            rows=[r for r in csv.DictReader(f) if r['world']==a.world and r['column']==a.against and (not a.structure or r['structure']==a.structure)]
        if not rows:raise ValueError('Unknown condition')
        # A purpose must be explicit before ranking. Default preserves the
        # whole profile instead of silently equating HP with competitiveness.
        if a.goal!='profile':
            key={'win_by_deadline':'won','survive_deadline':'lost','deadline_life':'life'}[a.goal]
            rows.sort(key=lambda r:float(r[key]),reverse=a.goal!='survive_deadline')
        output=dict(world=a.world,against=a.against,rows=rows,
            goal=a.goal,interpretation='Held-out conditional abstract profiles. Any goal-specific sorting is descriptive, not independent validation or a real card/deck ranking. Default profile has no scalar winner; final_outcomes compares frozen objective policies at actual termination.')
    print(json.dumps(output,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
