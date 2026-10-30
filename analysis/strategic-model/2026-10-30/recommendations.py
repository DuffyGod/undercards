"""Training-only body choice, followed by a read-only held-out result report.

This analysis question was added while evaluation was running, before reading
evaluation outcomes. The selection function cannot access outcome files.
It is not retroactively described as part of the initial preregistration.
"""
import argparse,json,subprocess
from engine import HERE

DEST=HERE/'experiment-v01'


def select():
    out=DEST/'body-selection.json'
    if out.exists():raise ValueError('Do not replace a saved body selection')
    m=json.loads((DEST/'manifest.json').read_text());p=json.loads((DEST/'plan.json').read_text())
    real={b for b,c in m['bodies'].items() if c['card_id'] is not None and not c['counterfactual']}
    rows=[]
    for w in m['worlds']:
        for h in m['structures']:
            cs=[c for c in p['cases'] if c['world']==w and c['structure']==h and c['body'] in real]
            cs=sorted(cs,key=lambda c:-c['fit']['value'])  # plan order breaks ties
            rows.append(dict(world=w,structure=h,selected_body=cs[0]['body'],
                train_ranking=[dict(body=c['body'],value=c['fit']['value']) for c in cs]))
    out.write_text(json.dumps(dict(
        selection_inputs=['manifest.json','plan.json'],selection='Highest training finite-pool maximin among five real ordinary bodies; plan order breaks ties',
        timing='Analysis extension added during evaluation before evaluation outcomes/summary were read; not original preregistration',
        results=rows),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(rows,ensure_ascii=False))


def report():
    if subprocess.check_output(['git','status','--porcelain','--',str(DEST/'body-selection.json')],text=True).strip():
        raise ValueError('Commit training-only body choices before reporting evaluation outcomes')
    p=json.loads((DEST/'body-selection.json').read_text());s=json.loads((DEST/'summary.json').read_text());out=[]
    for c in p['results']:
        r=next(r for r in s['results'] if r['world']==c['world'] and r['structure']==c['structure'] and r['body']==c['selected_body'])
        out.append(dict(**c,eval_mixture=r['mixture'],eval_against=r['against'],observed_pool_minimum=min(v['win'] for v in r['against'])))
    (DEST/'body-recommendations.json').write_text(json.dumps(dict(results=out,
        interpretation='A training-chosen conditional body suggestion and fresh-deal diagnostics, limited to five ability-free candidates and three opponent rules. Observed evaluation minimum is descriptive, not a full-game or real-environment guarantee.'),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([dict(world=c['world'],host=c['structure'],body=c['selected_body'],minimum=c['observed_pool_minimum']) for c in out],ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['select','report']);a=p.parse_args()
    globals()[a.mode]()
