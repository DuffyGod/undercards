from pathlib import Path
from copy import deepcopy
import json,tempfile,unittest
import numpy as np
from card_eval.entity_value import EntityValueNetwork,entity_state,GLOBAL
from card_eval.network import Network
from card_eval.game import NativeGame
from card_eval.profiles import base_deck,opponents
from card_eval.policies import ReferencePolicy
from card_eval.legacy import features
from card_eval.catalog import Spec,Effect
from dataclasses import asdict


class EntityValueChecks(unittest.TestCase):
    def observation(self):return NativeGame((base_deck(),opponents()['pressure']),950801,(ReferencePolicy(),ReferencePolicy())).observation(0)

    def test_representation_retains_relation_lost_by_both_aggregate_models(self):
        witness=json.loads(Path('artifacts/card_eval/v7/value-alias-witness.json').read_text());a,b=witness['observations']
        entity=EntityValueNetwork();aggregate=EntityValueNetwork(variant='aggregate')
        self.assertFalse(np.array_equal(entity_state(a),entity_state(b)))
        self.assertEqual(aggregate.predict_value(aggregate.value_encode(a)),aggregate.predict_value(aggregate.value_encode(b)))
        self.assertGreater(abs(entity.predict_value(entity_state(a))-entity.predict_value(entity_state(b))),1e-9)

    def test_hand_order_names_and_ids_are_not_value_features(self):
        obs=self.observation();other=deepcopy(obs);other['hand'].reverse()
        for h in other['hand']:h.update(name='new_name',card_id=999)
        net=EntityValueNetwork()
        self.assertAlmostEqual(net.predict_value(net.value_encode(obs)),net.predict_value(net.value_encode(other)),places=12)

    def test_effect_trigger_and_scope_binding_is_not_collapsed(self):
        a=asdict(Spec('a',3,1,4,(),(Effect('play','damage','all_enemy',2),Effect('end','damage','opponent',1))))
        b=asdict(Spec('b',3,1,4,(),(Effect('play','damage','opponent',2),Effect('end','damage','all_enemy',1))))
        np.testing.assert_array_equal(features.card_features(a),features.card_features(b))
        obs=self.observation();other=deepcopy(obs)
        uid=obs['hand'][0]['uid'];role=obs['hand'][0]['role']
        obs['hand']=[dict(a,uid=uid,role=role)];other['hand']=[dict(b,uid=uid,role=role)]
        self.assertFalse(np.array_equal(entity_state(obs),entity_state(other)))

    def test_manual_gradients_match_finite_differences_for_both_arms(self):
        a=self.observation();b=deepcopy(a);b['hp']=3;b['enemy_hp']=8
        for variant in ('entity','aggregate'):
            net=EntityValueNetwork(variant=variant);x=np.asarray([net.value_encode(a),net.value_encode(b)])
            loss,grad=net.loss_grad(x,[0,1],[1,2]);rng=np.random.default_rng(88)
            for k,param in net.p.items():
                for index in rng.choice(param.size,min(4,param.size),replace=False):
                    old=param.flat[index];eps=1e-5
                    param.flat[index]=old+eps;plus=net.loss_grad(x,[0,1],[1,2])[0]
                    param.flat[index]=old-eps;minus=net.loss_grad(x,[0,1],[1,2])[0];param.flat[index]=old
                    self.assertAlmostEqual(float(grad[k].flat[index]),(plus-minus)/(2*eps),places=7,msg=k)

    def test_actor_unchanged_by_value_parameters_and_roundtrip(self):
        base=Network.load('card_eval/models/paired-v5.npz')[0];net=EntityValueNetwork(base)
        game=NativeGame((base_deck(),opponents()['pressure']),950802,(ReferencePolicy(),ReferencePolicy()));obs=game.observation(0);actions=game.legal_actions(0)
        p=base.forward(*base.encode(obs,actions))[0];q=net.forward(*net.encode(obs,actions))[0]
        np.testing.assert_array_equal(p,q);self.assertEqual(net.actor_fingerprint,base.actor_fingerprint)
        for w in net.p.values():w*=.7
        np.testing.assert_array_equal(p,net.forward(*net.encode(obs,actions))[0])
        with tempfile.TemporaryDirectory(dir='work') as directory:
            path=Path(directory)/'entity.npz';net.save(path,dict(validation=dict(qualified=False)))
            loaded,_=Network.load(path);self.assertEqual(net.fingerprint,loaded.fingerprint)
            self.assertEqual(net.predict_value(net.value_encode(obs)),loaded.predict_value(loaded.value_encode(obs)))


if __name__=='__main__':unittest.main()
