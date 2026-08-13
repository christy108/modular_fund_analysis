"""Config derivation + Experiment specs.

`build_cfg` reproduces the notebook's configuration cells EXACTLY:
  - cell 2  : scalar knobs + region if/elif block + the esg_choice end_year override
  - cell 8  : signal-design (action_characterization -> categories_dict, lc_signals)
  - cell 11 : hml_directions / universe_signals / analysis_selection

Config is *data* in this framework (a Process only receives its input frames, never
exp.config), so every derived value is packed into a one-row `cfg` frame whose ``json``
column carries the whole dict. Deriving it here — in one place, identical to the
notebook — keeps the Processes clean and parity-safe.
"""

from __future__ import annotations

import json

import polars as pl

_ESG_TAG = {
    "none": "esg_none@v1",
    "refinitiv": "esg_refinitiv@v1",
    "msci": "esg_msci@v1",
    "s&p": "esg_snp@v1",
}


# --------------------------------------------------------------------------- #
# Config derivation (mirrors Main.ipynb cells 2, 8, 11)
# --------------------------------------------------------------------------- #
def build_cfg(**overrides) -> dict:
    """Return the fully-derived config dict for a run.

    Pass only the knobs that differ from the notebook baseline as ``overrides``
    (e.g. ``build_cfg(esg_choice="msci")``); everything else matches cell 2 defaults.
    """
    # ---- cell 2: baseline scalar defaults --------------------------------- #
    c: dict = dict(
        golden_data="v_2C",
        region_analysis="United_States",
        fama_factors_currency="JPY",
        RF_JAPAN_PATH="./data/FAMA/Rf_Japan_Monthly.xlsx",
        action_characterization="original_matteo",
        start_year=2015,
        end_year=2024,
        no_simple_quantiles=7,
        ff_factors_number=3,
        esg_choice="none",
        esg_full_universe=False,
        show_esg_corr_matricies=False,
        esg_corr_method="pearson",
        esg_min_group_size=5,
        drop_real_estate_Full_ESG=True,
        drop_utilities_Full_ESG=True,
        download_gics_data=False,
        signal_denominator="Sum_All_Signals",
        alpha_bound=0.1,
        mktcap_covered=0.95,
        add_accounting_data=False,
        add_materiality=False,
        industry_level=0,
        japan_year_adjustment_split_month_for_two_or_one=3,
        execute_3_filters=True,
        min_available_fyears=3,
        min_initatives_annual_reports=5,
        drop_suspicious_gvkeys=True,
        drop_real_estate=True,
        drop_fin=False,
        drop_utilities=True,
        drop_health_care=False,
        anlayse_fashion_only=False,
        msci_score_column="weighted",
        use_alpha_bound=True,
        show_sample_portfolio=False,
        plot_coverage=False,
        show_esg_coverage=False,
        include_all_signals_in_cum_risk_table=True,
    )
    c.update(overrides)

    # ---- cell 2: esg_choice end_year override (order matters; applied after
    #      overrides so esg_choice takes effect, matching the notebook) ------ #
    if c["esg_choice"] == "refinitiv":
        c["end_year"] = 2024
    if c["esg_choice"] == "msci":
        c["end_year"] = 2024
    if c["esg_choice"] == "s&p":
        c["end_year"] = 2022
   
    # ---- cell 2: region if/elif block ------------------------------------- #
    region = c["region_analysis"]
    c["fama_factor_region"] = "Developed"
    c["currency_filter"] = None
    c["convert_to_USD"] = True
    c["region_filter"] = None
    c["execute_region_filters"] = None
    if region == "United_States":
        c.update(currency_filter=["USD"], region_filter=["United States and Canada"],
                 execute_region_filters=True, convert_to_USD=False,
                 fama_factor_region="United_States")
    elif region == "North_America_and_Canada":
        c.update(currency_filter=["USD"], region_filter=["United States and Canada"],
                 execute_region_filters=True, convert_to_USD=False,
                 fama_factor_region="North_America_and_Canada")
    elif region == "Europe_and_North_America":
        c.update(currency_filter=["EUR", "USD"], convert_to_USD=True,
                 fama_factor_region="Developed", execute_region_filters=False)
    elif region == "Europe_and_North_America_and_Japan":
        c.update(currency_filter=["EUR", "USD", "JPY"], convert_to_USD=True,
                 fama_factor_region="Developed", execute_region_filters=False)
    elif region == "Europe":
        c.update(currency_filter=["EUR"], region_filter=["Europe"],
                 execute_region_filters=True, convert_to_USD=True,
                 fama_factor_region="Europe")
    elif region == "Japan":
        c.update(currency_filter=["JPY"], region_filter=["Asia-Pacific"],
                 execute_region_filters=True,
                 convert_to_USD=(c["fama_factors_currency"] == "USD"),
                 fama_factor_region="Japan")

    # ---- cell 8: signal design ------------------------------------------- #
    from functions.signal_design.signal_definitions import (
        dict_2d_actions_stakeholders_original_matteo,
        dict_4_signals_Action_1D_Pre_Nikkei,
        dict_4_stakeholder_signals_Pre_Nikkei,
        dict_all_SDG_1D,
        dict_all_SDG_1D_prosperity_into_people,
    )


    from functions.signal_design.signal_definitions_materiality import (
        Materiality_Signals,
        immaterial_4_Behavioural_Signals,
        immaterial_3_Matteo_Signals,
        material_4_Behavioural_Signals,
        material_3_Matteo_Signals,)

    ac = c["action_characterization"]
    if ac == "original_matteo":
        categories_dict, s0, s1, s2 = dict_2d_actions_stakeholders_original_matteo()
        lc_signals = {"signal_0": s0, "signal_1": s1, "signal_2": s2}
    elif ac == "4_signals_new":
        categories_dict, s0, s1, s2, s3 = dict_4_signals_Action_1D_Pre_Nikkei()
        lc_signals = {"signal_0": s0, "signal_1": s1, "signal_2": s2, "signal_3": s3}
    elif ac == "4_stakeholder_new":
        categories_dict, s0, s1, s2, s3 = dict_4_stakeholder_signals_Pre_Nikkei()
        lc_signals = {"signal_0": s0, "signal_1": s1, "signal_2": s2, "signal_3": s3}

    elif ac == "dict_all_SDG_1D":
        categories_dict, s0, s1, s2 = dict_all_SDG_1D()
        lc_signals = {"signal_0": s0, "signal_1": s1, "signal_2": s2}
    elif ac == "dict_all_SDG_1D_prosperity_into_people":
        categories_dict, s0, s1 = dict_all_SDG_1D_prosperity_into_people()
        lc_signals = {"signal_0": s0, "signal_1": s1}

    #Materiality
    elif ac == "Material_Immaterial_only":
        categories_dict, s0, s1 = Materiality_Signals()
        lc_signals = {"signal_0": s0, "signal_1": s1}

    elif ac == "immaterial_4_Behavioural_Signals":
        categories_dict, s0, s1, s2, s3 = immaterial_4_Behavioural_Signals()
        lc_signals = {"signal_0": s0, "signal_1": s1, "signal_2": s2, "signal_3": s3}
    
    elif ac == "material_4_Behavioural_Signals":
        categories_dict, s0, s1, s2, s3 = material_4_Behavioural_Signals()
        lc_signals = {"signal_0": s0, "signal_1": s1, "signal_2": s2, "signal_3": s3}
    
    
    elif ac == "immaterial_3_Matteo_Signals":
        categories_dict, s0, s1, s2 = immaterial_3_Matteo_Signals()
        lc_signals = {"signal_0": s0, "signal_1": s1, "signal_2": s2}
    
 
    elif ac == "material_3_Matteo_Signals":
        categories_dict, s0, s1, s2 = material_3_Matteo_Signals()
        lc_signals = {"signal_0": s0, "signal_1": s1, "signal_2": s2}
    


    else:
        raise ValueError(f"unknown action_characterization {ac!r}")

    if c["esg_full_universe"]:
        if c["esg_choice"] == "none":
            raise ValueError("esg_full_universe=True requires a provider esg_choice.")
        lc_signals = {}

    # JSON keys must be strings; categories_dict keys are category-column names.
    c["categories_dict"] = {str(k): v for k, v in categories_dict.items()}
    c["lc_signals"] = lc_signals

    # ---- cell 11: hml_directions / universe_signals / analysis_selection -- #
    analyse_high_low = "High"
    bucket = "high" if analyse_high_low == "High" else "low"
    all_lc = [[f"signal_{i}", bucket] for i in range(len(lc_signals))]
    hml_directions = {sig: "high_minus_low" for sig in lc_signals}
    esg = c["esg_choice"]
    if esg == "none":
        universe_signals, analysis_selection = {}, all_lc
    elif esg == "refinitiv":
        universe_signals = {"esg_refinitive": "esg_refinitive"}
        analysis_selection = all_lc + [["esg_refinitive", "high"]]
        hml_directions["esg_refinitive"] = "high_minus_low"
    elif esg == "s&p":
        universe_signals = {"esg_sp": "esg_sp"}
        analysis_selection = [["esg_sp", "high"], ["esg_sp", "low"]] + all_lc
        hml_directions["esg_sp"] = "high_minus_low"
    elif esg == "msci":
        universe_signals = {"esg_msci": "esg_msci"}
        analysis_selection = all_lc + [["esg_msci", "high"]]
        hml_directions["esg_msci"] = "high_minus_low"
    else:
        raise ValueError(f"unknown esg_choice {esg!r}")

    c["analyse_high_low"] = analyse_high_low
    c["hml_directions"] = hml_directions
    c["universe_signals"] = universe_signals
    c["analysis_selection"] = analysis_selection
    return c


