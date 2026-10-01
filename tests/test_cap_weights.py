"""Unit tests for the capped market-cap weighting used by the High/Low legs.

`capped_weights` is pure, so it is the one part of the value-weighting change that can be
tested exhaustively without running the pipeline. The case that matters most is
`test_second_pass_breach`: a single-pass implementation gets it wrong and still looks
plausible.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from functions.portfolio_strategy_design.cap_weights import (
    InfeasibleCapError,
    capped_weights,
    concentration_stats,
    discarded_row,
)

CAP = 0.10


def _caps(values):
    return pd.Series([float(v) for v in values], index=[f"n{i}" for i in range(len(values))])


def _assert_valid(w, cap, *, n):
    assert len(w) == n
    assert abs(float(w.sum()) - 1.0) < 1e-10, f"weights sum to {w.sum()}"
    assert (w > 0).all()
    assert float(w.max()) <= cap * (1 + 1e-12), f"max weight {w.max()} breaches cap {cap}"


# --- the infeasible region: n * cap <= 1 --> DISCARD --------------------------------- #

def test_infeasible_raises_rather_than_weighting_anyway():
    # 3 names under a 10% cap: no vector sums to 1 with everything <= 0.10, so the
    # bucket-month is discarded by the caller instead of being weighted some other way.
    with pytest.raises(InfeasibleCapError, match="no capped weight vector exists"):
        capped_weights(_caps([50, 30, 20]), CAP)


def test_boundary_n_times_cap_equals_one_also_raises():
    """n == 1/cap is discarded too, and deliberately so.

    At exactly n * cap == 1 there IS a unique feasible vector -- every name at the cap --
    but it is equal weight, carrying no market-cap information at all. A bucket where the
    ceiling forces perfect equal weighting is not delivering cap weighting, so the rule is
    `n * cap <= 1`, inclusive.
    """
    with pytest.raises(InfeasibleCapError):
        capped_weights(_caps([1000] + [10] * 9), CAP)     # n=10, cap=0.10 -> n*cap = 1.0


def test_smallest_feasible_bucket_is_one_above_the_boundary():
    # n=11 at a 10% cap: n * cap = 1.1 > 1, so it is feasible.
    w = capped_weights(_caps([1000] + [10] * 10), CAP)
    _assert_valid(w, CAP, n=11)


def test_discard_threshold_tracks_the_cap_not_a_hardcoded_ten():
    # 15 names at a 5% cap: n * cap = 0.75 <= 1, so discarded despite n > 10.
    with pytest.raises(InfeasibleCapError):
        capped_weights(_caps(range(1, 16)), 0.05)
    # 21 names at a 5% cap: n * cap = 1.05 > 1, so genuinely cap-weighted.
    w = capped_weights(_caps([100] + [1] * 20), 0.05)
    _assert_valid(w, 0.05, n=21)
    assert not np.allclose(w.values, w.values[0])


# --- the feasible region ------------------------------------------------------------- #

def test_no_breach_returns_plain_value_weights():
    w = capped_weights(_caps([100] * 20), CAP)
    assert np.allclose(w.values, 0.05)
    _assert_valid(w, CAP, n=20)


def test_single_dominant_name_is_pinned_and_rest_are_pro_rata():
    # One name at 90% of total cap, 19 equal small ones.
    caps = _caps([900] + [100 / 19] * 19)
    w = capped_weights(caps, CAP)
    _assert_valid(w, CAP, n=20)
    assert abs(float(w.iloc[0]) - CAP) < 1e-12
    # The 19 free names share 0.90 equally, since their caps are equal.
    assert np.allclose(w.iloc[1:].values, 0.90 / 19)


def test_second_pass_breach():
    """A name under the ceiling initially, pushed over it by the redistribution.

    caps: A=700, B=60, ten at 24 (total 1000), cap=10%.
      pass 1: A=0.70 breaches -> pinned. Budget 0.90 over free caps summing to 300,
              so B = 0.90 * 60/300 = 0.18 -- B now breaches, having started at 0.06.
      pass 2: B pinned. Budget 0.80 over 240, so the smalls get 0.80 * 24/240 = 0.08.
    A single-pass implementation stops after pass 1 and leaves B at 18%.
    """
    caps = _caps([700, 60] + [24] * 10)
    w = capped_weights(caps, CAP)
    _assert_valid(w, CAP, n=12)
    assert abs(float(w.iloc[0]) - CAP) < 1e-12, "A must be pinned"
    assert abs(float(w.iloc[1]) - CAP) < 1e-12, "B must be pinned on the SECOND pass"
    assert np.allclose(w.iloc[2:].values, 0.08)


def test_pro_rata_preserves_size_ordering_below_the_cap():
    """The property that separates pro-rata from equal-weighting the residual.

    Below the ceiling a bigger firm still gets a bigger weight, in exact proportion to its
    cap. Constructed so only the first name pins, leaving every other name free and
    distinctly sized -- under the equal-weight residual rule the free weights would all
    collapse to one value instead.
    """
    caps = _caps([3000, 100, 90, 80, 70, 60] + [50] * 20)
    w = capped_weights(caps, CAP)
    _assert_valid(w, CAP, n=26)
    assert abs(float(w.iloc[0]) - CAP) < 1e-12
    free_w, free_caps = w.iloc[1:].values, caps.iloc[1:].values
    ratios = free_w / free_caps
    assert np.allclose(ratios, ratios[0]), "free weights must be a common multiple of their caps"
    assert abs(ratios[0] - 0.90 / 1400) < 1e-12   # budget 0.90 over free caps summing to 1400
    assert w.iloc[1] > w.iloc[2] > w.iloc[3] > w.iloc[4] > w.iloc[5] > w.iloc[6]


def test_cascade_pins_four_names_over_four_passes():
    """Repeated redistribution, each pass dragging one more name over the ceiling.

    caps: 5000, 400, 300, 200, 100, twenty at 50 (total 7000), cap=10%.
      pass 1: 5000 pins.        budget 0.90 / free 2000 -> 400 at .180, 300 at .135 breach
      pass 2: 400, 300 pin.     budget 0.70 / free 1300 -> 200 at .1077 breaches
      pass 3: 200 pins.         budget 0.60 / free 1100 -> 100 at .0545, 50s at .02727
      pass 4: nothing breaches.
    """
    caps = _caps([5000, 400, 300, 200, 100] + [50] * 20)
    w = capped_weights(caps, CAP)
    _assert_valid(w, CAP, n=25)
    assert (np.abs(w.iloc[:4].values - CAP) < 1e-12).all(), "the top four must all pin"
    assert abs(float(w.iloc[4]) - 0.60 * 100 / 1100) < 1e-12
    assert np.allclose(w.iloc[5:].values, 0.60 * 50 / 1100)


def test_cap_of_one_is_plain_value_weighting():
    caps = _caps([900, 50, 30, 20] + [1] * 20)
    w = capped_weights(caps, 1.0)
    assert np.allclose(w.values, caps.values / caps.sum())
    assert abs(float(w.sum()) - 1.0) < 1e-10


def test_many_dominant_names_all_pinned():
    # Five names each at 20% of total, plus a long tail: all five pin, tail shares 0.50.
    caps = _caps([200] * 5 + [10] * 50)
    w = capped_weights(caps, CAP)
    _assert_valid(w, CAP, n=55)
    assert (np.abs(w.iloc[:5].values - CAP) < 1e-12).all()
    assert np.allclose(w.iloc[5:].values, 0.50 / 50)


def test_index_is_preserved():
    caps = pd.Series([900.0, 50.0, 30.0, 20.0] + [1.0] * 20,
                     index=[f"gv{i}_01" for i in range(24)])
    w = capped_weights(caps, CAP)
    assert list(w.index) == list(caps.index)


# --- input validation ---------------------------------------------------------------- #

@pytest.mark.parametrize("bad_cap", [0.0, -0.1, 1.5, np.nan, np.inf])
def test_bad_cap_raises(bad_cap):
    with pytest.raises(ValueError, match="cap must be"):
        capped_weights(_caps([100] * 20), bad_cap)


def test_empty_raises():
    with pytest.raises(ValueError, match="empty cap vector"):
        capped_weights(pd.Series([], dtype=float), CAP)


def test_nan_cap_value_raises_rather_than_zero_weighting():
    caps = _caps([100] * 20)
    caps.iloc[3] = np.nan
    with pytest.raises(ValueError, match="NaN market cap"):
        capped_weights(caps, CAP)


@pytest.mark.parametrize("bad", [0.0, -5.0])
def test_non_positive_cap_value_raises(bad):
    caps = _caps([100] * 20)
    caps.iloc[7] = bad
    with pytest.raises(ValueError, match="non-positive market cap"):
        capped_weights(caps, CAP)


def test_non_series_raises():
    with pytest.raises(TypeError):
        capped_weights([100.0] * 20, CAP)


# --- diagnostics --------------------------------------------------------------------- #

def test_concentration_stats_on_a_capped_vector():
    caps = _caps([700, 60] + [24] * 10)
    w = capped_weights(caps, CAP)
    s = concentration_stats(w, CAP)
    assert s["n_holdings"] == 12
    assert s["n_pinned"] == 2
    assert abs(s["weight_sum"] - 1.0) < 1e-10
    assert abs(s["max_weight"] - CAP) < 1e-12
    assert s["discarded"] is False
    # HHI = 2*0.10^2 + 10*0.08^2 = 0.02 + 0.064 = 0.084 -> effective N ~ 11.9
    assert abs(s["hhi"] - 0.084) < 1e-12
    assert abs(s["effective_n"] - 1 / 0.084) < 1e-9
    assert abs(s["top5_share"] - (0.10 + 0.10 + 0.08 * 3)) < 1e-12


def test_discarded_row_matches_the_stats_columns():
    # The two must stack into one frame, so the column sets have to agree exactly.
    w = capped_weights(_caps([700, 60] + [24] * 10), CAP)
    assert set(discarded_row(4)) == set(concentration_stats(w, CAP))
    d = discarded_row(4)
    assert d["discarded"] is True and d["n_holdings"] == 4
    assert np.isnan(d["weight_sum"]) and np.isnan(d["effective_n"])


def test_effective_n_is_n_for_equal_weights():
    w = capped_weights(_caps([100] * 20), CAP)
    assert abs(concentration_stats(w, CAP)["effective_n"] - 20.0) < 1e-9


# --- integration: the discard actually reaches the return series --------------------- #
# `capped_weights` raising is only half the rule. These check that a discarded bucket-month
# becomes NaN (no return to analyse), that the audit still records WHY, and that equal
# weighting is NOT subject to the gate. None of this fires on the real panel -- its
# thinnest bucket holds 52 names -- so synthetic input is the only way to cover it.

def _panel(n_names, n_quantiles=2):
    dates = pd.to_datetime(["2020-01-31", "2020-02-29", "2020-03-31"])
    names = [f"n{i}" for i in range(n_names)]
    sig = pd.DataFrame([np.arange(1.0, n_names + 1.0)] * 3, index=dates, columns=names)
    ret = pd.DataFrame(0.05, index=dates, columns=names)
    caps = pd.DataFrame(100.0, index=dates, columns=names)
    return dates, sig, ret, caps


def test_infeasible_bucket_month_is_discarded_from_the_return_series():
    from functions.portfolio_strategy_design.Univariate_Portfolio import (
        UnivariateQuantilePortfolio,
    )
    dates, sig, ret, caps = _panel(12)          # K=2 -> 6 per bucket, 6 * 0.10 <= 1
    u = UnivariateQuantilePortfolio(signal=sig, returns=ret, n_quantiles=2,
                                    weights=caps, weight_cap=CAP)
    r = u.compute_returns()
    assert r.loc[dates[1]].isna().all(), "a discarded bucket-month must yield no return"
    d = pd.DataFrame(u.weight_diagnostics)
    assert d["discarded"].all()
    assert (d["n_holdings"] == 6).all(), "the audit must still record the bucket size"


def test_feasible_bucket_one_above_the_boundary_still_returns():
    from functions.portfolio_strategy_design.Univariate_Portfolio import (
        UnivariateQuantilePortfolio,
    )
    dates, sig, ret, caps = _panel(22)          # K=2 -> 11 per bucket, 11 * 0.10 > 1
    r = UnivariateQuantilePortfolio(signal=sig, returns=ret, n_quantiles=2,
                                    weights=caps, weight_cap=CAP).compute_returns()
    assert abs(r.loc[dates[1], "p_1"] - 0.05) < 1e-12


def test_equal_weighting_is_not_subject_to_the_cap_gate():
    from functions.portfolio_strategy_design.Univariate_Portfolio import (
        UnivariateQuantilePortfolio,
    )
    dates, sig, ret, _ = _panel(12)             # the same 6-name buckets as above
    r = UnivariateQuantilePortfolio(signal=sig, returns=ret, n_quantiles=2).compute_returns()
    assert abs(r.loc[dates[1], "p_1"] - 0.05) < 1e-12, "equal weight has no cap to violate"
