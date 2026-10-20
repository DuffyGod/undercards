"""Restrict saved menus to an explicit six-card arrival witness, no combat.

Removing an unused card is exact only for the declared hand-independent bodies.
Prior battles remain conditional; the witness checks draws/copies and money.
"""
import argparse,gzip,json,subprocess
from collections import Counter
from pathlib import Path
from package_model import HERE,ROOT,SUPPORTED,regions,score


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=HERE/'results')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():p.error('Use a new output directory')
    design=json.loads((args.source/'design.json').read_text())
    with gzip.open(args.source/'packages.json.gz','rt',encoding='utf-8') as f:data=json.load(f)
    allowed={'plain','armor','dodge','taunt','guard_without_other_guard','ex_without_gold_trigger'}
    assert all(SUPPORTED[int(cid)] in allowed for cid in design['used_cards'])
    kept=removed=0;summary=[]
    for name,case in design['cases'].items():
        hand=list(case['hand']);assert len(hand)==7 and hand.count(377)==1
        hand.remove(377);case['hand']=hand
        # Initial Dummy is paid on t1; its disappearance by t4 is conditioned.
        # The six currently available cards arrive without a mulligan/generation.
        witness=dict(initial_hand=[1,*hand[:2]],turn_draws=hand[2:],
                     turn1_play=[1],current_hand=hand,
                     assumptions='Three initial cards, one draw at each own turn including t1, no extra draw/generation; early Dummy is absent at this conditional root')
        inventory=Counter(witness['initial_hand'])
        for turn,cid in enumerate(witness['turn_draws'],1):
            inventory[cid]+=1
            if turn==1:inventory[1]-=1
            assert sum(inventory.values())<=7
        assert +inventory==Counter(hand)
        assert case['previous_spends']==[1,0,0] and case['seat']=='second'
        case['arrival_witness']=witness
        for setting,record in data[name]['settings'].items():
            for key in ('packages','variants'):
                filtered=[]
                for row in record[key]:
                    if 377 in row['package']:removed+=1;continue
                    old=dict(row);remaining=list(row['remaining_hand']);remaining.remove(377)
                    row['remaining_hand']=remaining;filtered.append(row);kept+=1
                    assert Counter(hand)-Counter(row['package'])==Counter(remaining)
                    assert {k:v for k,v in row.items() if k!='remaining_hand'}=={k:v for k,v in old.items() if k!='remaining_hand'}
                record[key]=filtered
            record['regions']=regions(record['packages'])
            if setting=='central':
                for mu in (0.,1.,2.,3.):
                    valid=[r for r in record['packages'] if r['feasible']]
                    best=max(valid,key=lambda r:score(r,.5,mu)) if valid else None
                    summary.append(dict(case=name,cash=data[name]['economy']['cash'],hand_price=mu,
                                        cash_price=.5,package=best['package'] if best else None,
                                        value=score(best,.5,mu) if best else None))
    design.update(source_results=str(args.source),
                  derivation='Remove unavailable Ranger Rudinn; filter hand-independent menus and rederive price regions, without physical search',
                  derivation_source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                  opening_limit='Arrival witness and natural balance only; early Dummy death, full prior fields and opponent draw/actions not simulated')
    design['used_cards'].pop('377')
    args.output.mkdir(parents=True)
    with gzip.open(args.output/'packages.json.gz','wt',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False)
    for file,value in [('design.json',design),('central-summary.json',summary),('receipt.json',dict(
            cases=len(data),kept_records=kept,removed_records=removed,
            arrival_inventory_checks=len(data),physical_search_executed=False,
            api_calls=0,source_results=str(args.source)))]:
        (args.output/file).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(cases=len(data),physical_search_executed=False,arrival_inventory_checks=len(data))))


if __name__=='__main__':main()
