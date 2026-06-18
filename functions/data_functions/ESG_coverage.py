"""ESG-coverage diagnostic for the fund_analysis pipeline.

Gated by the ``show_esg_coverage`` parameter in Main.ipynb. Reports, for the
three ESG providers (MSCI, Refinitiv/LSEG, S&P), the percentage of firm-years
that carry a non-NaN ESG score, across two samples:

  Sample 1 -- raw LC (PRE sample-filtering) signal-active firm-years for the
              region of interest (``loc == country``). "Signal-active" means the
              firm-year has >0 categorised activity, i.e. the same rule the
              pipeline uses to build ``sum_activities``.
  Sample 2 -- the post-filter analysis panel: every stock-year actually traded
              in ``global_returns``, joined to ESG on the same lagged fiscal year
              (``last_year``) the production pipeline uses.

All three provider columns are already merged onto the regional universes in
Main.ipynb (the cell that calls ``get_*_esg_merge_to_universe``), independent of
``esg_choice`` -- this module only reads them, it never re-runs a merge.

Temporal-basis caveat: MSCI and Refinitiv attach by fiscal year
(``universe.last_year == esg.year``); S&P attaches as-of the trading date
(``merge_asof``). So the S&P figure is on a point-in-time as-of basis while
MSCI/Refinitiv are fiscal-year matched -- directionally comparable, not on an
identical footing.
"""

import pandas as pd

PROVIDERS = ["MSCI", "Refinitiv", "S&P"]
# universe column name -> display name
_COLS = {"esg_msci": "MSCI", "esg_refinitive": "Refinitiv", "esg_sp": "S&P"}


def _norm_gvkey(s):
    """Reconcile the three gvkey encodings used across the pipeline
    ("10275", "10275.0", "010275") to one zero-padded 6-char string."""
    n = pd.to_numeric(s, errors="coerce")
    return n.astype("Int64").astype("string").str.zfill(6)


def build_esg_lookup(usa_universe, row_universe, japan_universe):
    """``(gvkey, last_year) -> {MSCI, Refinitiv, S&P}`` score table.

    Reads the ESG columns already merged onto the universes. ``groupby().first()``
    skips NaNs, so a non-null cell means "a score is present for that key"; this
    also makes S&P (which can hold several as-of values per key) well-defined for
    a presence/coverage count.
    """
    parts = pd.concat([usa_universe, row_universe, japan_universe])[
        ["gvkey", "last_year", *_COLS]
    ].copy()
    parts["gvkey"] = _norm_gvkey(parts["gvkey"])
    parts["last_year"] = parts["last_year"].astype("Int64")
    parts = parts.dropna(subset=["gvkey", "last_year"]).rename(columns=_COLS)
    return parts.groupby(["gvkey", "last_year"])[PROVIDERS].first()


def coverage_sample1_lc(lc_raw, esg_lookup, categories_dict, signal_denominator, country="JPN"):
    """Sample 1: raw-LC signal-active firm-years for ``country``; % with non-NaN ESG.

    ``lc_raw`` must be a snapshot of ``lc`` taken right after ``process_lc(...)``
    and BEFORE the sample filters, so the denominator is the broad
    report-issuing population. The category columns and ``categories_dict`` both
    exist at that point. Joined to ESG on the firm-year's own fiscal year
    (``rfyear``).
    """
    if signal_denominator == "Sum_All_Signals":
        active = lc_raw[list(categories_dict.keys())].sum(axis=1) > 0
    else:  # "Sum_All_Initiatives"
        active = lc_raw["n_predicted_initiatives"] > 0

    s1 = lc_raw.loc[active & (lc_raw["loc"] == country), ["gvkey", "rfyear"]].copy()
    s1["gvkey"] = _norm_gvkey(s1["gvkey"])
    s1["rfyear"] = s1["rfyear"].astype("Int64")
    s1 = s1.dropna().drop_duplicates()
    s1 = s1.merge(esg_lookup, left_on=["gvkey", "rfyear"], right_index=True, how="left")
    return {p: s1[p].notna().mean() * 100 for p in PROVIDERS}


def coverage_sample2_returns(global_returns, global_universe, esg_lookup):
    """Sample 2: unique stock-fiscal-years actually traded in ``global_returns``;
    % with non-NaN ESG.

    Each traded stock-month takes its authoritative ``last_year`` from
    ``global_universe`` (so the month-dependent Japan lag is honoured exactly as
    the main code computed it), then we aggregate to unique ``(gvkey, last_year)``
    before the ESG join -- avoiding any arbitrary collapse of the split-month lag.
    """
    gu = global_universe.copy()
    gu["gvkey"] = _norm_gvkey(gu["gvkey"])
    gu["date"] = pd.PeriodIndex(gu["date"], freq="M")
    gu_key = (
        gu.drop_duplicates(["gvkey_iid", "date"])
        .set_index(["gvkey_iid", "date"])["last_year"]
    )

    traded = global_returns.stack().index.to_frame(index=False)
    traded.columns = ["date", "gvkey_iid"]
    traded["date"] = pd.PeriodIndex(traded["date"], freq="M")
    traded = traded.merge(
        gu_key.rename("last_year"), left_on=["gvkey_iid", "date"], right_index=True, how="left"
    )
    traded["gvkey"] = _norm_gvkey(traded["gvkey_iid"].str.split("_").str[0])

    s2 = traded[["gvkey", "last_year"]].dropna().drop_duplicates()
    s2["last_year"] = s2["last_year"].astype("Int64")
    s2 = s2.merge(esg_lookup, left_on=["gvkey", "last_year"], right_index=True, how="left")
    return {p: s2[p].notna().mean() * 100 for p in PROVIDERS}


def esg_coverage_table(cov1, cov2, country="JPN"):
    """Assemble the 2x3 coverage table (rows = samples, cols = providers, % values)."""
    return pd.DataFrame(
        [cov1, cov2],
        index=[
            f"LC signal-active firm-years (raw, {country})",
            "Post-filter sample (global_returns)",
        ],
    )[PROVIDERS].round(1)
