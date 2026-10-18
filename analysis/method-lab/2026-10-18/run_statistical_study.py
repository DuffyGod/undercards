"""Estimate common-distribution heuristic prices and paired numeric marginals.

This benchmark samples DEMAND PROBES from printed card-pool statistics. It
does not turn that design distribution into observed metagame frequencies.
"""
from pathlib import Path
from collections import defaultdict
import argparse
import csv
import hashlib
import json
import math
import random
import statistics

from statistical_value import FEATURES, Prices, best_value, discount_option
from discount_statistics import expected_discount

HERE=Path(__file__).resolve().parent
OUT=HERE/'statistical-results'
SELECTED=[9,11,13,15,20,21,43,49,168,175,187,243,292,377,469,530,602,649,984]
SCENARIOS={
 'aggro_wide':dict(cohort='aggro',count=3,wounded=0,response='damage2',p=.1,resource='middle_cost'),
 'midrange_single':dict(cohort='midrange',count=1,wounded=0,response='damage4',p=.25,resource='middle_cost'),
 'control_silence':dict(cohort='control',count=1,wounded=0,response='silence',p=.25,resource='middle_cost'),
 'empty_development':dict(cohort='midrange',count=0,wounded=0,response='none',p=0.,resource='middle_cost'),
 'clock_pressure':dict(cohort='midrange',count=0,wounded=0,response='none',p=0.,resource='middle_cost',price_overrides=dict(stock=.35,face=.4)),
 'wounded_wide':dict(cohort='aggro',count=3,wounded=2,response='damage2',p=.1,resource='middle_cost'),
}
PARAMETERS={
 'central':{},'face_share_low':dict(face_share=.1),'face_share_high':dict(face_share=.35),
 'threshold_low':dict(threshold=.2),'threshold_high':dict(threshold=.6),
 'tail_zero':dict(tail=0.),'tail_full':dict(tail=1.),
 'draw_low':dict(draw=.4),'draw_high':dict(draw=.9),
 'face_price_low':dict(face=.15),'face_price_high':dict(face=.4),
}


