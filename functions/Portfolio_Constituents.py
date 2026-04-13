from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Hashable, Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _sanitize_filename(base: str) -> str:
    base = str(base).strip() if base is not None else "plot"
    base = re.sub(r'[\\/:*?"<>|]+', "_", base)
    base = re.sub(r"\s+", " ", base).strip().rstrip(".")
    return base if base else "plot"


def _formation_date(month_series: pd.Series, i: int, formation_dates: pd.DatetimeIndex | list | None) -> pd.Timestamp:
    name = month_series.name
    ts = pd.to_datetime(name, errors="coerce")
    if pd.isna(ts) and formation_dates is not None:
        ts = pd.to_datetime(formation_dates[i])
    if pd.isna(ts):
        raise ValueError(
            "Could not infer formation date from constituents Series `.name`. "
            "Pass `formation_dates` to PortfolioConstituents.__init__ (same length as constituents)."
        )
    return pd.Timestamp(ts)


class PortfolioConstituents:
    """
    Analyse univariate quantile portfolio constituents against `global_universe`
    (e.g. Industry, loc, MacroRegion via gvkey_iid and date).
    """

    def __init__(
        self,
        constituents: list[pd.Series],
        global_universe: pd.DataFrame,
        portfolio_type: str = "univariate_split",
        formation_dates: pd.DatetimeIndex | list[pd.Timestamp | str] | None = None,
    ):
        self.constituents = list(constituents)
        self.portfolio_type = portfolio_type
        self.formation_dates = formation_dates

        gu = global_universe.copy()
        if "date" not in gu.columns or "gvkey_iid" not in gu.columns:
            raise ValueError("global_universe must contain 'date' and 'gvkey_iid' columns.")
        gu["date"] = pd.to_datetime(gu["date"])
        self._universe = gu.sort_values(["gvkey_iid", "date"]).reset_index(drop=True)

    def _ensure_column(self, col: str) -> None:
        if col not in self._universe.columns:
            raise ValueError(
                f"Column {col!r} not found in global_universe. "
                f"Available: {list(self._universe.columns)}"
            )

    def _collect_gvkeys(
        self,
        month_series: pd.Series,
        *,
        portfolio_key: Hashable | int | None,
        analyse_all_portfolios_at_once: bool,
    ) -> pd.Index:
        """Return gvkey_iid index for one month according to sub-portfolio selection."""
        if analyse_all_portfolios_at_once:
            seen: set[str] = set()
            ordered: list[str] = []
            for v in month_series.values:
                idx = pd.Index(v).astype(str)
                for g in idx:
                    if g not in seen:
                        seen.add(g)
                        ordered.append(g)
            return pd.Index(ordered)

        keys = month_series.index
        if portfolio_key is None:
            sub = month_series.iloc[-1]
        elif isinstance(portfolio_key, int):
            sub = month_series.iloc[portfolio_key]
        else:
            sub = month_series.loc[portfolio_key]
        return pd.Index(sub).astype(str)

    def _resolve_gvkeys(
        self,
        gvkeys: Iterable[str],
        as_of: pd.Timestamp,
        col: str,
    ) -> pd.Series:
        """
        Point-in-time category per gvkey_iid: last row with date <= as_of in global_universe.
        Index order follows gvkeys; missing -> NaN.
        """
        self._ensure_column(col)
        gvkeys = list(gvkeys)
        if not gvkeys:
            return pd.Series(dtype=object)

        as_of = pd.to_datetime(as_of)
        u = self._universe[
            (self._universe["gvkey_iid"].isin(gvkeys)) & (self._universe["date"] <= as_of)
        ]
        if u.empty:
            return pd.Series(index=gvkeys, dtype=object)

        last_per = u.groupby("gvkey_iid", sort=False).last(numeric_only=False)
        s = last_per[col]
        return s.reindex(gvkeys)

    def _counts_by_category_over_time(
        self,
        col: str,
        *,
        portfolio_key: Hashable | int | None,
        analyse_all_portfolios_at_once: bool,
    ) -> tuple[pd.DatetimeIndex, pd.DataFrame]:
        """Build DataFrame of category counts x date (columns = categories)."""
        rows: list[dict[str, Any]] = []
        index_dates: list[pd.Timestamp] = []

        for i, month_series in enumerate(self.constituents):
            as_of = _formation_date(month_series, i, self.formation_dates)
            gvkeys = self._collect_gvkeys(
                month_series,
                portfolio_key=portfolio_key,
                analyse_all_portfolios_at_once=analyse_all_portfolios_at_once,
            )
            cats = self._resolve_gvkeys(gvkeys, as_of, col)
            vc = cats.value_counts(dropna=False)
            d = {str(k): int(v) for k, v in vc.items()}
            rows.append(d)
            index_dates.append(as_of)

        wide = pd.DataFrame(rows, index=pd.DatetimeIndex(index_dates, name="date"))
        wide = wide.sort_index()
        wide = wide.fillna(0).astype(int)
        return wide.index, wide

    def plot_category_over_time(
        self,
        col: str,
        portfolio_key: Hashable | int | None = None,
        analyse_all_portfolios_at_once: bool = False,
        all_sub_portfolios: bool = False,
        figsize: tuple[float, float] = (12, 6),
        title: str | None = None,
        save: bool = False,
        img_dir: str = "img",
        dpi: int = 300,
        filename: str | None = None,
        show: bool = True,
    ) -> Any:
        """
        Line chart: number of stocks per category value over time.

        Default: last quantile sub-portfolio each month. If ``analyse_all_portfolios_at_once``,
        union all sub-portfolios per month. If ``all_sub_portfolios``, one subplot per sub-portfolio.
        """
        if analyse_all_portfolios_at_once and all_sub_portfolios:
            raise ValueError("Choose at most one of analyse_all_portfolios_at_once and all_sub_portfolios.")

        self._ensure_column(col)

        if all_sub_portfolios:
            first = next((s for s in self.constituents if len(s)), None)
            if first is None:
                raise ValueError("constituents is empty or has no sub-portfolios.")
            sub_keys = list(first.index)
            n = len(sub_keys)
            ncols = min(3, n)
            nrows = int(np.ceil(n / ncols))
            fig, axes = plt.subplots(nrows, ncols, figsize=(figsize[0], figsize[1] * nrows / 2))
            axes_flat = np.atleast_1d(axes).ravel()
            for ax in axes_flat[n:]:
                ax.set_visible(False)
            for j, key in enumerate(sub_keys):
                ax = axes_flat[j]
                _, wide = self._counts_by_category_over_time(
                    col,
                    portfolio_key=key,
                    analyse_all_portfolios_at_once=False,
                )
                for cname in wide.columns:
                    ax.plot(wide.index, wide[cname], label=str(cname), marker="o", markersize=2)
                ax.set_title(f"{self.portfolio_type} — {key}")
                ax.set_ylabel("Count")
                ax.grid(True, alpha=0.3)
                ax.legend(loc="best", fontsize=7)
            fig.suptitle(
                title or f"Stocks by {col} over time (all sub-portfolios)",
                fontsize=12,
            )
            fig.autofmt_xdate()
            plt.tight_layout()
        else:
            _, wide = self._counts_by_category_over_time(
                col,
                portfolio_key=portfolio_key,
                analyse_all_portfolios_at_once=analyse_all_portfolios_at_once,
            )
            fig, ax = plt.subplots(figsize=figsize)
            for cname in wide.columns:
                ax.plot(wide.index, wide[cname], label=str(cname), marker="o", markersize=3)
            mode = "all sub-portfolios combined" if analyse_all_portfolios_at_once else (
                f"sub-portfolio {portfolio_key}" if portfolio_key is not None else "last sub-portfolio"
            )
            ax.set_title(title or f"{self.portfolio_type}: {col} ({mode})")
            ax.set_ylabel("Number of stocks")
            ax.legend(loc="best", fontsize=8)
            ax.grid(True, alpha=0.3)
            fig.autofmt_xdate()
            plt.tight_layout()

        if save:
            os.makedirs(img_dir, exist_ok=True)
            base = filename or (title or f"category_over_time_{col}_{self.portfolio_type}")
            out_path = Path(img_dir) / f"{_sanitize_filename(base)}.png"
            fig.savefig(out_path, dpi=dpi, bbox_inches="tight")

        if show:
            plt.show()
        else:
            plt.close(fig)

        return fig

    def total_stocks_over_time(
        self,
        *,
        unique: bool = False,
        plot: bool = True,
        figsize: tuple[float, float] = (12, 4),
        title: str | None = None,
        save: bool = False,
        img_dir: str = "img",
        dpi: int = 300,
        filename: str | None = None,
        show: bool = True,
    ) -> pd.Series | Any:
        """
        Total number of stocks across **all** sub-portfolios each month.

        - If ``unique=False`` (default): sum of portfolio sizes (matches typical quantile split logic).
        - If ``unique=True``: de-duplicated count across sub-portfolios (union per month).

        Returns the Series if ``plot=False``, otherwise returns the created figure.
        """
        if not self.constituents:
            raise ValueError("constituents is empty.")

        totals: list[int] = []
        dates: list[pd.Timestamp] = []

        for i, month_series in enumerate(self.constituents):
            as_of = _formation_date(month_series, i, self.formation_dates)
            dates.append(as_of)

            if unique:
                gvkeys = self._collect_gvkeys(
                    month_series,
                    portfolio_key=None,
                    analyse_all_portfolios_at_once=True,
                )
                totals.append(int(len(gvkeys)))
            else:
                # month_series values are per-sub-portfolio holdings (list/array-like)
                totals.append(int(month_series.apply(len).sum()))

        s = pd.Series(totals, index=pd.DatetimeIndex(dates, name="date"), name="total_stocks").sort_index()

        if not plot:
            return s

        fig, ax = plt.subplots(figsize=figsize)
        ax.plot(s.index, s.values, marker="o", markersize=3)
        ax.set_title(title or "Total stocks across all portfolios over time")
        ax.set_ylabel("Number of stocks")
        ax.grid(True, alpha=0.3)
        fig.autofmt_xdate()
        plt.tight_layout()

        if save:
            os.makedirs(img_dir, exist_ok=True)
            base = filename or (title or f"total_stocks_over_time_{self.portfolio_type}")
            out_path = Path(img_dir) / f"{_sanitize_filename(base)}.png"
            fig.savefig(out_path, dpi=dpi, bbox_inches="tight")

        # if show:
        #     plt.show()
        # else:
        #     plt.close(fig)

        return fig

    def run_all_plots(
        self,
        *,
        category_over_time_cols: list[str] | None = None,
        pie_cols: list[str] | None = None,
        analyse_all_portfolios_at_once: bool = False,
        all_sub_portfolios: bool = False,
        portfolio_key: Hashable | int | None = None,
        out_dir: str | None = None,
        save: bool = True,
        show: bool = True,
        dpi: int = 300,
    ) -> dict[str, Any]:
        """
        Convenience method to run the common set of constituent plots so notebooks stay small.

        - Over-time plots for `category_over_time_cols`
        - Final-month pie/donut plots for `pie_cols`

        Returns a dict with created figures.
        """
        category_over_time_cols = category_over_time_cols or ["Industry", "loc"]
        pie_cols = pie_cols or ["Industry", "loc", "MacroRegion"]
        out_dir = out_dir or str(Path("output") / f"portfolio_constituents_{self.portfolio_type}")

        figs: dict[str, Any] = {"category_over_time": {}, "pie": {}}

        over_time_suffix = (
            "all" if analyse_all_portfolios_at_once else ("all_subs" if all_sub_portfolios else "last")
        )
        pie_suffix = "all" if analyse_all_portfolios_at_once else "last"

        for col in category_over_time_cols:
            fig = self.plot_category_over_time(
                col,
                portfolio_key=portfolio_key,
                analyse_all_portfolios_at_once=analyse_all_portfolios_at_once,
                all_sub_portfolios=all_sub_portfolios,
                save=save,
                img_dir=out_dir,
                dpi=dpi,
                filename=f"{self.portfolio_type}_counts_over_time_{col}_{over_time_suffix}",
                show=show,
            )
            figs["category_over_time"][col] = fig

        for col in pie_cols:
            fig = self.plot_pie_categories(
                col,
                portfolio_key=portfolio_key,
                analyse_all_portfolios_at_once=analyse_all_portfolios_at_once,
                save=save,
                img_dir=out_dir,
                dpi=dpi,
                filename=f"{self.portfolio_type}_final_month_pie_{col}_{pie_suffix}",
                show=show,
            )
            figs["pie"][col] = fig

        return figs




        

    def plot_pie_categories(
        self,
        col: str,
        portfolio_key: Hashable | int | None = None,
        analyse_all_portfolios_at_once: bool = False,
        dropna: bool = False,
        value_mode: str = "percent",
        donut: bool = True,
        radius: float = 1.0,
        hole_radius: float = 0.6,
        outline_color: str = "black",
        outline_width: float = 1.0,
        label_fontsize: int = 11,
        title_fontsize: int = 14,
        show_total_in_center: bool = True,
        total_fontsize: int = 12,
        total_number_fontsize: int | None = None,
        total_label_fontsize: int | None = None,
        total_center_offset_frac: float = 0.08,
        total_label: str = "Companies",
        figsize: tuple[float, float] = (8, 8),
        startangle: float = 220,
        title: str | None = None,
        save: bool = False,
        img_dir: str = "img",
        dpi: int = 300,
        filename: str | None = None,
        show: bool = True,
    ) -> Any:
        """
        Pie or donut chart of category mix for constituents in the **final** month of the series.
        """
        self._ensure_column(col)
        if not self.constituents:
            raise ValueError("constituents is empty.")

        last_i = len(self.constituents) - 1
        month_series = self.constituents[-1]
        as_of = _formation_date(month_series, last_i, self.formation_dates)

        gvkeys = self._collect_gvkeys(
            month_series,
            portfolio_key=portfolio_key,
            analyse_all_portfolios_at_once=analyse_all_portfolios_at_once,
        )
        cats = self._resolve_gvkeys(gvkeys, as_of, col)
        if dropna:
            cats = cats.dropna()

        vc = cats.astype(str).value_counts(dropna=False)
        categories = vc.index.astype(str).tolist()
        counts = vc.values.astype(int)
        total = int(counts.sum())

        if total == 0:
            raise ValueError("No constituents to plot after filtering.")

        # Roll up tiny slices into "Other" to reduce clutter.
        # Rule: if there are >= 3 categories with < 1% share, group them.
        shares_pct = (counts / total) * 100.0
        small_mask = shares_pct < 1.0
        if not dropna:
            # Keep missing as its own slice even if tiny.
            small_mask = small_mask & (np.array(categories) != "nan")

        if int(np.sum(small_mask)) >= 2:
            other_count = int(np.sum(counts[small_mask]))
            kept_categories = [c for c, keep in zip(categories, ~small_mask) if keep]
            kept_counts = counts[~small_mask]
            categories = kept_categories + ["Other"]
            counts = np.append(kept_counts, other_count).astype(int)
            total = int(counts.sum())

        if value_mode == "percent":
            values = counts / total * 100
            value_label = "%"
            metric_formatter = lambda v: round(float(v), 1)
            default_title = f"{col} final month"
        elif value_mode == "count":
            values = counts
            value_label = "count"
            metric_formatter = lambda v: int(v)
            default_title = f"{col} final month"
        else:
            raise ValueError('value_mode must be "percent" or "count"')

        slice_labels = [
            f"{cat}\n{metric_formatter(v)} {value_label}"
            for cat, v in zip(categories, values)
        ]

        fig, ax = plt.subplots(figsize=figsize)
        ax.set_aspect("equal")

        ax.pie(
            values,
            labels=slice_labels,
            startangle=startangle,
            radius=radius,
            wedgeprops={"linewidth": outline_width, "edgecolor": outline_color},
            textprops={"fontsize": label_fontsize},
        )

        if donut:
            centre_circle = plt.Circle(
                (0, 0),
                hole_radius,
                fc="white",
                ec=outline_color,
                lw=outline_width,
            )
            ax.add_artist(centre_circle)

            if show_total_in_center:
                total_number_fs = total_fontsize if total_number_fontsize is None else total_number_fontsize
                total_label_fs = total_fontsize if total_label_fontsize is None else total_label_fontsize
                dy = hole_radius * total_center_offset_frac
                ax.text(0, dy, f"{total}", ha="center", va="center", fontsize=total_number_fs)
                ax.text(0, -dy, f"{total_label}", ha="center", va="center", fontsize=total_label_fs)

        resolved_title = title if title is not None else default_title
        ax.set_title(resolved_title, fontsize=title_fontsize)
        plt.tight_layout()

        if save:
            os.makedirs(img_dir, exist_ok=True)
            base = filename if filename is not None else resolved_title
            out_path = Path(img_dir) / f"{_sanitize_filename(base)}.png"
            fig.savefig(out_path, dpi=dpi, bbox_inches="tight")

        if show:
            plt.show()
        else:
            plt.close(fig)

        return fig
