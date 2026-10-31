from copy import deepcopy
from pathlib import Path
import json, tempfile, unittest
import numpy as np
from card_eval.action_value import ActionValueNetwork, ordered_card, encode, INPUT
from card_eval.network import Network
from card_eval.game import NativeGame
from card_eval.profiles import base_deck
from card_eval.policies import ReferencePolicy


class ActionValueChecks(unittest.TestCase):
    def game(self):
        return NativeGame((base_deck(),base_deck()),2598801,(ReferencePolicy(),ReferencePolicy()))

    def test_both_objective_gradients(self):
        rng=np.random.default_rng(68);x=rng.normal(0,.2,(5,INPUT));y=[0,1,1,1,0];groups=[0,0,1,1,1];w=[1,1,2,2,2]
        for objective in ('centered','pointwise'):
            net=ActionValueNetwork(objective=objective,hidden=3)
            _,grad=net.loss_grad(x,y,groups,w)
            for name,p in net.p.items():
                for i in rng.choice(p.size,min(5,p.size),replace=False):
                    old=p.flat[i];eps=1e-5
                    p.flat[i]=old+eps;plus=net.loss_grad(x,y,groups,w)[0]
                    p.flat[i]=old-eps;minus=net.loss_grad(x,y,groups,w)[0];p.flat[i]=old
                    self.assertAlmostEqual(float(grad[name].flat[i]),(plus-minus)/(2*eps),places=7,msg=objective+name)

    def test_centered_objective_removes_flat_fork_absolute_win_label(self):
        rng=np.random.default_rng(4);x=rng.normal(size=(3,INPUT))
        for objective in ('centered','pointwise'):
            net=ActionValueNetwork(objective=objective)
            a,ga=net.loss_grad(x,[0,0,0],[0,0,0],[1,1,1])
            b,gb=net.loss_grad(x,[1,1,1],[0,0,0],[1,1,1])
            if objective=='centered':
                self.assertAlmostEqual(a,b)
                for k in ga:np.testing.assert_allclose(ga[k],gb[k],atol=1e-14)
            else:self.assertGreater(abs(ga['c'][0]-gb['c'][0]),.9)

    def test_effect_order_witness_is_distinct_and_overflow_refused(self):
        a,b=json.loads(Path('artifacts/card_eval/v9/effect-order-witness.json').read_text())['observations']
        actions=[('end',-1,-1,-1),('play',0,-1,-1)]
        self.assertFalse(np.array_equal(encode(a,actions)[1][0][1],encode(b,actions)[1][0][1]))
        card=deepcopy(a['hand'][0]);card['effects']=card['effects']*5
        with self.assertRaisesRegex(ValueError,'capacity'):ordered_card(card)

    def test_head_name_uid_hand_order_invariant_and_missing_knowledge_refused(self):
        game=self.game();a=game.observation(0);actions=game.legal_actions(0);b=deepcopy(a)
        b['hand'].reverse()
        for h in b['hand']:h.update(name='renamed',card_id=909090)
        np.testing.assert_allclose(encode(a,actions)[1][0],encode(b,actions)[1][0])
        b.pop('knowledge')
        with self.assertRaisesRegex(ValueError,'missing'):encode(b,actions)

    def test_roundtrip_and_value_fit_cannot_change_policy(self):
        net=ActionValueNetwork(Network.load('card_eval/models/paired-v5.npz')[0]);game=self.game()
        obs=game.observation(0);actions=game.legal_actions(0);s,af=net.encode(obs,actions)
        before=net.actor_fingerprint;p=net.forward(s,af)[0].copy()
        net.fit_value([s,s],[0,1],[1,1],iterations=10)
        self.assertEqual(before,net.actor_fingerprint);np.testing.assert_array_equal(p,net.forward(s,af)[0])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'checkpoint.npz';net.save(path,dict(validation=dict(qualified=False)))
            loaded,_=Network.load(path);self.assertEqual(net.fingerprint,loaded.fingerprint)
            np.testing.assert_array_equal(p,loaded.forward(*loaded.encode(obs,actions))[0])


if __name__=='__main__':unittest.main()