def write_json(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def write_csv(name,rows):
    with (OUT/name).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def panels(inputs,scenario,samples,seed):
    cfg=SCENARIOS[scenario];cohort=inputs['cohorts'][cfg['cohort']]
    n=cfg['count'];wound=cfg['wounded']
    if n==0:return [dict(enemy=(),weight=1.,source_ids=[])],False
    if n==1:
        # Complete weighted finite cohort. Duplicate A/H bodies keep their
        # true printed-card design weight; no Monte Carlo confidence interval.
        return [dict(enemy=((c['attack'],max(1,c['health']-wound)),),weight=c['weight'],source_ids=[c['id']]) for c in cohort],False
    rng=random.Random(seed);rows=[]
    for _ in range(samples):
        drawn=rng.choices(cohort,weights=[r['weight'] for r in cohort],k=n)
        rows.append(dict(enemy=tuple((c['attack'],max(1,c['health']-wound)) for c in drawn),
            weight=1/samples,source_ids=[c['id'] for c in drawn]))
    return rows,True


def resources(inputs,name):
    r=inputs['resources'][name];records=r['records'];byhand=defaultdict(float)
    for x in records:byhand[x['hand_size_before_play']-1]+=x['weight']
    return records,dict(byhand),r['source_costs']


def mean_discount(costs,hand,cash=5):
    # Exact exchangeable multiset average. Source ARRAY ORDER is not evidence
    # about future hand composition and must have no effect on this price.
    return expected_discount(tuple(sorted(costs)),hand,cash)


def evaluate_one(card,inputs,panels,scenario,prices,marginals):
    cfg=SCENARIOS[scenario];records,handweights,costs=resources(inputs,cfg['resource'])
    discounts={h:mean_discount(costs,h) for h in handweights}
    cost=card['cost']
    payable_hand={h:sum(r['weight'] for r in records if r['hand_size_before_play']-1==h and r['gold_before_play']>=cost) for h in handweights}
    payable_up={h:sum(r['weight'] for r in records if r['hand_size_before_play']-1==h and r['gold_before_play']>=cost+1) for h in handweights}
    gross_by_hand={h:0. for h in handweights};atk=hp=fixed_atk=changes=0.;board_values=[]
    opportunity=costup=attack_opportunity=health_opportunity=0.
    for row in panels:
        enemy=row['enemy'];board=0.
        for hand,hw in handweights.items():
            q,chosen,menu=best_value(card,inputs['cards'],enemy,hand,prices,cfg['response'],cfg['p'],discounts[hand],details=True)
            gross_by_hand[hand]+=row['weight']*q
            board+=hw*q
            opportunity+=row['weight']*payable_hand[hand]*max(0.,q-cost)
            costup+=row['weight']*payable_up[hand]*max(0.,q-cost-1)
            if marginals:
                qa,ca,ma=best_value(card,inputs['cards'],enemy,hand,prices,cfg['response'],cfg['p'],discounts[hand],a_delta=1,details=True)
                qh,ch=best_value(card,inputs['cards'],enemy,hand,prices,cfg['response'],cfg['p'],discounts[hand],h_delta=1)
                weight=row['weight']*hw
                atk+=weight*(qa-q);hp+=weight*(qh-q)
                fixed_atk+=weight*(ma[chosen]-q)
                changes+=weight*(chosen!=ca)
                attack_opportunity+=row['weight']*payable_hand[hand]*(max(0.,qa-cost)-max(0.,q-cost))
                health_opportunity+=row['weight']*payable_hand[hand]*(max(0.,qh-cost)-max(0.,q-cost))
        board_values.append(board)
    gross=sum(handweights[h]*v for h,v in gross_by_hand.items())
    payable=sum(r['weight'] for r in records if r['gold_before_play']>=cost)
    return dict(gross_value=gross,net_value=gross-cost,plus_attack=atk if marginals else None,
        plus_health=hp if marginals else None,fixed_policy_plus_attack=fixed_atk if marginals else None,
        changed_plan_mass=changes if marginals else None,plus_cost_net=-1.,
        payable_share=payable,opportunity_index=opportunity,
        plus_attack_opportunity=attack_opportunity if marginals else None,
        plus_health_opportunity=health_opportunity if marginals else None,
        plus_cost_opportunity=costup-opportunity,by_hand_gross=gross_by_hand,
        board_values=board_values)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--samples',type=int,default=512)
    parser.add_argument('--parameters',nargs='+',default=list(PARAMETERS))
    parser.add_argument('--cards',type=int,nargs='+',default=SELECTED)
    parser.add_argument('--output-tag',default='full')
    parser.add_argument('--resource',choices=['lower_cost','middle_cost','higher_cost'])
    args=parser.parse_args()
    if args.samples<2:raise ValueError('At least two demand samples')
    OUT.mkdir(exist_ok=True)
    inputs=json.loads((HERE/'statistical_inputs.json').read_text(encoding='utf-8'))
    if args.resource:
        for cfg in SCENARIOS.values():cfg['resource']=args.resource
    allpanels={};sampled={}
    for i,s in enumerate(SCENARIOS):allpanels[s],sampled[s]=panels(inputs,s,args.samples,20261018+i)
    summaries=[];raw={};central_boards={};count=0
    for parameter in args.parameters:
        if parameter not in PARAMETERS:raise ValueError('Unknown shared parameter setting')
        for scenario,panel in allpanels.items():
            price_args={**SCENARIOS[scenario].get('price_overrides',{}),**PARAMETERS[parameter]}
            prices=Prices(inputs,**price_args)
            for cid in args.cards:
                card=inputs['cards'][str(cid)]
                result=evaluate_one(card,inputs,panel,scenario,prices,parameter=='central')
                if parameter=='central':central_boards[(scenario,cid)]=result['board_values']
                se=(statistics.stdev(result['board_values'])/math.sqrt(len(panel)) if sampled[scenario] else None)
                row=dict(parameter=parameter,scenario=scenario,id=cid,name=card['name'],cost=card['cost'],
                    **{k:v for k,v in result.items() if k not in ('by_hand_gross','board_values')},
                    demand_mc_standard_error=se)
                summaries.append(row)
                raw[f'{parameter}:{scenario}:{cid}']=dict(by_hand_gross=result['by_hand_gross'])
                count+=1
            print(json.dumps(dict(completed_parameter=parameter,scenario=scenario,rows=count)),flush=True)
            # These cache keys contain Prices/self; retain only numeric results.
            prices.body.cache_clear();prices.scale.value.cache_clear();prices.scale.effective_attack.cache_clear()
    paired=[]
    pairs=[(49,984),(649,530),(469,43),(20,13),(243,15),(175,602)]
    for scenario in SCENARIOS:
        for a,b in pairs:
            if a not in args.cards or b not in args.cards:continue
            diffs=[]
            for parameter in args.parameters:
                by={r['id']:r for r in summaries if r['scenario']==scenario and r['parameter']==parameter}
                diffs.append(dict(parameter=parameter,net_difference=by[a]['net_value']-by[b]['net_value']))
            boarda=central_boards.get((scenario,a));boardb=central_boards.get((scenario,b))
            deltas=[x-y for x,y in zip(boarda,boardb)] if boarda and boardb else []
            paired.append(dict(scenario=scenario,left=a,right=b,differences=diffs,
                min_shared_parameter_difference=min(d['net_difference'] for d in diffs),
                max_shared_parameter_difference=max(d['net_difference'] for d in diffs),
                paired_demand_mc_se=statistics.stdev(deltas)/math.sqrt(len(deltas)) if sampled[scenario] and deltas else None))
    tag=args.output_tag
    write_csv(tag+'-scores.csv',summaries)
    write_json(tag+'-scores.json',summaries);write_json(tag+'-by-hand.json',raw)
    write_json(tag+'-paired.json',paired)
    write_json(tag+'-design.json',dict(scenarios=SCENARIOS,parameters={p:PARAMETERS[p] for p in args.parameters},
        sample_count=args.samples,panels=allpanels,monte_carlo_panels=sampled,
        input_sha256=hashlib.sha256((HERE/'statistical_inputs.json').read_bytes()).hexdigest(),
        sources={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in
                 ('value_model.py','statistical_value.py','discount_statistics.py','statistical_data.py','run_statistical_study.py')},
        empirical_match_distribution=False,
        gross_denominator='Common demand and resource-slot weights, never candidate affordability filtering',
        opportunity_index='Standardized hypothetical slot intervention, not actual candidate-in-hand expectation',
        uncertainty='Parameter sensitivity and numerical demand-sampling error; neither is meta uncertainty'))
    print(json.dumps(dict(finished=True,score_rows=len(summaries),paired_rows=len(paired))))


if __name__=='__main__':main()
