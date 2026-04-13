from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

from functions.functions import conditional_pct_change, standardize_pivot

_LC_MERGE_BASE: tuple[str, ...] = (
    "gvkey",
    "rfyear",
    "MacroRegion",
    "loc",
    "Industry",
    "signal_0",
    "signal_1",
    "signal_2",
    "sum_activities",
)


def _lc_merge_columns(category_columns: Sequence[str]) -> list[str]:
    return list(_LC_MERGE_BASE) + sorted(category_columns)


def intersect_gvkeys_and_filter(
    global_universe: pd.DataFrame, lc: pd.DataFrame
) -> pd.DataFrame:
    """Keep WRDS rows whose gvkey appears in both panels."""
    lc_gvkey = lc["gvkey"].unique()
    gu_gvkey = global_universe["gvkey"].unique()
    mapping = np.intersect1d(lc_gvkey, gu_gvkey)
    return global_universe[global_universe["gvkey"].isin(mapping)].copy()


def merge_lc_into_global_universe(
    global_universe: pd.DataFrame,
    lc: pd.DataFrame,
    category_columns: Sequence[str],
) -> pd.DataFrame:
    """Attach LC signals and activity columns at fiscal year (`last_year` ↔ `rfyear`)."""
    cols = _lc_merge_columns(category_columns)
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
    """Within each `gvkey_iid`, compute `tr` from `tri` with gap masking (`conditional_pct_change`)."""
    return (
        global_universe.groupby("gvkey_iid", group_keys=False)
        .apply(conditional_pct_change)
        .reset_index(drop=True)
    )


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


def dropna_std_cols_and_build_pivots(
    global_universe: pd.DataFrame, cols_standardization: Sequence[str]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Drop rows missing standardization keys; build wide return and signal matrices."""
    gu = global_universe.copy()
    cols = list(cols_standardization)
    gu = gu.dropna(subset=cols)
    global_returns = gu.pivot(index="date", columns="gvkey_iid", values="tr")
    s0 = gu.pivot(index="date", columns="gvkey_iid", values="signal_0")
    s1 = gu.pivot(index="date", columns="gvkey_iid", values="signal_1")
    s2 = gu.pivot(index="date", columns="gvkey_iid", values="signal_2")
    return gu, global_returns, s0, s1, s2


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


def apply_cross_signal_nan_mask(
    global_returns: pd.DataFrame,
    global_signal_0: pd.DataFrame,
    global_signal_1: pd.DataFrame,
    global_signal_2: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """NaN any (date, asset) where return or any signal is missing (common universe)."""
    r = global_returns.copy()
    s0 = global_signal_0.copy()
    s1 = global_signal_1.copy()
    s2 = global_signal_2.copy()
    mask = r.isna() | s0.isna() | s1.isna() | s2.isna()
    r[mask] = np.nan
    s0[mask] = np.nan
    s1[mask] = np.nan
    s2[mask] = np.nan
    return r, s0, s1, s2


def standardize_all_signals(
    global_signal_0: pd.DataFrame,
    global_signal_1: pd.DataFrame,
    global_signal_2: pd.DataFrame,
    global_universe: pd.DataFrame,
    cols_standardization: Sequence[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cols = list(cols_standardization)
    g0 = standardize_pivot(global_signal_0, global_universe, cols)
    g1 = standardize_pivot(global_signal_1, global_universe, cols)
    g2 = standardize_pivot(global_signal_2, global_universe, cols)
    return g0, g1, g2


def merge_signals_long(
    global_signal_0: pd.DataFrame,
    global_signal_1: pd.DataFrame,
    global_signal_2: pd.DataFrame,
) -> pd.DataFrame:
    """Stack standardized signals and merge on (date, gvkey_iid); drop incomplete rows."""
    g0l = global_signal_0.stack().reset_index()
    g0l.columns = ["date", "gvkey_iid", "signal_0"]
    g1l = global_signal_1.stack().reset_index()
    g1l.columns = ["date", "gvkey_iid", "signal_1"]
    g2l = global_signal_2.stack().reset_index()
    g2l.columns = ["date", "gvkey_iid", "signal_2"]
    out = g0l.merge(g1l, on=["date", "gvkey_iid"], how="left")
    out = out.merge(g2l, on=["date", "gvkey_iid"], how="left")
    out = out.dropna(subset=["signal_0", "signal_1", "signal_2"])
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
    global_signal_0: pd.DataFrame
    global_signal_1: pd.DataFrame
    global_signal_2: pd.DataFrame
    global_combined_signal_max_min: pd.DataFrame
    global_long_df: pd.DataFrame
    fama_french: pd.DataFrame
    res_suffix: str


def prepare_univariate_sorting_inputs(
    global_universe: pd.DataFrame,
    lc: pd.DataFrame,
    fama_french: pd.DataFrame,
    category_columns: Sequence[str],
    cols_standardization: Sequence[str],
    *,
    apply_geo_filter: bool = False,
) -> UnivariateSortingPrep:
    """
    Build monthly panel, pivots, aligned factors, masked and z-scored signals, and long-format merge.

    Does not mutate the input `global_universe` or `lc` (works on copies).
    """
    gu = global_universe.copy()
    gu = intersect_gvkeys_and_filter(gu, lc)
    gu = merge_lc_into_global_universe(gu, lc, category_columns)
    gu = add_gvkey_iid_sort_clean(gu)
    gu = to_monthly_last_trading_date(gu)
    gu = compute_monthly_returns_long(gu)
    gu = normalize_category_shares(gu, category_columns)
    if apply_geo_filter:
        gu = apply_optional_geo_filter(gu)

    gu, global_returns, s0, s1, s2 = dropna_std_cols_and_build_pivots(
        gu, cols_standardization
    )

    ff = align_fama_french_to_returns(fama_french, global_returns)

    global_returns, s0, s1, s2 = apply_cross_signal_nan_mask(global_returns, s0, s1, s2)
    s0, s1, s2 = standardize_all_signals(s0, s1, s2, gu, cols_standardization)
    combined = s2 - s0
    long_df = merge_signals_long(s0, s1, s2)
    suffix = _res_suffix_from_returns_index(global_returns.index)

    return UnivariateSortingPrep(
        global_universe=gu,
        global_returns=global_returns,
        global_signal_0=s0,
        global_signal_1=s1,
        global_signal_2=s2,
        global_combined_signal_max_min=combined,
        global_long_df=long_df,
        fama_french=ff,
        res_suffix=suffix,
    )
