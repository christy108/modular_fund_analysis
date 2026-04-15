from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd




#Helper Functions
def top_x_by_industry(
    signal_row: pd.Series,
    industry_row: pd.Series,
    n_by_industry: dict | None = None,
    *,
    keep_industries: list[str] | None = None,
    ascending: bool = False,
) -> pd.Series:
    """
    Select top X tickers per industry for a single date.

    Parameters
    ----------
    signal_row : pd.Series
        Index = gvkey_iid, values = signal at one date (e.g., global_signal_2.iloc[i, :]).
    industry_row : pd.Series
        Index = gvkey_iid, values = Industry for the same date (aligned to signal_row.index).
    n_by_industry : dict
        Mapping Industry -> number of stocks to select.
    keep_industries : list[str]
        If provided, only these industries are processed (others ignored).
    ascending : bool
        False = pick largest signal (top). True = pick smallest (bottom).

    Returns
    -------
    pd.Series
        Index = industries, values = pd.Index of selected gvkey_iid for that industry.
        (Same “shape” idea as your quantile output: a container of constituents.)
    """
    if n_by_industry is None:
        raise ValueError("n_by_industry must be provided (e.g., from SectorPortfolio.n_by_industry).")

    # Align & drop rows missing either signal or industry
    df = pd.DataFrame({"signal": signal_row, "Industry": industry_row}).dropna(subset=["signal", "Industry"])

    if keep_industries is not None:
        df = df[df["Industry"].isin(keep_industries)]

    out = pd.Series(dtype=object)

    # Process each industry separately
    for ind, g in df.groupby("Industry"):
        n = int(n_by_industry.get(ind, 0))
        if n <= 0:
            out.loc[ind] = pd.Index([], dtype=object)
            continue

        chosen = g.sort_values("signal", ascending=ascending).head(n).index
        out.loc[ind] = pd.Index(chosen)

    return out