def cfg_frame(cfg: dict) -> pl.DataFrame:
    """Pack a config dict into the one-row ``cfg`` frame carried to every node."""
    return pl.DataFrame({"json": [json.dumps(cfg)]})


# --------------------------------------------------------------------------- #
# Experiment builders
# --------------------------------------------------------------------------- #
def _external_cfg_inputs(pipeline, frame) -> dict:
    """Bind every external ``*.cfg`` port to the same cfg frame."""
    return {port: frame for port in pipeline.external_inputs() if port.endswith(".cfg")}


def make_experiment(name: str, cfg: dict, *, prepare_tag: str | None = None):
    """Build an Experiment: one Pipeline, the given cfg, process selection.

    ``prepare_tag`` chooses the prepare_panel Process; defaults to the ESG-universe
    variant when cfg.esg_full_universe else the LC variant.
    """
    from leonardo_nodes import Experiment

    from New_Pipeline.registry import build_pipeline

    pipe = build_pipeline()
    frame = cfg_frame(cfg)

    if prepare_tag is None:
        prepare_tag = "prepare_esg_universe@v1" if cfg.get("esg_full_universe") else "prepare_lc@v1"



    selection = {}
    for m_name, contract_name in [(n.name, n.contract.name) for n in pipe.topological_order()]:
        if m_name == "prepare_panel":
            selection[m_name] = prepare_tag
        elif m_name == "merge_esg_provider":
            selection[m_name] = _ESG_TAG[cfg["esg_choice"]]
        else:
            selection[m_name] = f"{contract_name}@v1"

    return Experiment(
        name=name,
        pipeline=pipe,
        process_selection=selection,
        inputs=_external_cfg_inputs(pipe, frame),
        config={"seed": 0},
    )


