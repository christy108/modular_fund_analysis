"""Load & clean the Local Content (LC) panel and derive behavioural signals.

Node `load_signal_lc`: Contract + Process + Node, read top-to-bottom.
Reproduces Main.ipynb cells 4, 14, 15, 16, 18, 21 verbatim, reusing
functions/data_functions/process_lc.py unchanged. Output is carried losslessly
(pickle) because the LC table is a wide, mixed-dtype plumbing frame.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process

from New_Pipeline._common import cfg_schema, open_schema, store

CONTRACT = Contract(
    name="load_signal_lc",
    intent="""Load the Golden LC panel and turn it into a firm-fiscal-year table carrying the
behavioural signals (advocacy/preparation/transformation) used for sorting: apply the sample
filters, industry mapping and the winsor alpha-trim, then set signal_i = sum_with_i / sum_activities.
Dataset version, filters and thresholds are read from cfg; the algorithm is left to the Process.

Mandatory measures (enforced by schema / audits):
- one row per surviving gvkey-fiscal-year with the behavioural signal columns present
- rows only drop via the declared filters

Surfaces: (none — output is a lossless pickle bundle, not a tidy frame; a plain
``RowCountViz`` would always report 1 and add no information).""",
    input_schema={"cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[],
)


@process(tag="load_signal_lc@v1", contract="load_signal_lc", author="refactor")
def load_signal_lc_v1(cfg):
    import json
    import os
    from pathlib import Path

    import pandas as pd

    from functions.data_functions.process_lc import (
        add_available_fyears,
        filter_sum_activities_by_fiscal_year_quantiles,
        map_sectors,
        process_lc,
    )
    from New_Pipeline.boundary import pack_obj

    C = json.loads(cfg["json"][0])

    # ---- cell 4: load Golden dataset ------------------------------------- #
    golden_location = Path(
        os.environ.get(
            "GOLDEN_LOCATION",
            Path.home() / "Documents" / "GitHub" / "data" / "Golden_Data",
        )
    )
    golden_files = {
        "v_2C": "LC_dataset_v_2C_20260512.csv",
        "v_2B3": "LC_dataset_v_2B3_20260511.csv",
        "v_2A": "LC_dataset_v_2A.csv",
        "v_2B1": "LC_dataset_v_2B1_20260409.csv",
    }
    lc = pd.read_csv(golden_location / golden_files[C["golden_data"]])

    # ---- cell 14: process_lc + 3-filter block + drop real estate --------- #
    lc = process_lc(lc, C["start_year"], C["end_year"])

    lc_raw_for_coverage = None
    if C["show_esg_coverage"]:
        lc_raw_for_coverage = lc.copy()

    if C["execute_3_filters"]:
        lc = add_available_fyears(lc)
        print(f"Before filtering companies with less than {C['min_available_fyears']} years of data: ", lc.shape)
        lc = lc[lc["n_available_fyears"] >= C["min_available_fyears"]]
        print(f"After filtering companies with less than {C['min_available_fyears']} years of data: ", lc.shape)

        if C["drop_suspicious_gvkeys"]:
            print("Shape before: ", lc.shape)
            lc_suspicious = pd.read_csv(golden_location / "lc_gvkey_suspicious.csv")
            print("Number of suspicious: ", lc_suspicious.shape[0])
            print(lc_suspicious["suspicious_flag"].value_counts())
            lc_suspicious["original_gvkey"] = lc_suspicious["original_gvkey"].astype(str).str.zfill(6)
            lc["gvkey"] = lc["gvkey"].astype(str).str.zfill(6)
            print("Number of suspicious that are NAN: ", lc_suspicious["suspicious_flag"].isna().sum())
            print("unique gvkeys: ", lc["gvkey"].nunique(), "Unique gvkeys in suspicious: ", lc_suspicious["original_gvkey"].nunique())
            lc = lc.merge(
                lc_suspicious[["original_gvkey", "suspicious_flag", "likely_reason_codes"]],
                left_on="gvkey", right_on="original_gvkey", how="left",
            )
            print(lc["suspicious_flag"].value_counts())
            print("Number of suspicious that are NAN: ", lc["suspicious_flag"].isna().sum())
            os.makedirs("./data/debug", exist_ok=True)
            lc.to_csv("./data/debug/lc_before_suspicious_filtered.csv")
            lc = lc[lc["suspicious_flag"] != True]  # noqa: E712 (matches notebook)
            print("Shape after filtering Truly Sus: ", lc.shape)

        print("Before filtering Annual Reports: ", lc.shape)
        lc = lc[~((lc["n_predicted_initiatives"] < C["min_initatives_annual_reports"]) & (lc["report_type"] == "Annual Report"))]
        print("After filtering Annual Reports: ", lc.shape)
        lc.to_csv("./data/debug/lc_after_all_filter.csv")

    if C["anlayse_fashion_only"]:
        lc = lc[lc["GICS_level_3"].isin(["Textiles, Apparel & Luxury Goods"])]
    if C["drop_real_estate"]:
        lc = lc[lc["GICS_level_1"] != "Real Estate"]

    # ---- cell 15: industry mapping + drops + region filters -------------- #
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
        if C["region_analysis"] == "United_States":
            lc = lc[lc["loc"] == "USA"]

    # ---- cell 16: category aggregation ----------------------------------- #
    categories_dict = C["categories_dict"]  # {category_col: group_int}
    for key, value in categories_dict.items():
        if f"sum_with_{value}" in lc.columns:
            lc[f"sum_with_{value}"] += lc[key]
        else:
            lc[f"sum_with_{value}"] = lc[key].values

    if C["signal_denominator"] == "Sum_All_Signals":
        lc["sum_activities"] = lc.loc[:, list(categories_dict.keys())].sum(axis=1)
    elif C["signal_denominator"] == "Sum_All_Initiatives":
        lc["sum_activities"] = lc["n_predicted_initiatives"]

    print(lc["sum_activities"].describe())

    # ---- cell 18: winsor alpha-trim -------------------------------------- #
    if C["use_alpha_bound"]:
        lc = filter_sum_activities_by_fiscal_year_quantiles(
            lc, lower_exclude=(C["alpha_bound"] / 2), upper_exclude=(C["alpha_bound"] / 2)
        )
    else:
        lower_exclude = 0.2 * 2
        upper_exclude = 0.05 * 2
        lc = filter_sum_activities_by_fiscal_year_quantiles(
            lc, lower_exclude=(lower_exclude / 2), upper_exclude=(upper_exclude / 2)
        )

    print(lc["sum_activities"].describe())

    # ---- cell 21: signal_i ----------------------------------------------- #
    max_category = max(int(v) for v in categories_dict.values())
    for i in range(max_category + 1):
        lc[f"signal_{i}"] = lc[f"sum_with_{i}"] / lc["sum_activities"]

    return pack_obj({"lc": lc, "lc_raw_for_coverage": lc_raw_for_coverage})


NODE = Node(
    name="load_signal_lc",
    contract=CONTRACT,
    store=store,
    inputs=("cfg",),
    outputs=("out",),
)
