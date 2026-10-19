"""One new causal probe: add a real third background card, same6G/two slots.

Separates changed focal hand-count effects from background replacement. No
deck assembly, enemy simulation, regenerated old experiment or price fitting.
"""
from dataclasses import asdict
from itertools import combinations
from pathlib import Path
import json

from run_study import METHOD, settings, physical_curve
from slot_value import SlotSolver
from value_model import BodyScale
from frontier import value, paired_range

HERE = Path(__file__).resolve().parent
IDS = (43, 49, 168, 530, 984)


def main():
    target = HERE/'controlled-hand-probe.json'
    if target.exists():
        raise RuntimeError('Preserve the existing probe; use a new path for a new experiment')
    inputs = json.loads((METHOD/'statistical_inputs.json').read_text(encoding='utf-8'))
    common = dict(cash=6, slots=2, enemy=((3,2),)*3)
    results = {'two_backgrounds':{},'plus_aaron':{}}; rows=[]
    for name,p in settings().items():
        scale = BodyScale(inputs['reference'],p['face_share'],p['threshold'])
        solver = SlotSolver(inputs['cards'],scale,p['face_price'])
        for label,bg in [('two_backgrounds',(2,4)),('plus_aaron',(2,4,15))]:
            curves={};forced={}
            for cid in IDS:
                quotes=solver.quotes(cid,bg,common['enemy'],common['slots'])
                curves[str(cid)]=physical_curve(quotes,common['cash'])
                curves['background']=physical_curve([q for q in quotes if not q.plan.candidate_used],6)
                forced[str(cid)]=physical_curve([q for q in quotes if q.plan.candidate_used and
                    not q.plan.prefix and not q.plan.suffix],6)
            results[label][name]=dict(curves=curves,forced_focal_only=forced)
        for cid in IDS:
            before=results['two_backgrounds'][name];after=results['plus_aaron'][name]
            # All focal cards cost exactly6. If used at6G, no background can
            # also be paid. Consequently max(B,forced_focal)=full menu exactly.
            for lam in (0,.5,1):
                for r in (before,after):
                    expected=max(value(r['curves']['background'],lam),value(r['forced_focal_only'][str(cid)],lam))
                    if abs(expected-value(r['curves'][str(cid)],lam))>1e-9:
                        raise AssertionError('Focal/background decomposition failed')
            forced_delta=value(after['forced_focal_only'][str(cid)],.5)-value(before['forced_focal_only'][str(cid)],.5)
            if cid==984:
                expected=-scale.value(2,3)
            elif cid==49:
                expected=scale.value(5,5)-scale.value(4,4)
            else:
                expected=0.
            if abs(forced_delta-expected)>1e-9:
                raise AssertionError('Independent conditional hand-count identity failed')
            rows.append(dict(setting=name,id=cid,name=inputs['cards'][str(cid)]['name'],
                focal_only_delta=forced_delta,
                independent_mechanism_delta=expected,
                actual_menu_before_half=value(before['curves'][str(cid)],.5),
                actual_menu_after_half=value(after['curves'][str(cid)],.5),
                background_before_half=value(before['curves']['background'],.5),
                background_after_half=value(after['curves']['background'],.5)))
        solver.quotes.cache_clear();solver._focal_plans.cache_clear()
        scale.value.cache_clear();scale.effective_attack.cache_clear()
    out=dict(assessment_kind='heuristic',empirically_calibrated=False,
        intervention='Background [Froggit,Moldsmal] -> [Froggit,Moldsmal,Aaron], identical cash6/slots2/enemy3x3/2',
        hypothesis='Hand structure changes focal realization AND replacement competition; do not collapse them into a card-name bonus',
        forced_focal_only_is_diagnostic=True,
        forced_play_is_not_the_adopted_policy=True,
        current_deadline_only=True,opponent_reply=False,
        identity='Every used focal costs6; at cash6 no other card can be played: M=max(B,Focal-only)',
        input_and_frontier_revision='a8b8e9d',
        source_code='controlled_hand_probe.py in the same Git delivery',
        cross_card_before_after=[dict(left=a,right=b,
            before=paired_range({s:r['curves'] for s,r in results['two_backgrounds'].items()},a,b),
            after=paired_range({s:r['curves'] for s,r in results['plus_aaron'].items()},a,b))
            for a,b in combinations(IDS,2)],
        results=results,rows=rows)
    target.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'new_focal_cases':len(rows),'conditional_decomposition_identities':len(rows)*6,
                      'hand_count_identities':len(rows),'api_requests':0}))


if __name__=='__main__':main()
