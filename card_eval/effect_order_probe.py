"""Constructed effect-order alias, not a sampled final or training example."""
from pathlib import Path
import argparse,json
import numpy as np
from .catalog import Spec,Effect
from .legacy import model
from .game import NativeGame
from .profiles import base_deck
from .policies import ReferencePolicy
from .entity_value import entity_state
from .entity_research import models
from .training import dump


def probe(folder):
    folder=Path(folder);damage=Effect('play','damage','opponent',3);draw=Effect('play','draw','owner',1);observations=[];terminals=[]
    for effects in ((damage,draw),(draw,damage)):
        spec=Spec('effect_order_probe',0,effects=effects);own=(spec,)*3+base_deck()[3:]
        game=NativeGame((own,base_deck()),2399900,(ReferencePolicy(),ReferencePolicy()))
        a,b=game.players;a.deck=[];a.hand=[model.Card(0,'candidate')];a.units=[];a.played=24;a.hp=1;a.turn=22;a.fatigue=0
        b.deck=[];b.hand=[];b.units=[];b.played=25;b.hp=3;b.turn=22;b.fatigue=0
        obs=game.observation(0);observations.append(obs)
        game.apply(0,('play',0,-1,-1));terminals.append(dict(own_hp=a.hp,enemy_hp=b.hp,won=a.hp>0 and b.hp<=0))
    if not np.array_equal(*(entity_state(o) for o in observations)):raise ValueError('The current encoder no longer aliases effect order')
    if [r['won'] for r in terminals]!=[True,False]:raise ValueError('Rule-order witness did not reach opposite outcomes')
    predictions={}
    for name,net in models(folder).items():
        if name=='v5':continue
        p=[(net.predict_value(net.encode(o,[('end',-1,-1,-1)])[0])+1)/2 for o in observations]
        if p[0]!=p[1]:raise ValueError('Unexpected distinction in frozen value inputs')
        predictions[name]=p
    result=dict(type='constructed_known-empty-deck_boundary',independent_random_openings=0,
        observations=observations,terminals=terminals,predictions=predictions,entity_inputs_identical=True,
        minimum_equal_pair_brier=.25,used_for_training_or_selection=False,
        scope='Rules execute effect list in order. Current joint-count tensor preserves trigger/op/scope binding, but still pools effect sequence. Not a natural-opening reachability or frequency claim; no final model changed.')
    dump(folder/'effect-order-witness.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',required=True,type=Path);args=p.parse_args();r=probe(args.folder);print(json.dumps({k:v for k,v in r.items() if k!='observations'},indent=2))
