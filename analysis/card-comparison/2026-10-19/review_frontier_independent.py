"""Independent finite-line review; no old card experiment is rerun.

The oracle keeps Fraction arithmetic, visits ALL original line intersections,
and evaluates max(original lines). Production hull/difference routines are
never used to construct expected results.
"""
from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path
import json
import math
import random

import frontier as production

HERE = Path(__file__).resolve().parent
TOL = 1e-8


def line(b, m):
    return dict(intercept=b, slope=m)


def f(x):
    return F(str(x))


def intersections(groups):
    xs = {F(0), F(1)}
    for lines in groups:
        for i, a in enumerate(lines):
            for b in lines[i + 1:]:
                dm = f(a['slope']) - f(b['slope'])
                if dm:
                    x = (f(b['intercept']) - f(a['intercept'])) / dm
                    if 0 <= x <= 1:
                        xs.add(x)
    return sorted(xs)


def direct(lines, x):
    return max(f(z['intercept']) + f(z['slope']) * x for z in lines)


def reference_difference(left, right):
    xs = intersections([left, right])
    ys = [direct(left, x) - direct(right, x) for x in xs]
    roots = {x for x, y in zip(xs, ys) if not y}
    for a, b, ya, yb in zip(xs, xs[1:], ys, ys[1:]):
        if ya * yb < 0:
            roots.add(a - ya * (b - a) / (yb - ya))
    return min(ys), max(ys), sorted(roots)


def reference_interval(constraints):
    # Independent candidate-point feasibility, rather than updating bounds.
    candidates = {F(0), F(1)}
    for a, b in constraints:
        if b and 0 <= -a / b <= 1:
            candidates.add(-a / b)
    feasible = [q for q in candidates if all(a + b * q >= 0 for a, b in constraints)]
    return [min(feasible), max(feasible)] if feasible else None


def reference_mixture(first, second, lam=None):
    constraints = []
    for theta in first:
        groups = [first[theta]['A'], first[theta]['B'],
                  second[theta]['A'], second[theta]['B']]
        xs = [f(lam)] if lam is not None else intersections(groups)
        for x in xs:
            d0 = direct(groups[0], x) - direct(groups[1], x)
            d1 = direct(groups[2], x) - direct(groups[3], x)
            constraints.append((d0, d1 - d0))
    return (reference_interval(constraints),
            reference_interval([(-a, -b) for a, b in constraints]))


def close(actual, expected):
    assert math.isclose(actual, float(expected), rel_tol=1e-9, abs_tol=TOL), (actual, expected)


def interval_close(actual, expected):
    assert (actual is None) == (expected is None), (actual, expected)
    if expected is not None:
        assert actual[0] <= actual[1], actual
        for a, e in zip(actual, expected):
            close(a, e)


