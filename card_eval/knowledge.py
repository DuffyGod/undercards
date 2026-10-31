"""Order-free owner deck knowledge and actually public played-card memory.

Never reads an opponent's unplayed card, shuffled order, hand or random seed.
These are explicit observed summaries, not a learned belief or sufficient state.
"""
from dataclasses import asdict
import json
import numpy as np
from .legacy import features

SCHEMA = 'known-deck-public-plays-1'
SUMMARY_DIM = 16
EXTRA_DIM = 3 * features.CARD_DIM + 3 * SUMMARY_DIM + 2
STATE_DIM = 74 + EXTRA_DIM


def semantic(spec):
    raw = asdict(spec) if not isinstance(spec, dict) else spec
    return json.loads(json.dumps({k: raw[k] for k in ('cost','attack','health','keywords','effects')}, sort_keys=True))


def summary(spec):
    kw=dict(spec['keywords']); es=spec['effects']
    values=[spec['cost']/10,spec['attack']/10,spec['health']/10]
    values += [kw.get(k,0)/(3 if k=='dodge' else 1) for k in ('haste','charge','taunt','armor','dodge')]
    values += [sum(e['amount'] for e in es if e['op']=='draw' and e['trigger']==t)/10 for t in ('play','start','end')]
    values += [sum(e['amount'] for e in es if e['op']=='heal')/10,
               sum(e['amount'] for e in es if e['op']=='damage' and e['scope']=='all_enemy')/10,
               sum(e['op']=='kill' for e in es),
               sum(e['amount'] for e in es if e['op']=='buff')/10,
               sum(e['health'] for e in es if e['op']=='buff')/10]
    return np.asarray(values,float)


def aggregate(specs):
    ordered=sorted((semantic(s) for s in specs),key=lambda s:json.dumps(s,sort_keys=True))
    full=sum((features.card_features(s) for s in ordered),np.zeros(features.CARD_DIM))/25
    small=sum((summary(s) for s in ordered),np.zeros(SUMMARY_DIM))/25
    return full,small


class Knowledge:
    def __init__(self,decks):
        if len(decks)!=2 or any(len(d)!=25 for d in decks): raise ValueError('Two known owner deck lists required')
        self.known=[aggregate(deck) for deck in decks]
        self.played=[[],[]]
        self.seen=[aggregate([]),aggregate([])]

    def observe_play(self,actor,spec):
        self.played[actor].append(semantic(spec));self.seen[actor]=aggregate(self.played[actor])

    def fields(self,actor):
        other=1-actor
        vector=np.r_[self.known[actor][0],self.seen[actor][0],self.seen[other][0],
                     self.known[actor][1],self.seen[actor][1],self.seen[other][1],
                     len(self.played[actor])/25,len(self.played[other])/25]
        if vector.shape!=(EXTRA_DIM,): raise ValueError('Knowledge shape mismatch')
        return dict(knowledge_schema=SCHEMA,knowledge=vector.tolist())


def vector(obs):
    if obs.get('knowledge_schema')!=SCHEMA or 'knowledge' not in obs:
        raise ValueError('Required known-deck/public-play observation is missing; do not substitute zero')
    out=np.asarray(obs['knowledge'],float)
    if out.shape!=(EXTRA_DIM,) or not np.isfinite(out).all(): raise ValueError('Invalid known/seen semantic observation')
    return out
