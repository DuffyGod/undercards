"""Derive receipt/play/hold diagnostics from saved evaluation, never simulate."""
import gzip,json
import numpy as np
from engine import HERE,COLS


def derive():
    dest=HERE/'experiment-v01';plan=json.loads((dest/'plan.json').read_text())
    seeds={s:i for i,s in enumerate(plan['eval_seeds'])};out=[]
    for world in sorted({c['world'] for c in plan['cases']}):
        records={}
        with gzip.open(dest/f'eval-{world}.jsonl.gz','rt') as f:
            for r in map(json.loads,f):records[r['structure'],r['body'],r['seed'],r['row'],r['column']]=r
        for case in (c for c in plan['cases'] if c['world']==world):
            p=case['fit']['row_mixture'];against=[]
            for j in range(3):
                samples=[]
                for seed in seeds:
                    sample=np.zeros(5)
                    for row,weight in enumerate(p):
                        if weight<=1e-9:continue
                        r=records[case['structure'],case['body'],seed,row,j]
                        played=r['candidate_played']>0;received=r['candidate_drawn']>0
                        assert not played or received
                        sample+=weight*np.array([not received,received and not played,played,
                            r['candidate_first_turn'] if played else 0,r['candidate_played']])
                    assert abs(sum(sample[:3])-1)<1e-8;samples.append(sample)
                a=np.mean(samples,axis=0)
                against.append(dict(column=COLS[j].name,p_not_received=float(a[0]),p_received_never_played=float(a[1]),p_played=float(a[2]),
                    mean_first_entry_if_played=float(a[3]/a[2]) if a[2] else None,mean_copies_played=float(a[4])))
            out.append(dict(world=world,structure=case['structure'],body=case['body'],against=against))
    result=dict(results=out,interpretation='Whole-evaluation probabilities under frozen mixtures; received excludes burned draws. First-entry time conditional on eventual play is descriptive, not causal opportunity cost or a selection score. No added simulations.')
    (dest/'opportunity.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(conditional_profiles=len(out),new_simulations=0)))


if __name__=='__main__':derive()
