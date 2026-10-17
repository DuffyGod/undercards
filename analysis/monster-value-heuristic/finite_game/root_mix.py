"""Two-world robust expected guarantees over preverified common policies.

The world is fixed before the own private random draw, but the enemy can react
to the realized public play. This computes an expected HP guarantee, never a
physical per-realization HP guarantee or a probability distribution of worlds.
"""
from fractions import Fraction
import math

VERSION='two-world-fixed-policy-mixture-0.1.0'


def rational(n): return {'fraction':str(n),'decimal':float(n)}


def evaluate(data):
    if not isinstance(data,dict) or set(data)!={'worlds','policies','policies_are_common','world_fixed_before_randomization'}:
        raise ValueError('Explicit two-world policy matrix and information timing required')
    if data['policies_are_common'] is not True or data['world_fixed_before_randomization'] is not True:
        raise ValueError('Per-world oracle plans or a world chosen after the private draw do not satisfy this expected-guarantee protocol')
    worlds=data['worlds']; rows=data['policies']
    if not isinstance(worlds,list) or len(worlds)!=2 or len(set(worlds))!=2 or any(not isinstance(w,str) for w in worlds):
        raise ValueError('Exactly two distinct declared worlds required')
    if not isinstance(rows,list) or not rows or any(not isinstance(r,dict) or set(r)!={'id','guarantees'} for r in rows):
        raise ValueError('Policies have an id and two verified guarantees')
    if len({r['id'] for r in rows})!=len(rows):raise ValueError('Duplicate policy id')
    values=[]
    for r in rows:
        if not isinstance(r['guarantees'],list) or len(r['guarantees'])!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in r['guarantees']):
            raise ValueError('Unknown, infeasible and nonfinite quotes cannot enter a numeric policy matrix')
        values.append(tuple(Fraction(str(v)) for v in r['guarantees']))
    candidates=[]
    for i,pair in enumerate(values):candidates.append((min(pair),{i:Fraction(1)},pair))
    for i,a in enumerate(values):
        for j in range(i+1,len(values)):
            b=values[j]
            denominator=(a[0]-a[1])-(b[0]-b[1])
            if not denominator:continue
            p=(a[0]-a[1])/denominator
            if not 0<=p<=1:continue
            expected=tuple((1-p)*a[k]+p*b[k] for k in (0,1))
            candidates.append((min(expected),{i:1-p,j:p},expected))
    best=max(candidates,key=lambda x:x[0]);physical=min(min(values[i]) for i,p in best[1].items() if p)
    return dict(version=VERSION,robust_expected_hp=rational(best[0]),
        probabilities=[dict(policy_id=rows[i]['id'],probability=rational(p)) for i,p in best[1].items() if p],
        expected_guarantees_by_world={worlds[k]:rational(best[2][k]) for k in (0,1)},
        guaranteed_hp_every_realization=rational(physical),
        best_single_policy_hp=rational(max(min(pair) for pair in values)),
        world_probabilities_inferred=False,
        semantics='Lower envelope over fixed worlds of randomized common-policy guarantees. Own policy probabilities are decisions; hidden-world probabilities are never supplied or inferred. '
                  'With two world constraints an optimum exists using at most two policies; pair crossings and pure policies exhaust the upper convex hull.')
