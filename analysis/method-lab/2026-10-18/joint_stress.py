"""Joint, common-parameter stress points; never interpret counts as probabilities.

Original conversion model remains frozen. Four factors at two levels, plus
the central setting; same demand panels and resources for every candidate.
"""
from collections import defaultdict
from itertools import product
from pathlib import Path
import argparse
import csv
import hashlib
import json
import math
import statistics

from statistical_value import Prices
from run_statistical_study import evaluate_one, SELECTED, SCENARIOS
from compressed_statistics import evaluate_compressed

HERE=Path(__file__).resolve().parent
OUT=HERE/'joint-stress'
FACTORS=dict(face_share=(.1,.35),threshold=(.2,.6),tail=(0.,1.),face=(.15,.4))
PAIRS=((49,984),(649,530),(469,43),(20,13))


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cards',nargs='+',type=int,default=SELECTED)
    parser.add_argument('--marginal-corners',action='store_true',help='Also pair +ATK/+HP at all stress points')
    parser.add_argument('--resource',default='middle_cost',choices=('lower_cost','middle_cost','higher_cost'))
    parser.add_argument('--tag',default='joint')
    args=parser.parse_args()
    OUT.mkdir(exist_ok=True)
    inputs=read(HERE/'statistical_inputs.json')
    design=read(HERE/'statistical-results/final-design.json')
    for filename,digest in design['sources'].items():
        if sha(HERE/filename)!=digest:raise RuntimeError('Frozen producer changed: '+filename)
    cases={k:dict(scenario=k,panels=[dict(p,enemy=tuple(tuple(e) for e in p['enemy'])) for p in design['panels'][k]],sampled=design['monte_carlo_panels'][k])
        for k in ('aggro_wide','midrange_single','control_silence','empty_development','wounded_wide')}
    survivor_panels=[]
    for p in design['panels']['aggro_wide']:
        # The prior AOE belongs to the common background, not to the focal card.
        survivor_panels.append(dict(enemy=tuple((a,h-2) for a,h in p['enemy'] if h>2),
            weight=p['weight'],source_ids=p['source_ids']))
    cases['aoe2_survivors']=dict(scenario='aggro_wide',panels=survivor_panels,sampled=True)
    for cfg in SCENARIOS.values():cfg['resource']=args.resource
    settings={'central':{}}
    names=list(FACTORS)
    for bits in product((0,1),repeat=len(names)):
        settings['corner_'+''.join(map(str,bits))]={name:FACTORS[name][bit] for name,bit in zip(names,bits)}
    rows=[];board_results={}
    for setting,parameters in settings.items():
        prices=Prices(inputs,**parameters)
        for case,info in cases.items():
            for cid in args.cards:
                card=inputs['cards'][str(cid)]
                result=evaluate_compressed(card,inputs,info['panels'],info['scenario'],prices,
                                    setting=='central' or args.marginal_corners)
                board_results[setting,case,cid]=result['board_values']
                rows.append(dict(setting=setting,case=case,id=cid,name=card['name'],
                    **{k:v for k,v in result.items() if k not in ('board_values','by_hand_gross')}))
        prices.body.cache_clear();prices.scale.value.cache_clear();prices.scale.effective_attack.cache_clear()
        print(json.dumps(dict(completed=setting,rows=len(rows))),flush=True)
    by={(r['setting'],r['case'],r['id']):r for r in rows}
    comparisons=[]
    for case,info in cases.items():
        for left,right in PAIRS:
            if left not in args.cards or right not in args.cards:continue
            points=[]
            for setting in settings:
                a,b=by[setting,case,left],by[setting,case,right]
                delta=[x-y for x,y in zip(board_results[setting,case,left],board_results[setting,case,right])]
                points.append(dict(setting=setting,net_difference=a['net_value']-b['net_value'],
                    opportunity_difference=a['opportunity_index']-b['opportunity_index'],
                    paired_mc_se=statistics.stdev(delta)/math.sqrt(len(delta)) if info['sampled'] else None))
            comparisons.append(dict(case=case,left=left,right=right,
                min=min(points,key=lambda r:r['net_difference']),max=max(points,key=lambda r:r['net_difference']),
                central=points[0],points=points))
    with (OUT/(args.tag+'-scores.csv')).open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    write(OUT/(args.tag+'-comparisons.json'),comparisons)
    write(OUT/(args.tag+'-design.json'),dict(factors=FACTORS,settings=settings,resource=args.resource,
        cards=args.cards,cases={k:dict(scenario=v['scenario'],sampled=v['sampled'],count=len(v['panels'])) for k,v in cases.items()},
        original_panel_source='statistical-results/final-design.json',
        original_panel_sha256=sha(HERE/'statistical-results/final-design.json'),
        aoe2_transform='H -> H-2, delete H<=0; retain empty boards and common denominator',
        marginal_corners=args.marginal_corners,
        source_sha256={f:sha(HERE/f) for f in ('joint_stress.py','compressed_statistics.py','statistical_value.py','run_statistical_study.py','discount_statistics.py','value_model.py','statistical_inputs.json')},
        limitations=['Finite shared stress points, not continuous worst-case bounds',
            'No probability or empirical win rate assigned to settings',
            'Original wounded_wide uses a separate frozen source sample; do not call it a same-board transform of aggro_wide',
            'Draw price fixed .65; this factorial does not test Bench draw-price uncertainty'] ))
    print(json.dumps(dict(finished=True,rows=len(rows),comparisons=len(comparisons))),flush=True)


if __name__=='__main__':main()
