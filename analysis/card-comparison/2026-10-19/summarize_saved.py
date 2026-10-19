"""Derive audit findings from saved curves. Does not execute the physical solver."""
from itertools import combinations, product
from pathlib import Path
import csv
import gzip
import json

from frontier import difference, value, diagnose_pair, mixture, single_use_opportunity_bounds
from run_study import case_id, write_csv, dump

HERE=Path(__file__).resolve().parent


def main():
    destination=HERE/'derived'
    if destination.exists():
        raise RuntimeError('Preserve existing derived evidence; use a new output for a new analysis')
    destination.mkdir()
    with gzip.open(HERE/'results/curves.json.gz','rt',encoding='utf-8') as f:data=json.load(f)
    rows=list(csv.DictReader((HERE/'results/pairwise.csv').open(encoding='utf-8',newline='')))
    counterexamples=[];suppressed_equal=0;interpreted=[]
    for row in rows:
        curves=data[row['case']]['settings']
        diagnosis=diagnose_pair(curves,row['left'],row['right'])
        if diagnosis['both_suppressed_by_background_or_budget']:
            suppressed_equal+=1
        interpreted.append(dict(row,both_suppressed_by_background_or_budget=diagnosis['both_suppressed_by_background_or_budget'],
                                whole_card_ordering_identified=False))
        for setting,c in curves.items():
            a,b=c[row['left']],c[row['right']]
            anchors=[value(a,x)-value(b,x) for x in (0,.5,1)]
            d=difference(a,b)
            if min(anchors)>=-1e-9 and d['minimum']<-1e-7 or max(anchors)<=1e-9 and d['maximum']>1e-7:
                counterexamples.append(dict(case=row['case'],left=row['left'],right=row['right'],
                    setting=setting,three_anchor_differences=anchors,**d))
    central=[r for r in counterexamples if r['setting']=='central']
    pairs=sorted({(int(r['left']),int(r['right'])) for r in rows})
    mixture_rows=[]
    for menu,cash,slots,(board0,board1),(a,b) in product(
        ['two_plain','three_plain','four_plain'],[6,8,10],[1,2,4],
        combinations(['empty','three_3_2','single_6_7'],2),pairs):
        first=data[case_id(menu,board0,cash,slots)]['settings']
        second=data[case_id(menu,board1,cash,slots)]['settings']
        r=mixture(first,second,a,b)
        mixture_rows.append(dict(menu=menu,cash=cash,slots=slots,first_board=board0,
            second_board=board1,left=a,right=b,
            left_weakly_preferred_q=json.dumps(r['left_weakly_preferred_mass']),
            right_weakly_preferred_q=json.dumps(r['right_weakly_preferred_mass'])))
    dump(destination/'sampling-counterexamples.json',counterexamples)
    write_csv(destination/'interpreted-pairs.csv',interpreted)
    write_csv(destination/'all-background-mixtures.csv',mixture_rows)
    dump(destination/'findings.json',dict(
        source='Previously generated results/curves.json.gz; no physical solver rerun',
        central_three_anchor_blind_cases=len(central),
        largest_central_missed_negative_difference=max([-r['minimum'] for r in central],default=0),
        all_price_three_anchor_blind_cases=len(counterexamples),
        all_equal_or_suppressed_pair_rows=suppressed_equal,
        mixture_rows=len(mixture_rows),
        no_row_counts_are_independent_game_samples=True,
        timing_nonidentification_example=single_use_opportunity_bounds(4,[.5,.5],3),
        scientific_interpretation=[
            'Most central sampling blind spots here are tiny; the material hand-structure reversal is a separate controlled probe',
            'Cash/budget/background changes are conditional analyses, not a fabricated metagame mixture',
            'No probability assigned to price corners; compare pairs at the SAME setting and cash price',
            'Both suppressed is a current opportunity statement, not a whole-card equality assertion',
            'Static opportunity proportions do not identify the temporal window dependence needed for carry value']))
    print(json.dumps({'derived_pairs':len(interpreted),'mixtures':len(mixture_rows),
                      'central_sampling_blind_cases':len(central),'old_experiments_rerun':False}))


if __name__=='__main__':main()
