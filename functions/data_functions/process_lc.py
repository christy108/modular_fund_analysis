import re

import numpy as np
import pandas as pd

_TYPE_SREC_RE = re.compile(r"^TYPE_SREC:\s*(.+?)\s*-\s*(.+?)\s*$")
_SDG_SREC_RE = re.compile(r"^SDG_SREC:\s*SDG\s*(\d+)\s*-\s*(.+?)\s*$")


def _stakeholder_column_groups(df, pattern):
    groups = {}
    for col in df.columns:
        m = pattern.match(str(col))
        if m is None:
            continue
        groups.setdefault(m.group(2).strip(), []).append(col)
    return groups


def _sum_stakeholder_groups(df, groups):
    return pd.DataFrame({k: df[cols].fillna(0).sum(axis=1) for k, cols in groups.items()})


def add_srec_stakeholder_columns(lc: pd.DataFrame) -> pd.DataFrame:
    by_type = _sum_stakeholder_groups(lc, _stakeholder_column_groups(lc, _TYPE_SREC_RE))
    by_sdg = _sum_stakeholder_groups(lc, _stakeholder_column_groups(lc, _SDG_SREC_RE))
    by_type, by_sdg = by_type.align(by_sdg, join="outer", fill_value=0)
    if not np.array_equal(by_type.values, by_sdg.values):
        diff = (by_type - by_sdg).stack()
        raise ValueError(
            "TYPE_SREC vs SDG_SREC stakeholder totals differ:\n"
            + diff[diff != 0].head(10).to_string()
        )

    print("Added SREC columns: ", by_type.columns)
    out = by_type.rename(columns=lambda s: f"SREC: {s}")
    return lc.join(out)


def process_lc(lc: pd.DataFrame, start_year: int, end_year: int):
    lc.dropna(subset=['gvkey'], inplace=True)

    # Change types to align with WRDS
    lc['gvkey'] = lc['gvkey'].astype(int).astype(str)
    lc['rfyear'] = lc['rfyear'].astype('Int64')

    # Keep rows with some minimum information
    lc = lc.dropna(subset=['gvkey', 'rfyear', 'loc', 'MacroRegion', 'GICS_level_1', 'GICS_level_2', 'GICS_level_3'])

    # Filter rows where MacroRegion is in the specified list
    regions = ["Asia-Pacific", "Europe", "United States and Canada"]
    lc = lc[lc['MacroRegion'].isin(regions)]

    lc = add_missing_gvkeys(lc)



    # Filter data to keep observatios from `start_year`
    lc = lc[lc['rfyear'] >= start_year]
    lc = lc[lc['rfyear'] <= end_year]

    return add_srec_stakeholder_columns(lc)


def add_available_fyears(
    lc: pd.DataFrame,
    rfyear_col: str = "rfyear",
    gvkey_col: str = "gvkey",
) -> pd.DataFrame:
    """
    Adds two columns to `lc`:
      - available_fyears:   sorted list of unique rfyear values for that gvkey
      - n_available_fyears: count of unique rfyears for that gvkey
    """
    years_per_gvkey = (
        lc.groupby(gvkey_col)[rfyear_col]
          .apply(lambda s: sorted(int(y) for y in s.dropna().unique()))
          .rename("available_fyears")
    )

    agg = years_per_gvkey.to_frame()
    agg["n_available_fyears"] = agg["available_fyears"].apply(len)
    agg = agg.reset_index()

    lc = lc.drop(columns=["available_fyears", "n_available_fyears"], errors="ignore")
    return lc.merge(agg, on=gvkey_col, how="left")




def filter_sum_activities_by_fiscal_year_quantiles(
    lc: pd.DataFrame,
    lower_exclude: float,
    upper_exclude: float,
    *,
    activities_col: str = "sum_activities",
    year_col: str = "rfyear",
) -> pd.DataFrame:
    """
    Within each `year_col`, drop the bottom `lower_exclude` and top `upper_exclude`
    fractions of `activities_col` (open interval: strict inequalities).
    lower_exclude, upper_exclude in [0, 1); require lower_exclude + upper_exclude < 1.
    """
    if not 0 <= lower_exclude < 1 or not 0 <= upper_exclude < 1:
        raise ValueError("lower_exclude and upper_exclude must be in [0, 1).")
    if lower_exclude + upper_exclude >= 1:
        raise ValueError("lower_exclude + upper_exclude must be < 1.")
    g = lc.groupby(year_col)[activities_col]
    lower = g.transform(lambda x: x.quantile(lower_exclude))
    upper = g.transform(lambda x: x.quantile(1 - upper_exclude))
    return lc[(lc[activities_col] > lower) & (lc[activities_col] < upper)].copy()



def map_sectors(x):
    # Skip Industrials, Health Care, Utilities
    if x in ['Energy', 'Materials']:
        return 'Primary Industries'
    elif x in ['Consumer Discretionary', 'Consumer Staples']:
        return 'Consumer'

    # make Financial = Financials if you want to include finance sector
    elif x in ['Financials', 'Real Estate']:
        return 'Financial'
    elif x in ['Communication Services', 'Information Technology']:
        return 'ICT'
    return x

def add_missing_gvkeys(lc: pd.DataFrame):
        dict_of_gvkeys = {"Artner Co Ltd": 287055, "TDK Corp": 10275, "StemCell Institute Inc": 349316}
        mask = lc["gvkey"].isna() & lc["conml"].isin(dict_of_gvkeys)
        lc.loc[mask, "gvkey"] = lc.loc[mask, "conml"].map(dict_of_gvkeys)
        print(f">>>> add_missing_gvkeys: filled {mask.sum()} rows")
        return lc




def add_available_fyears(
    lc: pd.DataFrame,
    rfyear_col: str = "rfyear",
    gvkey_col: str = "gvkey",
) -> pd.DataFrame:
    """
    Adds two columns to `lc`:
      - available_fyears:   sorted list of unique rfyear values for that gvkey
      - n_available_fyears: count of unique rfyears for that gvkey
    """
    years_per_gvkey = (
        lc.groupby(gvkey_col)[rfyear_col]
          .apply(lambda s: sorted(int(y) for y in s.dropna().unique()))
          .rename("available_fyears")
    )

    agg = years_per_gvkey.to_frame()
    agg["n_available_fyears"] = agg["available_fyears"].apply(len)
    agg = agg.reset_index()

    lc = lc.drop(columns=["available_fyears", "n_available_fyears"], errors="ignore")
    return lc.merge(agg, on=gvkey_col, how="left")



