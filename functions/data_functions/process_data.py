import pandas as pd
import numpy as np


def process_japan_universe(japan_universe, fx_rates, convert_to_USD, japan_year_adjustment_split_month_for_two_or_one):
    """
    Standardizes date and gvkey, merges in FX rates by (date, curcdd),
    converts mktcap_lcu and tri_lcu to base-currency mktcap/tri, and
    creates last_year for fundamentals merging (Jan–Jun: (year-2); Jul–Dec: (year-1)).
    """

    # Set dates to datetime format
    japan_universe["date"] = pd.to_datetime(japan_universe["date"])
    japan_universe["gvkey"] = japan_universe["gvkey"].astype(float).astype(str)

    # Currency conversions (optional)
    if convert_to_USD:
        japan_universe = pd.merge(japan_universe, fx_rates, on=["date", "curcdd"], how="left")
        japan_universe["mktcap"] = japan_universe["mktcap_lcu"] / japan_universe["rate"]
        japan_universe["tri"] = japan_universe["tri_lcu"] / japan_universe["rate"]
    else:
        japan_universe["mktcap"] = japan_universe["mktcap_lcu"]
        japan_universe["tri"] = japan_universe["tri_lcu"]

    # double check thissssss
    # Create the correct year to merge on fundamentals
    japan_universe["last_year"] = np.where(
        japan_universe["date"].dt.month <= japan_year_adjustment_split_month_for_two_or_one,
        japan_universe["date"].dt.year - 2,
        japan_universe["date"].dt.year - 1,
    )

    japan_universe["last_year"] = japan_universe["last_year"].astype(int)

    return japan_universe


def process_row_universe(row_universe, fx_rates, convert_to_USD):


    """
    standardizes date andgvkey, merges in FX rates by (date, curcdd), 
    converts mktcap_lcu and tri_lcu to base-currency mktcap/tri, and 
    creates last_year for fundamentals merging (Jan–Jun: (year-2); Jul–Dec: (year-1)).
    """


    # Set dates to datetime format
    row_universe['date'] = pd.to_datetime(row_universe['date'])
    row_universe['gvkey'] = row_universe['gvkey'].astype(float).astype(str)

    # Currency conversions (optional)
    if convert_to_USD:
        row_universe = pd.merge(row_universe, fx_rates, on=["date", "curcdd"], how="left")
        row_universe["mktcap"] = row_universe["mktcap_lcu"] / row_universe["rate"]
        row_universe["tri"] = row_universe["tri_lcu"] / row_universe["rate"]
    else:
        row_universe["mktcap"] = row_universe["mktcap_lcu"]
        row_universe["tri"] = row_universe["tri_lcu"]

    # Create the correct year to merge on fundamentals
    # For dates in H1 (Jan-Jun), accounting data from Y-1 isn't out yet, so use Y-2's report.
    # For dates in H2 (Jul-Dec), accounting data from Y-1 is available.
    row_universe['last_year'] = np.where(
        row_universe['date'].dt.month <= 6, 
        row_universe['date'].dt.year - 2, 
        row_universe['date'].dt.year - 1
    )

    row_universe['last_year'] = row_universe['last_year'].astype(int)

    return row_universe


def process_usa_universe(usa_universe):

    """
    Same as process_row_universe, but for USA universe,
    no FX rates needed. as its in USD.
    """


    # Set dates to datetime format
    usa_universe['date'] = pd.to_datetime(usa_universe['date'])
    usa_universe['gvkey'] = usa_universe['gvkey'].astype(float).astype(str)

    # Add column to indicate that the LCU is US dollars
    usa_universe['curcdd'] = 'USD'

    # Create the correct year to merge on fundamentals
    # For dates in H1 (Jan-Jun), accounting data from Y-1 isn't out yet, so use Y-2's report.
    # For dates in H2 (Jul-Dec), accounting data from Y-1 is available.
    usa_universe['last_year'] = np.where(
        usa_universe['date'].dt.month <= 6, 
        usa_universe['date'].dt.year - 2, 
        usa_universe['date'].dt.year - 1
    )

    usa_universe['last_year'] = usa_universe['last_year'].astype(int)

    return usa_universe


