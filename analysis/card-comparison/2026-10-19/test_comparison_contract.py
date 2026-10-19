import unittest
from compare_cards import compare
from frontier import envelope
from run_study import case_id


def flat(v):
    return envelope([dict(intercept=v, slope=0,
                          action={'candidate_used':False,'suffix':[]})])


class ComparisonContractTests(unittest.TestCase):
    def setUp(self):
        self.design = dict(candidate_ids=[1,2,3], names={'1':'x','2':'reference','3':'z'},
                           background_menus={'three_plain':[4,5]})
        self.data = {case_id('three_plain','empty',6,2):dict(settings={
            'central':{'1':flat(4),'2':flat(3),'3':flat(3),'background':flat(3)}})}

    def test_current_improvement_does_not_claim_identified_full_card_value(self):
        out = compare(self.data,self.design,[1,2],'three_plain','empty',6,2,'central',.5)
        self.assertEqual(out['comparisons'][0]['minimum'],1)
        self.assertFalse(out['comparisons'][0]['whole_card_ordering_identified'])
        self.assertFalse(out['cards'][0]['multi_turn_holding_cost_identified'])

    def test_both_suppressed_is_explicit_and_does_not_force_deployment(self):
        out = compare(self.data,self.design,[2,3],'three_plain','empty',6,2,'central',.5)
        self.assertTrue(out['comparisons'][0]['both_suppressed_by_background_or_budget'])
        self.assertFalse(out['cards'][0]['focal_required_for_strict_gain'])
        self.assertFalse(out['cards'][0]['one_optimal_current_plan']['candidate_used'])

    def test_unmatched_or_uncovered_conditions_are_rejected_instead_of_averaged(self):
        for ids,cash in [([1,99],6),([1,2],5),([1,1],6)]:
            with self.assertRaises(ValueError):
                compare(self.data,self.design,ids,'three_plain','empty',cash,2)


if __name__ == '__main__':
    unittest.main()
