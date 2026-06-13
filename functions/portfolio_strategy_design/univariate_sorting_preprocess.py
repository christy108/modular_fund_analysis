from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

import os
import sys
# When running this file directly, add repo root to sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from functions.functions import standardize_pivot




_LC_MERGE_FIXED: tuple[str, ...] = (
    "gvkey",
    "rfyear",
    "MacroRegion",
    "loc",
    "Industry",
    "sum_activities",
)


def _lc_merge_columns(
    category_columns: Sequence[str], lc_signal_columns: Sequence[str]
) -> list[str]:
    return list(_LC_MERGE_FIXED) + list(lc_signal_columns) + sorted(category_columns)


def intersect_gvkeys_and_filter(
    global_universe: pd.DataFrame, lc: pd.DataFrame
) -> pd.DataFrame:
    """Keep WRDS rows whose gvkey appears in both panels."""

    #Fill the gvkey with 0s to make it 6 digits
    lc["gvkey"] = lc["gvkey"].astype(str).str.zfill(6)
    lc_gvkey = lc["gvkey"].unique()
    gu_gvkey = global_universe["gvkey"].unique()
    mapping = np.intersect1d(lc_gvkey, gu_gvkey)
    return global_universe[global_universe["gvkey"].isin(mapping)].copy()


def merge_lc_into_global_universe(
    global_universe: pd.DataFrame,
    lc: pd.DataFrame,
    category_columns: Sequence[str],
    lc_signal_columns: Sequence[str],
) -> pd.DataFrame:
    """Attach LC signals and activity columns at fiscal year (`last_year` ↔ `rfyear`)."""
    cols = _lc_merge_columns(category_columns, lc_signal_columns)
    missing = [c for c in cols if c not in lc.columns]
    if missing:
        raise ValueError(f"lc is missing columns required for merge: {missing}")
    return pd.merge(
        global_universe,
        lc[cols],
        left_on=["gvkey", "last_year"],
        right_on=["gvkey", "rfyear"],
        how="left",
    )


def add_gvkey_iid_sort_clean(global_universe: pd.DataFrame) -> pd.DataFrame:
    """Issue id, sort by issue and date, drop rows without price history."""
    gu = global_universe.copy()
    gu["gvkey_iid"] = gu["gvkey"].astype(str) + "_" + gu["iid"].astype(str)
    gu = gu.sort_values(by=["gvkey_iid", "date"])
    gu = gu.dropna(subset=["date", "tri"])
    return gu


def to_monthly_last_trading_date(global_universe: pd.DataFrame) -> pd.DataFrame:
    """Collapse to last observation date per calendar month per issue, then one row per (issue, month)."""
    gu = global_universe.copy()
    gu["year"] = gu["date"].dt.year
    gu["month"] = gu["date"].dt.month
    last_dates = gu.groupby(["year", "month"])["date"].last().reset_index()
    gu = gu.merge(last_dates, on=["year", "month"], suffixes=("", "_last"))
    gu["date"] = gu["date_last"]
    gu = gu.drop(columns=["date_last"])
    return gu.groupby(["gvkey_iid", "year", "month"]).last().reset_index()


def compute_monthly_returns_long(global_universe: pd.DataFrame) -> pd.DataFrame:
    """Within each `gvkey_iid`, compute `tr` from `tri` with gap masking (vectorized)."""
    gu = global_universe.copy()

    # Preserve row order exactly as input (so downstream merges/indexing match prior runs),
    # while computing pct_change on (gvkey_iid, date)-sorted rows.
    orig_index = gu.index
    gu_sorted = gu.sort_values(["gvkey_iid", "date"])

    date_diff_days = gu_sorted.groupby("gvkey_iid")["date"].diff().dt.days
    tr = gu_sorted.groupby("gvkey_iid")["tri"].pct_change()

    # Match conditional_pct_change: allow up to 31+5 day gaps (weekends/holidays).
    gu_sorted["tr"] = tr.where(date_diff_days <= 36, np.nan)

    return gu_sorted.reindex(orig_index)


def normalize_category_shares(
    global_universe: pd.DataFrame, category_columns: Sequence[str]
) -> pd.DataFrame:
    """Divide activity columns by `sum_activities` (same as notebook)."""
    gu = global_universe.copy()
    cats = sorted(category_columns)
    gu[cats] = gu[cats].div(gu["sum_activities"], axis=0)
    return gu


