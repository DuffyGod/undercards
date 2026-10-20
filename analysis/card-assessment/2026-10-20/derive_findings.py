"""Local cross-card counterfactuals and carrying surfaces, no pool averages."""
import json,csv
from value_ledger import *
from build_assessments import derive,PROFILES,B

def best(cid,root,prices):
    options=derive(cid,PROFILES[cid][0],root)
    options=[l for l in options if l['valuation_stage']=='deployment']
    if not options:raise ValueError('No current-window option')
    chosen=max(options,key=lambda l:quote(l,prices)['net_payment_margin'])
    return dict(ledger=chosen,quote=quote(chosen,prices))

def main():
    out=HERE/'results';cases=[]
    for prices in [CENTRAL]+PRICE_CORNERS:
        wideA=best(21,'wide',prices);wideB=best(236,'wide',prices)
        smallA=best(21,'small',prices);smallB=best(236,'small',prices)
        dw=wideA['quote']['decline_or_play_surplus']-wideB['quote']['decline_or_play_surplus']
        ds=smallA['quote']['decline_or_play_surplus']-smallB['quote']['decline_or_play_surplus']
        q=-ds/(dw-ds) if dw!=ds else None
        cases.append(dict(prices=prices,wide_plane=wideA,wide_hotdog=wideB,single_plane=smallA,single_hotdog=smallB,
            optional_delta_wide=dw,optional_delta_single=ds,required_wide_fraction=q,
            scope='Only two specified ordinary target conditions, current causal action choices, equal extra holding/replacement cost. Fraction unknown; not real meta frequency.'))
    (out/'family-comparisons.json').write_text(json.dumps(dict(plane_hotdog=cases),ensure_ascii=False,indent=2)+'\n')
    rows=[]
    for h in (3,5,8):
        for a in range(1,13):
            l=dict(own_before=[],enemy_before=[B(a,h)],own_after=[B(6,a+3)],enemy_after=[B(1,h)],paid_gold=8,events={})
            v=quote(l);rows.append(dict(enemy_attack=a,enemy_hp=h,gross=v['absolute_gross'],net=v['net_payment_margin']))
    with (out/'toriel-target-surface.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    good=derive(8,'toriel','tall')[0];bad=derive(8,'toriel','small')[0]
    curves=[carrying(good,bad,q=q/20,holding_cost=h) for h in (0,.75,1.5) for q in range(21)]
    (out/'carrying-surface.json').write_text(json.dumps(curves,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(central_wide_delta=cases[0]['optional_delta_wide'],central_single_delta=cases[0]['optional_delta_single'],required_wide_fraction=cases[0]['required_wide_fraction'])))

if __name__=='__main__':main()
