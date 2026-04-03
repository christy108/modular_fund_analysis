from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _compound_returns(slice_df: pd.DataFrame) -> pd.Series:
    """Cumulative return per column: prod(1 + r) - 1, skipping NaNs per column."""
    out = pd.Series(index=slice_df.columns, dtype=float)
    for col in slice_df.columns:
        r = slice_df[col].dropna()
        if r.empty:
            out[col] = np.nan
        else:
            out[col] = float((r + 1).prod() - 1)
    return out


def _format_pct(decimal: float) -> str:
    if decimal is None or (isinstance(decimal, float) and np.isnan(decimal)):
        return ""
    return f"{100.0 * decimal:.2f}%"


class StrategyPerformance:
    """Cumulative performance table from a simple-return panel (strategies as columns)."""

    HORIZON_COLUMNS = ["1m", "3m", "YTD", "1yr", "3yr", "5yr", "10yr", "Since launch"]

    def __init__(self, portfolio_returns: pd.DataFrame):
        df = portfolio_returns.copy()
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        df.sort_index(inplace=True)

        self.portfolio_returns = df

    def cumulative_performance_table(
        self,
        csv_path: str | Path,
        as_of: pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        """
        Build strategies × horizons table, save formatted CSV, return formatted DataFrame.
        """
        df = self.portfolio_returns
        if df.empty:
            raise ValueError("portfolio_returns is empty")

        end = as_of if as_of is not None else df.index.max()
        df_asof = df.loc[df.index <= end]
        if df_asof.empty:
            raise ValueError("No rows on or before as_of")

        numeric = pd.DataFrame(
            index=df.columns,
            columns=self.HORIZON_COLUMNS,
            dtype=float,
        )

        n = len(df_asof)
        last_k = lambda k: df_asof.iloc[-min(k, n) :]

        numeric["1m"] = _compound_returns(last_k(1))
        numeric["3m"] = _compound_returns(last_k(3))
        ytd = df_asof[df_asof.index.year == end.year]
        numeric["YTD"] = _compound_returns(ytd)
        numeric["1yr"] = _compound_returns(last_k(12))
        numeric["3yr"] = _compound_returns(last_k(36))
        numeric["5yr"] = _compound_returns(last_k(60))
        numeric["10yr"] = _compound_returns(last_k(120))
        numeric["Since launch"] = _compound_returns(df_asof)

        formatted = numeric.map(_format_pct)
        path = Path(csv_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        formatted.to_csv(path)
        return formatted

    def rolling_sharpe(self, window: int) -> pd.DataFrame:
        """
        Annualized rolling Sharpe of excess returns (monthly): (mean / std) * sqrt(12).
        """
        if window < 2:
            raise ValueError("window must be at least 2 for rolling Sharpe")
        df = self.portfolio_returns
        roll = df.rolling(window=window, min_periods=window)
        mean = roll.mean()
        std = roll.std(ddof=1)
        out = (mean / std) * np.sqrt(12)
        return out.replace([np.inf, -np.inf], np.nan)

    def plot_rolling_sharpe(
        self,
        window: int,
        ax: Any = None,
        figsize: tuple[float, float] = (10, 4),
        **plot_kwargs: Any,
    ) -> Any:
        """
        Plot rolling annualized Sharpe for every column (one line per strategy).
        """
        sharpe = self.rolling_sharpe(window)
        if ax is None:
            _, ax = plt.subplots(figsize=figsize)
        for col in sharpe.columns:
            ax.plot(sharpe.index, sharpe[col], label=col, **plot_kwargs)
        ax.axhline(0.0, color="gray", linewidth=0.8, linestyle="--")
        ax.set_title(f"Rolling Sharpe ({window} months), annualized (sqrt(12))")
        ax.set_ylabel("Sharpe")
        ax.legend(loc="best")
        ax.grid(True, alpha=0.3)
        return ax
