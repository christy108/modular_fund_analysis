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


def _format_num(x: float, dp: int = 2) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    return f"{float(x):.{dp}f}"


class StrategyPerformance:
    """Cumulative performance table from a simple-return panel (strategies as columns)."""

    HORIZON_COLUMNS = ["1m", "3m", "YTD", "1yr", "3yr", "5yr", "10yr", "Since launch"]

    def __init__(self, portfolio_returns: pd.DataFrame, ff3_parts_df: pd.DataFrame | None = None):
        df = portfolio_returns.copy()
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        df.sort_index(inplace=True)

        self.portfolio_returns = df
        self.ff3_parts_df = ff3_parts_df.copy() if isinstance(ff3_parts_df, pd.DataFrame) else None

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

    def gross_cumulative_returns(
        self,
        portfolio_returns: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """
        Gross cumulative wealth index per column: ``(1 + r).cumprod()``.

        Same series as used by ``plot_cumulative_returns``.
        """
        df = self.portfolio_returns if portfolio_returns is None else portfolio_returns.copy()
        if df.empty:
            raise ValueError("portfolio_returns is empty")
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        return (1.0 + df.sort_index()).cumprod()

    def save_gross_cumulative_returns_csv(
        self,
        csv_path: str | Path,
        portfolio_returns: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """Save gross cumulative returns (plot input) to CSV."""
        cumulative = self.gross_cumulative_returns(portfolio_returns)
        path = Path(csv_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        cumulative.to_csv(path)
        return cumulative

    def performance_risk_metrics_table(
        self,
        csv_path: str | Path,
        as_of: pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        """
        Build strategies × risk-metrics table, save formatted CSV, return formatted DataFrame.

        Metrics:
        - Sharpe (annualized, monthly): (mean / std) * sqrt(12)
        - VaR 1% (monthly): pct_change().quantile(0.01)
        - Max Drawdown: min(wealth / cummax(wealth) - 1), where wealth = cumprod(1 + r)
        """
        df = self.portfolio_returns
        if df.empty:
            raise ValueError("portfolio_returns is empty")

        end = as_of if as_of is not None else df.index.max()
        df_asof = df.loc[df.index <= end]
        if df_asof.empty:
            raise ValueError("No rows on or before as_of")

        metrics = pd.DataFrame(
            index=df.columns,
            columns=["Sharpe", "VaR 1%", "Max Drawdown"],
            dtype=float,
        )

        for col in df.columns:
            r = df_asof[col].dropna()
            if r.empty:
                continue

            std = float(r.std(ddof=1))
            mean = float(r.mean())
            metrics.loc[col, "Sharpe"] = (
                (mean / std) * float(np.sqrt(12)) if std != 0.0 else np.nan
            )

            r_chg = r.dropna()
            metrics.loc[col, "VaR 1%"] = (
                float(r_chg.quantile(0.01)) if not r_chg.empty else np.nan
            )

            wealth = (1.0 + r).cumprod()
            drawdown = wealth / wealth.cummax() - 1.0
            metrics.loc[col, "Max Drawdown"] = float(drawdown.min())

        # Optional: add FF3 alpha + p-value(alpha) for matching strategy columns
        if self.ff3_parts_df is not None:
            ff3 = self.ff3_parts_df
            if "alpha" in ff3.index and "p-value(alpha)" in ff3.index:
                common = metrics.index.intersection(ff3.columns)
                if len(common) > 0:
                    metrics["Alpha"] = np.nan
                    metrics["p-value(alpha)"] = np.nan
                    metrics.loc[common, "Alpha"] = ff3.loc["alpha", common].astype(float)
                    metrics.loc[common, "p-value(alpha)"] = ff3.loc["p-value(alpha)", common].astype(float)

        formatted = pd.DataFrame(index=metrics.index)
        formatted["Sharpe"] = metrics["Sharpe"].map(lambda x: _format_num(x, dp=2))
        formatted["VaR 1%"] = metrics["VaR 1%"].map(_format_pct)
        formatted["Max Drawdown"] = metrics["Max Drawdown"].map(_format_pct)
        if "Alpha" in metrics.columns:
            formatted["Alpha"] = metrics["Alpha"].map(lambda x: _format_num(x, dp=2))
        if "p-value(alpha)" in metrics.columns:
            formatted["p-value(alpha)"] = metrics["p-value(alpha)"].map(lambda x: _format_num(x, dp=3))

        path = Path(csv_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        formatted.to_csv(path)
        return formatted

    def plot_rolling_sharpe(
        self,
        window: int,
        ax: Any = None,
        figsize: tuple[float, float] = (10, 4),
        line_styles: list[str] | None = None,
        save_path: str | Path | None = None,
        **plot_kwargs: Any,
    ) -> Any:
        """
        Plot rolling annualized Sharpe for every column (one line per strategy).
        If save_path is set, writes the figure (e.g. PDF or PNG) after drawing.
        """
        sharpe = self.rolling_sharpe(window)
        if line_styles is None:
            line_styles = ["--", "-.", "-", ":"]
        if ax is None:
            _, ax = plt.subplots(figsize=figsize)
        fig = ax.figure
        for i, col in enumerate(sharpe.columns):
            ax.plot(
                sharpe.index,
                sharpe[col],
                label=col,
                linestyle=line_styles[i % len(line_styles)],
                **plot_kwargs,
            )
        ax.axhline(0.0, color="gray", linewidth=0.8, linestyle="--")
        ax.set_title(f"Rolling Annualised Sharpe ({window}-month window)")
        ax.set_ylabel("Sharpe")
        ax.legend(loc="best")
        ax.grid(True, alpha=0.3)
        if save_path is not None:
            out = Path(save_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(out, bbox_inches="tight")
        return ax

    def plot_cumulative_returns(
        self,
        portfolio_returns: pd.DataFrame | None = None,
        *,
        colors: list[str] | None = None,
        line_styles: list[str] | None = None,
        linewidth: float = 2.3,
        ylabel: str = "US Dollars",
        xlabel: str = "Date",
        title: str | None = None,
        legend_title: str = "Legend",
        legend_bbox_to_anchor: tuple[float, float] = (1.05, 1.0),
        legend_loc: str = "upper left",
        tight_layout_rect: tuple[float, float, float, float] = (0, 0, 1.6, 0.9),
        ax: Any = None,
        figsize: tuple[float, float] = (10, 4),
        save_path: str | Path | None = None,
        csv_path: str | Path | None = None,
        show: bool = True,
    ) -> Any:
        """
        Compute and plot cumulative returns per column using the notebook styling.

        Expects `portfolio_returns` to be simple returns (e.g., monthly excess returns).
        Cumulative wealth is computed as `(1 + r).cumprod()` per column.
        """
        cumulative = self.gross_cumulative_returns(portfolio_returns)
        if csv_path is not None:
            path = Path(csv_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            cumulative.to_csv(path)

        # Match `indices.ipynb` defaults if not provided.
        if colors is None:
            colors = ["black", "#d62728", "#87CEEB", "#9467bd", "#ADD8E6","#FFA500","#008000"]
        if line_styles is None:
            line_styles = ["--", "-.", "-", ":"]

        if ax is None:
            _, ax = plt.subplots(figsize=figsize)
        fig = ax.figure

        for i, col in enumerate(cumulative.columns):
            ax.plot(
                cumulative.index,
                cumulative[col],
                label=str(col),
                color=colors[i % len(colors)],
                linewidth=linewidth,
                linestyle=line_styles[i % len(line_styles)],
            )

        if title is not None:
            ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.grid(True)

        # Match `indices.ipynb` styling/approach (legend outside + extra right margin).
        plt.legend(title=legend_title, bbox_to_anchor=legend_bbox_to_anchor, loc=legend_loc)
        plt.tight_layout(rect=list(tight_layout_rect))

        if save_path is not None:
            out = Path(save_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(out, bbox_inches="tight")

        if show:
            plt.show()
        else:
            plt.close(fig)

        return ax


# Default palette used by plot_cumulative_returns (kept in sync so the long plot is unchanged).
_CUMULATIVE_PALETTE = ["black", "#d62728", "#87CEEB", "#9467bd", "#ADD8E6", "#FFA500", "#008000"]


def aligned_cumulative_colors(long_columns, spread_columns, palette=None):
    """Colour each high-low spread to match its ``High <signal>`` leg in the long plot.

    The long plot keeps the default per-column palette (its appearance is unchanged); each
    ``High - Low <signal>`` / ``Low - High <signal>`` spread is then coloured the same as the
    long plot's ``High <signal>`` line. Returns ``(long_colors, spread_colors)`` aligned to the
    given column orders, so the same signal has the same colour across both plots.
    """
    palette = palette or _CUMULATIVE_PALETTE
    long_columns = list(long_columns)
    spread_columns = list(spread_columns)
    long_color = {c: palette[i % len(palette)] for i, c in enumerate(long_columns)}

    def _high_leg(spread):
        name = spread
        for p in ("High - Low ", "Low - High "):
            name = name.replace(p, "")
        return "High " + name

    spread_colors = [
        long_color.get(_high_leg(c), palette[i % len(palette)])
        for i, c in enumerate(spread_columns)
    ]
    return list(long_color.values()), spread_colors


def consistent_cumulative_colors(high_columns, low_columns, spread_columns, palette=None):
    """One colour per SIGNAL across the three cumulative plots (High / Low / High-Low).

    The High plot gets the default positional palette; every other column is coloured by
    stripping its leg prefix ("Low ", "High - Low ", "Low - High ") and reusing the same
    signal's High-leg colour. Benchmarks (Market/Sample) keep their High-plot colour too.
    Returns (high_colors, low_colors, spread_colors) aligned to the given column orders.
    """
    palette = palette or _CUMULATIVE_PALETTE
    high_columns = [str(c) for c in high_columns]
    high_colors = [palette[i % len(palette)] for i in range(len(high_columns))]

    by_signal = {}
    for c, col in zip(high_columns, high_colors):
        key = c[len("High "):] if c.startswith("High ") else c   # signal name, or benchmark label
        by_signal[key] = col

    def _colour(c, i):
        s = str(c)
        for p in ("High - Low ", "Low - High ", "Low ", "High "):   # longest prefixes first
            if s.startswith(p):
                return by_signal.get(s[len(p):], palette[i % len(palette)])
        return by_signal.get(s, palette[i % len(palette)])          # benchmarks pass through

    low_colors = [_colour(c, i) for i, c in enumerate(low_columns)]
    spread_colors = [_colour(c, i) for i, c in enumerate(spread_columns)]
    return high_colors, low_colors, spread_colors
