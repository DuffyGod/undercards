"""New uncertainty accounting checks, independent of the game transition code."""
import unittest
from completion_bounds import empirical_envelope,lower_binomial


class CompletionChecks(unittest.TestCase):
    def test_unfinished_is_an_interval_not_a_half_win(self):
        self.assertEqual(empirical_envelope([[.25]],[[.25]]),[.25,.75])

    def test_all_terminal_closes_empirical_completion_gap(self):
        lower,upper=empirical_envelope([[1,0],[0,1]],[[0,1],[1,0]])
        self.assertAlmostEqual(lower,.5);self.assertAlmostEqual(upper,.5)

    def test_removing_losses_only_widens_unknown_upper_side(self):
        a=empirical_envelope([[.4]],[[.4]])
        b=empirical_envelope([[.4]],[[.1]])
        self.assertAlmostEqual(a[0],b[0]);self.assertGreater(b[1],a[1])
        self.assertEqual(lower_binomial(0,128,.001),0)

    def test_inconsistent_outcomes_refused(self):
        with self.assertRaises(ValueError):empirical_envelope([[.7]],[[.4]])


if __name__=='__main__':unittest.main(verbosity=2)
