"""Targeted receipt for the previously observed interval-boundary repair.

Does not rerun the already-passed envelope/random-menu review.
"""
from pathlib import Path
import json

from frontier import affine_nonnegative_interval


CASES = [
    ('original_inverted_interval', [(-.5000000000001, 1), (.5, -1)], None),
    ('reverse_constraint_order', [(.5, -1), (-.5000000000001, 1)], None),
    ('exact_interior_singleton', [(-.5, 1), (.5, -1)], [.5, .5]),
    ('narrow_positive_interior', [(-.5, 1), (.5000000000001, -1)], [.5, .5000000000001]),
    ('empty_at_left_boundary', [(-1e-13, -1)], None),
    ('left_boundary_singleton', [(0, -1)], [0, 0]),
    ('left_boundary_clipping', [(1e-13, 1)], [0, 1]),
    ('narrow_left_interval', [(1e-13, -1)], [0, 1e-13]),
    ('empty_at_right_boundary', [(-1.0000000000001, 1)], None),
    ('right_boundary_singleton', [(-1, 1)], [1, 1]),
    ('right_boundary_clipping', [(1.0000000000001, -1)], [0, 1]),
    ('narrow_right_interval', [(-.9999999999999, 1)], [.9999999999999, 1]),
    ('two_endpoint_constraints', [(0, 1), (1, -1)], [0, 1]),
    ('no_constraints', [], [0, 1]),
    ('constant_negative_above_tolerance', [(-1e-8, 0)], None),
    ('constant_zero', [(0, 0)], [0, 1]),
    ('constant_positive', [(1, 0)], [0, 1]),
]


def review():
    checked = []
    for label, constraints, expected in CASES:
        actual = affine_nonnegative_interval(constraints)
        assert actual == expected, (label, actual, expected)
        if actual is not None:
            assert 0 <= actual[0] <= actual[1] <= 1, (label, actual)
        checked.append(dict(case=label, constraints=constraints, expected=expected,
                            actual=actual, passed=True))
    return dict(scope='Only the interval-boundary repair and nearby endpoint safety.',
                original_finding_preserved='review-frontier-independent.json',
                original_failure_now_returns=None, passed_cases=len(checked),
                original_main_mathematical_checks_rerun=False, cases=checked,
                limitation='Floating-point/tolerance semantics for near-zero constant inequalities are unchanged; this checks bound ordering and [0,1] endpoints.')


if __name__ == '__main__':
    result = review()
    Path(__file__).with_name('review-frontier-boundary-fix.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(passed_cases=result['passed_cases'], original_failure_now_returns=None)))
