from copy import deepcopy
from pathlib import Path
import io,tempfile,unittest
import numpy as np
from card_eval.game import NativeGame
from card_eval.profiles import base_deck
from card_eval.policies import ReferencePolicy
from card_eval.suffix_sampling import SuffixController,OnlineForkRecorder,stable
from card_eval.regret_model import RegretNetwork
from card_eval.action_value import INPUT,encode
from card_eval.network import Network


class StopAtDecision(Exception):pass


class Capture:
    def choose(self,obs,actions):self.obs=obs;self.actions=actions;raise StopAtDecision()


class SuffixPolicyChecks(unittest.TestCase):
    def root(self):
        capture=Capture();g=NativeGame((base_deck(),base_deck()),3098801,(capture,ReferencePolicy()))
        with self.assertRaises(StopAtDecision):g.act_turn(0)
        return g,capture.obs,capture.actions

    def test_future_order_intervention_preserves_both_observations_and_opponent(self):
        g,obs,actions=self.root();before=[g.observation(a) for a in (0,1)];own=[c.uid for c in g.players[0].deck]
        enemy=deepcopy(g.players[1]);row=dict(observation=obs,legal_actions=actions,selection=dict(action=actions[0]))
        controller=SuffixController([row],0,actions[0],(ReferencePolicy(),ReferencePolicy()),777);controller.game=g
        selected=controller.choose(obs,actions)
        self.assertEqual(selected['action'],actions[0]);self.assertTrue(controller.checked)
        self.assertEqual(before,[g.observation(a) for a in (0,1)]);self.assertEqual(enemy,g.players[1])
        self.assertEqual(sorted(own),sorted(c.uid for c in g.players[0].deck));self.assertNotEqual(own,[c.uid for c in g.players[0].deck])
        np.testing.assert_array_equal(encode(obs,actions)[1][0],encode(g.observation(0),actions)[1][0])

    def test_online_root_selection_never_replaces_a_root_using_later_history(self):
        _,obs,actions=self.root();obs=deepcopy(obs);obs['turn']=3
        rec=OnlineForkRecorder(io.StringIO(),99,(3,8));rec.record(obs,actions,dict(action=actions[0]))
        first=dict(rec.forks)
        for turn in (4,5,6,7,8,9,10,11,12):
            later=deepcopy(obs);later['turn']=turn;rec.record(later,actions,dict(action=actions[0]))
        self.assertEqual(rec.forks[0],first[0]);self.assertEqual(rec.rows[rec.forks[1]]['observation']['turn'],8)

    def test_fractional_and_masked_objective_gradients(self):
        rng=np.random.default_rng(7);x=rng.normal(0,.2,(6,INPUT));y=np.array([0.,.25,np.nan,.75,1.,.5]);groups=np.array([0,0,0,1,1,1])
        for objective in ('regret','centered'):
            net=RegretNetwork(objective=objective,hidden=3);args=(x,y,groups,{0:0,1:3},{0:.3,1:.7})
            _,grad=net.loss_grad(*args)
            for name,p in net.p.items():
                for i in rng.choice(p.size,min(5,p.size),replace=False):
                    old=p.flat[i];eps=1e-5;p.flat[i]=old+eps;plus=net.loss_grad(*args)[0]
                    p.flat[i]=old-eps;minus=net.loss_grad(*args)[0];p.flat[i]=old
                    self.assertAlmostEqual(float(grad[name].flat[i]),(plus-minus)/(2*eps),places=7,msg=objective+name)
            filled=y.copy();filled[2]=0.
            self.assertNotAlmostEqual(net.loss_grad(*args)[0],net.loss_grad(x,filled,groups,{0:0,1:3},{0:.3,1:.7})[0],places=10)

    def test_policy_roundtrip_and_critic_cannot_change_logit_choice(self):
        _,obs,actions=self.root();base=Network.load('card_eval/models/paired-v5.npz')[0];net=RegretNetwork(base)
        s,af=net.encode(obs,actions);before=net.actor_fingerprint;p=net.forward(s,af)[0]
        net.fit_value([s,s],[0,1],[1,1],iterations=8)
        self.assertEqual(before,net.actor_fingerprint);np.testing.assert_array_equal(p,net.forward(s,af)[0])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'policy.npz';net.save(path,dict(validation=dict(qualified=False)))
            loaded,_=Network.load(path);self.assertEqual(net.fingerprint,loaded.fingerprint)
            np.testing.assert_array_equal(p,loaded.forward(*loaded.encode(obs,actions))[0])


if __name__=='__main__':unittest.main()