def review():
    rng = random.Random(202610190217)
    checks = dict(envelope_cases=0, difference_cases=0, weighted_cases=0,
                  mixture_cases=0, paired_range_cases=0)
    observations = []

    def random_lines():
        return [line(rng.randint(0, 35), -rng.randint(0, 14))
                for _ in range(rng.randint(1, 7))]

    def check_pair(a, b):
        ca, cb = production.envelope(a), production.envelope(b)
        xs = intersections([a, b])
        probes = xs + [(u + v) / 2 for u, v in zip(xs, xs[1:])]
        for lines, curve in ((a, ca), (b, cb)):
            for x in probes:
                close(production.value(curve, float(x)), direct(lines, x))
            assert curve[0]['low'] == 0 and curve[-1]['high'] == 1
            checks['envelope_cases'] += 1
        expected = reference_difference(a, b)
        actual = production.difference(ca, cb)
        close(actual['minimum'], expected[0]); close(actual['maximum'], expected[1])
        # Roots on flat zero intervals may be represented by interval endpoints.
        # Every reported root must be an actual root; all isolated roots must appear.
        for x in actual['zero_points']:
            close(direct(a, f(x)) - direct(b, f(x)), 0)
        for x in expected[2]:
            y0 = direct(a, max(F(0), x - F(1, 10**7))) - direct(b, max(F(0), x - F(1, 10**7)))
            y1 = direct(a, min(F(1), x + F(1, 10**7))) - direct(b, min(F(1), x + F(1, 10**7)))
            if y0 and y1:
                assert any(abs(float(x) - z) <= TOL for z in actual['zero_points']), (x, actual)
        checks['difference_cases'] += 1
        return actual

    twice = check_pair([line(8, -8), line(4, 0)], [line(7, -4)])
    close(twice['minimum'], -1); close(twice['maximum'], 1)
    assert twice['zero_points'] == [.25, .75], twice
    observations.append(dict(case='two_order_reversals', result=twice))
    check_pair([line(1, 0), line(2, 0), line(2, -1)], [line(2, 0)])
    check_pair([line(5, -5), line(0, 0)], [line(1, 0), line(4, -4)])
    for _ in range(300):
        check_pair(random_lines(), random_lines())

    for _ in range(100):
        groups = [random_lines() for _ in range(rng.randint(2, 4))]
        weights = [F(1, len(groups))] * len(groups)
        result = production.weighted_curve([production.envelope(g) for g in groups], list(map(float, weights)))
        xs = intersections(groups)
        for x in xs + [(a + b) / 2 for a, b in zip(xs, xs[1:])]:
            close(production.value(result, float(x)), sum(w * direct(g, x) for w, g in zip(weights, groups)))
        checks['weighted_cases'] += 1

    def check_mixture(first, second, lam=None):
        expected = reference_mixture(first, second, lam)
        curves = [{theta: {cid: production.envelope(lines) for cid, lines in cards.items()}
                   for theta, cards in scenario.items()} for scenario in (first, second)]
        actual = production.mixture(*curves, 'A', 'B', lam=lam)
        interval_close(actual['left_weakly_preferred_mass'], expected[0])
        interval_close(actual['right_weakly_preferred_mass'], expected[1])
        checks['mixture_cases'] += 1
        return actual

    first = {'t': {'A': [line(1, 0)], 'B': [line(2, -2)]}}
    second = {'t': {'A': [line(2, -2)], 'B': [line(1, 0)]}}
    cancellation = check_mixture(first, second)
    assert cancellation['left_weakly_preferred_mass'] == [.5, .5]
    assert cancellation['right_weakly_preferred_mass'] == [.5, .5]
    observations.append(dict(case='shared_lambda_cancellation', result=cancellation,
                             reason='Per-scenario independent extrema would incorrectly discard the common q=.5 equality.'))
    for _ in range(160):
        scenarios = [{str(t): {cid: random_lines() for cid in ('A', 'B')}
                      for t in range(rng.randint(1, 4))} for _ in range(1)]
        first = scenarios[0]
        second = {t: {cid: random_lines() for cid in ('A', 'B')} for t in first}
        check_mixture(first, second)
        check_mixture(first, second, lam=.37)
        curves = {t: {cid: production.envelope(lines) for cid, lines in cards.items()}
                  for t, cards in first.items()}
        actual = production.paired_range(curves, 'A', 'B')
        ds = [reference_difference(cards['A'], cards['B']) for cards in first.values()]
        close(actual['minimum'], min(d[0] for d in ds))
        close(actual['maximum'], max(d[1] for d in ds))
        checks['paired_range_cases'] += 1

    # Preserve this known boundary bug as evidence without failing all other review.
    degenerate = production.affine_nonnegative_interval([(-.5000000000001, 1), (.5, -1)])
    boundary_ok = degenerate is None or degenerate[0] <= degenerate[1]
    findings = [] if boundary_ok else [dict(severity='small numerical boundary bug',
        function='affine_nonnegative_interval',
        input=[[-.5000000000001, 1], [.5, -1]], output=degenerate,
        mathematical_interval=None, problem='Tolerance permits an inverted interval.',
        recommendation='Return None for strictly inconsistent bounds, or explicitly merge near ties into one valid point.')]
    return dict(scope='New finite synthetic menu mathematics only; no historical card experiment or model calibration rerun.',
                independent_oracle='Fraction all-pair original line intersections and direct max evaluation; no production hull/difference oracle.',
                seed=202610190217, checks=checks, mathematical_checks_passed=True,
                observations=observations, findings=findings,
                limitation='Integer synthetic menus plus selected cancellation/tie boundaries; not proof of all floating-point inputs or real-game validity.')


if __name__ == '__main__':
    result = review()
    target = HERE / 'review-frontier-independent.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(checks=result['checks'], findings=result['findings']), ensure_ascii=False))
