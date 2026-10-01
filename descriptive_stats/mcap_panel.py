"""Build the per-(year,month,gvkey,iid) last-market-cap panel per region, exactly as
process_global_universe sees it, and dump to parquet for analysis.

Replicates: get_*_universe (all_secstat file, year<=end_year, security_status=
all_firms_even_delisted -> no row dropped) -> process_*_universe (FX conversion when
convert_to_USD) -> process_global_universe (drop mktcap NA, currency_filter, last cap per
(month,year,gvkey,iid)).
"""
import os, sys, pickle
import polars as pl

os.chdir("/Users/cbruce1/Documents/GitHub/modular_fund_analysis")
sys.path.insert(0, os.getcwd())
OUT = sys.argv[1]

REGION = {
    "United_States": dict(path="data/usa_universe_all_secstat.csv", cap="mktcap",
                          ccy=["USD"], convert=False, has_ccy=False),
    "Europe":        dict(path="data/row_universe_all_secstat_new.csv", cap="mktcap_lcu",
                          ccy=["CHF","GBP","EUR","NOK","SEK","DKK"], convert=True, has_ccy=True),
    "Japan":         dict(path="data/japan_universe_all_secstat.csv", cap="mktcap_lcu",
                          ccy=["JPY"], convert=False, has_ccy=True),
}
END_YEAR = 2024

# ---- FX rates, exactly as get_processed_fx_rates -------------------------------- #
from functions.data_functions.get_data import get_processed_fx_rates
fx = pl.from_pandas(get_processed_fx_rates(END_YEAR)[["date", "curcdd", "rate"]]).with_columns(
    pl.col("date").cast(pl.Date), pl.col("rate").cast(pl.Float64))
print("fx rows", fx.height, "dates", fx["date"].min(), fx["date"].max())

for region, R in REGION.items():
    print("=" * 70, flush=True)
    print(region, R["path"], flush=True)
    cols = ["date", "gvkey", "iid", R["cap"]] + (["curcdd"] if R["has_ccy"] else [])
    lf = pl.scan_csv(R["path"], infer_schema_length=10000,
                     schema_overrides={"gvkey": pl.Float64, "iid": pl.Utf8,
                                       "curcdd": pl.Utf8, R["cap"]: pl.Float64}).select(cols)
    lf = lf.with_columns(pl.col("date").str.to_date("%Y-%m-%d"))
    if not R["has_ccy"]:
        lf = lf.with_columns(pl.lit("USD").alias("curcdd"))
    # year <= end_year (get_*_universe); no start-year filter exists in the load path
    lf = lf.with_columns(pl.col("date").dt.year().alias("year"),
                         pl.col("date").dt.month().alias("month"))
    lf = lf.filter(pl.col("year") <= END_YEAR)
    # currency_filter (process_global_universe)
    lf = lf.filter(pl.col("curcdd").is_in(R["ccy"]))
    # FX conversion (process_row_universe / process_japan_universe)
    if R["convert"]:
        lf = lf.join(fx.lazy(), on=["date", "curcdd"], how="left")
        lf = lf.with_columns((pl.col(R["cap"]) / pl.col("rate")).alias("mktcap"))
    else:
        lf = lf.with_columns(pl.col(R["cap"]).alias("mktcap"))
    # drop missing mktcap (process_global_universe)
    lf = lf.filter(pl.col("mktcap").is_not_null())
    # gvkey -> repo-standard 6-char zero-padded string
    lf = lf.with_columns(
        pl.col("gvkey").cast(pl.Int64).cast(pl.Utf8).str.zfill(6).alias("gvkey"))
    # last cap per (month, year, gvkey, iid): the value at the latest date in that month
    lf = (lf.sort(["month", "year", "gvkey", "iid", "date"])
            .group_by(["year", "month", "gvkey", "iid"])
            .agg(pl.col("mktcap").last().alias("last_mktcap"),
                 pl.col("date").last().alias("last_date"),
                 pl.col("curcdd").last().alias("curcdd")))
    df = lf.collect(engine="streaming")
    print(region, "listing-months", df.height, "years",
          df["year"].min(), df["year"].max(), "unique gvkeys", df["gvkey"].n_unique(), flush=True)
    df.write_parquet(f"{OUT}/panel_{region}.parquet")
print("done")
