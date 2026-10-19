"""Finite menu price envelopes and partial identification; no game simulation."""
from __future__ import annotations

import math

TOL = 1e-9


def number(value, name, low=None, high=None):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(name + ' must be a finite number')
    if low is not None and value < low or high is not None and value > high:
        raise ValueError(name + ' is outside its declared range')
    return value


def envelope(lines):
    """Upper envelope of intercept+slope*lambda over the FULL [0,1].

    Floating point arithmetic, not an exact-rational or server certificate.
    Menu costs are physical payments; a common lambda*cash is cancelled.
    """
    if not lines:
        raise ValueError('A nonempty physical menu is required')
    by_slope = {}
    for line in lines:
        m = number(line['slope'], 'slope')
        b = number(line['intercept'], 'intercept')
        if m not in by_slope or b > by_slope[m]['intercept']:
            by_slope[m] = dict(line)
    hull = []
    starts = []
    for m, line in sorted(by_slope.items()):
        x = -math.inf
        while hull:
            x = (hull[-1]['intercept'] - line['intercept']) / (m - hull[-1]['slope'])
            if x > starts[-1]:
                break
            hull.pop(); starts.pop()
        if not hull:
            x = -math.inf
        hull.append(line); starts.append(x)
    pieces = []
    for i, line in enumerate(hull):
        low = max(0., starts[i])
        high = min(1., starts[i + 1] if i + 1 < len(starts) else math.inf)
        if high > low:
            pieces.append(dict(line, low=low, high=high))
    return pieces


def piece_at(curve, lam):
    number(lam, 'cash residual coefficient', 0, 1)
    for p in curve:
        if p['low'] <= lam <= p['high']:
            return p
    raise ValueError('Curve does not cover the requested price')


def value(curve, lam):
    p = piece_at(curve, lam)
    return p['intercept'] + p['slope'] * lam


def knots(*curves):
    return sorted({0., 1.} | {p[k] for c in curves for p in c for k in ('low', 'high')})


def difference(left, right):
    """All extrema/crossings of two piecewise linear curves, paired in lambda."""
    xs = knots(left, right)
    points = [(x, value(left, x) - value(right, x)) for x in xs]
    roots = []
    for (a, da), (b, db) in zip(points, points[1:]):
        if da * db < 0:
            roots.append(a - da * (b - a) / (db - da))
    roots.extend(x for x, d in points if abs(d) <= TOL)
    low = min(points, key=lambda x: x[1]); high = max(points, key=lambda x: x[1])
    return dict(minimum=low[1], maximum=high[1], minimum_at=low[0], maximum_at=high[0],
                zero_points=sorted(set(roots)))


def weighted_curve(curves, weights):
    if len(curves) != len(weights) or not curves:
        raise ValueError('Every declared world needs a curve and weight')
    for w in weights:
        number(w, 'design weight', 0)
    if not math.isclose(sum(weights), 1., abs_tol=1e-10):
        raise ValueError('Design weights must sum to one')
    out = []
    xs = knots(*curves)
    for lo, hi in zip(xs, xs[1:]):
        selected = [piece_at(c, (lo + hi) / 2) for c in curves]
        out.append(dict(low=lo, high=hi,
                        intercept=sum(w * p['intercept'] for w, p in zip(weights, selected)),
                        slope=sum(w * p['slope'] for w, p in zip(weights, selected))))
    return out


def classification(low, high):
    if low >= -TOL and high <= TOL:
        return 'equal_in_current_projection'
    if low > TOL:
        return 'left_strictly_preferred_on_declared_support'
    if high < -TOL:
        return 'right_strictly_preferred_on_declared_support'
    if low >= -TOL:
        return 'left_weakly_preferred_on_declared_support'
    if high <= TOL:
        return 'right_weakly_preferred_on_declared_support'
    return 'conditional_ordering'


def paired_range(setting_curves, left, right, lam=None):
    if lam is not None:
        number(lam, 'cash residual coefficient', 0, 1)
    witnesses = []
    for setting, curves in setting_curves.items():
        a, b = curves[str(left)], curves[str(right)]
        if lam is None:
            d = difference(a, b)
        else:
            x = value(a, lam) - value(b, lam)
            d = dict(minimum=x, maximum=x, minimum_at=lam, maximum_at=lam)
        witnesses.append(dict(setting=setting, **d))
    lo = min(witnesses, key=lambda d: d['minimum'])
    hi = max(witnesses, key=lambda d: d['maximum'])
    return dict(minimum=lo['minimum'], maximum=hi['maximum'],
                minimum_witness=dict(setting=lo['setting'], cash_price=lo['minimum_at']),
                maximum_witness=dict(setting=hi['setting'], cash_price=hi['maximum_at']),
                status=classification(lo['minimum'], hi['maximum']))


def affine_nonnegative_interval(lines):
    """Intersection of a+b*q >= 0 for q in [0,1], without assigning q."""
    low, high = 0., 1.
    for a, b in lines:
        if abs(b) < 1e-14:
            if a < -TOL:
                return None
            continue
        crossing = -a / b
        if b > 0:
            low = max(low, crossing)
        else:
            high = min(high, crossing)
    if low > high or high < 0 or low > 1:
        return None
    return [max(0., low), min(1., high)]


def mixture(first, second, left, right, lam=None):
    """Fixed candidate before board reveal; theta/lambda shared across boards.

    q is the mass of the SECOND board, not an estimated arrival probability.
    Each observed board admits its own legitimate current menu.
    """
    if set(first) != set(second):
        raise ValueError('Both scenarios must share identical price settings')
    constraints = []
    for setting in first:
        a, b = first[setting], second[setting]
        curves = [a[str(left)], a[str(right)], b[str(left)], b[str(right)]]
        for x in [lam] if lam is not None else knots(*curves):
            d0 = value(curves[0], x) - value(curves[1], x)
            d1 = value(curves[2], x) - value(curves[3], x)
            constraints.append((d0, d1 - d0))
    return dict(second_board_mass_is_unknown=True,
                left_weakly_preferred_mass=affine_nonnegative_interval(constraints),
                right_weakly_preferred_mass=affine_nonnegative_interval([(-a, -b) for a, b in constraints]),
                meaning='All selected shared price settings and cash prices; not a meta estimate or a waiting-time model')


def single_use_opportunity_bounds(reward, marginals, reference_value):
    """Sharp union bounds, assuming free waiting and one identical payoff.

    The chance process is NOT inferred from card pools. With unknown temporal
    dependence, one-period opportunity frequencies do not identify carry value.
    """
    number(reward, 'conditional reward', 0)
    number(reference_value, 'reference payoff')
    if not marginals:
        raise ValueError('At least one observation window is required')
    for p in marginals:
        number(p, 'opportunity marginal', 0, 1)
    low, high = max(marginals), min(1., sum(marginals))
    return dict(opportunity_union_bounds=[low, high],
                relative_value_bounds=[reward * low - reference_value,
                                       reward * high - reference_value],
                temporal_dependence_identified=False,
                scope='One use, constant reward, free waiting, no intertemporal budget competition; supplied marginals only')
