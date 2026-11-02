"""Constructed off-action callback-order boundary; never a training sample."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import argparse,json
import numpy as np
from .action_value import encode
from .catalog import Spec,Effect
from .game import NativeGame,Unit
from .knowledge import Knowledge
from .policies import ReferencePolicy
from .profiles import base_deck
from .public_planner import PublicGame
from .training import dump,commit


def construct():
    hit=Effect('end','damage','opponent',1);draw=Effect('end','draw','owner',1)
    heal=Spec('visible_heal_probe',0,effects=(Effect('play','heal','owner',1),))
    observations=[];outcomes=[];arrays=[]
    for effects in ((hit,draw),(draw,hit)):
        unit=Spec('visible_off_action_callback',1,0,3,effects=effects)
        cards=list(base_deck());cards[0]=unit;cards[1]=heal
        game=NativeGame((tuple(cards),base_deck()),4999901,(ReferencePolicy(),ReferencePolicy()))
        obs=game.observation(0);known=Knowledge((tuple(cards),base_deck()));known.observe_play(0,unit)
        obs.update(hp=1,enemy_hp=1,cash=1,enemy_cash=0,turn=6,enemy_turn=6,deck_count=0,enemy_deck_count=0,
            enemy_hand_count=0,fatigue=0,enemy_fatigue=0,spent=0,previous_spent=0,enemy_previous_spent=0,
            own=[asdict(Unit(0,'custom',0,3,3,spec=unit))],enemy=[],
            hand=[dict(uid=1,role='custom',candidate=False,**asdict(heal))],history=[],**known.fields(0))
        public=PublicGame(obs);actions=public.legal_actions(0)
        assert actions==[('end',-1,-1,-1),('play',1,-1,-1)]
        outcomes.append([public.child(actions[0]).terminal(),public.child(actions[1]).child(actions[0]).terminal()])
        arrays.append(encode(obs,actions)[1][0]);observations.append(obs)
    assert np.array_equal(arrays[0],arrays[1]) and outcomes==[[True,True],[False,True]]
    return dict(type='constructed_public_off_action_callback_order_boundary',independent_random_openings=0,
        observations=observations,legal_actions=actions,entire_555_action_matrix_identical=True,
        outcomes_end_or_heal_then_end=outcomes,heal_vs_end_terminal_contrasts=[0,1],
        identical_pair_contrast_minimum_equal_weight_mse=.25,
        distinct_optimal_actions_required=False,
        implication='Current action matrix drops ordered effects on non-source/non-target units. A recurrent encoder of only those same matrices cannot recover the missing visible fact. This proves action-value representation insufficiency, not unavoidable policy error: healing wins in both states.',
        fitting_or_selection_use=False,unknown_effects_imputed=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.output.exists():raise ValueError('Preserve probe')
    dump(args.output,dict(construct(),source_commit=commit()))
