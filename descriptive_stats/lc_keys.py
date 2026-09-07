"""Extract the LC gvkey set per region, exactly as New_Pipeline/nodes/01_process_lc.py does."""
import os, sys, json, pickle
from pathlib import Path
import pandas as pd

os.chdir("/Users/cbruce1/Documents/GitHub/modular_fund_analysis")
sys.path.insert(0, os.getcwd())

from New_Pipeline.experiments import build_cfg
from New_Pipeline._common import normalise_gvkeys
from functions.data_functions.process_lc import process_lc, add_available_fyears
from functions.data_functions.process_lc import map_sectors

golden_location = Path(os.environ.get(
    "GOLDEN_DATA_DIR", Path.home() / "Documents" / "GitHub" / "data" / "Golden_Data"))
golden_files = {"v_2A1": "LC_dataset_v2A1_20260813.parquet"}

_locs_eu = ['AUT','BEL','CHE','DEU','DNK','ESP','FIN','FRA','GBR','GRC','IRL','ITA','NLD','NOR','PRT','SWE']

out = {}
for region in ["United_States", "Europe", "Japan"]:
    C = build_cfg(region_analysis=region)
    print("=" * 70)
    print(region, "start", C["start_year"], "end", C["end_year"],
          "ccy", C["currency_filter"], "region_filter", C["region_filter"],
          "convert_to_USD", C["convert_to_USD"],
          "mcap", C["mktcap_covered_if_filter_by_cum_market_cap"],
          "method", C["market_cap_filter"], "secstat", C["security_status"])
    f = golden_location / golden_files[C["golden_data"]]
    try:
        lc = pd.read_csv(f)
    except Exception:
        lc = pd.read_parquet(f)

    lc = process_lc(lc, C["start_year"], C["end_year"])

    mode = C["execute_3_filters"]
    if mode != "none":
        if mode == "all":
            lc = add_available_fyears(lc)
            lc = lc[lc["n_available_fyears"] >= C["min_available_rfyears_if_execute_3_filters_true"]]
        if C["drop_suspicious_gvkeys"]:
            sus = pd.read_csv(golden_location / "lc_gvkey_suspicious.csv")
            sus["original_gvkey"] = normalise_gvkeys(sus["original_gvkey"])
            lc["gvkey"] = normalise_gvkeys(lc["gvkey"])
            lc = lc.merge(sus[["original_gvkey", "suspicious_flag", "likely_reason_codes"]],
                          left_on="gvkey", right_on="original_gvkey", how="left")
            lc = lc[lc["suspicious_flag"] != True]  # noqa: E712
        if mode == "all":
            lc = lc[~((lc["n_predicted_initiatives"] < C["min_initatives_annual_reports_if_execute_3_filters_true"])
                      & (lc["report_type_gpt2"] == "Annual Report"))]

    if C["anlayse_fashion_only"]:
        lc = lc[lc["GICS_level_3"].isin(["Textiles, Apparel & Luxury Goods"])]
    if C["drop_real_estate"]:
        lc = lc[lc["GICS_level_1"] != "Real Estate"]

    if C["industry_level"] == 0:
        lc["Industry"] = lc["GICS_level_1"].apply(map_sectors)
    elif C["industry_level"] == 1:
        lc["Industry"] = lc["GICS_level_1"]
    elif C["industry_level"] == 2:
        lc["Industry"] = lc["GICS_level_2"]
    if C["drop_fin"]:
        lc = lc[lc["Industry"] != "Financial"]
    if C["drop_utilities"]:
        lc = lc[lc["Industry"] != "Utilities"]
    if C["drop_health_care"]:
        lc = lc[lc["Industry"] != "Health Care"]

    if C["execute_region_filters"] is True:
        lc = lc[lc["MacroRegion"].isin(C["region_filter"])]
        if region == "United_States":
            lc = lc[lc["loc"] == "USA"]
        if region == "Europe":
            lc = lc[lc["loc"].isin(_locs_eu)]

    if C["add_materiality"]:
        from functions.data_functions.process_materiality import add_materiality_to_lc
        lc = add_materiality_to_lc(lc, C["materiality_version"], C["golden_data"])

    lc["gvkey"] = normalise_gvkeys(lc["gvkey"])
    keys = set(lc["gvkey"].unique())
    pairs = lc[["gvkey", "rfyear"]].dropna().drop_duplicates()
    pairs["rfyear"] = pairs["rfyear"].astype(int)
    print(f"{region}: lc rows {len(lc)}, unique gvkeys {len(keys)}, rfyear "
          f"{lc['rfyear'].min()}-{lc['rfyear'].max()}")
    out[region] = {"gvkeys": keys, "pairs": pairs, "cfg": {k: C[k] for k in
        ["start_year","end_year","currency_filter","region_filter","convert_to_USD",
         "mktcap_covered_if_filter_by_cum_market_cap","market_cap_filter","security_status",
         "add_materiality","japan_year_adjustment_split_month_for_two_or_one","esg_choice"]}}

with open(sys.argv[1], "wb") as fh:
    pickle.dump(out, fh)
print("saved", sys.argv[1])
