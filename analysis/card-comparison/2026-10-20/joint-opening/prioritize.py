"""Conditional carrying comparison by deadline, objective and acceptable risk.

Only reads five frozen composition families. No construction or simulation.
Marginal Wilson bounds can screen uncertainty; they are not a guarantee about
real matches, multiple comparisons, or both constraints simultaneously.
"""
import argparse,json
from analyze import HERE,load,wilson
from milestones import at_turn

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--opponent',choices=('mid','large_reply','pressure_mid','pressure_large'),required=True)
    p.add_argument('--seat',choices=('first','second'),required=True)
    p.add_argument('--turn',type=int,choices=range(1,9),default=8)
    p.add_argument('--objective',choices=('kill','pressure15','survival15'),default='kill')
    p.add_argument('--min-objective',type=float,default=0)
    p.add_argument('--max-death',type=float,default=1)
    p.add_argument('--conservative',action='store_true');args=p.parse_args()
    if not 0<=args.min_objective<=1 or not 0<=args.max_death<=1:raise ValueError('Probability constraints must be in [0,1]')
    stages=('stress','stress_extension') if args.opponent.startswith('pressure_') else ('tactics','extension')
    options=[]
    for stage in stages:
        spec,groups=load(HERE/stage)
        for g,rs in groups:
            if g['opponent']!=args.opponent or g['seat']!=int(args.seat=='second'):continue
            ms=[at_turn(r,args.turn) for r in rs]
            goal=lambda m:m['killed'] if args.objective=='kill' else m['pressure_15'] if args.objective=='pressure15' else m['hp']>=15
            success=sum(goal(m) for m in ms);dead=sum(m['dead'] for m in ms);n=len(ms)
            a=wilson(success,n);b=wilson(dead,n)
            goal_ok=(a[0] if args.conservative else success/n)>=args.min_objective
            risk_ok=(b[1] if args.conservative else dead/n)<=args.max_death
            options.append(dict(composition=g['composition'],stage=stage,n=n,
                objective_count=success,objective_rate=success/n,objective_wilson95=a,
                death_count=dead,death_rate=dead/n,death_wilson95=b,
                accepted=goal_ok and risk_ok,meets_objective=goal_ok,meets_risk=risk_ok))
    for a in options:
        a['empirical_pareto']=not any(b['objective_rate']>=a['objective_rate'] and b['death_rate']<=a['death_rate'] and
            (b['objective_rate']>a['objective_rate'] or b['death_rate']<a['death_rate']) for b in options)
    options.sort(key=lambda a:(not a['accepted'],-a['objective_rate'],a['death_rate']))
    print(json.dumps(dict(conditions=vars(args),own_soul='KINDNESS',own_policy='balanced',both_public_tactics=True,
        interpretation='Finite composition/causal-policy shuffle outcomes only. Empirical Pareto ignores sampling uncertainty; conservative screening uses marginal 95% Wilson bounds, not a simultaneous or real-match guarantee.',
        options=options),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