def apply_optional_geo_filter(global_universe: pd.DataFrame) -> pd.DataFrame:
    """Exclude selected domiciles and foreign-currency listings within macro regions."""
    # gu = global_universe.copy()
    # gu = gu[~gu["loc"].isin(["CAN", "CHE", "GBR"])]
    # foreign_listed = (gu["MacroRegion"] == "Europe") & (gu["curcdd"] != "EUR")
    # foreign_listed |= (gu["MacroRegion"] == "United States and Canada") & (
    #     gu["curcdd"] != "USD"
    # )
    return gu[~foreign_listed]



def _fama_french_dates_as_timestamps(dates: pd.Series) -> pd.Series:
    """Notebook uses Period `date`; some callers use datetime. Normalize for comparison."""
    if pd.api.types.is_datetime64_any_dtype(dates):
        return pd.to_datetime(dates)
    return dates.dt.to_timestamp(how="end")


def align_fama_french_to_returns(
    fama_french: pd.DataFrame, global_returns: pd.DataFrame
) -> pd.DataFrame:
    """Filter by min return date, then set index to `global_returns.index` (drops `date`)."""
    ff = fama_french.copy()
    ts_end = _fama_french_dates_as_timestamps(ff["date"])
    ff = ff[ts_end >= global_returns.index.min()].copy()
    ff.index = global_returns.index
    return ff.drop(columns=["date"])




