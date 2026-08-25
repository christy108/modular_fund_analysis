from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from functions.functions import univariate_portfolio_sorting


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
    # "half_open" (frozen behaviour) or "closed"; see univariate_portfolio_sorting. Last
    # field so positional construction of the existing ones is unaffected.
    quantile_interval_bounds: str = "half_open"

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

        self.constituents_over_time: list[pd.Series] = []
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
                else:
                    s = next_ret.reindex(tickers).dropna()
                    val = float(s.mean()) if len(s) else np.nan

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

