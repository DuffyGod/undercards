"""New bounded response study. No historic kernel, deck builder or API."""
from itertools import combinations
from pathlib import Path
import argparse
import csv
import gzip
import json
import subprocess
import time

from run_study import METHOD, settings, dump, write_csv
from slot_value import SlotSolver
from value_model import BodyScale
from response_window import SUPPORTED,frontier_after_reply,compare_reply
from frontier import paired_range,difference,value

HERE=Path(__file__).resolve().parent
CASES={
    'empty_limit':dict(enemy=(),own_hp=15,cash=6,bg=(2,187,15),floor=1),
    'immediate_attack_needed':dict(enemy=((4,2),),own_hp=3,cash=3,bg=(2,4),floor=1),
    'lethal_4_2_at_3hp':dict(enemy=((4,2),),own_hp=3,cash=4,bg=(2,4),floor=1),
    'same_enemy_at_4hp':dict(enemy=((4,2),),own_hp=4,cash=4,bg=(2,4),floor=1),
    'same_enemy_require_2hp':dict(enemy=((4,2),),own_hp=4,cash=4,bg=(2,4),floor=2),
    'balanced_trade':dict(enemy=((5,5),),own_hp=15,cash=6,bg=(),floor=1),
    'durable_threat':dict(enemy=((5,8),),own_hp=15,cash=6,bg=(),floor=1),
    'durable_threat_with_background':dict(enemy=((5,8),),own_hp=15,cash=6,bg=(2,187,15),floor=1),
    'big_threat_more_cash':dict(enemy=((6,7),),own_hp=15,cash=8,bg=(2,187,15),floor=1),
    'small_threat':dict(enemy=((1,2),),own_hp=15,cash=4,bg=(2,4),floor=1),
    'dodge_cannot_block_lethal_face':dict(enemy=((5,8),),own_hp=5,cash=6,bg=(2,187,15),floor=1),
}


def common_compare(settings_map,a,b):
    states=[(r[str(a)]['guarantee_feasible'],r[str(b)]['guarantee_feasible']) for r in settings_map.values()]
    if len(set(states))!=1:
        raise AssertionError('Hard physical feasibility cannot depend on normative price coefficients')
    fa,fb=states[0]
    if not fa or not fb:
        return dict(left_feasible=fa,right_feasible=fb,numeric_difference=None,
                    status='survival_feasibility_differs' if fa!=fb else 'neither_guarantees_survival')
    curves={s:{str(a):r[str(a)]['curve'],str(b):r[str(b)]['curve']} for s,r in settings_map.items()}
    return dict(left_feasible=True,right_feasible=True,
                numeric_difference=paired_range(curves,a,b),
                status=paired_range(curves,a,b)['status'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--pilot',action='store_true')
    args=parser.parse_args()
    if args.output.exists():parser.error('Preserve earlier evidence; output directory must be new')
    args.output.mkdir(parents=True)
    start=time.monotonic()
    inputs=json.loads((METHOD/'statistical_inputs.json').read_text(encoding='utf-8'))
    ids=(9,13,20,168,187) if args.pilot else SUPPORTED
    cases={k:CASES[k] for k in ('immediate_attack_needed','lethal_4_2_at_3hp')} if args.pilot else CASES
    prices={'central':settings()['central']} if args.pilot else settings()
    all_results={case:{} for case in cases};checks=0
    for label,p in prices.items():
        scale=BodyScale(inputs['reference'],p['face_share'],p['threshold'])
        solver=SlotSolver(inputs['cards'],scale,p['face_price'])
        for case,c in cases.items():
            results={}
            for cid in ids:
                args_physical=(solver,cid,c['bg'],c['enemy'],c['cash'],4,c['own_hp'],c['floor'])
                r=frontier_after_reply(*args_physical)
                if cid in (168,175,377):
                    control=frontier_after_reply(*args_physical,remove_focal_defense=True)
                    if r['guarantee_feasible']!=control['guarantee_feasible']:
                        raise AssertionError('Standalone Dodge/Armor does not prevent a legal hero face attack')
                    r['defense_removed_control']=control
                    if r['curve'] is not None:
                        delta=difference(r['curve'],control['curve'])
                        if delta['minimum'] < -1e-8:
                            raise AssertionError('Defense removal improved this monotone one-response projection')
                        r['defense_increment']=delta
                results[str(cid)]=r;checks+=len(r['menus'])
            all_results[case][label]=results
        solver.quotes.cache_clear();solver._focal_plans.cache_clear()
        scale.value.cache_clear();scale.effective_attack.cache_clear()
        print(json.dumps({'completed_price':label,'menu_records':checks}),flush=True)
    pairs=[(a,b) for a,b in combinations(ids,2) if inputs['cards'][str(a)]['cost']==inputs['cards'][str(b)]['cost']]
    summary=[]
    for case,r in all_results.items():
        for a,b in pairs:
            d=common_compare(r,a,b)
            delta=d['numeric_difference']
            summary.append(dict(case=case,left=a,right=b,left_feasible=d['left_feasible'],
                right_feasible=d['right_feasible'],minimum=delta['minimum'] if delta else None,
                maximum=delta['maximum'] if delta else None,status=d['status']))
    empty_checks=0
    if 'empty_limit' in all_results:
        with gzip.open(HERE/'results/curves.json.gz','rt',encoding='utf-8') as f:old=json.load(f)
        source=old['three_plain/empty/g6/k4']['settings']
        for label,r in all_results['empty_limit'].items():
            for cid in ids:
                delta=difference(r[str(cid)]['curve'],source[label][str(cid)])
                if max(abs(delta['minimum']),abs(delta['maximum']))>1e-8:
                    raise AssertionError('Empty-enemy limit disagrees with retained no-response curve')
                empty_checks+=1
    with gzip.GzipFile(filename=str(args.output/'reply-curves.json.gz'),mode='wb',mtime=0) as f:
        f.write(json.dumps(all_results,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
    write_csv(args.output/'pairs.csv',summary)
    dump(args.output/'design.json',dict(assessment_kind='heuristic',empirically_calibrated=False,
        producer_source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        candidate_ids=ids,price_settings=prices,cases=cases,
        source_files=['response_window.py','run_reply_study.py','frontier.py'],
        price_input='analysis/method-lab/2026-10-18/statistical_inputs.json',
        initial_own_board='empty, four free physical slots',enemy_hero_hp=30,
        enemy_action='One ordinary ready enemy may attack a living friendly body, attack hero, or decline',
        opponent_other_actions='No hand plays, draws, income, turn triggers or additional attackers in this declared window',
        survival_goal='Every enemy response meets the stated own-HP floor; infeasible values remain null',
        signed_damage_price='Nonlethal player damage only, at common external face_price',
        field_warning='guaranteed_own_hp and asset-worst reply HP are different bounds; do not splice their witnesses',
        unknown_future='Dust discounts and other future options outside this deadline are not estimated',
        excluded='Bullseye/chain/death-child and multi-enemy combat rejected; no pretend-zero support',
        parameter_probabilities=None,real_match_winrate=None))
    dump(args.output/'receipt.json',dict(menu_records=checks,case_count=len(cases),cards=len(ids),
        pair_rows=len(summary),empty_enemy_curve_identities=empty_checks,
        old_producer_executed=False,api_requests=0,seconds=time.monotonic()-start))
    print(json.dumps({'finished':True,'menu_records':checks,'empty_limit_checks':empty_checks,
                      'seconds':time.monotonic()-start}))


if __name__=='__main__':main()
