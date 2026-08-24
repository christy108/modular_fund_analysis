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
from New_Pipeline.dashboard_viz import BundleDualAxisViz, BundleTableViz, config_table


# ---- Dashboard extractors (bundle -> widget payloads; no computation happens here) --- #

def _sample_descriptives(bundle):
    """One row: unique gvkeys, unique gvkey-year observations, and total initiatives in
    the sample that survives this node (after all filters, and the materiality merge if
    that flag is on)."""
    return bundle.get("sample_descriptives")


def _firms_and_initiatives(bundle):
    """Per-fiscal-year unique companies / firm-year observations / total initiatives for
    the sample that survives this node."""
    return bundle.get("firms_and_initiatives")


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

Surfaces: the run's full configuration as a parameter/value/description table
(``BundleTableViz``); descriptives of the sample that survives this node — unique gvkeys, unique
gvkey-year observations, total initiatives (``BundleTableViz``); and unique companies
against total initiatives over time on separate y-axes (``BundleDualAxisViz``).""",
    input_schema={"cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[
        BundleTableViz(config_table, title="Run configuration", n=200,
                       key="table:config",
                       description="Every cfg key this run received: parameter, value, and "
                                   "what it does. Baseline knobs first (notebook cell 2), then "
                                   "the values derived from them (cells 8 and 11). Keys marked "
                                   "'provenance only' are hashed and name output files but are "
                                   "not read by any node."),
        BundleTableViz(_sample_descriptives, title="Final sample descriptives",
                       key="table:sample_descriptives"),
        BundleDualAxisViz(
            _firms_and_initiatives,
            title="Unique companies and total initiatives over time",
            x_col="rfyear", left_col="unique_companies", right_col="total_initiatives",
            left_label="Unique companies", right_label="Total initiatives",
            x_label="Fiscal year",
            key="dual_axis:firms_and_initiatives",
        ),
    ],
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
    from New_Pipeline._common import count_firms, funnel_frame, normalise_gvkeys
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
        "v_2A1": "LC_dataset_v2A1_20260813.parquet",
        "v_2A": "LC_dataset_v2A_20260812.parquet",
        "v_2C": "LC_dataset_v_2C_20260512.csv",
        "v_2B3": "LC_dataset_v_2B3_20260511.csv",
        "v_2B1": "LC_dataset_v_2B1_20260409.csv",
    }

    try:
        lc = pd.read_csv(golden_location / golden_files[C["golden_data"]])
    except:
        lc = pd.read_parquet(golden_location / golden_files[C["golden_data"]])

    # ---- audit: sample filter funnel, LC side (stages 1-5) --------------------------- #
    # Each row is "distinct firms still standing after this filter". Stages 1-5 run INSIDE
    # the frozen functions/data_functions/process_lc.py::process_lc, which returns only its
    # final frame, so they are replayed here on a copy of the seven columns they read.
    #
    # The copy is taken BEFORE the call because process_lc mutates its argument in place
    # (process_lc.py:41, `dropna(..., inplace=True)`) -- afterwards the "raw" frame is
    # already partly filtered and stage 0 is unrecoverable. The replay is cross-checked
    # against the real returned frame immediately after the call.
    #
    # add_missing_gvkeys (process_lc.py:156) and add_srec_stakeholder_columns (:24) are
    # deliberately not stages: the first only fills values -- and is in fact dead, since
    # the :41 dropna already removed every NaN gvkey it looks for -- and the second only
    # joins columns.
    funnel_rows = [(
        "Raw GOLDEN data (all regions)", "LC",
        f"01_process_lc / {golden_files[C['golden_data']]}",
        count_firms(lc["gvkey"]),
    )]

    _key_cols = ["gvkey", "rfyear", "loc", "MacroRegion",
                 "GICS_level_1", "GICS_level_2", "GICS_level_3"]
    _r = lc[_key_cols].copy()

    _r = _r.dropna(subset=["gvkey"])                                  # process_lc.py:41
    _r["gvkey"] = _r["gvkey"].astype(int).astype(str)                 # process_lc.py:42
    _r["rfyear"] = _r["rfyear"].astype("Int64")                       # process_lc.py:43
    funnel_rows.append(("Drop rows missing gvkey", "LC",
                        "process_lc.py:41 / process_lc", count_firms(_r["gvkey"])))

    _r = _r.dropna(subset=_key_cols)                                  # process_lc.py:48
    funnel_rows.append(("Drop rows missing key fields (rfyear, loc, MacroRegion, GICS 1/2/3)",
                        "LC", "process_lc.py:48 / process_lc", count_firms(_r["gvkey"])))

    _regions = ["Asia-Pacific", "Europe", "United States and Canada"]
    _r = _r[_r["MacroRegion"].isin(_regions)]                         # process_lc.py:51-52
    funnel_rows.append((f"MacroRegion in {_regions}", "LC",
                        "process_lc.py:51 / process_lc", count_firms(_r["gvkey"])))

    _r = _r[_r["rfyear"] >= C["start_year"]]                          # process_lc.py:59
    funnel_rows.append((f"rfyear >= start_year ({C['start_year']})", "LC",
                        "process_lc.py:59 / process_lc", count_firms(_r["gvkey"])))

    _r = _r[_r["rfyear"] <= C["end_year"]]                            # process_lc.py:60
    funnel_rows.append((f"rfyear <= end_year ({C['end_year']})", "LC",
                        "process_lc.py:60 / process_lc", count_firms(_r["gvkey"])))
    _replayed = count_firms(_r["gvkey"])
    del _r

    # ---- cell 14: process_lc + 3-filter block + drop real estate --------- #
    lc = process_lc(lc, C["start_year"], C["end_year"])

    # Cross-check the stages-1-5 replay against what the frozen function actually returned.
    # Reported in the funnel audit's summary rather than raised: like node 10's
    # `cross_check_all_match`, this is a regression canary (a pandas upgrade changing dropna
    # or comparison semantics), not a reconciliation the run should depend on.
    _replay_ok = bool(_replayed == count_firms(lc["gvkey"]))
    if not _replay_ok:
        print(f"[process_lc] funnel replay MISMATCH: replayed {_replayed} firms after "
              f"process_lc, real frame has {count_firms(lc['gvkey'])}")

    # Appends one funnel row per filter below, measured on `lc` as it stands at that point.
    # `active=False` records the stage with a null count -- meaning "this filter did not run
    # under this config", which the audit renders as an em dash and which is NOT zero.
    def _stage(label, where, active=True):
        funnel_rows.append((label, "LC", where, count_firms(lc["gvkey"]) if active else None))

    lc_raw_for_coverage = None
    if C["show_esg_coverage"]:
        lc_raw_for_coverage = lc.copy()

    if C["execute_3_filters"]:
        lc = add_available_fyears(lc)
        print(f"Before filtering companies with less than {C['min_available_fyears']} years of data: ", lc.shape)
        lc = lc[lc["n_available_fyears"] >= C["min_available_fyears"]]
        print(f"After filtering companies with less than {C['min_available_fyears']} years of data: ", lc.shape)
        _stage(f">= min_available_fyears ({C['min_available_fyears']}) fiscal years",
               "01_process_lc.py:120 / execute_3_filters")

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
        _stage("Drop suspicious gvkeys", "01_process_lc.py:140 / drop_suspicious_gvkeys",
               active=C["drop_suspicious_gvkeys"])

        print("Before filtering Annual Reports: ", lc.shape)
        
        print(golden_files[C["golden_data"]] )
        
        if C["golden_data"] == "v_2A" or C["golden_data"] == "v_2A1":
                    lc = lc[~((lc["n_predicted_initiatives"] < C["min_initatives_annual_reports"]) & (lc["report_type_gpt2"] == "Annual Report"))]

        else:
            lc = lc[~((lc["n_predicted_initiatives"] < C["min_initatives_annual_reports"]) & (lc["report_type"] == "Annual Report"))]

        print("After filtering Annual Reports: ", lc.shape)
        _stage(f"Drop Annual Reports with < min_initatives_annual_reports "
               f"({C['min_initatives_annual_reports']}) initiatives",
               "01_process_lc.py:148 / execute_3_filters")
        lc.to_csv("./data/debug/lc_after_all_filter.csv")
    else:
        # The three stages of the block still get rows, all null: the funnel should show
        # WHICH filters this config skipped, not silently omit them.
        _stage(">= min_available_fyears fiscal years",
               "01_process_lc.py:120 / execute_3_filters", active=False)
        _stage("Drop suspicious gvkeys",
               "01_process_lc.py:140 / drop_suspicious_gvkeys", active=False)
        _stage("Drop Annual Reports with < min_initatives_annual_reports initiatives",
               "01_process_lc.py:148 / execute_3_filters", active=False)

    if C["anlayse_fashion_only"]:
        lc = lc[lc["GICS_level_3"].isin(["Textiles, Apparel & Luxury Goods"])]
    _stage("Keep fashion only (GICS_level_3 = Textiles, Apparel & Luxury Goods)",
           "01_process_lc.py:157 / anlayse_fashion_only", active=C["anlayse_fashion_only"])
    if C["drop_real_estate"]:
        lc = lc[lc["GICS_level_1"] != "Real Estate"]
    _stage("Drop Real Estate", "01_process_lc.py:159 / drop_real_estate",
           active=C["drop_real_estate"])

    # ---- cell 15: industry mapping + drops + region filters -------------- #
    if C["industry_level"] == 0:
        lc["Industry"] = lc["GICS_level_1"].apply(map_sectors)
    elif C["industry_level"] == 1:
        lc["Industry"] = lc["GICS_level_1"]
    elif C["industry_level"] == 2:
        lc["Industry"] = lc["GICS_level_2"]

    if C["drop_fin"]:
        lc = lc[lc["Industry"] != "Financial"]
    _stage(f"Industry map (level {C['industry_level']}) -> drop Financial",
           "01_process_lc.py:170 / drop_fin", active=C["drop_fin"])
    if C["drop_utilities"]:
        lc = lc[lc["Industry"] != "Utilities"]
    _stage("Industry map -> drop Utilities", "01_process_lc.py:172 / drop_utilities",
           active=C["drop_utilities"])
    if C["drop_health_care"]:
        lc = lc[lc["Industry"] != "Health Care"]
    _stage("Industry map -> drop Health Care", "01_process_lc.py:174 / drop_health_care",
           active=C["drop_health_care"])

    _region_filters_on = C["execute_region_filters"] is True
    _usa_filter_on = _region_filters_on and C["region_analysis"] == "United_States"
    if _region_filters_on:
        lc = lc[lc["MacroRegion"].isin(C["region_filter"])]
        _stage(f"MacroRegion in region_filter ({list(C['region_filter'])})",
               "01_process_lc.py:177 / execute_region_filters")
        if _usa_filter_on:
            lc = lc[lc["loc"] == "USA"]
    else:
        _stage("MacroRegion in region_filter",
               "01_process_lc.py:177 / execute_region_filters", active=False)
    _stage('loc == "USA"', "01_process_lc.py:179 / region_analysis",
           active=_usa_filter_on)

    # ---- optional: inner-merge SASB materiality counts onto lc ----------- #
    # Gated (default off): the inner join filters lc to firm-years present in the
    # materiality workbook, so it changes the sample and must stay off for base_none
    # parity. Runs last, once (gvkey, rfyear) are final.
    if C["add_materiality"]:
        from functions.data_functions.process_materiality import add_materiality_to_lc

        print("Before Adding Materiality", lc.shape)
        lc = add_materiality_to_lc(lc, C["materiality_version"])
        print("After Adding Materiality", lc.shape)
    _stage(f"SASB materiality inner join (version {C['materiality_version']})",
           "01_process_lc.py:189 / add_materiality", active=C["add_materiality"])

    # ---- audit: descriptives of the sample that survives this node ------------------ #
    # No universe-intersection step exists here (that's node 06) — lc itself is the
    # surviving sample. Dedupe on (gvkey, rfyear) defensively: multiple report_type rows
    # can share a firm-fiscal-year.
    lc_dedup = lc.drop_duplicates(subset=["gvkey", "rfyear"])
    if len(lc_dedup) != len(lc):
        print(f"[process_lc] WARNING: lc had {len(lc) - len(lc_dedup)} duplicate (gvkey, rfyear) rows")

    sample_descriptives = pd.DataFrame([{
        "unique_gvkeys": lc_dedup["gvkey"].nunique(),
        "gvkey_year_obs": len(lc_dedup),
        "total_initiatives": int(lc_dedup["n_predicted_initiatives"].sum()),
    }])
    # Second self-check: the last LC funnel stage must agree with the endpoint descriptive
    # computed independently just above (string-gvkey nunique on a deduped frame, versus the
    # funnel's numeric-gvkey count on the live frame). Both verdicts travel together as one
    # dict, forwarded untouched by derive_signals and prepare_panel, because the audit node
    # that reports them sees neither of the two numbers being compared here.
    _known = [r[3] for r in funnel_rows if r[3] is not None]
    funnel_checks = {
        "process_lc_replay_ok": _replay_ok,
        "lc_endpoint_ok": bool(
            _known and _known[-1] == int(sample_descriptives.at[0, "unique_gvkeys"])
        ),
    }
    if not funnel_checks["lc_endpoint_ok"]:
        print(f"[process_lc] funnel endpoint MISMATCH: last LC stage "
              f"{_known[-1] if _known else None} vs sample_descriptives "
              f"{int(sample_descriptives.at[0, 'unique_gvkeys'])}")

    firms_and_initiatives = (
        lc_dedup.groupby("rfyear")
        .agg(
            unique_companies=("gvkey", "nunique"),
            firm_year_observations=("gvkey", "size"),
            total_initiatives=("n_predicted_initiatives", "sum"),
        )
        .sort_index()
        .reset_index()
    )

    return pack_obj({
        "lc": lc,
        # The run's config, verbatim, for the "Run configuration" dashboard table.
        # Audits compute over a node's OUTPUT only (Contract.compute_audits), so the
        # cfg has to ride out of a node to be renderable at all; this is the first node
        # in topological order, which puts the table at the top of the page. Audit-only
        # -- no downstream node reads this key.
        "cfg_json": cfg["json"][0],
        "lc_raw_for_coverage": lc_raw_for_coverage,
        "sample_descriptives": sample_descriptives,
        "firms_and_initiatives": firms_and_initiatives,
        "funnel": funnel_frame(funnel_rows),
        "funnel_checks": funnel_checks,
    })


NODE = Node(
    name="process_lc",
    contract=CONTRACT,
    store=store,
    inputs=("cfg",),
    outputs=("out",),
)
