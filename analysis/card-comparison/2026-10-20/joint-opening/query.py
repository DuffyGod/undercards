"""Query saved causal opening groups, or paired differences. No simulation."""
import argparse,json
from pathlib import Path
from analyze import load,summarize,paired,METRICS,EXTRA
HERE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',default='main');p.add_argument('--compare-stage')
    p.add_argument('--composition',required=True);p.add_argument('--compare-composition')
    p.add_argument('--policy',default='balanced');p.add_argument('--compare-policy')
    p.add_argument('--soul',default='KINDNESS');p.add_argument('--opponent',default='large_reply');p.add_argument('--compare-opponent')
    p.add_argument('--seat',choices=('first','second'),default='first')
    p.add_argument('--intervention',default='base');p.add_argument('--compare-intervention')
    p.add_argument('--metrics',nargs='+',choices=METRICS+EXTRA,default=['killed','dead','opponent_hp','hp','any_slot_missed','burned'])
    args=p.parse_args()
    spec,groups=load(HERE/args.stage)
    specifier=dict(composition=args.composition,policy=args.policy,soul=args.soul,opponent=args.opponent,
                   seat=int(args.seat=='second'),intervention=args.intervention)
    def select(which,source_groups=groups):
        rows=[r for g,r in source_groups if g==which]
        if len(rows)!=1:raise ValueError('Requested cell absent/ambiguous; no interpolation')
        return rows[0]
    left=select(specifier)
    comparisons=[(k,getattr(args,'compare_'+k)) for k in ('composition','policy','intervention','opponent') if getattr(args,'compare_'+k)]
    if len(comparisons)>1:raise ValueError('Change only one field per query')
    if comparisons:
        key,v=comparisons[0];right_spec=specifier|{key:v}
        right_source,right_groups=load(HERE/(args.compare_stage or args.stage))
        stats=paired(left,select(right_spec,right_groups))
        out=dict(left=specifier,right=right_spec,difference='left minus right',
                 reference_stage=args.compare_stage or args.stage,reference_version=right_source['version'],reference_commit=right_source['source_commit'])
    else:stats=summarize(left);out=dict(group=specifier)
    out.update(version=spec['version'],source_commit=spec['source_commit'],metrics={k:stats[k] for k in args.metrics},interpretation='These composition/shuffle/policy assumptions only; not real win probability.')
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
