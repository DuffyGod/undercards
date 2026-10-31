from pathlib import Path
import tempfile, unittest
import numpy as np
from card_eval.catalog import Spec, Effect
from card_eval.game import NativeGame
from card_eval.profiles import base_deck, opponents
from card_eval.policies import ReferencePolicy, LearnedPolicy
from card_eval.network import Network
from card_eval.advantage_model import AdvantageNetwork, encode, HEAD_DIM
from card_eval.counterfactual_research import PrefixController, PrefixAgent


class MemoryRecorder:
    def __init__(self): self.rows = []
    def record(self, obs, actions, selected):
        self.rows.append(dict(observation=obs, legal_actions=actions, selection=selected))
    def finish(self, result): self.result = result


class CounterfactualChecks(unittest.TestCase):
    def test_same_intervention_and_continuation_reconstruct_original_terminal(self):
        decks = (base_deck(), opponents()['pressure']); rec = MemoryRecorder()
        r = NativeGame(decks, 950201, (ReferencePolicy('guard'), ReferencePolicy('race')), recorder=rec).run()
        fork = next(j for j, row in enumerate(rec.rows) if row['observation']['player'] == 0 and len(row['legal_actions']) > 1)
        controller = PrefixController(rec.rows, fork, rec.rows[fork]['selection']['action'], (ReferencePolicy('guard'), ReferencePolicy('race')))
        branch = NativeGame(decks, 950201, (PrefixAgent(controller), PrefixAgent(controller))).run()
        self.assertTrue(controller.checked)
        for key in ('won','lost','round','a_hp','b_hp','a_cash','a_played','a_draws','candidate_wait'):
            self.assertEqual(r[key], branch[key], key)

    def test_prefix_mismatch_is_rejected(self):
        controller = PrefixController([dict(observation=dict(player=0), legal_actions=[('end',-1,-1,-1)])], 0,
            ('end',-1,-1,-1), (ReferencePolicy(),ReferencePolicy()))
        with self.assertRaisesRegex(ValueError, 'prefix'):
            controller.choose(dict(player=1), [('end',-1,-1,-1)])

    def test_mechanism_scope_and_new_names_are_semantic_inputs(self):
        rec = MemoryRecorder(); g = NativeGame((base_deck(),opponents()['pressure']),950202,(ReferencePolicy(),ReferencePolicy()),recorder=rec)
        g.players[0].cash=20; obs=g.observation(0); actions=g.legal_actions(0); s,a=encode(obs,actions)
        for h in obs['hand']: h.update(name='unknown_name',card_id=999)
        sr,ar=encode(obs,actions); np.testing.assert_array_equal(s,sr); np.testing.assert_array_equal(a,ar)
        h=obs['hand'][0]; h['effects']=[dict(trigger='end',op='damage',scope='opponent',amount=1,health=0)]
        first=encode(obs,actions)[1]; h['effects'][0]['scope']='self'; second=encode(obs,actions)[1]
        self.assertFalse(np.array_equal(first,second))

    def test_paired_targets_ignore_common_offset_and_critic_cannot_change_policy(self):
        x=np.zeros((2,HEAD_DIM)); x[0,0]=1; x[1,0]=-1
        a=AdvantageNetwork(); b=AdvantageNetwork()
        a.fit_advantage([(x,[0,.8])],iterations=30); b.fit_advantage([(x,[.2,1.])],iterations=30)
        np.testing.assert_allclose(a.advantage,b.advantage,atol=1e-10)
        before=a.actor_fingerprint; a.fit_value(np.array([[1.,0.],[1.,1.]]),[0,1],[1.,1.])
        self.assertEqual(before,a.actor_fingerprint)

    def test_roundtrip_load_and_legal_policy_choice(self):
        net=AdvantageNetwork(); g=NativeGame((base_deck(),opponents()['pressure']),950203,(ReferencePolicy(),ReferencePolicy()))
        obs=g.observation(0); actions=g.legal_actions(0)
        with tempfile.TemporaryDirectory(dir='work') as directory:
            path=Path(directory)/'policy.npz'; net.save(path,dict(validation=dict(qualified=False)))
            loaded,_=Network.load(path); self.assertEqual(net.fingerprint,loaded.fingerprint)
            self.assertIn(LearnedPolicy(loaded).choose(obs,actions)['action'],actions)


if __name__=='__main__': unittest.main()
