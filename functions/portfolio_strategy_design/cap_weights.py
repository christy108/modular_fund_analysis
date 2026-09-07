from __future__ import annotations

import numpy as np
import pandas as pd

# Relative slack on the breach test. Redistribution sets the pinned names to EXACTLY `cap`,
# so on the next pass they sit on the ceiling to within float noise. Without the slack a
# rounding error of 1e-17 reads as a breach, the name is re-pinned, the free budget shrinks
# by another full `cap`, and the loop chases its own arithmetic. The `& ~pinned` guard
# already excludes pinned names, so this only matters for a FREE name that lands exactly on
# the ceiling -- which the redistribution formula can produce (see the n == 1/cap case).
_BREACH_TOL = 1e-12

# Tolerance on the closing sum-to-one assertion. Accumulated float error in a sum of n
# terms grows like n * eps, so ~500 holdings gives ~1e-13; 1e-10 leaves headroom without
# being loose enough to hide a real bug (a genuine weighting error is O(cap), not O(1e-10)).
_SUM_TOL = 1e-10


class InfeasibleCapError(ValueError):
    """No weight vector satisfies both ``sum(w) == 1`` and ``w <= cap``.

    Raised when ``n * cap <= 1`` -- ten holdings or fewer at a 10% cap. A bucket that
    small is not a portfolio: its return is idiosyncratic noise whichever way it is
    weighted, so the caller DISCARDS the bucket-month (its return becomes NaN) rather than
    weighting it somehow. Its own exception type so a caller has to opt into swallowing it,
    and so it can never be confused with the input-validation ValueErrors below.
    """


def capped_weights(caps: pd.Series, cap: float) -> pd.Series:
    """Market-cap weights for one portfolio, with an iteratively enforced single-name cap.

    ``caps`` are the market caps of the holdings at the FORMATION date (positive, no NaN);
    ``cap`` is the maximum weight any one name may carry, e.g. 0.10. Returns weights summing
    to 1.0, indexed like ``caps``.

    The rule, which is the MSCI/S&P capping algorithm:

    1. Weight by market cap.
    2. Any name over ``cap`` is pinned at exactly ``cap`` -- that is ``cap`` of the WHOLE
       portfolio, not of whatever is left.
    3. The remaining budget, ``1 - cap * n_pinned``, is split among the still-free names
       PRO-RATA by their own market caps.
    4. Repeat: a name can be comfortably under the ceiling in step 1 and breach it only
       after step 3 pushes a pinned name's excess onto it. A single pass therefore does NOT
       satisfy the constraint -- this is the whole reason the loop exists.

    ``cap=1.0`` needs no special case: nothing can ever breach a ceiling of 1, so the loop
    returns plain market-cap weights on its first pass.

    Infeasibility. A sum of n numbers each at most ``cap`` is at most ``n * cap``, so once
    ``n * cap <= 1`` NO vector satisfies both ``sum(w) == 1`` and ``w <= cap`` -- with a 10%
    cap that is any portfolio of 10 names or fewer. This raises ``InfeasibleCapError`` there
    rather than picking some weighting anyway: a bucket that small is not a portfolio, its
    return is idiosyncratic noise however it is weighted, and it is discarded from the
    analysis entirely. The test is ``n * cap <= 1`` rather than a hardcoded 10 so it tracks
    ``max_portfolio_weight_if_portfolio_weighting_equal`` when that is swept -- at a 5% cap the boundary is 20 names.

    Note this applies ONLY to cap weighting. Equal weighting has no such constraint to
    violate, so a small equal-weighted bucket is not gated here.
    """
    if not isinstance(caps, pd.Series):
        raise TypeError(f"capped_weights expects a pd.Series of market caps, got {type(caps).__name__}")

    n = int(len(caps))
    if n == 0:
        raise ValueError("capped_weights got an empty cap vector; the caller must handle empty buckets")
    if not np.isfinite(cap) or not (0.0 < cap <= 1.0):
        raise ValueError(f"cap must be a finite number in (0, 1], got {cap!r}")

    v = caps.astype(float)
    if v.isna().any():
        _bad = list(v.index[v.isna()])
        raise ValueError(
            f"capped_weights got {len(_bad)} holding(s) with a NaN market cap "
            f"(first few: {_bad[:5]}). Treating NaN as zero would silently drop the holding "
            f"from the portfolio, so this raises instead -- fix the panel upstream."
        )
    if (v <= 0).any():
        _bad = list(v.index[v <= 0])
        raise ValueError(
            f"capped_weights got {len(_bad)} holding(s) with a non-positive market cap "
            f"(first few: {_bad[:5]}); a market cap must be strictly positive."
        )

    if n * cap <= 1.0:
        raise InfeasibleCapError(
            f"no capped weight vector exists for n={n} holdings at cap={cap}: "
            f"n * cap = {n * cap:.4f} <= 1, so the weights cannot both sum to 1 and stay "
            f"under the ceiling. This bucket-month is discarded."
        )

    w = v / v.sum()
    pinned = pd.Series(False, index=caps.index)

    # Each pass either pins at least one new name or returns, and there are n names, so
    # n + 1 passes is a real bound rather than a guess at a safe number.
    for _ in range(n + 1):
        breach = (w > cap * (1.0 + _BREACH_TOL)) & ~pinned
        if not bool(breach.any()):
            _sum = float(w.sum())
            if abs(_sum - 1.0) > _SUM_TOL:
                raise RuntimeError(f"capped_weights produced weights summing to {_sum!r}, not 1.0")
            return w

        pinned |= breach
        free = ~pinned
        if not bool(free.any()):
            # Unreachable: every name pinned means sum == n * cap > 1 by the feasibility
            # guard above, and the redistribution can only pin a name whose weight EXCEEDS
            # cap, which cannot be true of all of them at once. Asserted rather than left to
            # divide by an empty sum.
            raise RuntimeError(
                f"capped_weights pinned all {n} holdings at cap={cap}, which the feasibility "
                f"guard should have made impossible"
            )

        w.loc[pinned] = cap
        # The pro-rata redistribution. The denominator is the FREE names' total cap, not the
        # portfolio's -- that is what makes each free name's share proportional among the
        # remainder. Recomputed from `v` rather than rescaling the previous `w`: the two are
        # mathematically identical (redistribution scales every free weight by one common
        # factor, so their ratios are already the cap ratios) but going back to `v` avoids
        # compounding float drift across passes.
        w.loc[free] = (1.0 - cap * int(pinned.sum())) * v[free] / v[free].sum()

    raise RuntimeError(
        f"capped_weights did not converge in {n + 1} passes for n={n}, cap={cap}; "
        f"the pinned set should grow monotonically, so this indicates a bug"
    )


