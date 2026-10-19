import unittest

from frontier import (affine_nonnegative_interval, difference, envelope, mixture,
                      paired_range, single_use_opportunity_bounds, value)


def line(a, b):
    return dict(intercept=a, slope=b)


class DecisionBoundaryTests(unittest.TestCase):
    def test_three_price_samples_can_miss_a_real_interior_reversal(self):
        # Nonnegative payments: A menus cost3/cost1; B menu cost2; both may abstain.
        a = envelope([line(1.1, -3), line(.7, -1), line(0, 0)])
        b = envelope([line(1, -2), line(0, 0)])
        self.assertTrue(all(value(a, x) >= value(b, x) for x in (0, .5, 1)))
        d = difference(a, b)
        self.assertAlmostEqual(d['minimum_at'], .2)
        self.assertAlmostEqual(d['minimum'], -.1)
        self.assertTrue(any(abs(x-.1) < 1e-10 for x in d['zero_points']))
        self.assertTrue(any(abs(x-.3) < 1e-10 for x in d['zero_points']))

    def test_common_price_must_not_be_pessimized_separately_for_each_board(self):
        # Differences are lambda-.5 and .5-lambda. Their equal mixture is0
        # for every shared lambda, while min(d0)+min(d1) would falsely be-1.
        first = {'s': {'a': envelope([line(0, 1)]), 'b': envelope([line(.5, 0)])}}
        second = {'s': {'a': envelope([line(.5, 0)]), 'b': envelope([line(0, 1)])}}
        r = mixture(first, second, 'a', 'b')
        self.assertEqual(r['left_weakly_preferred_mass'], [.5, .5])
        self.assertEqual(r['right_weakly_preferred_mass'], [.5, .5])

    def test_parameter_corner_votes_do_not_become_probabilities(self):
        data = {'x': {'a': envelope([line(2, 0)]), 'b': envelope([line(0, 0)])},
                'y': {'a': envelope([line(0, 0)]), 'b': envelope([line(1, 0)])}}
        result = paired_range(data, 'a', 'b')
        self.assertEqual(result['minimum'], -1)
        self.assertEqual(result['maximum'], 2)
        self.assertEqual(result['status'], 'conditional_ordering')

    def test_small_infeasible_intersection_never_returns_reversed_endpoints(self):
        self.assertIsNone(affine_nonnegative_interval([(-.5000000000001, 1), (.5, -1)]))
        self.assertEqual(affine_nonnegative_interval([(-.5, 1), (.5, -1)]), [.5, .5])

    def test_identical_one_period_marginals_leave_carrying_sign_unidentified(self):
        result = single_use_opportunity_bounds(4, [.5, .5], 3)
        self.assertEqual(result['relative_value_bounds'], [-1, 1])
        persistent = .5 * max(4, 4) + .5 * max(0, 0) - 3
        alternating = .5 * max(4, 0) + .5 * max(0, 4) - 3
        self.assertEqual([persistent, alternating], result['relative_value_bounds'])

    def test_invalid_opportunity_inputs_cannot_manufacture_a_carry_score(self):
        for marginals in ([], [.5, 1.01], [True]):
            with self.assertRaises(ValueError):
                single_use_opportunity_bounds(4, marginals, 3)


if __name__ == '__main__':
    unittest.main()
