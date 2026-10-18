"""Query common statistical quotations and fixed-slot payment comparisons.

Read frozen results, preserving profile/price assumptions and paired theta.
No averaging across unspecified opponent profiles, cash or board capacity.
"""
from pathlib import Path
from itertools import combinations
import argparse
import csv
import gzip
import json
import math
import statistics

HERE=Path(__file__).resolve().parent
PROFILES={
    'aggro_pool':('joint','aggro_wide'),
    'midrange_single':('joint','midrange_single'),
    'control_silence':('joint','control_silence'),
    'empty_development':('joint','empty_development'),
    'clamp_diagnostic':('joint','wounded_wide'),
    'aoe2_survivors':('joint','aoe2_survivors'),
    'icecap_vulkin':('prototype','icecap_vulkin'),
    'card_equal_full':('demand','card_equal_full'),
}


def _csv(path):
    with path.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))


def _range(rows,key):
    vals=[float(r[key]) for r in rows if r.get(key) not in (None,'')]
    return [min(vals),max(vals)] if vals else None


def _number(value):
    if value in ('True',True):return 1.
    if value in ('False',False):return 0.
    return float(value)


def deployment(ids,profile):
    family,case=PROFILES[profile]
    if family in ('joint','prototype'):
        source=HERE/('joint-stress/joint-scores.csv' if family=='joint' else 'joint-stress/prototype-scores.csv')
        rows=[r for r in _csv(source) if r['case']==case]
        central=[r for r in rows if r['setting']=='central']
        settings=sorted({r['setting'] for r in rows})
    else:
        source=HERE/'demand-stress/results.json'
        data=json.loads(source.read_text(encoding='utf-8'))
        rows=[dict(r,setting='central') for r in data['scores'] if r['panel']==case]
        central=rows;settings=['central']
    by={int(r['id']):r for r in central}
    if any(cid not in by for cid in ids):raise ValueError('Candidate unavailable in this frozen profile')
    quoted=[]
    for cid in ids:
        r=by[cid];subset=[x for x in rows if int(x['id'])==cid]
        quoted.append(dict(id=cid,name=r['name'],net_value=float(r['net_value']),
            plus_attack=float(r['plus_attack']),fixed_current_plan_plus_attack=float(r['fixed_policy_plus_attack']),
            gain_over_canonical_fixed_plan=float(r['plus_attack'])-float(r['fixed_policy_plus_attack']),
            plus_health=float(r['plus_health']),payable_share=float(r['payable_share']),
            opportunity_index=float(r['opportunity_index']),
            joint_parameter_ranges={key:_range(subset,key) for key in
                ('net_value','plus_attack','fixed_policy_plus_attack','plus_health')}
                if len(settings)>1 else None,
            fixed_baseline_optimal_range=([float(r['fixed_baseline_optimal_plus_attack_min']),float(r['fixed_baseline_optimal_plus_attack_max'])]
                if r.get('fixed_baseline_optimal_plus_attack_min') is not None else None),
            mandatory_reoptimization_gain=(float(r['mandatory_reoptimization_gain'])
                if r.get('mandatory_reoptimization_gain') is not None else None)))
    paired=[]
    for a,b in combinations(ids,2):
        points=[]
        for setting in settings:
            lookup={int(r['id']):r for r in rows if r['setting']==setting}
            points.append(dict(setting=setting,net_difference=float(lookup[a]['net_value'])-float(lookup[b]['net_value'])))
        paired.append(dict(left=a,right=b,central=next(p['net_difference'] for p in points if p['setting']=='central'),
            joint_stress_range=_range(points,'net_difference') if len(settings)>1 else None))
    return dict(profile=profile,source=source.relative_to(HERE).as_posix(),
        unit='model-G, common body anchor F(6,5)=5; not empirical Gold equivalence',
        setting_count=len(settings),range_meaning='Finite shared parameter stress points, not confidence or continuous-box bounds',
        cards=quoted,comparisons=paired)