def dropna_std_cols_and_build_pivots(
    global_universe: pd.DataFrame,
    cols_standardization: Sequence[str],
    signal_columns: Sequence[str],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    """Drop rows missing standardization keys; build wide return and per-signal matrices."""
    gu = global_universe.copy()
    cols = list(cols_standardization)
    gu = gu.dropna(subset=cols)

    global_returns = gu.pivot(index="date", columns="gvkey_iid", values="tr")
    signals: dict[str, pd.DataFrame] = {
        col: gu.pivot(index="date", columns="gvkey_iid", values=col)
        for col in signal_columns
    }
    return gu, global_returns, signals



def apply_cross_signal_nan_mask(
    global_returns: pd.DataFrame,
    signals: Mapping[str, pd.DataFrame],
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """NaN any (date, asset) where return or any signal is missing (common universe)."""
    r = global_returns.copy()
    masked_signals = {name: s.copy() for name, s in signals.items()}
    mask = r.isna()
    for s in masked_signals.values():
        mask = mask | s.isna()
    r[mask] = np.nan
    for name in masked_signals:
        masked_signals[name][mask] = np.nan
    return r, masked_signals


def standardize_all_signals(
    signals: Mapping[str, pd.DataFrame],
    global_universe: pd.DataFrame,
    cols_standardization: Sequence[str],
) -> dict[str, pd.DataFrame]:
    cols = list(cols_standardization)
    return {
        name: standardize_pivot(s, global_universe, cols)
        for name, s in signals.items()
    }


def merge_signals_long(signals: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Stack standardized signals and merge on (date, gvkey_iid); drop incomplete rows."""
    if not signals:
        raise ValueError("signals must contain at least one pivot")

    names = list(signals.keys())
    stacked: list[pd.DataFrame] = []
    for name in names:
        long = signals[name].stack().reset_index()
        long.columns = ["date", "gvkey_iid", name]
        stacked.append(long)

    out = stacked[0]
    for df in stacked[1:]:
        out = out.merge(df, on=["date", "gvkey_iid"], how="left")
    out = out.dropna(subset=names)
    return out


def _res_suffix_from_returns_index(returns_index: pd.Index) -> str:
    if len(returns_index) == 0:
        return "empty"
    start = pd.Timestamp(returns_index.min())
    end = pd.Timestamp(returns_index.max())
    if pd.isna(start) or pd.isna(end):
        return "empty"
    return f"{start.strftime('%Y-%m')}_{end.strftime('%Y-%m')}"


@dataclass
class UnivariateSortingPrep:
    """Outputs of `prepare_univariate_sorting_inputs` for univariate portfolio sorting."""

    global_universe: pd.DataFrame
    global_returns: pd.DataFrame
    signals: dict[str, pd.DataFrame]
    signal_names: dict[str, str]
    global_long_df: pd.DataFrame
    fama_french: pd.DataFrame
    res_suffix: str


def prepare_univariate_sorting_inputs(
    global_universe: pd.DataFrame,
    lc: pd.DataFrame,
    fama_french: pd.DataFrame,
    lc_signals: Mapping[str, str],
    universe_signals: Mapping[str, str],
    category_columns: Sequence[str],
    cols_standardization: Sequence[str],
    *,
    apply_geo_filter: bool = False,
) -> UnivariateSortingPrep:
    """
    Build monthly panel, pivots, aligned factors, masked and z-scored signals, and long-format merge.

    Parameters
    ----------
    lc_signals
        Mapping ``{column_name: display_name}`` for signals that live in ``lc`` and
        must be merged into ``global_universe`` at fiscal year.
    universe_signals
        Mapping ``{column_name: display_name}`` for signals already present on
        ``global_universe`` (e.g. ``esg``). No LC merge performed for these.

    Does not mutate the input ``global_universe`` or ``lc`` (works on copies).
    """
    lc_signals = dict(lc_signals)
    universe_signals = dict(universe_signals)

    overlap = set(lc_signals).intersection(universe_signals)
    if overlap:
        raise ValueError(
            f"columns appear in both lc_signals and universe_signals: {sorted(overlap)}"
        )

    missing_lc = [c for c in lc_signals if c not in lc.columns]
    if missing_lc:
        raise ValueError(f"lc is missing lc_signals columns: {missing_lc}")

    missing_gu = [c for c in universe_signals if c not in global_universe.columns]
    if missing_gu:
        raise ValueError(
            f"global_universe is missing universe_signals columns: {missing_gu}"
        )

    signal_columns: list[str] = list(lc_signals.keys()) + list(universe_signals.keys())
    signal_names: dict[str, str] = {**lc_signals, **universe_signals}

    gu = global_universe.copy()
    gu = intersect_gvkeys_and_filter(gu, lc)
    gu = merge_lc_into_global_universe(gu, lc, category_columns, list(lc_signals.keys()))
    gu = add_gvkey_iid_sort_clean(gu)
    gu = to_monthly_last_trading_date(gu)
    gu = compute_monthly_returns_long(gu)
    gu = normalize_category_shares(gu, category_columns)
    if apply_geo_filter:
        gu = apply_optional_geo_filter(gu)

    gu, global_returns, signals = dropna_std_cols_and_build_pivots(
        gu, cols_standardization, signal_columns
    )

    # --- Diagnostic: print FF dates vs returns dates side by side to check alignment ---
    _ff_dates = _fama_french_dates_as_timestamps(fama_french["date"].copy())
    _ff_dates = _ff_dates[_ff_dates >= global_returns.index.min()].reset_index(drop=True)
    _ret_dates = pd.Series(global_returns.index, name="returns_date")
    _cmp = pd.DataFrame(
        {
            "ff_date": _ff_dates.dt.strftime("%Y-%m"),
            "returns_date": pd.Series(_ret_dates).dt.strftime("%Y-%m"),
        }
    )
    _cmp["match"] = _cmp["ff_date"] == _cmp["returns_date"]
    print(f"[prepare_univariate_sorting_inputs] FF rows={len(_ff_dates)} | returns rows={len(global_returns)}")
    print(f"[prepare_univariate_sorting_inputs] all months match: {bool(_cmp['match'].all())}")
    with pd.option_context("display.max_rows", None):
        print(_cmp.to_string(index=True))

    if len(_ff_dates) != len(global_returns) or not bool(_cmp["match"].all()):
        _mismatches = _cmp[~_cmp["match"]]
        raise ValueError(
            "Fama-French dates do not match returns dates "
            f"(FF rows={len(_ff_dates)}, returns rows={len(global_returns)}). "
            "First mismatches:\n"
            f"{_mismatches.head(10).to_string(index=True)}"
        )

    ff = align_fama_french_to_returns(fama_french, global_returns)

    global_returns, signals = apply_cross_signal_nan_mask(global_returns, signals)
    signals = standardize_all_signals(signals, gu, cols_standardization)
    long_df = merge_signals_long(signals)
    suffix = _res_suffix_from_returns_index(global_returns.index)

    return UnivariateSortingPrep(
        global_universe=gu,
        global_returns=global_returns,
        signals=signals,
        signal_names=signal_names,
        global_long_df=long_df,
        fama_french=ff,
        res_suffix=suffix,
    )
