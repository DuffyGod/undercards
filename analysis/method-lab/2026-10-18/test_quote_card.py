import unittest
from quote_card import slot


class FrozenQueryBoundary(unittest.TestCase):
    def test_alternate_reference_keeps_missing_marginals_unknown_and_only_shifts_zero(self):
        a=slot([20,530],'three_plain','three_3_2',4,2,0.,2)
        b=slot([20,530],'three_plain','three_3_2',4,2,0.,4)
        for row in b['cards']:
            self.assertIsNone(row['plus_attack_reoptimized'])
            self.assertIsNone(row['cash_opportunity_gain_above_residual'])
        self.assertAlmostEqual(a['comparisons'][0]['slot_difference'],b['comparisons'][0]['slot_difference'])
        shifts=[x['slot_delta']-y['slot_delta'] for x,y in zip(a['cards'],b['cards'])]
        self.assertAlmostEqual(shifts[0],shifts[1])
        self.assertNotEqual(shifts[0],0.)


if __name__=='__main__':unittest.main()
