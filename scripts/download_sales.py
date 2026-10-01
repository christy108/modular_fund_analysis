"""Download annual Compustat `sale` for the USA / RoW / Japan universes -> one CSV.

    .venv/bin/python -m scripts.download_sales
    .venv/bin/python -m scripts.download_sales --start 2010 --end 2026 --out data/sales_all_regions.csv

Standalone, run by hand. Writes `data/sales_all_regions.csv` and touches nothing else.

**gvkey inclusion mirrors the universe downloads exactly.** Each region's gvkey set is
the DISTINCT gvkeys from the same secd/g_secd query `get_*_universe` runs -- same
primary-issue join (priusa / prirow), same tpci / prccd / cshtrd / exchg / currency
filters. That is done as a CTE rather than a copied gvkey list so the two cannot drift.

**Inactive firms are included.** Like the universe queries, nothing filters `secstat`
here -- delisted / acquired / bankrupt names keep their fundamentals, so a sample built
on this is not survivorship-biased. (The universe getters apply `security_status` in
pandas AFTER loading, not in SQL; same idea.)

**`sale > 0` is enforced in SQL**, not merely `IS NOT NULL`. This is a correctness
requirement, not tidying, because the intended use is a RATIO (`initiatives / sale`):
  - `sale == 0` (9,113 rows, 2,112 firms -- pre-revenue biotech / mining / SPACs, 750 of
    them zero in every year) yields `inf`, which survives the quantile sort and fills the
    TOP bucket with shell companies.
  - `sale < 0` (123 rows -- trading losses at financials, restatement reversals) flips
    the ratio's sign, sending high-initiative firms into the BOTTOM bucket.
Both corrupt results silently rather than raising, so they are excluded at the source.

Output columns: region, gvkey, fyear, datadate, curcd, sale, fx_rate, sale_usd
  - `sale` is in MILLIONS of `curcd` -- Compustat funda's native unit, unscaled, kept
    as-is so the figure stays auditable against Compustat.
  - `curcd` is the firm's REPORTING currency (not necessarily the listing's trading
    currency, which is `curcdd` on the universe side).
  - `sale_usd` is millions of USD, converted at the ANNUAL MEAN rate for that fiscal
    year. Annual mean, not year-end spot, because revenue is a FLOW earned across the
    year -- market cap is a stock and correctly uses daily spot elsewhere.
  - one row per (region, gvkey, fyear).

`sale_usd` is NaN, never silently wrong, when no rate exists: FRB H.10 covers only
CHF/DKK/EUR/GBP/JPY/NOK/SEK (+ USD = 1) and the bundled file ends 2024-12-31, so later
fiscal years have no rate. Both gaps are reported at the end of the run.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from New_Pipeline._common import normalise_gvkeys

OUT_DEFAULT = Path("data/sales_all_regions.csv")

# The funda filters that pin ONE record per firm-year -- funda carries several rows per
# firm-year across indfmt/datafmt/popsrc/consol and without these the join fans out.
#
# THE CODES DIFFER BETWEEN THE NORTH-AMERICAN AND GLOBAL FILES. Applying the NA codes to
# g_funda matches zero rows (verified: g_funda is 100% datafmt='HIST_STD', popsrc='I'),
# which is silent -- an empty region, not an error. Hence one clause per file.
_STD_NA = "f.indfmt='INDL' AND f.datafmt='STD'      AND f.popsrc='D' AND f.consol='C'"
_STD_GL = "f.indfmt='INDL' AND f.datafmt='HIST_STD' AND f.popsrc='I' AND f.consol='C'"

# Per region: (funda table, standard-record filter, the gvkey-selecting CTE copied from
# get_*_universe). The CTE WHERE clauses are the SAME ones in
# functions/data_functions/get_data.py -- if those ever change, change these with them.
QUERIES = {
    "usa": ("comp_na_daily_all.funda", _STD_NA, """
        WITH listings AS (
            SELECT gvkey, priusa FROM comp.company WHERE priusa IS NOT NULL
        ),
        gvkeys AS (
            SELECT DISTINCT s.gvkey
            FROM comp.secd AS s
            JOIN listings l ON (s.gvkey = l.gvkey AND s.iid = l.priusa)
            WHERE s.datadate BETWEEN '01/01/{start}' AND '12/31/{end}'
              AND s.tpci = '0' AND s.prccd > 0 AND s.cshtrd > 0
              AND s.exchg IN (11, 12, 14)
        )
    """),
    "row": ("comp_global_daily.g_funda", _STD_GL, """
        WITH listings AS (
            SELECT gvkey, prirow FROM comp.g_company WHERE prirow IS NOT NULL
        ),
        gvkeys AS (
            SELECT DISTINCT s.gvkey
            FROM comp.g_secd AS s
            JOIN listings l ON (s.gvkey = l.gvkey AND s.iid = l.prirow)
            WHERE s.datadate BETWEEN '01/01/{start}' AND '12/31/{end}'
              AND s.tpci = '0' AND s.prccd > 0 AND s.cshtrd > 0
              AND s.exchg IN (273, 132, 294, 278, 221, 261, 286, 167, 154, 171, 107,
                              172, 209, 198, 271, 104, 192, 122, 193, 201, 151, 194)
              AND s.curcdd IN ('CHF', 'GBP', 'EUR')
        )
    """),
    "japan": ("comp_global_daily.g_funda", _STD_GL, """
        WITH listings AS (
            SELECT gvkey, prirow FROM comp.g_company WHERE prirow IS NOT NULL
        ),
        gvkeys AS (
            SELECT DISTINCT s.gvkey
            FROM comp.g_secd AS s
            JOIN listings l ON (s.gvkey = l.gvkey AND s.iid = l.prirow)
            WHERE s.datadate BETWEEN '01/01/{start}' AND '12/31/{end}'
              AND s.tpci = '0' AND s.prccd > 0 AND s.cshtrd > 0
              AND s.exchg = 264 AND s.curcdd = 'JPY'
        )
    """),
}


def fetch(conn, region: str, start: int, end: int) -> pd.DataFrame:
    table, std, cte = QUERIES[region]
    sql = cte.format(start=start, end=end) + f"""
        SELECT f.gvkey, f.fyear, f.datadate, f.curcd, f.sale
        FROM {table} AS f
        JOIN gvkeys g ON f.gvkey = g.gvkey
        WHERE f.fyear BETWEEN {start} AND {end}
          AND f.sale > 0
          AND {std}
    """
    df = pd.DataFrame(conn.raw_sql(sql, date_cols=["datadate"]))
    if df.empty:
        return df

    # Normalise gvkey to the repo-standard zero-padded 6-char string BEFORE deduping.
    # WRDS returns it in mixed forms ('1004', '001004', 1004.0 depending on the table and
    # driver), and deduping on the raw value would treat two spellings of one firm as two
    # firms -- exactly the split-key trap documented on _common.count_firms. Padding
    # first also makes the file join straight onto `lc`, which zfills the same way in
    # intersect_gvkeys_and_filter.
    df["gvkey"] = normalise_gvkeys(pd.to_numeric(df["gvkey"], errors="coerce")
                                     .astype("Int64").astype(str))

    # Defensive: the _STD filters should already make this unique. A restated/re-filed
    # year is the residual case; keep the latest datadate for it.
    before = len(df)
    df = df.sort_values("datadate").drop_duplicates(["gvkey", "fyear"], keep="last")
    if len(df) != before:
        print(f"    deduped {before - len(df)} duplicate (gvkey, fyear) rows")

    df.insert(0, "region", region)
    return df.reset_index(drop=True)


def add_sale_usd(df: pd.DataFrame, end_year: int) -> pd.DataFrame:
    """Add `fx_rate` and `sale_usd` (millions USD), averaged over each firm's OWN
    fiscal year: the 12 months ending on its `datadate`.

    Average, not year-end spot, because revenue is a FLOW earned across the year --
    which is also what IAS 21 / ASC 830 require for income-statement items (balance-sheet
    items take the closing rate, which is why the universe path correctly uses daily spot
    for market cap; the two are different conversions, not duplicated work).

    The window follows `datadate` rather than the calendar year because fiscal years
    frequently are not calendar years -- 87.7% of the Japanese firms here close outside
    December, 65.4% in March. Averaging Jan-Dec for a March closer would price a year of
    revenue over a window shifted by a quarter, and JPY moved ~115 -> ~150 across 2022,
    so that is a real error rather than a rounding one.

    NOTE this makes the rate FIRM-specific, so unlike a single calendar-year rate it does
    NOT cancel out of the (rfyear, curcdd, Industry) z-score downstream. That is correct:
    two firms whose fiscal years cover different months genuinely earned their revenue at
    different exchange rates.

    Reuses the pipeline's own FX table, so there is one FX source in the repo. Its `rate`
    is quoted foreign-per-USD (EUR/GBP are inverted inside `get_processed_fx_rates`),
    hence `sale / rate`. Anything without a rate stays NaN rather than silently passing
    a local-currency figure through as if it were USD.
    """
    import warnings

    import numpy as np

    from functions.data_functions.get_data import get_processed_fx_rates

    with warnings.catch_warnings():          # frozen fn trips pandas 2.2 chained-assign
        warnings.simplefilter("ignore", FutureWarning)
        fx = get_processed_fx_rates(end_year)

    out = df.copy()
    out["datadate"] = pd.to_datetime(out["datadate"], errors="coerce")

    # Mean daily rate over (datadate - 12 months, datadate], per currency.
    # Done as a cumulative-sum lookup rather than a per-row filter: 183k rows x 29k daily
    # quotes would be ~5 billion comparisons, whereas two searchsorted calls per currency
    # are effectively instant and give exactly the same window mean.
    out["fx_rate"] = np.nan
    for ccy, g in fx.dropna(subset=["rate"]).groupby("curcdd"):
        rows = out.index[out["curcd"] == ccy]
        if len(rows) == 0:
            continue
        g = g.sort_values("date")
        dates = g["date"].to_numpy()
        csum = np.concatenate([[0.0], np.cumsum(g["rate"].to_numpy())])

        end = out.loc[rows, "datadate"].to_numpy()
        start = (out.loc[rows, "datadate"] - pd.DateOffset(months=12)).to_numpy()
        i0 = np.searchsorted(dates, start, side="right")
        i1 = np.searchsorted(dates, end, side="right")
        n = i1 - i0
        # n == 0 means the window falls entirely outside the FX file -> leave NaN.
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = np.where(n > 0, (csum[i1] - csum[i0]) / np.where(n > 0, n, 1), np.nan)
        out.loc[rows, "fx_rate"] = mean

    # USD needs no rate and FRB does not quote one against itself.
    out.loc[out["curcd"] == "USD", "fx_rate"] = 1.0
    with warnings.catch_warnings():
        # pandas 2.2 chained-assignment FutureWarning is a known false positive on this
        # pattern in this repo -- see the note in New_Pipeline/_common.py.
        warnings.simplefilter("ignore", FutureWarning)
        out["sale_usd"] = out["sale"] / out["fx_rate"]

    gap = out[out["sale_usd"].isna()]
    if len(gap):
        by_ccy = gap["curcd"].value_counts()
        unconvertible = sorted(by_ccy.index)
        yrs = sorted(gap["fyear"].dropna().astype(int).unique())
        print(f"\n  {len(gap):,} of {len(out):,} rows ({len(gap)/len(out):.1%}) have no "
              f"sale_usd:")
        print(f"    currencies : {dict(by_ccy.head(8))}")
        print(f"    fyears     : {yrs[:3]}{' ... ' if len(yrs) > 6 else ' '}{yrs[-3:]}")
        print(f"    (FRB H.10 covers CHF/DKK/EUR/GBP/JPY/NOK/SEK and ends 2024 -- "
              f"other currencies and fyear > 2024 cannot be converted)")
    return out


def main(argv: list[str]) -> None:
    def opt(flag, default):
        return argv[argv.index(flag) + 1] if flag in argv else default

    start, end = int(opt("--start", 2010)), int(opt("--end", 2026))
    out = Path(opt("--out", OUT_DEFAULT))

    import wrds
    conn = wrds.Connection(wrds_username="cbruce1")

    frames = []
    for region in QUERIES:
        print(f"=== {region}", flush=True)
        df = fetch(conn, region, start, end)
        if df.empty:
            print("    !! nothing returned")
            continue
        print(f"    {len(df):,} firm-years | {df['gvkey'].nunique():,} firms "
              f"| fyear {int(df.fyear.min())}-{int(df.fyear.max())} "
              f"| curcd {df['curcd'].value_counts().head(4).to_dict()}")
        frames.append(df)

    if not frames:
        raise SystemExit("no data returned for any region")

    allsales = pd.concat(frames, ignore_index=True)
    allsales = add_sale_usd(allsales, end)
    out.parent.mkdir(parents=True, exist_ok=True)
    allsales.to_csv(out, index=False)

    print(f"\n{len(allsales):,} rows -> {out}")
    print(allsales.groupby("region").agg(rows=("sale", "size"), firms=("gvkey", "nunique"),
                                         median_sale=("sale", "median"),
                                         median_sale_usd=("sale_usd", "median")).to_string())
    # A gvkey can legitimately appear in two regions (dual-listed); flag it so a later
    # merge on gvkey alone is a conscious choice rather than a surprise.
    dup = allsales.duplicated(["gvkey", "fyear"]).sum()
    if dup:
        print(f"\nNOTE {dup:,} (gvkey, fyear) pairs appear in more than one region "
              f"(dual-listed). Deduplicate before merging on gvkey alone.")


if __name__ == "__main__":
    main(sys.argv[1:])
