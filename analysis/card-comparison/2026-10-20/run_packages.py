"""Produce NEW fixed-visible-hand evidence; refuses existing output directories."""
import argparse,csv,gzip,json,subprocess,time
from pathlib import Path
from package_model import (HERE,ROOT,SOULS,settings,BodyScale,ledger,
                           package_endpoints,price_rows,regions,score)

GUARD_HAND=[38,15,15,602,187,377,1]
EX_HAND=[64,15,15,602,187,377,1]
BOARDS={'empty':[], 'one_large_hit':[[10,1]], 'two_durable':[[5,7],[5,7]],
        'order_probe':[[1,1],[2,4]], 'three_medium':[[4,4],[4,4],[4,4]],
        'four_small':[[1,2],[1,2],[1,2],[1,2]], 'kindness_taunt':[[4,1]],
        'justice_emergency':[[4,1],[4,4]]}


def cases(pilot=False):
    out={}
    boards={k:BOARDS[k] for k in ('one_large_hit','order_probe')} if pilot else BOARDS
    souls=('KINDNESS','JUSTICE') if pilot else SOULS
    for soul in souls:
        for name,enemy in boards.items():
            for body_floor in ((1,) if pilot else (0,1)):
                key=f'guard/{soul}/{name}/keep{body_floor}'
                out[key]=dict(hand=GUARD_HAND,soul=soul,seat='second',previous_spends=[1,0,0],
                              enemy=enemy,own_hp=6 if name=='justice_emergency' else 30,
                              minimum_hp=1,minimum_bodies=body_floor,enemy_cash=0,
                              enemy_soul='INTEGRITY',enemy_previous_spent=0)
    if not pilot:
        # Same 12G ledger, a second real large monster with an inactive Magic.
        for soul in ('INTEGRITY','KINDNESS','JUSTICE'):
            for name in ('empty','two_durable','three_medium'):
                out[f'ex/{soul}/{name}/keep1']=dict(
                    hand=EX_HAND,soul=soul,seat='second',previous_spends=[1,0,0],
                    enemy=BOARDS[name],own_hp=30,minimum_hp=1,minimum_bodies=1,enemy_cash=0,
                    enemy_soul='INTEGRITY',enemy_previous_spent=0)
    return out


def dump(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--pilot',action='store_true')
    args=p.parse_args()
    if args.output.exists():p.error('Use a new output directory; never overwrite evidence')
    paths=[str((HERE/n).relative_to(ROOT)) for n in ('package_model.py','run_packages.py')]
    dirty=subprocess.check_output(['git','status','--porcelain','--',*paths],cwd=ROOT,text=True).strip()
    if dirty:p.error('Commit numerical producer source before generating evidence')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    args.output.mkdir(parents=True);started=time.monotonic()
    source=json.loads((ROOT/'skills/undercards/references/snapshot.json').read_text())
    cards={str(c['id']):c for c in source['cards']}
    inputs=json.loads((ROOT/'analysis/method-lab/2026-10-18/statistical_inputs.json').read_text())
    price_settings={'central':settings()['central']} if args.pilot else settings()
    design=cases(args.pilot);data={};summary=[];physical_count=0;endpoints=0
    # Goal changes do not regenerate physical states; reuse each distinct window.
    physical_cache={}
    for name,case in design.items():
        physical_key=json.dumps({k:v for k,v in case.items() if k!='minimum_bodies'},sort_keys=True)
        if physical_key not in physical_cache:
            gold,physical=package_endpoints(cards,dict(case,minimum_bodies=0))
            physical_cache[physical_key]=(gold,physical)
            physical_count+=len(physical);endpoints+=sum(r['outcome_count'] for r in physical)
        gold,physical=physical_cache[physical_key]
        rows=[dict(r,feasible=r['guaranteed_hp']>=case['minimum_hp'] and
                             r['guaranteed_bodies']>=case['minimum_bodies']) for r in physical]
        data[name]=dict(economy=gold,settings={})
        for setting,prices in price_settings.items():
            scale=BodyScale(inputs['reference'],prices['face_share'],prices['threshold'])
            best,variants=price_rows(rows,case,scale,prices['face_price'])
            data[name]['settings'][setting]=dict(packages=best,variants=variants,regions=regions(best))
            if setting=='central':
                for mu in (0.,1.,2.,3.):
                    valid=[r for r in best if r['feasible']]
                    chosen=max(valid,key=lambda r:score(r,.5,mu)) if valid else None
                    summary.append(dict(case=name,cash=gold['cash'],hand_price=mu,cash_price=.5,
                                        package=chosen['package'] if chosen else None,
                                        value=score(chosen,.5,mu) if chosen else None))
    with gzip.open(args.output/'packages.json.gz','wt',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False)
    dump(args.output/'design.json',dict(producer_source_commit=commit,assessment_kind='heuristic',
         empirically_calibrated=False,cases=design,price_settings=price_settings,
         cash_price_domain=[0,1],hand_price_display_domain=[0,3],
         hand_price_interpretation='Unidentified homogeneous per-card opportunity price; sensitivity, not measured card value',
         source='skills/undercards/references/snapshot.json; compiled 2026-10-05',
         used_cards={str(cid):cards[str(cid)] for cid in sorted({c for case in design.values() for c in case['hand']})},
         conditional_scope='Budget ledger plus one deployment and complete ordinary-enemy attack phase; not an opening trajectory or match',
         enemy_soul='INTEGRITY; no cards played or expenditures, previous spend zero, end rebate zero',
         inactive_guard_dust='Only one Royal Guard available; no other ally Royal Guard, future hand/deck effects unpriced',
         inactive_ex_magic='Action cash below20 and enemy cash below10, so no reset after paying10',
         unknown='Prior field/draw trajectory, real opportunity correlations, future SOUL/card effects and resource prices uncalibrated'))
    dump(args.output/'central-summary.json',summary)
    dump(args.output/'receipt.json',dict(cases=len(design),distinct_physical_windows=len(physical_cache),
         physical_deployment_variants=physical_count,distinct_response_endpoints_across_variants=endpoints,
         price_settings=len(price_settings),old_producers_executed=False,api_calls=0,seconds=time.monotonic()-started))
    print(json.dumps(json.loads((args.output/'receipt.json').read_text())))


if __name__=='__main__':main()
