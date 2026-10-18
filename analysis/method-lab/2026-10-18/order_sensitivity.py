"""Price a shared, paid hand-tuning opportunity without free hand adjustment.

Two fixed hand slots: focal card and a 2G plain Froggit. Both must be played.
Same final cash payment and background body in both orders. Only focal hand
count differs. This is an ordering counterfactual, not a full deck optimizer.
"""
from pathlib import Path
import hashlib
import json

from statistical_value import Prices, best_value

HERE=Path(__file__).resolve().parent
OUT=HERE/'statistical-results'


def main():
    inputs=json.loads((HERE/'statistical_inputs.json').read_text(encoding='utf-8'))
    design=json.loads((OUT/'final-design.json').read_text(encoding='utf-8'))
    rows=[]
    for resource,data in inputs['resources'].items():
        for scenario in ('aggro_wide','midrange_single','control_silence','wounded_wide'):
            cfg=design['scenarios'][scenario]
            prices=Prices(inputs)
            for cid in (49,984):
                card=inputs['cards'][str(cid)]
                premium=payable_premium=changed=payable=0.
                for record in data['records']:
                    hand=record['hand_size_before_play']-1
                    # Need a real second slot. Never create a free extra card.
                    if hand<1:continue
                    can_pay=record['gold_before_play']>=card['cost']+2
                    payable+=record['weight']*can_pay
                    for board in design['panels'][scenario]:
                        weight=record['weight']*board['weight']
                        focal_first=best_value(card,inputs['cards'],board['enemy'],hand,
                            prices,cfg['response'],cfg['p'],0.)[0]
                        background_first=best_value(card,inputs['cards'],board['enemy'],hand-1,
                            prices,cfg['response'],cfg['p'],0.)[0]
                        gain=max(0.,background_first-focal_first)
                        premium+=weight*gain
                        payable_premium+=weight*can_pay*gain
                        changed+=weight*(gain>1e-10)
                rows.append(dict(resource=resource,scenario=scenario,id=cid,name=card['name'],
                    ordering_gross_premium=premium,payable_ordering_premium=payable_premium,
                    joint_payable_mass=payable,preferred_background_first_mass=changed))
    result=dict(contract=dict(background='Mandatory plain 2G Froggit held in a second fixed hand slot',
        payment='Both orders spend focal.cost + 2; no free hand tuning',
        cancellation='Same remaining background 2/3 body cancels; at most three own slots needed',
        response='Only the focal-root reply of the main study; not arbitrary whole-board reply',
        baseline='Focal first; compare max over two orders in the same observable state',
        price='Only the isolated order premium, not whole-card value or actual holding frequencies'),
        source_hashes={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in
            ('order_sensitivity.py','statistical_value.py','statistical_inputs.json','statistical-results/final-design.json')},
        rows=rows)
    (OUT/'paid-order-sensitivity.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(rows,ensure_ascii=False))


if __name__=='__main__':main()
