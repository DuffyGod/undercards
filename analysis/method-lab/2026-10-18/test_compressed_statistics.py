"""Compression must preserve existing scores, cash gates and stat marginals."""
from pathlib import Path
import json
import unittest

from compressed_statistics import evaluate_compressed
from run_statistical_study import SELECTED, evaluate_one
from statistical_value import Prices


class CompressionInvariant(unittest.TestCase):
    def test_all_frozen_mechanisms_preserve_joint_cash_and_numeric_marginals(self):
        inputs=json.loads((Path(__file__).parent/'statistical_inputs.json').read_text(encoding='utf-8'))
        panels=[dict(enemy=(),weight=.2),dict(enemy=((3,2),)*3,weight=.3),dict(enemy=((6,7),),weight=.5)]
        for parameters in ({},{'face_share':.1,'threshold':.6,'tail':1.,'face':.4}):
            prices=Prices(inputs,**parameters)
            for cid in SELECTED:
                card=inputs['cards'][str(cid)]
                before=evaluate_one(card,inputs,panels,'aggro_wide',prices,True)
                after=evaluate_compressed(card,inputs,panels,'aggro_wide',prices,True)
                for key in before:
                    if isinstance(before[key],(int,float)):
                        self.assertAlmostEqual(before[key],after[key],places=11,msg=f'{cid}:{key}')
                    elif isinstance(before[key],list):
                        for a,b in zip(before[key],after[key]):self.assertAlmostEqual(a,b,places=11)
                    elif isinstance(before[key],dict):
                        for h,v in before[key].items():self.assertAlmostEqual(v,after[key][h],places=11)


if __name__=='__main__':unittest.main()
