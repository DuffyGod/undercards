"""A structural value-encoding witness, not an empirical win-rate sample."""
from dataclasses import asdict
import argparse,json
import numpy as np
from .catalog import Spec
from .game import NativeGame,Unit
from .profiles import base_deck
from .policies import LearnedPolicy,ReferencePolicy
from .network import Network
from .relations import state_features
from .knowledge import vector
from .training import dump


def witness(checkpoints):
    one=Spec('probe_one',0,1,2);five=Spec('probe_five',0,5,2)
    taunt=Spec('probe_taunt',0,1,9,(('taunt',1),),());plain=Spec('probe_plain',0,1,9)
    decks=(tuple([one]*3+[five]*3+list(base_deck()[6:])),tuple([taunt]*3+[plain]*3+list(base_deck()[6:])))
    base=Network.load(checkpoints['old'])[0];observations=[];outcomes=[];paths=[]
    for taunt_hp in (1,9):
        game=NativeGame(decks,2079900,(LearnedPolicy(base),ReferencePolicy()))
        for side,p in enumerate(game.players):
            p.deck=[];p.hand=[];p.played=25;p.turn=22;p.total_spent=sum(s.cost for s in decks[side]);p.income=p.total_spent;p.cash=1
            for spec in decks[side]:game.knowledge.observe_play(side,spec)
        game.players[0].hp=1;game.players[1].hp=5
        game.players[0].units=[Unit(0,'custom',1,2,2,ready=True,spec=one),Unit(3,'custom',5,2,2,ready=True,spec=five)]
        game.players[1].units=[Unit(0,'custom',1,taunt_hp,9,spec=taunt,taunt=True),Unit(3,'custom',1,10-taunt_hp,9,spec=plain)]
        observations.append(game.observation(0));path=[]
        for _ in range(10):
            if min(p.hp for p in game.players)<=0:break
            actions=game.legal_actions(0);action=game.agents[0].choose(game.observation(0),actions)['action'];path.append(action)
            if action[0]=='end':break
            game.apply(0,action)
        else:raise ValueError('Probe action bound exceeded')
        if min(p.hp for p in game.players)>0:game.act_turn(1)
        if min(p.hp for p in game.players)>0:raise ValueError('Expected deterministic terminal boundary')
        outcomes.append(int(game.players[0].hp>0 and game.players[1].hp<=0));paths.append(path)
    states=[state_features(o) for o in observations]
    if not np.array_equal(*states) or not np.array_equal(*(vector(o) for o in observations)):
        raise ValueError('Witness does not alias the old74 and known/seen encoding')
    if outcomes!=[1,0]:raise ValueError('Witness terminal distinction disappeared')
    predictions={}
    for name,path in checkpoints.items():
        net=Network.load(path)[0];values=[(net.predict_value(net.encode(o,[('end',-1,-1,-1)])[0])+1)/2 for o in observations]
        if values[0]!=values[1]:raise ValueError('Unexpected critic distinction')
        predictions[name]=values
    return dict(type='constructed_rule_boundary_counterexample',independent_random_openings=0,
        scope='Both hidden regions empty; same public scalar/aggregate/history/known-play features. Swap current HP between enemy taunt and plain unit. All source descriptors and aggregate sums unchanged.',
        limits='Boundary states constructed directly, not sampled natural openings or a reachability/frequency claim. No model selected or tuned using this witness.',
        observations=observations,decks=[[asdict(s) for s in d] for d in decks],outcomes=outcomes,actions=paths,
        predictions=predictions,old74_identical=True,known_seen_identical=True,
        minimum_equal_pair_brier=.25,interpretation='Any critic using this encoding must return equal predictions although these declared deterministic continuations have opposite terminal labels. More afterstate labels alone cannot remove this representation alias.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args()
    result=witness(dict(old='artifacts/card_eval/v5/primary-value.npz',root='artifacts/card_eval/v7/root-value.npz',afterstate='artifacts/card_eval/v7/afterstate-value.npz',memory='artifacts/card_eval/v6/primary-value.npz'))
    dump(args.output,result);print(json.dumps({k:v for k,v in result.items() if k not in ('observations','decks')}))
