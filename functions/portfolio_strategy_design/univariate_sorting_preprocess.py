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
    show_corr_matrices: bool = False,
    corr_method: str = "pearson",
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


    6
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

    # NON-normalised ESG-vs-behavioural relationship, shown BEFORE standardization.
    # Only when requested and an ESG signal is present (esg_choice != "none").
    if show_corr_matrices and any(str(k).startswith("esg") for k in signals):
        from functions.portfolio_metrics.signal_correlation import (
            esg_signal_regressions_from_pivots, signal_correlation_matrix_from_pivots,
        )
        esg_signal_regressions_from_pivots(signals, signal_names, show=True)
        signal_correlation_matrix_from_pivots(
            signals, signal_names, method=corr_method,
            title="Signal correlation matrix (non-normalised)", show=True,
        )

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


def prepare_esg_universe_sorting_inputs(
    global_universe: pd.DataFrame,
    gics_by_gvkey: pd.DataFrame,
    fama_french: pd.DataFrame,
    universe_signals: Mapping[str, str],
    *,
    industry_level: int = 0,
    year_col: str = "last_year",
    min_group_size: int = 5,
    drop_real_estate: bool = False,
    drop_utilities: bool = False,
) -> UnivariateSortingPrep:
    """Level 2: univariate-sort inputs for an ESG signal on the FULL Compustat universe,
    WITHOUT merging the LC dataset.

    The Compustat universe carries no GICS, so ``gics_by_gvkey`` (from ``get_gics_by_gvkey``)
    supplies the industry classification. ESG is standardized industry/currency/year-neutrally
    within ``(year_col, curcdd, Industry)``, where ``Industry`` is derived from ``industry_level``
    EXACTLY like the LC path: 0 -> ``map_sectors`` coarse buckets, 1 -> GICS sector, 2 -> GICS
    industry group. Same machinery as the LC path, minus the LC intersection/merge and the
    LC-derived ``rfyear``/category steps.

    ``global_universe`` must be the POST-``process_global_universe`` frame (so ``tri``/``mktcap``
    are already in the run's numeraire) and ``fama_french`` the already currency-aligned factor
    set -- no FX conversion happens here. ``universe_signals`` should hold a single ESG column
    (e.g. ``{"esg_msci": "esg_msci"}``). Returns the same ``UnivariateSortingPrep`` so all
    downstream notebook cells work unchanged.
    """
    universe_signals = dict(universe_signals)
    if not universe_signals:
        raise ValueError(
            "universe_signals is empty: analyse_esg_only/esg_full_universe require a provider "
            "esg_choice (not 'none')."
        )
    if industry_level not in (0, 1, 2):
        raise ValueError(
            f"industry_level must be 0 (map_sectors), 1 (GICS sector), or 2 (GICS group), got {industry_level!r}"
        )

    signal_columns = list(universe_signals)
    signal_names = dict(universe_signals)
    cols_standardization = [year_col, "curcdd", "Industry"]

    gu = global_universe.copy()
    missing_sig = [c for c in signal_columns if c not in gu.columns]
    if missing_sig:
        raise ValueError(f"global_universe is missing ESG signal column(s): {missing_sig}")

    # --- attach GICS (industry classification) by gvkey; universe has none of its own ---
    gics = gics_by_gvkey.copy()
    gu["gvkey"] = gu["gvkey"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    gics["gvkey"] = gics["gvkey"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    _all_gics = ("GICS_level_1", "GICS_level_2", "GICS_level_3", "GICS_level_4")
    gic_cols = [c for c in _all_gics if c in gics.columns]
    gu = gu.merge(gics[["gvkey", *gic_cols]].drop_duplicates("gvkey"), on="gvkey", how="left")

    # --- derive the `Industry` standardization key from industry_level, mirroring the LC path ---
    # 0 -> map_sectors coarse buckets; 1 -> GICS sector (named); 2 -> GICS industry group code.
    from functions.data_functions.process_lc import map_sectors
    _GICS_SECTOR_NAME = {
        10: "Energy", 15: "Materials", 20: "Industrials", 25: "Consumer Discretionary",
        30: "Consumer Staples", 35: "Health Care", 40: "Financials",
        45: "Information Technology", 50: "Communication Services",
        55: "Real Estate", 60: "Utilities",
    }
    _sector_name = pd.to_numeric(gu["GICS_level_1"], errors="coerce").map(_GICS_SECTOR_NAME)

    # --- optional ESG-only sector drops, on the RAW GICS sector ---
    # Must happen BEFORE map_sectors, which folds Real Estate into the "Financial" bucket
    # (after that, Real Estate is indistinguishable from Financials).
    if drop_real_estate:
        _keep = _sector_name != "Real Estate"
        gu, _sector_name = gu[_keep], _sector_name[_keep]
    if drop_utilities:
        _keep = _sector_name != "Utilities"
        gu, _sector_name = gu[_keep], _sector_name[_keep]

    if industry_level == 0:
        gu["Industry"] = _sector_name.map(lambda x: map_sectors(x) if pd.notna(x) else np.nan)
    elif industry_level == 1:
        gu["Industry"] = _sector_name
    else:  # industry_level == 2
        gu["Industry"] = gu["GICS_level_2"]

    # --- universe-native monthly returns (NO LC steps) ---
    gu = add_gvkey_iid_sort_clean(gu)
    gu = to_monthly_last_trading_date(gu)
    gu = compute_monthly_returns_long(gu)

    # --- drop rows missing any standardization key (incl. firms with no GICS) ---
    n0 = len(gu)
    gu = gu.dropna(subset=cols_standardization)
    print(f"[prepare_esg_universe] dropped {n0 - len(gu)} rows missing {cols_standardization}")

    # --- min-group guard: thin (year, currency, GICS) cells -> degenerate z-scores ---
    sizes = gu.groupby(cols_standardization)["gvkey_iid"].transform("nunique")
    n1 = len(gu)
    gu = gu[sizes >= int(min_group_size)]
    print(
        f"[prepare_esg_universe] dropped {n1 - len(gu)} firm-months in groups < "
        f"{min_group_size} names (grouping on {cols_standardization})"
    )

    # --- build pivots, align factors, mask, standardize (same as the LC path) ---
    gu, global_returns, signals = dropna_std_cols_and_build_pivots(
        gu, cols_standardization, signal_columns
    )

    # Align FF to returns by MONTH INTERSECTION. The cached universe can carry months
    # outside the FF window (e.g. years before start_year that start_year did not trim),
    # so we keep only the months present in BOTH, then index positionally.
    ff = fama_french.copy()
    ff["_per"] = _fama_french_dates_as_timestamps(ff["date"]).dt.to_period("M").values
    _ret_per = global_returns.index.to_period("M")
    _ff_periods = set(ff["_per"])
    _keep = _ret_per.isin(_ff_periods)
    n_ret0 = len(global_returns)
    global_returns = global_returns.loc[_keep]
    signals = {k: v.loc[_keep] for k, v in signals.items()}
    _ret_per = global_returns.index.to_period("M")
    ff = ff[ff["_per"].isin(set(_ret_per))].drop_duplicates("_per").sort_values("_per")
    print(
        f"[prepare_esg_universe] kept {len(global_returns)}/{n_ret0} return months covered by FF "
        f"| FF rows={len(ff)}"
    )
    if len(ff) != len(global_returns):
        raise ValueError(
            "Fama-French / returns month mismatch after intersection "
            f"(FF rows={len(ff)}, returns rows={len(global_returns)})."
        )

    # --- PROOF: the positional assignment below only aligns if, row-for-row, the
    # FF month (sorted ascending by `_per`) equals the returns month at the SAME
    # position. `ff` was sorted; `global_returns` was only boolean-masked, so this
    # also catches a non-monotonic returns index that would silently misalign. ---
    _ret_per_chk = global_returns.index.to_period("M")
    _ff_per_chk = pd.PeriodIndex(ff["_per"].values, freq="M")
    _matches = (_ret_per_chk == _ff_per_chk)
    _proof = pd.DataFrame(
        {"row": range(len(_ret_per_chk)),
         "returns_month": _ret_per_chk.astype(str),
         "ff_month": _ff_per_chk.astype(str),
         "match": _matches},
    )
    print("[prepare_esg_universe] FF<->returns month alignment proof (positional):")
    print(_proof.head(6).to_string(index=False))
    print("   ... " if len(_proof) > 12 else "")
    if len(_proof) > 12:
        print(_proof.tail(6).to_string(index=False))
    print(
        f"   matched {int(_matches.sum())}/{len(_matches)} rows | "
        f"returns index monotonic-increasing={global_returns.index.is_monotonic_increasing}"
    )
    if not _matches.all():
        _bad = _proof.loc[~_matches]
        raise ValueError(
            "FF/returns month MISALIGNMENT at "
            f"{len(_bad)} row(s); first offenders:\n{_bad.head(10).to_string(index=False)}"
        )
    print("   -> every FF row sits on the same calendar month as its returns row. OK")

    ff.index = global_returns.index
    ff = ff.drop(columns=["date", "_per"])

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