@dataclass
class SectorPortfolio:
    """
    Build an industry-split (sector) portfolio from a signal and compute next-period returns.

    This class mirrors the logic in `indices.ipynb`:
    - For each date i, pick top-X stocks per Industry using the signal at i
    - Compute next-period return at i+1 for each Industry as the mean return of its selected stocks
    - Compute an equal-weight portfolio return as the mean across industry return columns
    """

    signal: pd.DataFrame
    returns: pd.DataFrame
    global_universe: pd.DataFrame
    sector_split: int
    manual_input_split: bool = False
    n_by_industry: dict[str, int] | None = None
    first_conditioning_set: int = 0
    ascending: bool = False
    keep_industries: list[str] | None = None

    def __post_init__(self) -> None:
        required_cols = {"date", "gvkey_iid", "Industry"}
        missing = required_cols - set(self.global_universe.columns)
        if missing:
            raise ValueError(f"global_universe missing required columns: {sorted(missing)}")

        self.signal = self.signal.copy()
        self.returns = self.returns.copy()

        # Build industry pivot and align to signal/returns shape.
        gu = self.global_universe.copy()
        gu["date"] = pd.to_datetime(gu["date"])
        industry_pivot = gu.pivot(index="date", columns="gvkey_iid", values="Industry")

        self.signal.index = pd.to_datetime(self.signal.index)
        self.returns.index = pd.to_datetime(self.returns.index)

        # Align indices (dates) and columns (tickers) across all inputs.
        common_index = self.returns.index.intersection(self.signal.index)
        if common_index.empty:
            raise ValueError("signal and returns have no overlapping dates in their indices.")

        common_cols = self.returns.columns.intersection(self.signal.columns)
        if common_cols.empty:
            raise ValueError("signal and returns have no overlapping tickers in their columns.")

        self.signal = self.signal.loc[common_index, common_cols]
        self.returns = self.returns.loc[common_index, common_cols]
        self._industry = industry_pivot.reindex(index=common_index, columns=common_cols)

        if self.manual_input_split:
            if self.n_by_industry is None:
                raise ValueError("When manual_input_split=True, you must pass n_by_industry.")
            self.n_by_industry = {str(k): int(v) for k, v in self.n_by_industry.items()}
        else:
            inds = (
                pd.Series(gu["Industry"])
                .dropna()
                .astype(str)
                .drop_duplicates()
                .sort_values()
                .tolist()
            )
            self.n_by_industry = {ind: int(self.sector_split) for ind in inds}

        self.constituents_over_time: list[pd.Series] = []
        self.portfolio_constituents_over_time: list[pd.Index] = []
        self._industry_returns: pd.DataFrame | None = None


        if self.manual_input_split:
            print("WARINING: Averege number of stocks per industry is not equal, thus average return will be wrong using equal industry average")

    @property
    def industries(self) -> list[str]:
        return list(self.n_by_industry.keys()) if self.n_by_industry is not None else []





    def compute_industry_returns(self) -> pd.DataFrame:
        """
        Return a DataFrame (index=dates, columns=industries) of next-period industry returns.

        Row i+1 contains the return computed from selections formed at row i (next-month convention).
        """
        industries = self.industries
        ind_ret = pd.DataFrame(index=self.returns.index, columns=industries, dtype=float)

        # Match notebook behavior: only populate from first_conditioning_set+1 onward with 0.0 baseline.
        start = int(self.first_conditioning_set) + 1
        if start < len(ind_ret.index):
            ind_ret.iloc[start:, :] = 0.0

        self.constituents_over_time = []
        self.portfolio_constituents_over_time = []

        for i in range(int(self.first_conditioning_set), self.returns.shape[0] - 1):
            date = self.returns.index[i]
            current_signal = self.signal.iloc[i, :]
            current_industry = self._industry.iloc[i, :]
            next_ret = self.returns.iloc[i + 1, :]

            selected = top_x_by_industry(
                signal_row=current_signal,
                industry_row=current_industry,
                n_by_industry=self.n_by_industry,
                keep_industries=self.keep_industries,
                ascending=self.ascending,
            )
            selected.name = date
            self.constituents_over_time.append(selected)

            # Combined portfolio constituents (union across industries) for this formation date.
            seen: set[Any] = set()
            ordered: list[Any] = []
            for v in selected.values:
                idx = pd.Index(v)
                for g in idx:
                    if g not in seen:
                        seen.add(g)
                        ordered.append(g)
            self.portfolio_constituents_over_time.append(pd.Index(ordered))

            for ind in selected.index:
                tickers = pd.Index(selected[ind])
                if tickers.empty:
                    val = np.nan
                else:
                    s = next_ret.reindex(tickers).dropna()
                    val = float(s.mean()) if len(s) else np.nan

                # Use += to mirror notebook logic (accumulate).
                # If baseline is NaN (earlier rows), this stays NaN.
                col_loc = ind_ret.columns.get_loc(ind)
                ind_ret.iloc[i + 1, col_loc] += val

        self._industry_returns = ind_ret
        return ind_ret






    def get_constituents_over_time(self, *, portfolio: bool = False) -> list[pd.Series] | list[pd.Index]:
        """
        Return constituents over time.\n\n        - portfolio=False (default): list of pd.Series (index=Industry, values=pd.Index of tickers)\n        - portfolio=True: list of pd.Index (union of tickers across industries each date)\n\n        Computes constituents if not already computed.\n        """
        if not self.constituents_over_time or (portfolio and not self.portfolio_constituents_over_time):
            self.compute_industry_returns()
        return self.portfolio_constituents_over_time if portfolio else self.constituents_over_time

    def industry_return(self, industry: str) -> pd.Series:
        """Return the computed return series for a single industry."""
        if self._industry_returns is None:
            self.compute_industry_returns()
        assert self._industry_returns is not None
        return self._industry_returns[str(industry)]

    def equal_weight_mean_return(self) -> pd.Series:
        """
        Equal-weight (non-weighted) mean return across industries each date.

        This matches: `industry_returns.mean(axis=1)`.
        """
        if self._industry_returns is None:
            self.compute_industry_returns()
        assert self._industry_returns is not None
        return self._industry_returns.mean(axis=1)

