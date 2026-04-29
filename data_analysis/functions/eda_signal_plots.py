from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


@dataclass(frozen=True)
class SignalColumns:
    """Resolved signal column names present on the input DataFrame."""

    signal_0: str
    signal_1: str
    signal_2: str

    @property
    def as_list(self) -> list[str]:
        return [self.signal_0, self.signal_1, self.signal_2]


def ensure_signal_columns(
    lc: pd.DataFrame,
    *,
    prefer: Sequence[str] = ("signal_0", "signal_1", "signal_2"),
    fallback_sum_with_prefix: str = "sum_with_",
    denom_col: str = "sum_activities",
) -> tuple[pd.DataFrame, SignalColumns]:
    """
    Ensure the LC dataframe has three signal columns.

    - If `prefer` columns exist, use them.
    - Else, compute them from `sum_with_0/1/2` divided by `denom_col`.
    """
    lc2 = lc.copy()

    if all(c in lc2.columns for c in prefer):
        return lc2, SignalColumns(prefer[0], prefer[1], prefer[2])

    sum_cols = [f"{fallback_sum_with_prefix}{i}" for i in (0, 1, 2)]
    missing = [c for c in sum_cols + [denom_col] if c not in lc2.columns]
    if missing:
        raise ValueError(
            "Cannot resolve signal columns. Missing required columns: "
            + ", ".join(missing)
        )

    # Avoid division warnings; undefined when denom is 0.
    denom = pd.to_numeric(lc2[denom_col], errors="coerce").replace(0, np.nan)
    for i, out_col in enumerate(prefer):
        num = pd.to_numeric(lc2[sum_cols[i]], errors="coerce")
        lc2[out_col] = num / denom

    return lc2, SignalColumns(prefer[0], prefer[1], prefer[2])


def plot_mean_signals_by_rfyear(
    lc: pd.DataFrame,
    *,
    rfyear_col: str = "rfyear",
    signal_cols: Sequence[str] = ("signal_0", "signal_1", "signal_2"),
    signal_labels: Sequence[str] = ("signal_0", "signal_1", "signal_2"),
    colours: Sequence[str] | None = None,
    line_styles: Sequence[str] | None = None,
    markers: Sequence[str] | None = None,
    marker: str = "x",
    figsize: tuple[int, int] = (11, 4),
    title: str | None = None,
) -> pd.DataFrame:
    """Plot mean of each signal over time by fiscal year; returns the grouped means."""
    if len(signal_cols) != 3 or len(signal_labels) != 3:
        raise ValueError("signal_cols and signal_labels must have length 3.")
    cols = [rfyear_col, *signal_cols]
    tmp = lc.loc[:, cols].dropna(subset=[rfyear_col]).copy()
    means = tmp.groupby(rfyear_col)[list(signal_cols)].mean(numeric_only=True).sort_index()

    fig, ax = plt.subplots(figsize=figsize)
    for idx, (col, label) in enumerate(zip(signal_cols, signal_labels, strict=False)):
        c = colours[idx % len(colours)] if colours else None
        ls = line_styles[idx % len(line_styles)] if line_styles else "-"
        mk = markers[idx % len(markers)] if markers else marker
        ax.plot(
            means.index,
            means[col].values,
            linewidth=2.0,
            color=c,
            linestyle=ls,
            marker=mk,
            label=str(label),
        )
    ax.set_xlabel(f"Reporting fiscal year ({rfyear_col})")
    ax.set_ylabel("Mean signal value")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="upper left", frameon=False, ncol=3)
    ax.set_title(title or "Mean signals over time (by rfyear)")
    plt.tight_layout()
    plt.show()
    return means


def plot_mean_signals_by_rfyear_industry(
    lc: pd.DataFrame,
    *,
    rfyear_col: str = "rfyear",
    industry_col: str = "Industry",
    signal_cols: Sequence[str] = ("signal_0", "signal_1", "signal_2"),
    signal_labels: Sequence[str] = ("signal_0", "signal_1", "signal_2"),
    plot_top_n: int | None = 10,
    marker: str = "x",
    colours: Sequence[str] | None = None,
    line_styles: Sequence[str] | None = None,
    markers: Sequence[str] | None = None,
    figsize: tuple[int, int] = (11, 10),
    other_label: str = "Other",
    dropna_industry: bool = True,
) -> dict[str, pd.DataFrame]:
    """
    For each signal, plot mean signal by (rfyear × Industry) over time.

    Returns a dict {signal_name: pivot_df_used_for_plot}.
    """
    if len(signal_cols) != 3 or len(signal_labels) != 3:
        raise ValueError("signal_cols and signal_labels must have length 3.")

    required = {rfyear_col, industry_col, *signal_cols}
    missing = [c for c in required if c not in lc.columns]
    if missing:
        raise ValueError(f"lc is missing required columns: {missing}")

    tmp = lc[[rfyear_col, industry_col, *signal_cols]].dropna(subset=[rfyear_col]).copy()
    if dropna_industry:
        tmp = tmp.dropna(subset=[industry_col]).copy()
    else:
        tmp[industry_col] = tmp[industry_col].fillna("Unknown")
    tmp[industry_col] = tmp[industry_col].astype(str).str.strip()

    out: dict[str, pd.DataFrame] = {}
    fig, axes = plt.subplots(nrows=3, ncols=1, figsize=figsize, sharex=True)
    if not isinstance(axes, np.ndarray):
        axes = np.array([axes])

    for ax, sig, label in zip(axes, signal_cols, signal_labels, strict=False):
        means = (
            tmp.groupby([rfyear_col, industry_col])[sig]
            .mean(numeric_only=True)
            .reset_index(name="mean_signal")
        )
        pivot = (
            means.pivot(index=rfyear_col, columns=industry_col, values="mean_signal")
            .sort_index()
        )

        if plot_top_n is not None and pivot.shape[1] > plot_top_n:
            industry_sums = pivot.mean(axis=0, skipna=True).sort_values(ascending=False)
            top = industry_sums.head(plot_top_n).index
            other = industry_sums.index.difference(top)
            pivot_plot = pivot[top].copy()
            if len(other) > 0:
                pivot_plot[other_label] = pivot[other].mean(axis=1, skipna=True)
        else:
            pivot_plot = pivot

        for idx, col in enumerate(pivot_plot.columns):
            c = colours[idx % len(colours)] if colours else None
            ls = line_styles[idx % len(line_styles)] if line_styles else "-"
            mk = markers[idx % len(markers)] if markers else marker
            ax.plot(
                pivot_plot.index,
                pivot_plot[col].values,
                linewidth=2,
                color=c,
                linestyle=ls,
                marker=mk,
                label=str(col),
            )

        ax.set_title(f"Mean {label} by Industry over time")
        ax.set_ylabel("Mean signal")
        ax.grid(True, axis="y", alpha=0.3)
        out[str(sig)] = pivot_plot

    axes[-1].set_xlabel(f"Reporting fiscal year ({rfyear_col})")
    # single legend outside (uses last axes handles)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper left",
        bbox_to_anchor=(1.02, 1),
        frameon=False,
        title=industry_col,
    )
    plt.tight_layout()
    plt.show()

    return out

