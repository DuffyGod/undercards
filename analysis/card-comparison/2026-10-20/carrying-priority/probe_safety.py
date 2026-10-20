"""New endpoint-safety goal on the two scripts exposing life-price ambiguity."""
import argparse,json,subprocess
from opening_sequence import HERE,OpeningGraph,BodyScale

ROOT=HERE.parents[3]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--policies',nargs='+',choices=('bridge_5','save_9_at3','bridge_9'),default=('bridge_5','save_9_at3'))
    p.add_argument('--floors',nargs='+',type=int,default=(15,20))
    p.add_argument('--output',type=str,default='safety-probe.json')
    args=p.parse_args();output=HERE/args.output
    if output.exists():raise ValueError('Do not overwrite a probe')
    paths=[str((HERE/p).relative_to(ROOT)) for p in ('opening_sequence.py','probe_safety.py')]
    if subprocess.check_output(['git','status','--porcelain','--',*paths],cwd=ROOT,text=True).strip():
        raise ValueError('Commit probe sources first')
    cards={str(c['id']):c for c in json.loads((ROOT/'skills/undercards/references/snapshot.json').read_text())['cards']}
    inputs=json.loads((ROOT/'analysis/method-lab/2026-10-18/statistical_inputs.json').read_text())
    scale=BodyScale(inputs['reference'],.2,.4);rows=[]
    for policy in args.policies:
        graph=OpeningGraph(cards,policy,'mid_pressure','second','KINDNESS',5)
        for floor in args.floors:
            rows.append(dict(policy=policy,goal='Own endpoint HP at least '+str(floor),
                             **graph.evaluate(scale,.25,.5,1.,minimum_hp=floor)))
    output.write_text(json.dumps(dict(producer_source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
         case='second/KINDNESS/mid_pressure/t5',new_physical_graphs=len(args.policies),new_goals=args.floors,
         old_goal_one_not_rerun=True,rows=rows,api_calls=0,
         scope='Hard HP at cutoff, not a measured acceptable health level; fixed deployment scripts and ordinary combat only'),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([dict(policy=r['policy'],floor=r['minimum_hp'],guarantee=r['goal_guaranteed'],
                           hp=r['final']['players'][0]['hp'],value=r['value']) for r in rows]))


if __name__=='__main__':main()
