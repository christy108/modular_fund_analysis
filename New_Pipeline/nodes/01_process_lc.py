"""Load and clean the Local Content (LC) panel — data-ingestion + sample selection.

Node `process_lc`: reproduces Main.ipynb cells 4, 14, 15 verbatim, reusing
functions/data_functions/process_lc.py unchanged. This is the first of two nodes
that used to be one (``load_signal_lc``); the paired second node
(``derive_signals``) handles cell 16, 18, 21 — category aggregation, winsor
alpha-trim, and the ``signal_i`` ratio. Splitting the two makes each concern
independently auditable and lets signal-construction methodology be A/B'd
without touching data-loading logic.

Output is a lossless (pickle) bundle carrying the cleaned LC panel plus, when
gated by ``cfg.show_esg_coverage``, a raw-post-``process_lc`` snapshot used only
by the ``esg_coverage`` diagnostic. When the gate is off, that snapshot is None.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process

from New_Pipeline._common import cfg_schema, open_schema, store

CONTRACT = Contract(
    name="process_lc",
    intent="""Load the Golden LC panel and produce an analysis-ready firm-fiscal-year table:
apply the configured sample filters (min-fyears / suspicious gvkeys / min-initiatives),
map industries, and drop by industry / region as configured. Dataset version, filter
thresholds, industry level, and region are read from cfg. The signal columns
(sum_with_*, sum_activities, signal_i) are NOT computed here — they belong to the
paired ``derive_signals`` node.

Mandatory measures (enforced by schema / audits):
- one row per surviving gvkey-fiscal-year with GICS + Industry columns present
- rows only drop via the declared filters

Surfaces: (none — output is a lossless pickle bundle, not a tidy frame; a plain
``RowCountViz`` would always report 1 and add no information).""",
    input_schema={"cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[],
)


@process(tag="process_lc@v1", contract="process_lc", author="refactor")
def process_lc_v1(cfg):
    import json
    import os
    from pathlib import Path

    import pandas as pd

    from functions.data_functions.process_lc import (
        add_available_fyears,
        map_sectors,
        process_lc,
    )
    from New_Pipeline._common import normalise_gvkeys
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

    #This can later be toggled - it dosent always need to be loaded
    # lc_materiality = pd.read_excel("Matched_SASB_GOLDEN_long_matchings_vZERO_FirmYear.xlxs", sheet = )


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
            lc_suspicious["original_gvkey"] = normalise_gvkeys(lc_suspicious["original_gvkey"])
            lc["gvkey"] = normalise_gvkeys(lc["gvkey"])
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

    return pack_obj({"lc": lc, "lc_raw_for_coverage": lc_raw_for_coverage})


NODE = Node(
    name="process_lc",
    contract=CONTRACT,
    store=store,
    inputs=("cfg",),
    outputs=("out",),
)
