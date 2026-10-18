"""Exact without-replacement COST MULTISET averages; no card/deck simulation."""
from collections import Counter
from functools import lru_cache
from math import comb

from statistical_value import discount_option


@lru_cache(maxsize=None)
def expected_discount(sorted_costs,hand,cash=5,quality=1.):
    if type(hand) is not int or not 0<=hand<=len(sorted_costs):
        raise ValueError('Hand sample size is outside the source cost multiset')
    counts=tuple(sorted(Counter(sorted_costs).items()))
    denominator=comb(len(sorted_costs),hand)
    value=0.;mass=0.
    def visit(i,left,chosen,multiplicity):
        nonlocal value,mass
        if i==len(counts):
            if left:return
            probability=multiplicity/denominator
            value+=probability*discount_option(tuple(chosen),cash,quality)
            mass+=probability
            return
        cost,count=counts[i]
        for n in range(min(left,count)+1):
            visit(i+1,left-n,chosen+[cost]*n,multiplicity*comb(count,n))
    visit(0,hand,[],1)
    if abs(mass-1)>1e-10:raise RuntimeError('Cost multiset probability is not normalized')
    return value
