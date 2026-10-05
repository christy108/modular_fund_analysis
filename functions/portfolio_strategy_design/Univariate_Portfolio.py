from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from functions.functions import univariate_portfolio_sorting
from functions.portfolio_strategy_design.cap_weights import (
    InfeasibleCapError,
    capped_weights,
    concentration_stats,
    discarded_row,
)


@dataclass
class UnivariateQuantilePortfolio:
    """
    Univariate quantile portfolio construction (one signal at a time).

    Mirrors the `indices.ipynb` pattern:
    - Form portfolios at time i from the cross-section of `signal.iloc[i, :]`
    - Realize returns at time i+1 from `returns.iloc[i+1, :]`
    - Store constituents each formation date
    """

    signal: pd.DataFrame
    returns: pd.DataFrame
    n_quantiles: int
    first_conditioning_set: int = 0
    take_extremes: bool = False
    n_extremes_quantiles: int | None = None
    # "half_open" (frozen behaviour) or "closed"; see univariate_portfolio_sorting.
    quantile_interval_bounds: str = "half_open"
    # Market-cap weighting. `weights` is a date x gvkey_iid frame of market caps, read at the
    # FORMATION row; `weight_cap` is the single-name ceiling (e.g. 0.10). Both None keeps the
    # frozen equal-weight behaviour, and that is the default so an existing caller is
    # unaffected. Declared last so positional construction of the earlier fields still works
    # -- the same reason quantile_interval_bounds sits where it does.
    weights: pd.DataFrame | None = None
    weight_cap: float | None = None

    def __post_init__(self) -> None:
        self.signal = self.signal.copy()
        self.returns = self.returns.copy()

        if not isinstance(self.signal.index, pd.DatetimeIndex):
            self.signal.index = pd.to_datetime(self.signal.index)
        if not isinstance(self.returns.index, pd.DatetimeIndex):
            self.returns.index = pd.to_datetime(self.returns.index)

        self.signal.sort_index(inplace=True)
        self.returns.sort_index(inplace=True)

        common_index = self.returns.index.intersection(self.signal.index)
        if common_index.empty:
            raise ValueError("signal and returns have no overlapping dates in their indices.")

        common_cols = self.returns.columns.intersection(self.signal.columns)
        if common_cols.empty:
            raise ValueError("signal and returns have no overlapping tickers in their columns.")

        self.signal = self.signal.loc[common_index, common_cols]
        self.returns = self.returns.loc[common_index, common_cols]

        if self.weights is not None:
            if self.weight_cap is None:
                raise ValueError(
                    "weights were given without weight_cap; pass the single-name ceiling "
                    "explicitly (use 1.0 for uncapped value weighting)"
                )
            self.weights = self.weights.copy()
            if not isinstance(self.weights.index, pd.DatetimeIndex):
                self.weights.index = pd.to_datetime(self.weights.index)
            self.weights.sort_index(inplace=True)
            # Reindexed rather than intersected, so `weights` always has EXACTLY the shape of
            # signal/returns and `.iloc[i, :]` lines up row-for-row with `current_signal`. A
            # cell that comes back NaN is only a problem if that name is actually held, and
            # capped_weights raises there with the offending gvkey_iids -- a far better error
            # than failing construction over a name no bucket ever picks up. The count is
            # printed so a systematic gap is still visible.
            self.weights = self.weights.reindex(index=common_index, columns=common_cols)
            _n_missing = int(self.weights.isna().to_numpy().sum())
            if _n_missing:
                _cells = self.weights.shape[0] * self.weights.shape[1]
                print(f"[UnivariateQuantilePortfolio] weights have {_n_missing} NaN cell(s) "
                      f"of {_cells} ({_n_missing / _cells:.4%}); a bucket that holds one will raise")

        self.constituents_over_time: list[pd.Series] = []
        # One row per (formation date, bucket) when weighting is on; empty otherwise.
        self.weight_diagnostics: list[dict] = []
        # Per-NAME weights, first and last bucket only (the High/Low legs -- the same two
        # `low_high` keeps). Only these, because the middle buckets are never presented and
        # storing every name of every bucket would bloat the pickled bundle for nothing.
        self.leg_weights: list[dict] = []
        self._quantile_returns: pd.DataFrame | None = None

    @property
    def quantile_returns(self) -> pd.DataFrame:
        if self._quantile_returns is None:
            self.compute_returns()
        assert self._quantile_returns is not None
        return self._quantile_returns

    def _template_columns(self) -> list[str]:
        """
        Determine output columns based on sorting function behavior.

        - If take_extremes=False: p_1..p_{n_quantiles}
        - If take_extremes=True: sorting returns 3 slices by construction (see `univariate_portfolio_sorting`)
        """
        if not self.take_extremes:
            k = int(self.n_quantiles)
        else:
            # `univariate_portfolio_sorting` currently returns 3 slices in extremes mode
            # (low, middle, high), regardless of n_extremes_quantiles.
            k = 3
        return [f"p_{i}" for i in range(1, k + 1)]

    def compute_returns(self) -> pd.DataFrame:
        """
        Compute next-period mean returns for each portfolio bucket.

        Returns a DataFrame with columns `p_1..p_K`.
        Row i+1 contains returns from portfolios formed at row i (next-period convention).
        """
        if self.signal.empty or self.returns.empty:
            raise ValueError("signal/returns are empty after alignment.")

        cols = self._template_columns()
        out = pd.DataFrame(np.nan, index=self.signal.index, columns=cols, dtype=float)

        start = int(self.first_conditioning_set) + 1
        if start < len(out.index):
            out.iloc[start:, :] = 0.0

        self.constituents_over_time = []
        self.weight_diagnostics = []
        self.leg_weights = []
        # First and last output column = the Low and High legs, matching low_high().
        _leg_cols = {cols[0], cols[-1]}

        n_ext = 1 if self.n_extremes_quantiles is None else int(self.n_extremes_quantiles)

        for i in range(int(self.first_conditioning_set), self.signal.shape[0] - 1):
            formation_date = self.signal.index[i]
            current_signal = self.signal.iloc[i, :]
            next_ret = self.returns.iloc[i + 1, :]

            selected = univariate_portfolio_sorting(
                current_signal,
                self.n_quantiles,
                no_extremes_quantiles_1=n_ext,
                take_extremes=self.take_extremes,
                quantile_interval_bounds=self.quantile_interval_bounds,
            )
            selected.name = formation_date
            self.constituents_over_time.append(selected)

            for j, label in enumerate(selected.index):
                tickers = pd.Index(selected[label])
                if tickers.empty:
                    val = np.nan
                elif self.weights is None:
                    # Equal weight: .mean() over the surviving names IS the weighting, and it
                    # renormalises for free when a name's return is missing. Untouched.
                    s = next_ret.reindex(tickers).dropna()
                    val = float(s.mean()) if len(s) else np.nan
                else:
                    r = next_ret.reindex(tickers)
                    alive = r.notna()
                    if not bool(alive.any()):
                        val = np.nan
                    else:
                        # Caps come from row i -- the FORMATION row, the same row as
                        # `current_signal` -- while the return comes from row i+1. Reading
                        # row i+1's caps would be a look-ahead that mechanically favours
                        # whatever went up. The cap loop is then re-run on the SURVIVORS
                        # rather than the formation weights being rescaled, so the ceiling
                        # holds exactly in the weights that actually earn the return; a
                        # rescale would let a pinned name drift above it whenever a large
                        # peer delists.
                        c = self.weights.iloc[i, :].reindex(tickers)[alive]
                        try:
                            w = capped_weights(c, self.weight_cap)
                        except InfeasibleCapError:
                            # n * cap <= 1: no capped weight vector exists, and a bucket
                            # that small is not a portfolio. DISCARD the bucket-month --
                            # NaN, exactly as an empty bucket produces. Note NaN is not
                            # self-excluding downstream: (1+r).cumprod() SKIPS it, which
                            # books the month as a fabricated 0% return, so the caller must
                            # also hide the leg (see the thin-portfolio gate in
                            # 07_build_analyse_portfolios.py, which counts these alongside
                            # empty months for exactly that reason).
                            val = np.nan
                            _stats = discarded_row(int(alive.sum()))
                        else:
                            val = float((w * r[alive]).sum())
                            _stats = concentration_stats(w, self.weight_cap)
                            if label in _leg_cols:
                                self.leg_weights.extend(
                                    {"date": formation_date, "portfolio": label,
                                     "gvkey_iid": _k, "weight": float(_v)}
                                    for _k, _v in w.items()
                                )
                        self.weight_diagnostics.append({
                            "date": formation_date,
                            "portfolio": label,
                            **_stats,
                        })

                if j < len(out.columns):
                    out.iat[i + 1, j] += val

        self._quantile_returns = out
        return out

    def get_constituents_over_time(self) -> list[pd.Series]:
        if not self.constituents_over_time:
            self.compute_returns()
        return self.constituents_over_time

    def portfolio_return(self, portfolio: str | int) -> pd.Series:
        """
        Convenience getter for a single portfolio return series.

        - If `portfolio` is an int, uses 1-based indexing (1 -> p_1).
        - If `portfolio` is a str, expects column name like 'p_10'.
        """
        df = self.quantile_returns
        if isinstance(portfolio, int):
            col = f"p_{int(portfolio)}"
        else:
            col = str(portfolio)
        if col not in df.columns:
            raise KeyError(f"Portfolio {col!r} not found. Available: {list(df.columns)}")
        return df[col]