def process_global_universe(
    usa_universe,
    row_universe,
    japan_universe,
    currency_filter,
    mktcap_covered_if_filter_by_cum_market_cap,
    esg_choice,
    market_cap_filter="percent_total_mcap",
    percentage_stocks_removed_if_percent_stocks_true=0.01,
    floor_if_percent_stocks_true=100e6,
):
    """Assemble the global universe and apply ONE of two market-cap screens.

    ``market_cap_filter`` selects the screen:

    * ``"percent_total_mcap"`` (default) — the original rule, applied per
      currency-MONTH: rank listings ascending by month-end cap, cumulate from the
      smallest, and keep those whose running total exceeds
      ``(1 - mktcap_covered_if_filter_by_cum_market_cap)`` of the cell total. The
      percentage is a share of aggregate market-cap VALUE, which because cap is
      concentrated discards ~65% of listings at 0.95.
    * ``"percent_stocks"`` — applied per currency-YEAR. A listing is dropped for the
      whole of year Y iff, measured on its LAST cap in year Y-1, it is both among the
      smallest ``percentage_stocks_removed_if_percent_stocks_true`` of listings BY COUNT
      and below ``floor_if_percent_stocks_true``. Equivalently: apply the floor, but
      never remove more than the smallest x% of listings. Using Y-1 keeps the decision
      point-in-time; a listing with no Y-1 observation is dropped.

    The two percentages are NOT comparable: one is a share of value, the other a share
    of count.

    The new parameters are keyword-with-defaults and sit at the END of the signature
    because every call site in this repo passes positionally — see the callers in
    New_Pipeline/nodes/04_merge_esg_provider.py, functions/extra_functions/plot_coverage.py,
    scripts/download_us_gics.py and both notebooks. Defaulting to "percent_total_mcap"
    means all of those keep their exact previous behaviour untouched.
    """
    # Drop old identifier columns (if present)
    usa_universe = usa_universe.drop(columns=["cusip"], errors="ignore")
    row_universe = row_universe.drop(columns=["isin"], errors="ignore")
    if japan_universe is not None:
        japan_universe = japan_universe.drop(columns=["isin"], errors="ignore")

    # Merge and generate global universe (align to USA column schema)
    parts = [usa_universe]
    parts.append(row_universe.reindex(columns=usa_universe.columns))
    if japan_universe is not None:
        parts.append(japan_universe.reindex(columns=usa_universe.columns))
    global_universe = pd.concat(parts, axis=0, ignore_index=True)

    # Re-scale ESG ratings

    if esg_choice == "none":
        global_universe["esg"] /= 100
    elif esg_choice == "refinitiv":
        # LSEG `valuescore` is already on a 0-1 scale; no rescaling needed.
        # (The OLD Refinitiv export was 0-100 and divided by 100 here.)
        pass
    elif esg_choice == "s&p":
        global_universe["esg_sp"] /= 100
    elif esg_choice == "msci":
        # MSCI industry-adjusted / weighted scores are 0-10; rescale to 0-1.
        global_universe["esg_msci"] /= 10

   

    # Drop missings in `mktcap`
    global_universe = global_universe[global_universe["mktcap"].notna()]

    # Add temporal identifiers
    global_universe["month"] = global_universe["date"].dt.month
    global_universe["year"] = global_universe["date"].dt.year


    # Filter to keep listing in currency of interest
    if currency_filter is not None and len(currency_filter) > 0:
        global_universe = global_universe[global_universe["curcdd"].isin(currency_filter)]
   

    # First, ensure the data is sorted by date within each group
    global_universe_sorted = global_universe.sort_values(by=["date"])

    # Use the last() function to get the last available market cap values
    last_values = (
        global_universe_sorted.groupby(["month", "year", "curcdd", "gvkey", "iid"])
        .agg(last_mktcap=("mktcap", "last"))
        .reset_index()
    )

    # Sort `last_values`
    last_values = last_values.sort_values(by=["month", "year", "curcdd", "last_mktcap"])

    # Aggregate mktcap data
    last_values["cumulative_mktcap"] = last_values.groupby(["month", "year", "curcdd"])[
        "last_mktcap"
    ].cumsum()
    last_values["total_mktcap"] = last_values.groupby(["month", "year", "curcdd"])[
        "last_mktcap"
    ].transform("sum")

    # Merge this novel mktcap data
    global_universe = pd.merge(
        global_universe, 
        last_values,
        on=["month", "year", "curcdd", "gvkey", "iid"],
        how='left'
    )

    if market_cap_filter == "percent_total_mcap":
        # Keep `mktcap_covered_if_filter_by_cum_market_cap` of total market cap (of each
        # currency area). Unchanged from the original rule.
        global_universe = global_universe[
            global_universe["cumulative_mktcap"]
            > (1 - mktcap_covered_if_filter_by_cum_market_cap) * global_universe["total_mktcap"]
        ]

    elif market_cap_filter == "percent_stocks":
        # Drop the smallest x% of listings BY COUNT, but only those also below an
        # absolute floor. Decided once per YEAR on the previous year's last cap.
        if not 0 <= percentage_stocks_removed_if_percent_stocks_true <= 1:
            raise ValueError(
                "percentage_stocks_removed_if_percent_stocks_true is a FRACTION "
                f"(0.01 == 1%), got {percentage_stocks_removed_if_percent_stocks_true!r}"
            )
        # An absolute floor is only meaningful in a single currency. `mktcap` is in the
        # LISTING currency unless convert_to_USD converted it upstream, so comparing it
        # to a constant across currency areas is wrong (a JPY cap against a USD floor is
        # out by ~150x). Same guard plot_coverage.compute_coverage_over_time enforces.
        _ccy = sorted(global_universe["curcdd"].dropna().unique())
        if len(_ccy) > 1:
            raise ValueError(
                "market_cap_filter='percent_stocks' compares mktcap to an absolute "
                f"floor, but the universe spans {_ccy}. Use a single-currency "
                "currency_filter, or set convert_to_USD=True so every mktcap is in "
                "one currency."
            )

        # One reference cap per listing per YEAR: its last observation that year.
        # global_universe_sorted is already date-sorted, so "last" is the latest date --
        # the same construction the monthly block above uses.
        ref = (
            global_universe_sorted.groupby(["year", "curcdd", "gvkey", "iid"])
            .agg(ref_mktcap=("mktcap", "last"))
            .reset_index()
        )

        # Rank by COUNT within each reference year+currency (not by value share).
        ref = ref.sort_values(by=["year", "curcdd", "ref_mktcap"])
        _cell = ["year", "curcdd"]
        ref["ref_pct_rank"] = (ref.groupby(_cell).cumcount() + 1) / ref.groupby(_cell)[
            "ref_mktcap"
        ].transform("size")
        ref["drop_ref"] = (
            ref["ref_pct_rank"] <= percentage_stocks_removed_if_percent_stocks_true
        ) & (ref["ref_mktcap"] < floor_if_percent_stocks_true)

        # Year Y's membership is decided by year Y-1's reference: shift forward, join.
        ref["year"] = ref["year"] + 1
        global_universe = pd.merge(
            global_universe,
            ref[["year", "curcdd", "gvkey", "iid", "ref_mktcap", "ref_pct_rank", "drop_ref"]],
            on=["year", "curcdd", "gvkey", "iid"],
            how="left",
        )

        # .eq(False) keeps ONLY listings whose Y-1 reference says keep, dropping both
        # drop_ref=True and drop_ref=NaN in one expression. NaN means "no Y-1
        # observation" -- a new listing, or every listing in the earliest year present --
        # which is dropped by design. This also matches how the percent_total_mcap branch
        # treats rows whose NaN gvkey/iid never matched the merge (NaN > x is False).
        global_universe = global_universe[global_universe["drop_ref"].eq(False)]

    else:
        # NOT optional: without this a typo'd value falls through both branches and the
        # universe passes COMPLETELY UNFILTERED -- a silent ~3x sample change that looks
        # like a real result.
        raise ValueError(f"unknown market_cap_filter {market_cap_filter!r}")

    # Drop the percent_stocks helper columns so the returned column set is identical
    # under either method (no-op on the percent_total_mcap path, which never adds them).
    global_universe = global_universe.drop(
        columns=["ref_mktcap", "ref_pct_rank", "drop_ref"], errors="ignore"
    )

    # Format the gvkeys
    global_universe["gvkey"] = (
        global_universe["gvkey"].dropna().astype(float).astype(int).astype(str)
    )

    return global_universe


