"""Paired seed intervals; unresolved outcomes are bounded, never imputed."""
import numpy as np


def interval(low, high=None, alpha=.05):
    a = np.asarray(low, float); b = a if high is None else np.asarray(high, float)
    if not len(a) or a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all() or np.any(a > b):
        raise ValueError('Nonempty finite ordered completion bounds required')
    rng = np.random.default_rng(773)
    indices = rng.integers(0, len(a), (5000, len(a)))
    lower = np.mean(a[indices], axis=1); upper = np.mean(b[indices], axis=1)
    return dict(mean=float(a.mean()) if np.array_equal(a, b) else None,
        completion_range=[float(a.mean()), float(b.mean())], low=float(np.quantile(lower, alpha / 2)),
        high=float(np.quantile(upper, 1 - alpha / 2)), alpha=alpha, independent_seed_clusters=len(a),
        unresolved_seed_clusters=int(np.sum(a != b)))
