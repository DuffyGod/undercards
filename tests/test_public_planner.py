from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from card_eval.catalog import Spec, Effect
from card_eval.game import NativeGame
from card_eval.legacy import bridge
from card_eval.profiles import base_deck, opponents
from card_eval.policies import ReferencePolicy, LearnedPolicy
from card_eval.network import Network
from card_eval.public_planner import PublicGame, PublicPlanner, UnknownDraw, signature
from card_eval.api import default_request,evaluate,validate
from card_eval.catalog import InputError
from card_eval._planner_v1 import PublicPlanner as FrozenPlanner


class PublicPlanningChecks(unittest.TestCase):
    def game(self, enemy='pressure'):
        return NativeGame((base_deck(),opponents()[enemy]),950701,(ReferencePolicy(),ReferencePolicy()))

    def model(self): return Network.load(Path('card_eval/models/paired-v5.npz'))[0]

    def test_public_reconstruction_and_differential_rules(self):
        class CheckedGame(NativeGame):
            checked=0
            def apply(inner, actor, action):
                public=PublicGame(inner.observation(actor))
                self.assertEqual(signature(public.observation()),signature(inner.observation(actor)))
                self.assertEqual(public.legal_actions(actor),inner.legal_actions(actor))
                try:child=public.child(action)
                except UnknownDraw:child=None
                super(CheckedGame,inner).apply(actor,action)
                if child is not None:
                    self.assertEqual(signature(child.observation()),signature(inner.observation(actor)))
                    inner.checked+=1
        game=CheckedGame((base_deck(),opponents()['refill']),950702,(ReferencePolicy('guard'),ReferencePolicy()))
        result=game.run();self.assertFalse(result['unfinished']);self.assertGreater(game.checked,10)

    def test_unknown_draw_is_atomic_and_empty_deck_fatigue_is_exact(self):
        game=self.game();game.players[0].cash=20
        draw=Spec('test_draw',1,effects=(Effect('play','draw','owner',1),))
        card=game.players[0].hand[0];decks=list(game.native_decks);decks[0]=tuple(draw if j==card.uid else s for j,s in enumerate(decks[0]));game.native_decks=tuple(decks)
        obs=game.observation(0);public=PublicGame(obs);action=('play',card.uid,-1,-1)
        with self.assertRaises(UnknownDraw):public.child(action)
        self.assertEqual(public.observation(),obs)
        obs['deck_count']=0;obs['fatigue']=3
        child=PublicGame(obs).child(action)
        self.assertEqual(child.observation()['hp'],obs['hp']-4)
        self.assertEqual(child.observation()['fatigue'],4)

    def test_proof_combines_deployment_attack_and_spell_and_commits(self):
        game=self.game();cards=game.players[0].hand[:2]
        charge=Spec('semantic_charge',3,5,4,(('charge',1),),())
        bolt=Spec('semantic_bolt',2,effects=(Effect('play','damage','opponent',3),))
        deck=list(game.native_decks[0]);deck[cards[0].uid]=charge;deck[cards[1].uid]=bolt
        game.native_decks=(tuple(deck),game.native_decks[1]);game.players[0].hand=cards
        game.players[0].cash=5;game.players[1].hp=8
        planner=PublicPlanner(self.model(),mode='proof')
        obs=game.observation(0);actions=game.legal_actions(0)
        first=planner.choose(obs,actions);self.assertEqual(first['planner_reason'],'public_proof');self.assertEqual(first['proof_length'],3)
        game.apply(0,first['action'])
        for _ in range(2):
            row=planner.choose(game.observation(0),game.legal_actions(0))
            self.assertEqual(row['planner_reason'],'committed_proof');self.assertFalse(row['proof_mismatch'])
            game.apply(0,row['action'])
        self.assertLessEqual(game.players[1].hp,0)

    def test_unknown_draw_order_and_end_callback_boundaries(self):
        game=self.game();game.players[0].cash=10;game.players[1].hp=3
        card=game.players[0].hand[0]
        for effects,unknown in [((Effect('play','damage','opponent',3),Effect('play','draw','owner',1)),False),
                                ((Effect('play','draw','owner',1),Effect('play','damage','opponent',3)),True)]:
            obs=game.observation(0);held=next(h for h in obs['hand'] if h['uid']==card.uid)
            held['effects']=[vars(e) for e in effects]
            public=PublicGame(obs)
            if unknown:
                with self.assertRaises(UnknownDraw):public.child(('play',card.uid,-1,-1))
            else:self.assertTrue(public.child(('play',card.uid,-1,-1)).terminal())
        obs=game.observation(0)
        self.assertIsNone(PublicGame(obs).child(('end',-1,-1,-1)).terminal())
        from card_eval.legacy import environment
        ending=Spec('end_damage',2,1,4,(),(Effect('end','damage','opponent',3),))
        public=PublicGame(obs);public.players[0].units=[environment.Unit(88,'custom',1,4,4,spec=ending)]
        self.assertTrue(public.child(('end',-1,-1,-1)).terminal())
        draw_first=replace(ending,effects=(Effect('end','draw','owner',1),)+ending.effects)
        public.players[0].units=[replace(public.players[0].units[0],spec=draw_first)]
        with self.assertRaises(UnknownDraw):public.child(('end',-1,-1,-1))

    def test_hidden_worlds_do_not_change_planner_action(self):
        a=self.game('pressure');b=self.game('defense');a.players[0].cash=b.players[0].cash=10
        self.assertEqual(a.observation(0),b.observation(0))
        pa=PublicPlanner(self.model(),mode='value',nodes=12,seconds=.24)
        pb=PublicPlanner(self.model(),mode='value',nodes=12,seconds=.24)
        x=pa.choose(a.observation(0),a.legal_actions(0));y=pb.choose(b.observation(0),b.legal_actions(0))
        for field in ('action','planner_nodes','planner_reason','unknown_draw_boundaries'):self.assertEqual(x[field],y[field])

    def test_planner_has_separate_quality_gate_and_saved_configuration(self):
        request=default_request(['Bench'],samples=2);request['policies']=['learned'];request['planner']=dict(mode='value',nodes=4)
        blocked=evaluate(request);self.assertEqual(blocked['status'],'unqualified_policy')
        self.assertNotEqual(blocked['policy_validation']['frozen_policy'],blocked['policy_validation']['base_model'])
        request['allow_unqualified_policy']=True;request['opponents']=request['opponents'][:1]
        result=evaluate(request)
        self.assertEqual(result['status'],'complete');self.assertEqual(result['planner']['nodes'],4)
        self.assertEqual(result['comparisons'][0]['recommendation'],'experimental_only')
        self.assertNotEqual(result['base_model'],result['frozen_policy'])
        request['planner']['seconds']=.3
        with self.assertRaises(InputError):validate(request)

    def test_proved_four_attack_win_cannot_be_overridden_by_optimistic_value(self):
        from card_eval.legacy import environment
        from card_eval.relations import encode as relational_encode
        class OptimisticCritic:
            critic=np.zeros(74);fingerprint='test_critic_with_large_prediction_error'
            def encode(self,obs,actions):return relational_encode(obs,actions)
            def forward(self,state,actions):
                p=np.zeros(len(actions));p[1]=1.;return p,self.predict_value(state),None
            def predict_value(self,state):return -1. if state[18]>=.64 else 1.
        game=self.game();game.players[0].hand=[];game.players[1].hp=12
        plain=Spec('plain',0,4,2);taunt=Spec('taunt',0,1,1,(('taunt',1),),())
        game.players[0].units=[environment.Unit(j,'custom',a,2,2,ready=True,spec=plain) for j,a in ((1,4),(2,4),(3,4),(0,1))]
        game.players[1].units=[environment.Unit(40,'custom',1,1,1,spec=taunt,taunt=True)]
        obs=game.observation(0);actions=game.legal_actions(0)
        from card_eval.policies import lethal
        self.assertEqual(len(lethal(obs)[0]),4)
        critic=OptimisticCritic();s,af=critic.encode(obs,actions)
        self.assertEqual(critic.forward(s,af)[1],critic.predict_value(s))
        old=FrozenPlanner(OptimisticCritic(),'value',depth=1,margin=.3).choose(obs,actions)
        self.assertEqual(old['planner_reason'],'base_continuation_value');self.assertNotEqual(old['action'][1],0)
        fixed=PublicPlanner(OptimisticCritic(),'value',depth=1,margin=.3);first=fixed.choose(obs,actions)
        self.assertEqual(first['planner_reason'],'base_attack_proof');self.assertEqual(first['action'][1],0)
        self.assertNotEqual(old['policy'],first['policy']);game.apply(0,first['action'])
        while game.players[1].hp>0:
            row=fixed.choose(game.observation(0),game.legal_actions(0));self.assertEqual(row['planner_reason'],'base_attack_proof');game.apply(0,row['action'])
        self.assertLessEqual(game.players[1].hp,0)

    def test_negative_attack_search_is_reused_and_budget_restored(self):
        from card_eval.legacy import environment
        from card_eval.policies import lethal as actual_lethal
        game=self.game();game.players[0].hand=[];game.players[1].hp=3
        own=Spec('own',0,2,3);wall=Spec('wall',0,0,20,(('taunt',1),),())
        game.players[0].units=[environment.Unit(j,'custom',2,3,3,ready=True,spec=own) for j in range(4)]
        game.players[1].units=[environment.Unit(0,'custom',0,20,20,spec=wall,taunt=True)]
        obs=game.observation(0);actions=game.legal_actions(0);planner=PublicPlanner(self.model(),'value',nodes=4)
        with patch('card_eval.public_planner.lethal',wraps=actual_lethal) as outer,patch('card_eval.policies.lethal',wraps=actual_lethal) as inner:
            result=planner.choose(obs,actions)
        self.assertEqual(outer.call_count,1);self.assertEqual(inner.call_count,0)
        self.assertTrue(result['base_attack_search_reused']);self.assertEqual(planner.config['seconds'],.12)
        self.assertEqual(result['planner']['seconds'],.12);self.assertIn(result['action'],actions)
        self.assertIsNone(planner.base.attack_observation)


if __name__=='__main__':unittest.main()
