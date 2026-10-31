from pathlib import Path
import tempfile,unittest
import numpy as np
from card_eval.game import NativeGame
from card_eval.knowledge import Knowledge,vector,STATE_DIM
from card_eval.profiles import base_deck,opponents
from card_eval.policies import ReferencePolicy,LearnedPolicy
from card_eval.memory_model import MemoryNetwork
from card_eval.network import Network
from card_eval.memory_research import augmented_episodes,read_rows
from card_eval.counterfactual_research import PrefixController,PrefixAgent
from card_eval.training import decode


class KnowledgeChecks(unittest.TestCase):
    def game(self,enemy='pressure'):
        return NativeGame((base_deck(),opponents()[enemy]),950301,(ReferencePolicy(),ReferencePolicy()))

    def test_unplayed_opponent_identity_never_enters_owner_observation(self):
        a=self.game('pressure');b=self.game('defense')
        self.assertEqual(a.observation(0),b.observation(0))
        a.players[1].deck.reverse();a.players[0].deck.reverse()
        self.assertEqual(a.observation(0),b.observation(0))

    def test_owner_knows_multiset_but_not_order(self):
        own=base_deck();other=opponents()['pressure']
        a=Knowledge((own,other));b=Knowledge((own[::-1],other[::-1]))
        self.assertEqual(a.fields(0),b.fields(0));self.assertNotEqual(a.fields(0),a.fields(1))

    def test_public_play_survives_history_truncation_and_board_removal(self):
        g=self.game();before=vector(g.observation(0)).copy();g.players[1].cash=100
        action=next(a for a in g.legal_actions(1) if a[0]=='play');g.apply(1,action)
        after=vector(g.observation(0));self.assertEqual(after[-1],1/25);self.assertFalse(np.array_equal(before,after))
        for _ in range(12):g.event(0,'effect',op='heal',trigger='end',amount=0)
        g.players[1].units.clear();np.testing.assert_array_equal(after,vector(g.observation(0)))

    def test_missing_knowledge_is_not_silently_zero_and_roundtrip_preserves_policy(self):
        g=self.game();obs=g.observation(0);actions=g.legal_actions(0);net=MemoryNetwork()
        missing=dict(obs);missing.pop('knowledge_schema')
        with self.assertRaises(ValueError):net.encode(missing,actions)
        before=net.actor_fingerprint;xs=np.zeros((2,STATE_DIM));xs[:,0]=1;xs[1,1]=1
        net.fit_value(xs,[0,1],[1.,1.]);self.assertEqual(before,net.actor_fingerprint)
        with tempfile.TemporaryDirectory(dir='work') as directory:
            path=Path(directory)/'model.npz';net.save(path,dict(validation=dict(qualified=False)))
            loaded,_=Network.load(path);self.assertEqual(net.fingerprint,loaded.fingerprint)
            self.assertIn(LearnedPolicy(loaded).choose(obs,actions)['action'],actions)

    def test_old_serialized_public_prefix_reconstructs_live_knowledge(self):
        meta,records=next(augmented_episodes('train'))
        fork=next(read_rows(Path('artifacts/card_eval/v5/train-forks-0000.jsonl.gz')))
        self.assertEqual(meta['seed'],fork['seed']);index=fork['decision']
        action=records[index]['selection']['action']
        controller=PrefixController(records,index,action,(ReferencePolicy('race'),ReferencePolicy(meta['opponent'])))
        decks=tuple(tuple(decode(s) for s in deck) for deck in meta['decks'])
        r=NativeGame(decks,meta['seed'],(PrefixAgent(controller),PrefixAgent(controller)),seats=meta['seat'],souls=meta['souls']).run()
        self.assertTrue(controller.checked);self.assertFalse(r['unfinished'])


if __name__=='__main__':unittest.main()
