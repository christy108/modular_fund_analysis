import pandas as pd
import numpy as np


def process_japan_universe(japan_universe, fx_rates, convert_to_USD):
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

    # Create the correct year to merge on fundamentals
    japan_universe["last_year"] = np.where(
        japan_universe["date"].dt.month <= 6,
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
    mktcap_covered,
    esg_choice,
):
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
        global_universe["esg_refinitive"] /= 100
    elif esg_choice == "s&p":
        global_universe["esg_sp"] /= 100

   

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

    # Keep `mktcap_covered` of total market cap (of each currency area)
    global_universe = global_universe[
        global_universe["cumulative_mktcap"]
        > (1 - mktcap_covered) * global_universe["total_mktcap"]
    ]

    # Format the gvkeys
    global_universe["gvkey"] = (
        global_universe["gvkey"].dropna().astype(float).astype(int).astype(str)
    )

    return global_universe