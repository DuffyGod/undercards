import copy
import unittest
from . import root_mix as mix


def matrix(values=((9,15),(12,9),(9,12))):
    return dict(worlds=['s','w'],policies=[dict(id=i,guarantees=list(v)) for i,v in enumerate(values)],
                policies_are_common=True,world_fixed_before_randomization=True)


class RootMixTests(unittest.TestCase):
    def test_guarantee_and_expectation_are_distinct(self):
        r=mix.evaluate(matrix())
        self.assertEqual(r['robust_expected_hp']['fraction'],'11')
        self.assertEqual(r['guaranteed_hp_every_realization']['fraction'],'9')
        self.assertEqual({x['policy_id']:x['probability']['fraction'] for x in r['probabilities']},{0:'1/3',1:'2/3'})

    def test_dominated_pairs_do_not_produce_a_false_champion(self):
        r=mix.evaluate(matrix(((10,10),(0,4),(4,0))))
        self.assertEqual(r['robust_expected_hp']['fraction'],'10')
        self.assertEqual(r['probabilities'],[dict(policy_id=0,probability=dict(fraction='1',decimal=1.0))])

    def test_identical_and_one_policy(self):
        for v in [((3,3),),((3,3),(3,3))]:
            self.assertEqual(mix.evaluate(matrix(v))['robust_expected_hp']['fraction'],'3')

    def test_unknown_and_false_information_protocol_refused(self):
        for change in [dict(policies_are_common=False),dict(world_fixed_before_randomization=False),
                       dict(policies=[dict(id=0,guarantees=[None,10])])]:
            d=matrix();d.update(change)
            with self.assertRaises(ValueError):mix.evaluate(d)

    def test_endpoint_best_and_exact_decimal(self):
        r=mix.evaluate(matrix(((0.1,0.4),(0.3,0.2))))
        self.assertEqual(r['robust_expected_hp']['fraction'],'1/4')

    def test_world_and_policy_reordering_changes_no_value(self):
        d=matrix();a=mix.evaluate(d);d['policies'].reverse()
        self.assertEqual(mix.evaluate(d)['robust_expected_hp'],a['robust_expected_hp'])
        for r in d['policies']:r['guarantees'].reverse()
        d['worlds'].reverse()
        self.assertEqual(mix.evaluate(d)['robust_expected_hp'],a['robust_expected_hp'])


if __name__=='__main__':unittest.main()