def convert_factors_to_jpy(fama_french, fx_rates, rf_japan_path):
    """Convert USD Fama-French factors to a JPY (Japanese-investor) numeraire.

    - Market factor: add back US rf, scale by the month-over-month JPY/USD FX
      ratio FX(t)/FX(t-1), strip the 1, then subtract the Japanese rf.
    - Zero-cost long-short factors (SMB/HML/RMW/CMA): scale by the FX ratio only.
      The loop auto-adapts to FF3 (smb/hml) or FF5 (+rmw/cma) via `if c in columns`.
    - Risk-free: overwrite the US rf with the Japanese monthly T-bill.

    Merges are done on the Period[M] `date` key, so every row is matched by
    calendar month; row order and length are preserved (left merge), which keeps
    downstream positional code (cell 42 `.values`, regressions `reset_index`) valid.
    """
    ff = fama_french.copy()

    # Month-end JPY/USD level, then month-over-month ratio FX(t)/FX(t-1)
    jpy = (fx_rates.loc[fx_rates['curcdd'] == 'JPY', ['date', 'rate']]
           .dropna().sort_values('date').set_index('date')['rate'])
    jpy_me = jpy.resample('ME').last()
    fx_ratio = (jpy_me / jpy_me.shift(1)).rename('fx_ratio')
    fx_ratio.index = fx_ratio.index.to_period('M')   # match fama_french Period[M] key

    # Japanese monthly risk-free (T-bill) keyed by month
    rfj = pd.read_excel(rf_japan_path)[['Month', 'Rf Japan (monthly)']].dropna()
    rfj['Month'] = pd.PeriodIndex(rfj['Month'].astype(str), freq='M')
    rfj = rfj.set_index('Month')['Rf Japan (monthly)'].rename('rf_jp')

    # Left-merge by month: preserves order/length, matches month-to-month
    ff = ff.merge(fx_ratio, left_on='date', right_index=True, how='left')
    ff = ff.merge(rfj,      left_on='date', right_index=True, how='left')

    r = ff['fx_ratio']
    # Market factor uses the ORIGINAL US rf (before we overwrite rf below)
    ff['mktrf'] = (1 + ff['mktrf'] + ff['rf']) * r - 1 - ff['rf_jp']
    # Long-short factors: scale by FX ratio only (FF3 -> smb/hml; FF5 -> +rmw/cma)
    for c in ('smb', 'hml', 'rmw', 'cma'):
        if c in ff.columns:
            ff[c] = ff[c] * r
    # Overwrite the risk-free with the Japanese series
    ff['rf'] = ff['rf_jp']

    return ff.drop(columns=['fx_ratio', 'rf_jp'])