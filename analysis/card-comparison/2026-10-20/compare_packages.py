"""Query saved package evidence. No battle search or API call."""
import argparse,gzip,json
from itertools import combinations
from pathlib import Path
from package_model import HERE,score,clip


def compare(settings,left,right,lam,mu):
    planes=[];states=[]
    for name,result in settings.items():
        a=next((r for r in result['packages'] if r['package']==sorted(left)),None)
        b=next((r for r in result['packages'] if r['package']==sorted(right)),None)
        if a is None or b is None:raise ValueError('Both exact packages must exist in this same visible-hand and budget window')
        states.append((a['feasible'],b['feasible']))
        if a['feasible'] and b['feasible']:
            plane=[a['intercept']-b['intercept'],b['net_paid']-a['net_paid'],b['cards_used']-a['cards_used']]
            planes.append(dict(setting=name,coefficients=plane,left_minus_right=score(a,lam,mu)-score(b,lam,mu),
                               left_order=a['play_order'],right_order=b['play_order']))
    if len(set(states))!=1:raise ValueError('Physical feasibility cannot depend on prices')
    if not all(states[0]):return dict(left_feasible=states[0][0],right_feasible=states[0][1],numeric_difference=None)
    left_poly=[[0.,0.],[1.,0.],[1.,3.],[0.,3.]];right_poly=[p[:] for p in left_poly]
    for plane in planes:
        a,b,c=plane['coefficients'];left_poly=clip(left_poly,a,b,c);right_poly=clip(right_poly,-a,-b,-c)
    return dict(left_feasible=True,right_feasible=True,
                minimum=min(p['left_minus_right'] for p in planes),maximum=max(p['left_minus_right'] for p in planes),
                planes=planes,interpretation='a+b*cash_price+c*hand_price; no empirical probability over settings',
                left_weakly_preferred_all_settings_polygon=left_poly,
                right_weakly_preferred_all_settings_polygon=right_poly,
                polygon_domain=dict(cash_price=[0,1],hand_price=[0,3]))


def query(data,design,case,lam,mu,left=None,right=None):
    if case not in data:raise ValueError('Unknown case; use --list-cases')
    if not 0<=lam<=1 or not 0<=mu<=3:raise ValueError('Use declared display ranges: cash [0,1], hand [0,3]')
    result=data[case];selection={}
    for name,setting in result['settings'].items():
        feasible=[r for r in setting['packages'] if r['feasible']]
        best=max(feasible,key=lambda r:score(r,lam,mu)) if feasible else None
        selection[name]=None if best is None else dict(package=best['package'],play_order=best['play_order'],
                    value=score(best,lam,mu),paid=best['paid'],refund=best['refund'],cash_after=best['cash_after'],
                    cards_used=best['cards_used'],remaining_hand=best['remaining_hand'],
                    guaranteed_hp=best['guaranteed_hp'],guaranteed_bodies=best['guaranteed_bodies'],
                    minimum_hp_reply=best['minimum_hp_reply'],minimum_body_reply=best['minimum_body_reply'],
                    asset_worst_reply=best['asset_worst_reply'])
    out=dict(assessment_kind='heuristic',empirically_calibrated=False,case=case,condition=design['cases'][case],
             economy=result['economy'],prices=dict(cash=lam,hand=mu),best_by_shared_setting=selection,
             scope=design['conditional_scope'],producer_source_commit=design['producer_source_commit'],
             hand_price_warning=design['hand_price_interpretation'],
             witness_warning='HP, body and asset minima can have different witnesses; do not splice them')
    if (left is None)!=(right is None):raise ValueError('Specify both --left and --right')
    if left is not None:out['comparison']=compare(result['settings'],left,right,lam,mu)
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,default=HERE/'arrival-results')
    p.add_argument('--case');p.add_argument('--list-cases',action='store_true')
    p.add_argument('--cash-price',type=float,default=.5);p.add_argument('--hand-price',type=float,default=0.)
    p.add_argument('--left',type=int,nargs='*');p.add_argument('--right',type=int,nargs='*')
    args=p.parse_args()
    try:
        design=json.loads((args.results/'design.json').read_text())
        if args.list_cases:out=list(design['cases'])
        else:
            with gzip.open(args.results/'packages.json.gz','rt',encoding='utf-8') as f:data=json.load(f)
            out=query(data,design,args.case,args.cash_price,args.hand_price,args.left,args.right)
    except (ValueError,KeyError,FileNotFoundError) as e:p.error(str(e))
    print(json.dumps(out,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
