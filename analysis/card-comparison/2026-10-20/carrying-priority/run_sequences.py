"""Freeze new fixed-deployment opening diagnostics, not a deck optimizer."""
import argparse,gzip,json,subprocess,time
from pathlib import Path
from opening_sequence import (HERE,OpeningGraph,BodyScale,POLICIES,ENEMY_SCRIPTS,
                              OWN_INITIAL,OWN_DRAWS,ENEMY_INITIAL,ENEMY_DRAWS)
from package_model import settings

ROOT=HERE.parents[3]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--pilot',action='store_true')
    p.add_argument('--policies',nargs='+',choices=tuple(POLICIES))
    args=p.parse_args()
    if args.output.exists():p.error('New evidence directory required')
    paths=[str((HERE/n).relative_to(ROOT)) for n in ('opening_sequence.py','run_sequences.py')]
    if subprocess.check_output(['git','status','--porcelain','--',*paths],cwd=ROOT,text=True).strip():
        p.error('Commit numerical sources before producing evidence')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    args.output.mkdir(parents=True);start=time.monotonic()
    cards={str(c['id']):c for c in json.loads((ROOT/'skills/undercards/references/snapshot.json').read_text())['cards']}
    reference=json.loads((ROOT/'analysis/method-lab/2026-10-18/statistical_inputs.json').read_text())['reference']
    prices=settings();points=[(k,.5,1.) for k in prices]+[('central',.5,0.),('central',.5,2.)]
    policies=('staggered_three','late_same_three','bridge_draw_5','bridge_5') if args.pilot else tuple(POLICIES)
    if args.policies:policies=tuple(args.policies)
    enemies=('empty',) if args.pilot else ('empty','two_low','mid_pressure')
    seats=('first',) if args.pilot else ('first','second')
    souls=('INTEGRITY',) if args.pilot else ('INTEGRITY','KINDNESS')
    horizons=(4,) if args.pilot else (4,5)
    if args.pilot:points=[('central',.5,1.)]
    out={};nodes=0;graphs=0;failures=[]
    for seat in seats:
        for soul in souls:
            for enemy in enemies:
                for horizon in horizons:
                    key=f'{seat}/{soul}/{enemy}/t{horizon}';out[key]={}
                    for policy in policies:
                        if seat=='first' and policy in ('draw_accelerates_two','normal_two_later','save_9_at3','save_5_at2','draw_5_at2'):
                            continue  # These exact 12G scripts are affordable only second.
                        try:g=OpeningGraph(cards,policy,enemy,seat,soul,horizon)
                        except ValueError as error:
                            failures.append(dict(case=key,policy=policy,error=str(error)));continue
                        graphs+=1;nodes+=len(g.edges);results=[]
                        for name,lam,rho in points:
                            price=prices[name];scale=BodyScale(reference,price['face_share'],price['threshold'])
                            results.append(dict(setting=name,cash_price=lam,hand_price=rho,
                                                **g.evaluate(scale,price['face_price'],lam,rho)))
                        out[key][policy]=dict(graph_nodes=len(g.edges),results=results)
    design=dict(producer_source_commit=revision,assessment_kind='heuristic',empirically_calibrated=False,
                policies={k:POLICIES[k] for k in policies},enemy_scripts={k:ENEMY_SCRIPTS[k] for k in enemies},
                seats=seats,souls=souls,horizons=horizons,price_settings=prices,price_points=points,
                own_initial=OWN_INITIAL,own_draw_prefix=OWN_DRAWS,enemy_initial=ENEMY_INITIAL,enemy_draw_prefix=ENEMY_DRAWS,
                initial_board='Both empty; both30HP and1G',enemy_soul='INTEGRITY',
                arrival_assumption='Three initial cards, one known draw each own turn including t1; no mulligan; Bench draws from SAME sequence',
                search_scope='Perfect-information optimal ordinary combat, with prescribed deployments BEFORE combat; no alternative plays, spells, artifacts or hidden hands',
                second_only_policies=['draw_accelerates_two','normal_two_later','save_9_at3','save_5_at2','draw_5_at2'],
                objective='Lexicographic match result then F own minus F enemy, nonlethal HP difference, own cash and homogeneous remaining-hand price',
                interpretation='Conditional mechanisms and carrying heuristics, not match win rates or optimized deck curves',
                raw_record_scope='Each evaluated price saves its selected complete minimax witness and endpoint; full game DAGs are counted but not archived')
    for file,data in [('design.json',design),('failures.json',failures),('receipt.json',dict(
          physical_graphs=graphs,graph_nodes_summed=nodes,case_groups=len(out),price_points=len(points),
          failed_graphs=len(failures),api_calls=0,old_producers_executed=False,seconds=time.monotonic()-start))]:
        (args.output/file).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    with gzip.open(args.output/'sequences.json.gz','wt',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False)
    print(json.dumps(json.loads((args.output/'receipt.json').read_text())))
    if failures:raise SystemExit(1)


if __name__=='__main__':main()
