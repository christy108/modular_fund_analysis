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
        # Which Compustat securities enter the universe. "active_only" keeps
        # secstat=='A', reproducing the frozen behaviour (that filter used to live in the
        # SQL WHERE clause); "all_firms_even_delisted" keeps securities that are inactive
        # as of the extract date, so a delisted / acquired / bankrupt name retains its full
        # price history instead of being erased from every year. Removes the whole-firm
        # survivorship channel ONLY -- the cshtrd/exchg screens and the absent delisting
        # returns still bias the surviving names' tails. See
        # functions/data_functions/get_data.py::_apply_security_status.
        security_status="active_only", #all_firms_even_delisted
        no_simple_quantiles=7,
        # How a firm sitting exactly ON a quantile cutpoint is bucketed.
        #   "half_open" (frozen behaviour): buckets are (q_{i-1}, q_i] -- a tie block on a
        #       cutpoint goes wholly to the bucket BELOW it. Because bucket 1 has no lower
        #       bound, its breakpoint is inclusive while bucket K's is not, so for two
        #       complementary signals High_a = {z > q} but Low_b = {z >= q}: two portfolios
        #       that must be identical differ by the tie mass (see sort_cutpoint_audit).
        #   "closed": buckets are [q_{i-1}, q_i] -- both adjacent buckets keep the block, so
        #       the mirror is exact. Cost: the K buckets no longer PARTITION the universe
        #       (memberships sum to > N, bucket returns stop decomposing to the market).
        #       High and Low never share a cutpoint for K >= 3, so the spread is unaffected.
        quantile_interval_bounds="half_open",   # or "closed"
        ff_factors_number=3,
        esg_choice="none",
        esg_full_universe=False,
        show_esg_corr_matricies=False,
        esg_corr_method="pearson",
        esg_min_group_size=5,
        show_sort_cutpoint_audit=True,
        drop_real_estate_Full_ESG=True,
        drop_utilities_Full_ESG=True,
        download_gics_data=False,
        signal_denominator="Sum_All_Signals",
        signal_type="weights",    # "weights": signal_i = sum_with_i / sum_activities
                                   # "counts":  signal_i = sum_with_i (raw initiative total, no denominator)
        alpha_bound=0.1,
        # Which market-cap screen process_global_universe applies, and the knobs each
        # one owns. NOTE the two percentages are NOT comparable: mktcap_covered_... is a
        # share of aggregate market-cap VALUE (0.95 discards ~65% of listings), while
        # percentage_stocks_removed_... is a share of the listing COUNT.
        market_cap_filter="percent_total_mcap",   # or "percent_stocks"
        mktcap_covered_if_filter_by_cum_market_cap=0.95,
        percentage_stocks_removed_if_percent_stocks_true=0.01,   # fraction, not percent
        floor_if_percent_stocks_true=100e6,      # absolute, in the mktcap currency
        add_accounting_data=False,
        add_materiality=False,
        materiality_version=2,
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
        # mktcap_filter_audit node (audit-only, nothing downstream reads it). Default ON
        # because the whole point is that the market-cap filter is visible without opting
        # in; flip it off to skip the replay if the extra runtime ever matters.
        show_mktcap_filter_audit=True,
        # sample_funnel_audit node (audit-only, nothing downstream reads it). Default ON:
        # its rows are contributed by the nodes that already ran the filters, so it costs
        # a handful of nunique() calls rather than a replay.
        show_sample_funnel_audit=True,
        include_all_signals_in_cum_risk_table=True,
    )
    # Reject unknown override keys. `c.update` would otherwise accept a typo (or a key
    # renamed out from under a caller, e.g. the old `mktcap_covered`) as a dead entry and
    # silently run with the default -- a wrong number with no error anywhere.
    _unknown = set(overrides) - set(c)
    if _unknown:
        raise ValueError(
            f"build_cfg got unknown config key(s): {sorted(_unknown)}. "
            f"Add them to the baseline dict above, or fix the spelling."
        )
    c.update(overrides)

    # Validate the VALUE, not just the key. The check above rejects unknown keys; a
    # misspelt value would otherwise travel all the way into get_*_universe and raise
    # from inside a node, long after the run started.
    if c["quantile_interval_bounds"] not in ("half_open", "closed"):
        raise ValueError(
            f"quantile_interval_bounds must be 'half_open' or 'closed', "
            f"got {c['quantile_interval_bounds']!r}"
        )
    # Fast fail: univariate_portfolio_sorting raises on this too, but only once a run is
    # already minutes deep in loading data. At K=2 the single breakpoint is both the Low
    # bucket's upper edge and the High bucket's lower edge, so under "closed" a tie block
    # there is held LONG and SHORT at once in the High-Low spread.
    if c["quantile_interval_bounds"] == "closed" and c["no_simple_quantiles"] < 3:
        raise ValueError(
            f"quantile_interval_bounds='closed' requires no_simple_quantiles >= 3, got "
            f"{c['no_simple_quantiles']}. At K=2 the High and Low buckets share their only "
            f"breakpoint, so a tie block on it would be held long and short simultaneously."
        )

    if c["security_status"] not in ("active_only", "all_firms_even_delisted"):
        raise ValueError(
            f"security_status must be 'active_only' or 'all_firms_even_delisted', "
            f"got {c['security_status']!r}"
        )

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
        dict_SDG_3_groups_people_planet_prosperity,
        dict_SDG_5_groups_brackets,
        dict_SDG_Climate_Natural_Capital_vs_All_SDGS,
    )


    from functions.signal_design.signal_definitions_materiality import (
        Materiality_Signals,
        Materiality_Signals_3_groups_people_planet_prosperity_SDG,
        Materiality_Signals_5_groups_SDG_brackets,
        Materiality_Signals_Climate_Natural_Capital_vs_All_SDGS,
        Combined_Material_Immaterial_4_Behavioural_Signals,
        Combined_Material_Immaterial_3_Matteo_Signals,
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

    # Plain-SDG splits (no material/immaterial dimension): these key on the LC columns
    # 'SDG: 1'..'SDG: 17' directly, so unlike their materiality twins below they need
    # neither add_materiality nor the SASB workbook. Variable signal count, so unpack by
    # star — the group dicts in signal_definitions.py can be re-cut.
    elif ac == "SDG_3_groups_people_planet_prosperity":
        categories_dict, *names = dict_SDG_3_groups_people_planet_prosperity()
        lc_signals = {f"signal_{i}": n for i, n in enumerate(names)}

    elif ac == "SDG_5_groups_brackets":
        categories_dict, *names = dict_SDG_5_groups_brackets()
        lc_signals = {f"signal_{i}": n for i, n in enumerate(names)}

    elif ac == "SDG_Climate_Natural_Capital_vs_All_SDGS":
        categories_dict, *names = dict_SDG_Climate_Natural_Capital_vs_All_SDGS()
        lc_signals = {f"signal_{i}": n for i, n in enumerate(names)}

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

    # Combined material + immaterial in one sort: 8 signals (4 immaterial then 4
    # material behavioural signals), same categories_dict union as the two halves above.
    elif ac == "Combined_Material_Immaterial_4_Behavioural_Signals":
        categories_dict, s0, s1, s2, s3, s4, s5, s6, s7 = Combined_Material_Immaterial_4_Behavioural_Signals()
        lc_signals = {"signal_0": s0, "signal_1": s1, "signal_2": s2, "signal_3": s3,
                      "signal_4": s4, "signal_5": s5, "signal_6": s6, "signal_7": s7}

    elif ac == "immaterial_3_Matteo_Signals":
        categories_dict, s0, s1, s2 = immaterial_3_Matteo_Signals()
        lc_signals = {"signal_0": s0, "signal_1": s1, "signal_2": s2}


    elif ac == "material_3_Matteo_Signals":
        categories_dict, s0, s1, s2 = material_3_Matteo_Signals()
        lc_signals = {"signal_0": s0, "signal_1": s1, "signal_2": s2}

    # Combined material + immaterial in one sort: 6 signals (3 immaterial then 3
    # material Matteo signals), same categories_dict union as the two halves above.
    elif ac == "Combined_Material_Immaterial_3_Matteo_Signals":
        categories_dict, s0, s1, s2, s3, s4, s5 = Combined_Material_Immaterial_3_Matteo_Signals()
        lc_signals = {"signal_0": s0, "signal_1": s1, "signal_2": s2, "signal_3": s3,
                      "signal_4": s4, "signal_5": s5}

    # SDG-level materiality splits. These return a variable number of signals (one
    # material + one immaterial per SDG group), so unpack by star rather than by
    # position — the group dicts in signal_definitions_materiality.py can grow.
    elif ac == "Materiality_3_groups_people_planet_prosperity_SDG":
        categories_dict, *names = Materiality_Signals_3_groups_people_planet_prosperity_SDG()
        lc_signals = {f"signal_{i}": n for i, n in enumerate(names)}

    elif ac == "Materiality_5_groups_SDG_brackets":
        categories_dict, *names = Materiality_Signals_5_groups_SDG_brackets()
        lc_signals = {f"signal_{i}": n for i, n in enumerate(names)}

    elif ac == "Materiality_Climate_Natural_Capital_vs_All_SDGS":
        categories_dict, *names = Materiality_Signals_Climate_Natural_Capital_vs_All_SDGS()
        lc_signals = {f"signal_{i}": n for i, n in enumerate(names)}

    else:
        raise ValueError(f"unknown action_characterization {ac!r}")

    # Tag the flavour onto the human-readable signal names so weights- and counts-based runs
    # are distinguishable in portfolio labels and audit tables ("transformation" vs
    # "transformation_counts"). Only "counts" is suffixed: the bare name has always meant
    # weights, and it is compared as an exact string in the cumulative_table/risk_table
    # parity artifacts — suffixing it too would fail base_none parity on labels alone.
    signal_type = c["signal_type"]
    if signal_type not in ("weights", "counts"):
        raise ValueError(f"unknown signal_type {signal_type!r}")
    if signal_type == "counts":
        lc_signals = {k: f"{v}_counts" for k, v in lc_signals.items()}

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


def base_none_all_firms():
    # base_none, but the universe retains securities that are INACTIVE as of the Compustat
    # extract date (secstat != 'A') instead of dropping their entire price history. The
    # survivorship arm to compare against base_none.
    #
    # Reads the same on-disk extract as base_none -- one download, filtered in memory --
    # so the two arms cannot differ by data vintage, only by the filter. Removes the
    # whole-firm erasure channel only: cshtrd/exchg still eject a surviving firm's worst
    # months, and Compustat carries no delisting return, so terminal losses are still
    # missing from both arms.
    #
    # Expect: more listings per currency-month pre-screen, weaker long-leg alpha, and a
    # materially worse short leg. Per-region kept/dropped counts land in
    # runs/<ts>_base_none_all_firms/debug_prints.log.
    return make_experiment("base_none_all_firms",
                           build_cfg(security_status="all_firms_even_delisted"))


def base_pct_stocks():
    # base_none, but the universe screen is the gentler count-based rule: drop a listing
    # for the whole year iff its LAST cap in the previous year puts it in the smallest 1%
    # of listings AND below $100mn. Expect single digits of listings dropped per month
    # versus ~1,339 under the 95%-of-value rule -- and all of the first data year (2013)
    # dropped, since no listing has a 2012 reference cap.
    return make_experiment("base_pct_stocks", build_cfg(
        market_cap_filter="percent_stocks",
        percentage_stocks_removed_if_percent_stocks_true=0.2,
        floor_if_percent_stocks_true=100e6,
    ))


#1
def base_none_v_2A1():
    return make_experiment("base_none_v_2A1", build_cfg(golden_data = "v_2A1"))


def base_none_v_2A1_2023():
    return make_experiment("base_none_v_2A1_2023", build_cfg(golden_data = "v_2A1", end_year = 2023))


def base_none_v_2A1_no_3_filters():
    return make_experiment("base_none_v_2A1_no_3_filters", build_cfg(golden_data = "v_2A1", execute_3_filters = False, drop_fin = False))

def base_none_v_2A1_no_3_filters_drop_fin():
    return make_experiment("base_none_v_2A1_no_3_filters_drop_fin", build_cfg(golden_data = "v_2A1", execute_3_filters = False, drop_fin = True))




#2
def base_none_v_2A1_delisted_present():
    return make_experiment("base_none_v_2A1_delisted_present", build_cfg(golden_data = "v_2A1", security_status="all_firms_even_delisted"))

#3 
def base_none_v_2A1_mcap_covered_99(): #  market_cap_filter="percent_total_mcap",   # or "percent_stocks"
    return make_experiment("base_none_v_2A1_mcap_covered_99", build_cfg(golden_data = "v_2A1", mktcap_covered_if_filter_by_cum_market_cap = 0.99, market_cap_filter="percent_total_mcap"))

def base_none_v_2A1_mcap_covered_99_9(): #  market_cap_filter="percent_total_mcap",   # or "percent_stocks"
    return make_experiment("base_none_v_2A1_mcap_covered_99_9", build_cfg(golden_data = "v_2A1", mktcap_covered_if_filter_by_cum_market_cap = 0.999, market_cap_filter="percent_total_mcap"))

def base_none_v_2A1_mcap_covered_100(): #  market_cap_filter="percent_total_mcap",   # or "percent_stocks"
    return make_experiment("base_none_v_2A1_mcap_covered_100", build_cfg(golden_data = "v_2A1", mktcap_covered_if_filter_by_cum_market_cap = 1, market_cap_filter="percent_total_mcap"))



#4
def base_none_v_2A1_percent_stocks_5_100M_floor(): #  market_cap_filter="percent_total_mcap",   # or "percent_stocks"
    return make_experiment("base_none_v_2A1_percent_stocks_5_100M_floor", build_cfg(golden_data = "v_2A1", market_cap_filter="percent_stocks", 
    percentage_stocks_removed_if_percent_stocks_true=0.05, floor_if_percent_stocks_true=100e6))

def base_none_v_2A1_percent_stocks_20_100M_floor(): #  market_cap_filter="percent_total_mcap",   # or "percent_stocks"
    return make_experiment("base_none_v_2A1_percent_stocks_20_100M_floor", build_cfg(golden_data = "v_2A1", market_cap_filter="percent_stocks", 
    percentage_stocks_removed_if_percent_stocks_true=0.2, floor_if_percent_stocks_true=100e6))

def base_none_v_2A1_percent_stocks_50_200M_floor(): #  market_cap_filter="percent_total_mcap",   # or "percent_stocks"
    return make_experiment("base_none_v_2A1_percent_stocks_50_200M_floor", build_cfg(golden_data = "v_2A1", market_cap_filter="percent_stocks", 
    percentage_stocks_removed_if_percent_stocks_true=0.5, floor_if_percent_stocks_true=200e6))





def base_none_v_2A1_no_mcap_filter_no_3filter(): 
    return make_experiment("base_none_v_2A1_no_mcap_filter_no_3filter", build_cfg(golden_data = "v_2A1", 
    mktcap_covered_if_filter_by_cum_market_cap = 1, execute_3_filters = False,
     market_cap_filter="percent_total_mcap"))





def base_none_v_2A1_no_3filter_with_delisted_firms(): 
    return make_experiment("base_none_v_2A1_no_3filter_with_delisted_firms", build_cfg(golden_data = "v_2A1", execute_3_filters = False,
     market_cap_filter="percent_total_mcap",  security_status="all_firms_even_delisted"))


def base_none_v_2A1_no_mcap_filter_with_delisted_firms(): 
    return make_experiment("base_none_v_2A1_no_mcap_filter_with_delisted_firms", build_cfg(golden_data = "v_2A1", 
    mktcap_covered_if_filter_by_cum_market_cap = 1,
     market_cap_filter="percent_total_mcap",   security_status="all_firms_even_delisted" ))




def base_none_v_2A1_no_mcap_filter_no_3filter_with_delisted_firms_q10(): 
    return make_experiment("base_none_v_2A1_no_mcap_filter_no_3filter_with_delisted_firms", build_cfg(golden_data = "v_2A1", 
    mktcap_covered_if_filter_by_cum_market_cap = 1, execute_3_filters = False,
     market_cap_filter="percent_total_mcap",   security_status="all_firms_even_delisted", no_simple_quantiles = 10 ))


def base_none_v_2A1_no_mcap_filter_no_3filter_with_delisted_firms_q5(): 
    return make_experiment("base_none_v_2A1_no_mcap_filter_no_3filter_with_delisted_firms", build_cfg(golden_data = "v_2A1", 
    mktcap_covered_if_filter_by_cum_market_cap = 1, execute_3_filters = False,
     market_cap_filter="percent_total_mcap",   security_status="all_firms_even_delisted", no_simple_quantiles = 5 ))





def base_none_v_2A1_no_mcap_filter_no_3filter_with_delisted_firms(): 
    return make_experiment("base_none_v_2A1_no_mcap_filter_no_3filter_with_delisted_firms", build_cfg(golden_data = "v_2A1", 
    mktcap_covered_if_filter_by_cum_market_cap = 1, execute_3_filters = False,
     market_cap_filter="percent_total_mcap",   security_status="all_firms_even_delisted" ))






 


def base_none_counts():
    # base_none, but each signal is the raw total-initiative count for its group
    # rather than that group's share of sum_activities.
    return make_experiment("base_none_counts", build_cfg(signal_type="counts"))
 


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
    return make_experiment("base_materiality", build_cfg(add_materiality=True, action_characterization = "Material_Immaterial_only"))



def base_materiality_q3():
    # base_none + the optional SASB materiality inner-merge (adds the 15 count columns,
    # filters lc to firm-years present in the materiality workbook).
    return make_experiment("base_materiality_q3", build_cfg(add_materiality=True, action_characterization = "Material_Immaterial_only", no_simple_quantiles = 3))

def base_materiality_q2():
    # base_none + the optional SASB materiality inner-merge (adds the 15 count columns,
    # filters lc to firm-years present in the materiality workbook).
    return make_experiment("base_materiality_q2", build_cfg(add_materiality=True, action_characterization = "Material_Immaterial_only", no_simple_quantiles = 2))







def base_materiality_closed():
    # base_materiality with closed quantile intervals. The pair to compare against
    # base_materiality: High Material should become EXACTLY Low Immaterial, so the two
    # High-Low spread alphas become exact negatives (+/-0.78) instead of 0.72 / -0.78.
    return make_experiment("base_materiality_closed", build_cfg(
        add_materiality=True, action_characterization="Material_Immaterial_only",
        quantile_interval_bounds="closed"))


def base_none_closed():
    # base_none with closed quantile intervals. No complementary pair here, so no mirror to
    # fix -- this arm just measures what the convention costs on its own: the Low legs are
    # untouched (bucket 1 never executes the changed line) and each High leg gains its
    # cutpoint tie block.
    return make_experiment("base_none_closed", build_cfg(quantile_interval_bounds="closed"))


def base_4_signals():
    # base_materiality, but with the 4-signal "material" behavioural-signal characterization.
    return make_experiment("4_signals_new", build_cfg(add_materiality=True, action_characterization = "4_signals_new"))



def base_4_signals_V2A1():
    # base_materiality, but with the 4-signal "material" behavioural-signal characterization.
    return make_experiment("4_signals_new", build_cfg(add_materiality=True, golden_data = "v_2A1", action_characterization = "4_signals_new"))



def base_materiality_4_Signals():
    # base_materiality, but with the 4-signal "material" behavioural-signal characterization.
    return make_experiment("base_materiality_4_Signals", build_cfg(add_materiality=True, action_characterization = "material_4_Behavioural_Signals"))

def base_immateriality_4_Signals():
    # base_materiality, but with the 4-signal "immaterial" behavioural-signal characterization.
    return make_experiment("base_immateriality_4_Signals", build_cfg(add_materiality=True, action_characterization = "immaterial_4_Behavioural_Signals"))

def base_materiality_4_Signals_counts():
    # base_materiality, but with the 4-signal "material" behavioural-signal characterization.
    return make_experiment("base_materiality_4_Signals_counts", build_cfg(add_materiality=True, action_characterization = "material_4_Behavioural_Signals", signal_type="counts"))

def base_immateriality_4_Signals_counts():
    # base_materiality, but with the 4-signal "immaterial" behavioural-signal characterization.
    return make_experiment("base_immateriality_4_Signals_counts", build_cfg(add_materiality=True, action_characterization = "immaterial_4_Behavioural_Signals", signal_type="counts"))


def base_materiality_combined_4_Signals():
    # base_materiality, but sorting on all 8 behavioural signals together (4 immaterial +
    # 4 material) in one combined quantile sort, instead of the material-only /
    # immaterial-only halves above.
    return make_experiment("base_materiality_combined_4_Signals", build_cfg(add_materiality=True, action_characterization = "Combined_Material_Immaterial_4_Behavioural_Signals"))

def base_materiality_combined_4_Signals_counts():
    return make_experiment("base_materiality_combined_4_Signals_counts", build_cfg(add_materiality=True, action_characterization = "Combined_Material_Immaterial_4_Behavioural_Signals", signal_type="counts"))


def base_materiality_combined_3_Matteo_Signals():
    # base_materiality, but sorting on all 6 Matteo signals together (3 immaterial +
    # 3 material) in one combined quantile sort.
    return make_experiment("base_materiality_combined_3_Matteo_Signals", build_cfg(add_materiality=True, action_characterization = "Combined_Material_Immaterial_3_Matteo_Signals"))

def base_materiality_combined_3_Matteo_Signals_counts():
    return make_experiment("base_materiality_combined_3_Matteo_Signals_counts", build_cfg(add_materiality=True, action_characterization = "Combined_Material_Immaterial_3_Matteo_Signals", signal_type="counts"))



def base_materiality_counts():
    # base_materiality (2-signal Material_Immaterial_only), counts version.
    return make_experiment(
        "base_materiality_counts",
        build_cfg(add_materiality=True,
                  action_characterization="Material_Immaterial_only",
                  signal_type="counts"),
    )


# ---- SDG-level materiality splits ---------------------------------------- #
# All three need add_materiality=True (the signal columns are the per-SDG __total__
# breakdowns the SASB merge brings in) and materiality_version=2 (only the v2 workbook
# carries them). Each has a weights and a counts variant, as with the 4-signal designs.
def _sdg_materiality(name: str, ac: str, **overrides):
    return make_experiment(
        name,
        build_cfg(add_materiality=True, materiality_version=2,
                  action_characterization=ac, **overrides),
    )


def base_materiality_3_groups_ppp():
    # 6 signals: material/immaterial x People, Prosperity, Planet.
    return _sdg_materiality("base_materiality_3_groups_ppp",
                            "Materiality_3_groups_people_planet_prosperity_SDG")


def base_materiality_3_groups_ppp_counts():
    return _sdg_materiality("base_materiality_3_groups_ppp_counts",
                            "Materiality_3_groups_people_planet_prosperity_SDG",
                            signal_type="counts")


def base_materiality_5_groups_brackets():
    # 10 signals: material/immaterial x the five SDG brackets.
    return _sdg_materiality("base_materiality_5_groups_brackets",
                            "Materiality_5_groups_SDG_brackets")


def base_materiality_5_groups_brackets_counts():
    return _sdg_materiality("base_materiality_5_groups_brackets_counts",
                            "Materiality_5_groups_SDG_brackets",
                            signal_type="counts")


def base_materiality_climate_vs_each_sdg():
    # 30 signals: material/immaterial x (Climate & Natural Capital, then each of the
    # 14 non-climate SDGs on its own).
    return _sdg_materiality("base_materiality_climate_vs_each_sdg",
                            "Materiality_Climate_Natural_Capital_vs_All_SDGS")


def base_materiality_climate_vs_each_sdg_counts():
    return _sdg_materiality("base_materiality_climate_vs_each_sdg_counts",
                            "Materiality_Climate_Natural_Capital_vs_All_SDGS",
                            signal_type="counts")


# ---- plain-SDG splits (no materiality) ----------------------------------- #
# Same three group cuts as the SDG-level materiality experiments above, but on the raw
# 'SDG: N' LC columns, so no add_materiality / materiality_version is needed and the
# sample is the unrestricted base_none sample. Weights only — no counts variants.
def _sdg_only(name: str, ac: str, **overrides):
    return make_experiment(name, build_cfg(action_characterization=ac, **overrides))


def sdg_3_groups_ppp():
    # 3 signals: People, Prosperity, Planet.
    return _sdg_only("sdg_3_groups_ppp", "SDG_3_groups_people_planet_prosperity")


def sdg_5_groups_brackets():
    # 5 signals: one per SDG bracket.
    return _sdg_only("sdg_5_groups_brackets", "SDG_5_groups_brackets")


def sdg_climate_vs_each_sdg():
    # 15 signals: Climate & Natural Capital, then each of the 14 non-climate SDGs alone.
    return _sdg_only("sdg_climate_vs_each_sdg", "SDG_Climate_Natural_Capital_vs_All_SDGS")


EXPERIMENTS = {
    "base_none": base_none,
    "base_none_all_firms": base_none_all_firms, #base_none_delisted_present
    "base_pct_stocks": base_pct_stocks,

    #V2A1
    "base_none_v_2A1":base_none_v_2A1,
    "base_none_v_2A1_2023":base_none_v_2A1_2023,
    "base_none_v_2A1_no_3_filters":base_none_v_2A1_no_3_filters,
    "base_none_v_2A1_no_3_filters_drop_fin":base_none_v_2A1_no_3_filters_drop_fin,

    "base_none_v_2A1_delisted_present":base_none_v_2A1_delisted_present,


    "base_none_v_2A1_mcap_covered_99":base_none_v_2A1_mcap_covered_99,
    "base_none_v_2A1_mcap_covered_99_9":base_none_v_2A1_mcap_covered_99_9,
    "base_none_v_2A1_mcap_covered_100":base_none_v_2A1_mcap_covered_100,


    "base_none_v_2A1_percent_stocks_5_100M_floor":base_none_v_2A1_percent_stocks_5_100M_floor,
    "base_none_v_2A1_percent_stocks_20_100M_floor":base_none_v_2A1_percent_stocks_20_100M_floor,
    "base_none_v_2A1_percent_stocks_50_200M_floor":base_none_v_2A1_percent_stocks_50_200M_floor,

    #5
    "base_none_v_2A1_no_mcap_filter_no_3filter_with_delisted_firms":base_none_v_2A1_no_mcap_filter_no_3filter_with_delisted_firms,
    "base_none_v_2A1_no_mcap_filter_no_3filter_with_delisted_firms_q10":base_none_v_2A1_no_mcap_filter_no_3filter_with_delisted_firms_q10,
    "base_none_v_2A1_no_mcap_filter_no_3filter_with_delisted_firms_q5":base_none_v_2A1_no_mcap_filter_no_3filter_with_delisted_firms_q5,

    "base_none_v_2A1_no_mcap_filter_no_3filter":base_none_v_2A1_no_mcap_filter_no_3filter,
    "base_none_v_2A1_no_3filter_with_delisted_firms":base_none_v_2A1_no_3filter_with_delisted_firms,
    "base_none_v_2A1_no_mcap_filter_with_delisted_firms":base_none_v_2A1_no_mcap_filter_with_delisted_firms,


  








    "base_none_counts": base_none_counts,
    "esg_refinitiv": esg_refinitiv,
    "esg_msci": esg_msci,
    "esg_snp": esg_snp,
    "esg_full_universe": esg_full_universe,
    "show_corr": show_corr,


    "base_materiality": base_materiality,
    "base_materiality_closed": base_materiality_closed,
    "base_none_closed": base_none_closed,
    "base_materiality_q3":base_materiality_q3,
    "base_materiality_q2":base_materiality_q2,
     "4_signals_new": base_4_signals,
    "base_materiality_4_Signals": base_materiality_4_Signals,
    "base_immateriality_4_Signals": base_immateriality_4_Signals,
    "base_immateriality_4_Signals_counts": base_immateriality_4_Signals_counts,
    "base_materiality_4_Signals_counts":base_materiality_4_Signals_counts,
    "base_materiality_combined_4_Signals": base_materiality_combined_4_Signals,
    "base_materiality_combined_4_Signals_counts": base_materiality_combined_4_Signals_counts,
    "base_materiality_combined_3_Matteo_Signals": base_materiality_combined_3_Matteo_Signals,
    "base_materiality_combined_3_Matteo_Signals_counts": base_materiality_combined_3_Matteo_Signals_counts,

    "base_materiality_counts": base_materiality_counts,

    "base_materiality_3_groups_ppp": base_materiality_3_groups_ppp,
    "base_materiality_3_groups_ppp_counts": base_materiality_3_groups_ppp_counts,
    "base_materiality_5_groups_brackets": base_materiality_5_groups_brackets,
    "base_materiality_5_groups_brackets_counts": base_materiality_5_groups_brackets_counts,
    "base_materiality_climate_vs_each_sdg": base_materiality_climate_vs_each_sdg,
    "base_materiality_climate_vs_each_sdg_counts": base_materiality_climate_vs_each_sdg_counts,


    #Below dont work
    "sdg_3_groups_ppp": sdg_3_groups_ppp,
    "sdg_5_groups_brackets": sdg_5_groups_brackets,
    "sdg_climate_vs_each_sdg": sdg_climate_vs_each_sdg,




    "base_4_signals_V2A1":base_4_signals_V2A1,
    




   
}