# The required config matrix (built lazily to avoid importing the store at import time).
def base_none():
    return make_experiment("base_none", build_cfg())


def esg_refinitiv():
    return make_experiment("esg_refinitiv", build_cfg(esg_choice="refinitiv"))


def esg_msci():
    return make_experiment("esg_msci", build_cfg(esg_choice="msci"))


def esg_snp():
    return make_experiment("esg_snp", build_cfg(esg_choice="s&p"))


def esg_full_universe():
    return make_experiment("esg_full_universe", build_cfg(esg_full_universe=True, esg_choice="msci"))


def show_corr():
    return make_experiment(
        "show_corr", build_cfg(esg_choice="refinitiv", show_esg_corr_matricies=True, show_esg_coverage=True)
    )


def base_materiality():
    # base_none + the optional SASB materiality inner-merge (adds the 15 count columns,
    # filters lc to firm-years present in the materiality workbook).
    return make_experiment("base_materiality", build_cfg(add_materiality=True, action_characterization = "material_4_Behavioural_Signals"))


EXPERIMENTS = {
    "base_none": base_none,
    "esg_refinitiv": esg_refinitiv,
    "esg_msci": esg_msci,
    "esg_snp": esg_snp,
    "esg_full_universe": esg_full_universe,
    "show_corr": show_corr,
    "base_materiality": base_materiality,
}