def concentration_stats(w: pd.Series, cap: float) -> dict:
    """Per-bucket-month concentration diagnostics for one weight vector.

    Scalars only -- these go in a parquet with one row per (signal, bucket, formation date),
    so the frame stays small enough to export while still answering the question the cap
    exists to answer: how concentrated is the leg really. ``effective_n`` (1/HHI) is the one
    to read: a 12-name bucket under a 10% cap can legally hold 80% in eight names, so a raw
    holding count says very little.

    ``n_pinned`` counts names sitting at or above the ceiling. ``discarded`` is always False
    here -- a discarded bucket-month has no weight vector to describe, so the caller emits
    its row directly (see ``discarded_row``).
    """
    n = int(len(w))
    hhi = float((w ** 2).sum())
    return {
        "n_holdings": n,
        "max_weight": float(w.max()),
        "median_weight": float(w.median()),
        "min_weight": float(w.min()),
        "hhi": hhi,
        "effective_n": float(1.0 / hhi) if hhi > 0 else np.nan,
        "n_pinned": int((w >= cap * (1.0 - _BREACH_TOL)).sum()),
        "top5_share": float(w.nlargest(min(5, n)).sum()),
        "weight_sum": float(w.sum()),
        "discarded": False,
    }


def discarded_row(n_holdings: int) -> dict:
    """Diagnostics row for a bucket-month dropped as infeasible under the cap.

    Same columns as ``concentration_stats`` so the two stack into one frame, with the
    weight statistics NaN because no weight vector exists. Emitted rather than skipped so
    the audit shows WHICH months were dropped and how big they were -- a silently missing
    row would look like the month was never formed.
    """
    return {
        "n_holdings": int(n_holdings),
        "max_weight": np.nan,
        "median_weight": np.nan,
        "min_weight": np.nan,
        "hhi": np.nan,
        "effective_n": np.nan,
        "n_pinned": 0,
        "top5_share": np.nan,
        "weight_sum": np.nan,
        "discarded": True,
    }
