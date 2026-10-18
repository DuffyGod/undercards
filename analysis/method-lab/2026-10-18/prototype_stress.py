"""Exact IceCap/Vulkin demand under all17 shared parameter stress points.

Also bound fixed-action ATK marginals over ALL baseline-optimal plans, so an
arbitrary label or floating-point tie cannot masquerade as strategy change.
"""
from pathlib import Path
from collections import defaultdict
import csv
import hashlib
import json

from statistical_value import Prices, best_value
from run_statistical_study import SELECTED, resources, mean_discount
from compressed_statistics import evaluate_compressed

HERE=Path(__file__).resolve().parent
OUT=HERE/'joint-stress'


def tie_envelope(base,upgraded,atol=1e-10):
    q=max(base.values());qa=max(upgraded.values())
    eligible=[name for name,value in base.items() if q-value<=atol]
    fixed=[upgraded[name]-q for name in eligible]
    return min(fixed),max(fixed),max(0.,qa-q-max(fixed))


def main():
    inputs=json.loads((HERE/'statistical_inputs.json').read_text(encoding='utf-8'))
    demand=json.loads((HERE/'demand-stress/panels.json').read_text(encoding='utf-8'))
    settings=json.loads((OUT/'joint-design.json').read_text(encoding='utf-8'))['settings']
    # The frozen pressure runner exposes the same physical four count boards.
    candidates=demand['panels'].get('icecap_vulkin')
    if candidates is None:
        raise ValueError('Expected icecap_vulkin panel in frozen demand source')
    if isinstance(candidates,dict):candidates=candidates['rows'] if 'rows' in candidates else candidates['panels']
    panels=[dict(r,enemy=tuple(tuple(e) for e in r['enemy'])) for r in candidates]
    _,handweights,costs=resources(inputs,'middle_cost')
    discounts={h:mean_discount(costs,h) for h in handweights}
    rows=[]
    for setting,parameters in settings.items():
        prices=Prices(inputs,**parameters)
        for cid in SELECTED:
            card=inputs['cards'][str(cid)]
            r=evaluate_compressed(card,inputs,panels,'aggro_wide',prices,True)
            lo=hi=premium=0.
            for panel in panels:
                for hand,hw in handweights.items():
                    _,_,base=best_value(card,inputs['cards'],panel['enemy'],hand,prices,'damage2',.1,discounts[hand],details=True)
                    _,_,up=best_value(card,inputs['cards'],panel['enemy'],hand,prices,'damage2',.1,discounts[hand],a_delta=1,details=True)
                    a,b,c=tie_envelope(base,up)
                    w=panel['weight']*hw;lo+=w*a;hi+=w*b;premium+=w*c
            row=dict(setting=setting,case='icecap_vulkin',id=cid,name=card['name'],
                **{k:v for k,v in r.items() if k not in ('by_hand_gross','board_values','changed_plan_mass')},
                fixed_baseline_optimal_plus_attack_min=lo,fixed_baseline_optimal_plus_attack_max=hi,
                mandatory_reoptimization_gain=premium)
            if not lo-1e-8<=row['fixed_policy_plus_attack']<=hi+1e-8:
                raise AssertionError('Canonical fixed plan lies outside optimal-set bounds')
            rows.append(row)
        prices.body.cache_clear();prices.scale.value.cache_clear();prices.scale.effective_attack.cache_clear()
    with (OUT/'prototype-scores.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    comparisons=[]
    for a,b in ((649,530),(49,984),(469,43),(20,13)):
        points=[]
        for setting in settings:
            by={r['id']:r for r in rows if r['setting']==setting}
            points.append(dict(setting=setting,difference=by[a]['net_value']-by[b]['net_value']))
        comparisons.append(dict(left=a,right=b,central=points[0]['difference'],
            minimum=min(p['difference'] for p in points),maximum=max(p['difference'] for p in points),points=points))
    provenance=dict(source_sha256={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in
        ('prototype_stress.py','compressed_statistics.py','statistical_value.py','run_statistical_study.py',
         'statistical_inputs.json','demand-stress/panels.json','joint-stress/joint-design.json')},
        rows=len(rows),comparisons=comparisons,settings=settings,
        demand='Three targets from IceCap3/1 and Vulkin4/4 independently with probability1/2, exact binomial count integration',
        uncertainty='Exact conditional arithmetic; theta/hand histogram/demand assumptions are not empirical certainty',
        tie_rule='all plans within1e-10 of baseline maximum; expected fixed-plan min/max over visible states')
    (OUT/'prototype-design.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(rows=len(rows),comparisons=comparisons),ensure_ascii=False))


if __name__=='__main__':main()
