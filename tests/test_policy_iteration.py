from pathlib import Path
from tempfile import TemporaryDirectory
import gzip,json,unittest
from unittest.mock import patch
import numpy as np
from card_eval.policy_iteration import dataset,stopping_indices,root_turns
from card_eval.regret_model import RegretNetwork
from card_eval.network import Network
from card_eval.suffix_sampling import OnlineForkRecorder
import io


class PolicyIterationChecks(unittest.TestCase):
    def test_paired_targets_unknown_and_unsampled_actions_stay_missing(self):
        root=dict(record_type='root',seed=1,observation={},legal_actions=[['end',-1,-1,-1],['play',1,-1,-1],['play',2,-1,-1]],anchor=0,
            cells=[dict(target=t,action_index=i,result=dict(unfinished=(t=='updated' and i==1),won=None if t=='updated' and i==1 else i==0))
                   for t in ('updated','frozen') for i in (0,1)])
        with TemporaryDirectory() as temporary:
            folder=Path(temporary);(folder/'p1-train').mkdir()
            with gzip.open(folder/'p1-train/episode-0000.jsonl.gz','wt') as sink:sink.write(json.dumps(root)+'\n')
            with patch('card_eval.policy_iteration.encode',return_value=(None,(np.eye(3),None))):
                updated=dataset(folder,1,'train','updated');frozen=dataset(folder,1,'train','frozen')
            np.testing.assert_array_equal(updated['groups'],frozen['groups'])
            self.assertEqual(len(updated['x']),3);self.assertEqual(updated['y'][0],1)
            self.assertTrue(np.isnan(updated['y'][1]));self.assertTrue(np.isnan(updated['y'][2]))
            self.assertEqual(frozen['y'][1],0);self.assertTrue(np.isnan(frozen['y'][2]))

    def test_donor_root_reconstruction_matches_online_stopping(self):
        turns=root_turns(3640000,2026110213);rows=[];rec=OnlineForkRecorder(io.StringIO(),1,turns)
        with patch('card_eval.policy_iteration.lethal',return_value=((),0)),patch('card_eval.suffix_sampling.lethal',return_value=((),0)):
            for turn in range(1,15):
                obs=dict(player=0,turn=turn);actions=[('end',-1,-1,-1),('play',1,-1,-1)]
                row=dict(observation=obs,legal_actions=actions,selection=dict(action_index=0));rows.append(row)
                rec.record(obs,actions,row['selection'])
            self.assertEqual(stopping_indices(rows,turns),sorted(rec.forks.values()))
            self.assertEqual(stopping_indices(rows[:5],turns),stopping_indices(rows,turns)[:1])

    def test_target_annotation_roundtrip_preserves_behavior_and_legacy_fingerprint(self):
        path=Path('artifacts/card_eval/v11/regret_mean-selected.npz');net,meta=Network.load(path)
        self.assertEqual(net.fingerprint,meta['fingerprint']);before=net.actor_fingerprint
        net.target_description='one action then the current round0 policy'
        self.assertEqual(net.actor_fingerprint,before)
        with TemporaryDirectory() as temporary:
            p=Path(temporary)/'model.npz';net.save(p,dict(value_unfitted=True,validation=dict(qualified=False)))
            loaded,_=Network.load(p)
            self.assertEqual(loaded.target_description,net.target_description);self.assertEqual(loaded.fingerprint,net.fingerprint)


if __name__=='__main__':unittest.main()
