"""Matched policy-rule contrasts from saved evaluation; no simulations.

Keeping a policy rule does not freeze its literal actions: it responds legally
to changed public HP, affordability and targets. This is the appropriate
mechanism counterfactual, unlike replaying now-illegal actions.
"""
import gzip,json
from engine import HERE
from experiment import paired


def derive():
    dest=HERE/'experiment-v01';s=json.loads((dest/'summary.json').read_text());p=json.loads((dest/'plan.json').read_text())
    raw={}
    for world in sorted({c['world'] for c in p['cases']}):
        with gzip.open(dest/f'eval-{world}.jsonl.gz','rt') as f:
            for r in map(json.loads,f):
                if r['row'] in (0,1):raw[world,r['structure'],r['body'],r['seed'],r['row'],r['column']]=r['won']
    names=['trade_hold_two','face_hold_two','frontier_defender'];out=[]
    for c in s['comparisons']:
        j=names.index(c['column']);effects={}
        for i,name in [(0,'greedy_trade'),(1,'attack_frontier')]:
            sample=[raw[c['world'],c['structure'],c['a'],seed,i,j]-raw[c['world'],c['structure'],c['b'],seed,i,j] for seed in p['eval_seeds']]
            effects[name]=paired(sample)
        out.append(dict(world=c['world'],structure=c['structure'],a=c['a'],b=c['b'],column=c['column'],fixed_policy_differences=effects,
            fitted_policy_difference=c['win_difference']))
    result=dict(comparisons=out,interpretation='Same declared policy rules, paired entity deals and opponent columns; actions may respond to changed public state. Separates rule sensitivity from independently adapted fits; still not externally calibrated body strength. No new simulations.')
    (dest/'fixed-policy-comparisons.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(paired_policy_rule_comparisons=2*len(out),new_simulations=0)))


if __name__=='__main__':derive()