def slot(ids,menu,board_group,cash,slots,cash_residual,reference):
    source=HERE/'slot-results/slot-primary.csv.gz' if reference==2 else HERE/'slot-results/slot-reference-sensitivity.csv.gz'
    with gzip.open(source,'rt',encoding='utf-8',newline='') as f:
        rows=[r for r in csv.DictReader(f) if r['menu']==menu and r['board_group']==board_group
              and float(r['cash'])==cash and int(r['empty_slots'])==slots
              and float(r['cash_residual'])==cash_residual and int(r['candidate_id']) in ids]
    if {int(r['candidate_id']) for r in rows}!=set(ids):
        raise ValueError('No complete frozen slot panel at the requested cash/slots/menu; aggro_32 requires three_plain')
    result=[]
    keys=('slot_delta','candidate_gain_over_background','candidate_strictly_improves_background',
          'plus_attack_reoptimized','plus_attack_fixed_menu','plus_cash_candidate','plus_cash_slot_delta',
          'plus_slot_candidate','plus_slot_delta')
    for cid in ids:
        selected=[r for r in rows if int(r['candidate_id'])==cid]
        if len(selected)!=(32 if board_group=='aggro_32' else 1):
            raise ValueError('Incomplete or duplicated frozen board group')
        entry=dict(id=cid,name=selected[0]['candidate_name'],board_count=len(selected))
        for key in keys:
            vals=[_number(r[key]) for r in selected if r.get(key) not in ('',None)]
            entry[key]=sum(vals)/len(vals) if vals else None
        entry['slot_delta_mc_se']=(statistics.stdev(float(r['slot_delta']) for r in selected)/math.sqrt(len(selected))
                                    if len(selected)>1 else None)
        entry['cash_opportunity_gain_above_residual']=(entry['plus_cash_candidate']-cash_residual
            if entry['plus_cash_candidate'] is not None else None)
        result.append(entry)
    paired=[]
    for a,b in combinations(ids,2):
        ra={r['board']:float(r['slot_delta']) for r in rows if int(r['candidate_id'])==a}
        rb={r['board']:float(r['slot_delta']) for r in rows if int(r['candidate_id'])==b}
        deltas=[ra[k]-rb[k] for k in ra]
        paired.append(dict(left=a,right=b,slot_difference=sum(deltas)/len(deltas),
            paired_mc_se=statistics.stdev(deltas)/math.sqrt(len(deltas)) if len(deltas)>1 else None))
    return dict(menu=menu,board_group=board_group,cash=cash,available_slots=slots,cash_residual=cash_residual,
        reference_id=reference,source=source.relative_to(HERE).as_posix(),
        contract='Current deadline, actual blank background bodies, tail=0, no reply; same-slot difference, not deployment score',
        weights='Named board exact; aggro_32 is one shared 32-board numerical sample; cash and slot levels are NOT averaged',
        cards=result,comparisons=paired)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ids',nargs='+',type=int,required=True)
    parser.add_argument('--profile',choices=PROFILES,default='aggro_pool')
    parser.add_argument('--slot',action='store_true')
    parser.add_argument('--menu',choices=('two_plain','three_plain','four_plain'),default='three_plain')
    parser.add_argument('--board-group',choices=('empty','three_3_2','single_6_7','aggro_32'),default='aggro_32')
    parser.add_argument('--cash',type=int,choices=(4,6,8,10),default=8)
    parser.add_argument('--slots',type=int,choices=(1,2,4),default=2)
    parser.add_argument('--cash-residual',type=float,choices=(0.,.5,1.),default=1.)
    parser.add_argument('--reference',type=int,choices=(2,4),default=2)
    args=parser.parse_args()
    if len(set(args.ids))!=len(args.ids):parser.error('Each card ID must appear once')
    output=dict(deployment=deployment(args.ids,args.profile))
    if args.slot:
        output['fixed_slot']=slot(args.ids,args.menu,args.board_group,args.cash,args.slots,args.cash_residual,args.reference)
    print(json.dumps(output,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
