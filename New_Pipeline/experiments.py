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
        golden_data="v_2A1",
        region_analysis="United_States",
        fama_factors_currency="JPY",
        RF_JAPAN_PATH="./data/FAMA/Rf_Japan_Monthly.xlsx",
        action_characterization="Material_Immaterial_only",
        start_year=2016,
        end_year=2024,
        # Which Compustat securities enter the universe. "active_only" keeps
        # secstat=='A', reproducing the frozen behaviour (that filter used to live in the
        # SQL WHERE clause); "all_firms_even_delisted" keeps securities that are inactive
        # as of the extract date, so a delisted / acquired / bankrupt name retains its full
        # price history instead of being erased from every year. Removes the whole-firm
        # survivorship channel ONLY -- the cshtrd/exchg screens and the absent delisting
        # returns still bias the surviving names' tails. See
        # functions/data_functions/get_data.py::_apply_security_status.
        security_status="all_firms_even_delisted", #all_firms_even_delisted
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
        quantile_interval_bounds="closed",   # half_open or "closed"   closed: [max,q1],[q1,q2][q2,max] in sorts--- half_open: [max,q1],(q1,q2](q2,max] 
        ff_factors_number=3,
        esg_choice="none",
        esg_full_universe=False,
        show_esg_corr_matricies=False,
        esg_corr_method="pearson",
        esg_min_group_size=5,
        # Thin-portfolio gate (PRESENTATION ONLY -- the exported parquets always keep every
        # portfolio). A High/Low leg must hold at least `min_stocks_per_portfolio` names in at
        # least `min_portfolio_coverage` of formation months, or it is hidden from the
        # dashboard along with its High-Low spread. A bucket of a handful of names is not a
        # portfolio -- its return is idiosyncratic noise -- and showing it beside
        # well-populated ones invites reading signal into sampling error.
        # Calibrated at 25 rather than 30 deliberately: measured on the current runs, every
        # base_none / base_materiality leg clears 25 in 88% of months but only 73-77% of
        # months at 30, so a threshold of 30 would drop every signal in both configs.
        # Set min_stocks_per_portfolio=0 to disable the gate entirely.
        min_stocks_per_portfolio=25,
        min_portfolio_coverage=0.80,
        show_sort_cutpoint_audit=True,
        drop_real_estate_Full_ESG=True,
        drop_utilities_Full_ESG=True,
        download_gics_data=False,
        signal_denominator="Sum_All_Signals",
        signal_type="weights",    # "weights":     signal_i = sum_with_i / sum_activities
                                   # "counts":      signal_i = sum_with_i (raw initiative total)
                                   # "per_revenue": signal_i = sum_with_i / sale_usd -- the same
                                   #   count as "counts", scaled by revenue to strip firm size.
                                   #   Requires add_sales=True. NOTE this puts size in the
                                   #   denominator, so the sort partly inverts size: check the
                                   #   beta_smb row of the FF3 table before reading anything into it.
        # Merge annual Compustat revenue (data/sales_all_regions.csv, built by
        # scripts.download_sales) onto lc at (gvkey, rfyear) <- (gvkey, fyear). Additive:
        # a LEFT join, so it adds `sale`/`sale_usd` columns without dropping firm-years.
        # Only signal_type="per_revenue" consumes it; otherwise it just rides along.
        add_sales=False,
        sales_path="data/sales_all_regions.csv",
        alpha_bound=0.1,
        # Winsorise each signal_i within its rfyear: values above the (1 - p) quantile are
        # CAPPED at it and values below p are FLOORED at it. 0.0 = off (the default, so
        # every existing config is bit-identical).
        #
        # Distinct from alpha_bound, which TRIMS (drops) rows on sum_activities -- the
        # signal's *denominator* under "weights", and untouched under "per_revenue". This
        # clips the signal itself and keeps every firm-year.
        #
        # It is RANK-PRESERVING, so it cannot move the quantile sort directly: the same
        # firms land in the same buckets. Its only channel is standardize_pivot's
        # (x - mean)/std, where one extreme value inflates its group's std and so
        # compresses that group relative to the others the sort pools it with.
        # Consequently it matters most for signal_type="per_revenue" (unbounded, right-
        # skewed -- a small denominator gives a huge ratio) and barely at all for
        # "weights", which is a share bounded in [0, 1].
        winsorise_signal_pct=0.0,
        # Which market-cap screen process_global_universe applies, and the knobs each
        # one owns. NOTE the two percentages are NOT comparable: mktcap_covered_... is a
        # share of aggregate market-cap VALUE (0.95 discards ~65% of listings), while
        # percentage_stocks_removed_... is a share of the listing COUNT.
        market_cap_filter="percent_total_mcap",   # or "percent_stocks"
        mktcap_covered_if_filter_by_cum_market_cap=0.95,
        percentage_stocks_removed_if_percent_stocks_true=0.01,   # fraction, not percent
        floor_if_percent_stocks_true=100e6,      # absolute, in the mktcap currency
        add_accounting_data=False,
        add_materiality=True,
        materiality_version=2,
        # Which behavioural action action_characterization="Materiality_PP_Action_SDG"
        # restricts the People+Prosperity split to. None unless that design is selected.
        # Validated against the signal module's own _SDG_ACTIONS inside the dispatch, so a
        # typo raises in build_cfg rather than emptying the sort 20 minutes into a run.
        materiality_pp_action=None,

        # Which single SDG action_characterization="Materiality_single_SDG" sorts on
        # (1-17). Ignored by every other characterization; required by that one, which
        # raises if it is still None. A cfg key rather than 17 separate
        # action_characterization strings, so the choice is visible in the manifest and
        # hashes into the cfg frame like any other knob.
        materiality_single_sdg=None,
        industry_level=0,
        japan_year_adjustment_split_month_for_two_or_one=3,
        # Which of the three LC sample filters run, in process_lc:
        #   "all"             -- (1) >= min_available_rfyears_if_execute_3_filters_true fiscal years, (2) drop
        #                        suspicious gvkeys, (3) drop Annual Reports with
        #                        < min_initatives_annual_reports_if_execute_3_filters_true initiatives
        #   "suspicious_only" -- (2) only; filters 1 and 3 are skipped
        #   "none"            -- none of the three
        # True/False are accepted as aliases for "all"/"none" and normalised below, so
        # every consumer downstream only ever sees one of the three strings.
        # NOTE this defaults to "suspicious_only", NOT "all": base_none therefore no
        # longer reproduces the frozen notebook's sample. Set "all" to get that back.
        execute_3_filters="suspicious_only",
        min_available_rfyears_if_execute_3_filters_true=3,
        min_initatives_annual_reports_if_execute_3_filters_true=5,
        # Minimum initiatives a firm-year must have IN THE MATERIALITY GROUP before it is
        # allowed into the sort at all. Floors material_G + immaterial_G (the group's own
        # total, computed from categories_dict -- NOT sum_activities, which under
        # signal_denominator="Sum_All_Initiatives" is n_predicted_initiatives instead).
        #
        # Why: the signal is a ratio of two small integer counts, so a firm-year with a
        # single initiative in the group scores 1/1 = 1.0 and the sort reads it as maximal
        # materiality, when it carries no information about the firm's MIX at all. 4/5 = 0.8
        # looks weaker and is far better evidence. The 1/1-type rows pile up on the ratio's
        # ceiling, which is where the sort is most sensitive to them (the top bucket is
        # `> q_{K-1}`): on base_materiality_people_only, 18.8% of firm-years sit at exactly
        # 1.0 and that atom alone is wide enough to fill a whole bucket of seven.
        #
        # 0 = off, and off is the default so every existing config is untouched. Runs AFTER
        # the alpha-bound trim, so the trim's own numbers stay identical and any change is
        # attributable to this floor alone. The `initatives` spelling matches
        # min_initatives_annual_reports_if_execute_3_filters_true above.
        #
        # RAISES (below) on a non-materiality action_characterization, and on a materiality
        # design with more than ONE group -- see the validation for why multi-group cannot
        # be honoured. Read New_Pipeline/nodes/02_derive_signals.py's
        # "materiality split floor" audit to choose the value: it reports what each
        # candidate N would cost in firm-years and what it buys in pct_at_max.
        minimum_initatives_needed_to_split_by_materiality=0,
        # Dump lc to ./data/debug/*.csv inside process_lc. Default OFF: the two dumps are
        # ~128MB of CSV serialisation per run that nothing reads back, and because the
        # paths are FIXED they are also the one place concurrent runs would collide --
        # `New_Pipeline.sweep --jobs N` needs this off. Turn on to inspect one run by hand.
        write_debug_csv=False,
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
        # Save build_analyse_portfolios' material-initiative area plots as a PDF in the
        # run's archive directory (runs/<ts>_<config>/initiative_decomposition.pdf),
        # alongside dashboard.md. Rendered by run.py from the same widget payloads the
        # dashboard draws, so the two can never disagree. No-op unless the run actually
        # produces the decomposition (add_materiality + Material_Immaterial_only), and
        # deliberately NOT written to the --out snapshot: it is a report, not an artifact.
        area_initatives_plots_per_portfolio_to_PDF=False,
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
    if not 0.0 <= c["min_portfolio_coverage"] <= 1.0:
        raise ValueError(
            f"min_portfolio_coverage is a fraction in [0, 1], got "
            f"{c['min_portfolio_coverage']!r} (0.80 means 80% of months)"
        )
    if c["min_stocks_per_portfolio"] < 0:
        raise ValueError(
            f"min_stocks_per_portfolio must be >= 0 (0 disables the gate), got "
            f"{c['min_stocks_per_portfolio']!r}"
        )

    if c["quantile_interval_bounds"] not in ("half_open", "closed"):
        raise ValueError(
            f"quantile_interval_bounds must be 'half_open' or 'closed', "
            f"got {c['quantile_interval_bounds']!r}"
        )

    # Per-TAIL fraction, so 0.5 would clip everything to the median and anything above it
    # is nonsense (the lower cap would exceed the upper). Rejected here rather than
    # producing a silently degenerate signal minutes into a run.
    if not 0.0 <= c["winsorise_signal_pct"] < 0.5:
        raise ValueError(
            f"winsorise_signal_pct is a PER-TAIL fraction in [0, 0.5), got "
            f"{c['winsorise_signal_pct']!r} (0.01 clips the top and bottom 1%)"
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

    # Normalise the bool aliases BEFORE validating, so the cfg that gets serialised (and
    # hashed into the manifest) is always one of the three strings -- passing True and
    # passing "all" must not produce two different content hashes for the same run.
    # `is True` / `is False`, not truthiness: "none" is a truthy string, which is exactly
    # the trap this knob's shape invites.
    if c["execute_3_filters"] is True:
        c["execute_3_filters"] = "all"
    elif c["execute_3_filters"] is False:
        c["execute_3_filters"] = "none"
    if c["execute_3_filters"] not in ("all", "suspicious_only", "none"):
        raise ValueError(
            f"execute_3_filters must be 'all', 'suspicious_only' or 'none' "
            f"(True/False accepted as aliases for 'all'/'none'), "
            f"got {c['execute_3_filters']!r}"
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
        Materiality_People_SDG,
        Materiality_People_Plus_Prosperity_SDG,
        Materiality_People_Plus_Prosperity_Action_SDG,
        Materiality_People_Plus_Prosperity_VS_Planet_SDG,
        Materiality_One_Health_SDGS,
        Materiality_Narrow_Health_SDGS,
        Materiality_Health_and_Work_SDGS,
        Materiality_SDG_X,
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

    # ONE signal, the firm-year's whole initiative count -- no split by category,
    # materiality or SDG. Defined inline rather than in functions/signal_design/ because
    # it is a single column mapped to a single group, and functions/ is the frozen core.
    #
    # `n_predicted_initiatives` IS the total (mean 31, max 783 -- the same max
    # sum_activities reaches), so with signal_denominator="Sum_All_Signals" this also
    # makes sum_activities equal that total, which is what the alpha-bound trim then
    # operates on. Sensible: the trim drops firm-years with extreme total activity.
    #
    # Only meaningful with signal_type "counts" (signal = total initiatives) or
    # "per_revenue" (= total initiatives / revenue). Under "weights" the signal would be
    # sum_with_0 / sum_activities == 1.0 for every firm -- a constant, and an unsortable
    # signal -- so that combination is rejected below.
    elif ac == "total_initiatives":
        categories_dict = {"n_predicted_initiatives": 0}
        lc_signals = {"signal_0": "Total_Initiatives"}

    # elif ac == "immaterial_4_Behavioural_Signals":
    #     categories_dict, s0, s1, s2, s3 = immaterial_4_Behavioural_Signals()
    #     lc_signals = {"signal_0": s0, "signal_1": s1, "signal_2": s2, "signal_3": s3}

    # elif ac == "material_4_Behavioural_Signals":
    #     categories_dict, s0, s1, s2, s3 = material_4_Behavioural_Signals()
    #     lc_signals = {"signal_0": s0, "signal_1": s1, "signal_2": s2, "signal_3": s3}

    # Combined material + immaterial in one sort: 8 signals (4 immaterial then 4
    # material behavioural signals), same categories_dict union as the two halves above.
    elif ac == "Combined_Material_Immaterial_4_Behavioural_Signals":
        categories_dict, s0, s1, s2, s3, s4, s5, s6, s7 = Combined_Material_Immaterial_4_Behavioural_Signals()
        lc_signals = {"signal_0": s0, "signal_1": s1, "signal_2": s2, "signal_3": s3,
                      "signal_4": s4, "signal_5": s5, "signal_6": s6, "signal_7": s7}

    # elif ac == "immaterial_3_Matteo_Signals":
    #     categories_dict, s0, s1, s2 = immaterial_3_Matteo_Signals()
    #     lc_signals = {"signal_0": s0, "signal_1": s1, "signal_2": s2}


    # elif ac == "material_3_Matteo_Signals":
    #     categories_dict, s0, s1, s2 = material_3_Matteo_Signals()
    #     lc_signals = {"signal_0": s0, "signal_1": s1, "signal_2": s2}

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

    # One SDG group only, split material vs immaterial -- so with
    # signal_denominator="Sum_All_Signals" the denominator is material_People +
    # immaterial_People and signal_0 is the People material share, signal_1 its exact
    # mirror. Same 2-signal mirror-pair shape as Material_Immaterial_only, restricted to
    # the People SDGs (1,2,3,4,5,8,10) instead of all 17.
    elif ac == "Materiality_People_SDG":
        categories_dict, *names = Materiality_People_SDG()
        lc_signals = {f"signal_{i}": n for i, n in enumerate(names)}

    # Same one-group mirror pair, but People and Prosperity pooled -- i.e. everything
    # except the Planet SDGs (6, 7, 12, 13, 14, 15).
    elif ac == "Materiality_People_Plus_Prosperity_SDG":
        categories_dict, *names = Materiality_People_Plus_Prosperity_SDG()
        lc_signals = {f"signal_{i}": n for i, n in enumerate(names)}

    # Same one-group People+Prosperity cut, but restricted to ONE behavioural action
    # instead of the SDG total: the columns are material__<action>__SDG_n rather than
    # material__total__SDG_n. Still a mirror pair, but on a strictly thinner denominator --
    # read the signal_sparsity audit before trusting the sort.
    #
    # WHICH action comes from the cfg key, not from `ac`, so this single branch covers all
    # eight -- the same shape as Materiality_single_SDG below. That also makes the action a
    # sweepable axis: put materiality_pp_action in a sweep GRID and the design list follows.
    elif ac == "Materiality_PP_Action_SDG":
        _act = c["materiality_pp_action"]
        if _act is None:
            raise ValueError(
                "action_characterization='Materiality_PP_Action_SDG' needs "
                "materiality_pp_action=<one of adaptation/advocacy_new_def/"
                "advocacy_old_def/innovation/preparation/transformation/upskilling/total>; "
                "got None"
            )
        categories_dict, *names = Materiality_People_Plus_Prosperity_Action_SDG(_act)
        lc_signals = {f"signal_{i}": n for i, n in enumerate(names)}

    # Two groups covering all 17 SDGs, so unlike the one-group designs above the
    # denominator is every SDG count and each signal is that group's material (or
    # immaterial) share of ALL initiatives. The four sum to 1, so no mirror pair.
    elif ac == "Materiality_People_Plus_Prosperity_VS_Planet_SDG":
        categories_dict, *names = Materiality_People_Plus_Prosperity_VS_Planet_SDG()
        lc_signals = {f"signal_{i}": n for i, n in enumerate(names)}

    # Same one-group mirror-pair shape as Materiality_People_SDG, restricted to the three
    # Health_SDGS_Groups cuts (One_Health: SDGs 3,6,8,11,14,15; Narrow_Health: 3,6,11;
    # Health_and_Work: 3,6,8,11). The three groups overlap each other (e.g. SDG 3 is in
    # all three), but each branch here only ever passes ONE of them to
    # _signals_from_groups, so that overlap never collides -- these are three alternative
    # single-group signals, never combined in the same run.
    elif ac == "Materiality_One_Health_SDGS":
        categories_dict, *names = Materiality_One_Health_SDGS()
        lc_signals = {f"signal_{i}": n for i, n in enumerate(names)}

    elif ac == "Materiality_Narrow_Health_SDGS":
        categories_dict, *names = Materiality_Narrow_Health_SDGS()
        lc_signals = {f"signal_{i}": n for i, n in enumerate(names)}

    elif ac == "Materiality_Health_and_Work_SDGS":
        categories_dict, *names = Materiality_Health_and_Work_SDGS()
        lc_signals = {f"signal_{i}": n for i, n in enumerate(names)}

    # One SDG only, material vs immaterial. WHICH SDG comes from the cfg key rather
    # than from `ac`, so this single branch covers all 17.
    elif ac == "Materiality_single_SDG":
        _sdg = c["materiality_single_sdg"]
        if _sdg is None:
            raise ValueError(
                "action_characterization='Materiality_single_SDG' needs "
                "materiality_single_sdg=<1-17>; got None"
            )
        categories_dict, *names = Materiality_SDG_X(_sdg)
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
    if signal_type not in ("weights", "counts", "per_revenue"):
        raise ValueError(f"unknown signal_type {signal_type!r}")
    if ac == "total_initiatives" and signal_type == "weights":
        raise ValueError(
            "action_characterization='total_initiatives' has a single group covering every "
            "initiative, so signal_type='weights' would give sum_with_0 / sum_activities "
            "== 1.0 for every firm -- a constant, which cannot be sorted. Use "
            "signal_type='counts' (total initiatives) or 'per_revenue' (total initiatives "
            "/ revenue)."
        )
    if signal_type == "per_revenue" and not c["add_sales"]:
        raise ValueError(
            "signal_type='per_revenue' needs add_sales=True -- the denominator is the "
            "`sale_usd` column that the sales merge in process_lc attaches."
        )
    if signal_type == "counts":
        lc_signals = {k: f"{v}_counts" for k, v in lc_signals.items()}
    elif signal_type == "per_revenue":
        lc_signals = {k: f"{v}_per_rev" for k, v in lc_signals.items()}

    if c["esg_full_universe"]:
        if c["esg_choice"] == "none":
            raise ValueError("esg_full_universe=True requires a provider esg_choice.")
        lc_signals = {}

    # JSON keys must be strings; categories_dict keys are category-column names.
    c["categories_dict"] = {str(k): v for k, v in categories_dict.items()}
    c["lc_signals"] = lc_signals

    # ---- validate the materiality-split floor against the design it will run on ---- #
    # Here rather than in the value-checks above because it needs categories_dict, which
    # only exists after the action_characterization dispatch. Failing in build_cfg means
    # failing before the run starts, not 20 minutes in from inside a node.
    _min_split = c["minimum_initatives_needed_to_split_by_materiality"]
    if not isinstance(_min_split, int) or isinstance(_min_split, bool) or _min_split < 0:
        raise ValueError(
            f"minimum_initatives_needed_to_split_by_materiality must be a non-negative "
            f"int (0 = off), got {_min_split!r}"
        )
    if _min_split > 0:
        from New_Pipeline._common import materiality_split_groups

        _groups = materiality_split_groups(c["categories_dict"])
        if not _groups:
            raise ValueError(
                f"minimum_initatives_needed_to_split_by_materiality="
                f"{_min_split} needs a material/immaterial design, but "
                f"action_characterization={ac!r} has no material/immaterial group pair "
                f"(its category columns are {sorted(c['categories_dict'])[:4]}...). The "
                f"floor gates the SPLIT of a group into material vs immaterial, so it is "
                f"undefined where there is no such split. Use 0 to turn it off."
            )
        if len(_groups) > 1:
            raise ValueError(
                f"minimum_initatives_needed_to_split_by_materiality={_min_split} is only "
                f"supported for a SINGLE-group design, but action_characterization={ac!r} "
                f"has {len(_groups)} groups: "
                f"{[g['material_index'] for g in _groups]} (material indices).\n"
                f"Reason: a per-group floor has to leave the other groups' signals intact "
                f"for that firm-year, but functions/portfolio_strategy_design/"
                f"univariate_sorting_preprocess.py:170 apply_cross_signal_nan_mask NaNs a "
                f"(date, asset) cell where ANY signal is missing -- a deliberate "
                f"common-universe design in the frozen numeric core. So a per-group floor "
                f"would silently become 'drop unless EVERY group clears "
                f"{_min_split}', which on a {len(_groups)}-group design is a far harsher "
                f"filter than the one requested.\n"
                f"Use a single-group characterization instead (Material_Immaterial_only, "
                f"Materiality_People_SDG, Materiality_People_Plus_Prosperity_SDG, "
                f"Materiality_single_SDG), or 0 to turn the floor off."
            )

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


def base_none_half_open():
    # base_none with the ONLY change being the cutpoint tie-break convention, so this pair
    # isolates the tie mass and nothing else: same sample, same signal, same cutpoints.
    #
    # The signal is a ratio of small integer counts, so its support is a sparse set of
    # simple fractions and a cutpoint lands on a block of identical values routinely
    # (sort_cutpoint_summary reports months_tie_on_high_cut). Which way that block goes is
    # decided by convention, not by the data:
    #   base_none            "closed"    -> High = {z >= q_{K-1}}, block INCLUDED
    #   base_none_half_open  "half_open" -> High = {z >  q_{K-1}}, block EXCLUDED
    # The Low leg is {z <= q_1} in both, so it must come out bit-identical -- that is the
    # parity check on this pair. Any Low-leg difference means something other than the
    # tie-break moved, and the comparison is invalid.
    return make_experiment("base_none_half_open",
                           build_cfg(quantile_interval_bounds="half_open"))

 

def base_materiality():
    # base_none + the optional SASB materiality inner-merge (adds the 15 count columns,
    # filters lc to firm-years present in the materiality workbook).
    return make_experiment("base_materiality", build_cfg(add_materiality=True, action_characterization = "Material_Immaterial_only"))

def base_materiality_counts():
    # base_none + the optional SASB materiality inner-merge (adds the 15 count columns,
    # filters lc to firm-years present in the materiality workbook).
    return make_experiment("base_materiality_counts", build_cfg(add_materiality=True, action_characterization = "Material_Immaterial_only", signal_type="counts"))


def base_total_initiatives_counts():
    # ONE signal: the firm-year's whole initiative count, unsplit.
    # signal_0 = n_predicted_initiatives.
    #
    # add_materiality=True is NOT needed for the signal (n_predicted_initiatives is a raw
    # LC column) but is kept so this runs on the SAME sample as base_materiality_counts
    # and base_materiality_per_revenue -- otherwise the comparison would confound the
    # signal change with a sample change.
    return make_experiment(
        "base_total_initiatives_counts",
        build_cfg(add_materiality=True,
                  action_characterization="total_initiatives",
                  signal_type="counts"),
    )


def base_total_initiatives_per_revenue():
    # The same single total, scaled by revenue: signal_0 = n_predicted_initiatives / sale_usd.
    # Read against base_total_initiatives_counts -- identical numerator, the only
    # difference is the denominator, so any change in the spread is the size scaling.
    return make_experiment(
        "base_total_initiatives_per_revenue",
        build_cfg(add_materiality=True,
                  action_characterization="total_initiatives",
                  add_sales=True,
                  signal_type="per_revenue"),
    )


def base_materiality_per_revenue():
    # base_materiality_counts with revenue as the denominator instead of no denominator:
    # signal_i = material__total / sale_usd (and immaterial__total / sale_usd), i.e. the
    # SAME numerator as base_materiality_counts, scaled to strip out firm size.
    #
    # add_sales attaches data/sales_all_regions.csv (built by scripts.download_sales) with
    # a LEFT join, so the merge itself changes nothing; only signal_type="per_revenue"
    # consumes it. Firm-years with no revenue become a NaN signal and leave the sort --
    # ~93.6% are usable on this config, reported by the "Annual revenue merge — coverage"
    # widget on process_lc.
    #
    # Read this one against base_materiality_counts: same firms, same initiative counts,
    # the only difference is dividing by revenue. Because that puts size in the
    # denominator, check beta_smb in the FF3 table before attributing the spread to
    # behaviour rather than to a size tilt.
    return make_experiment(
        "base_materiality_per_revenue",
        build_cfg(add_materiality=True,
                  action_characterization="Material_Immaterial_only",
                  add_sales=True,
                  signal_type="per_revenue"),
    )


def base_materiality_including_delisted():
    # base_none + the optional SASB materiality inner-merge (adds the 15 count columns,
    # filters lc to firm-years present in the materiality workbook).
    return make_experiment("base_materiality_including_delisted", build_cfg(add_materiality=True, action_characterization = "Material_Immaterial_only",  security_status="all_firms_even_delisted", min_portfolio_coverage=0.6))


def base_materiality_v_2C():
    # base_none + the optional SASB materiality inner-merge (adds the 15 count columns,
    # filters lc to firm-years present in the materiality workbook).
    return make_experiment("base_materiality_v_2C", build_cfg(add_materiality=True, action_characterization = "Material_Immaterial_only", golden_data = "v_2C"))

def base_materiality_v_2A1():
    # base_none + the optional SASB materiality inner-merge (adds the 15 count columns,
    # filters lc to firm-years present in the materiality workbook).
    return make_experiment("base_materiality_v_2A1", build_cfg(add_materiality=True, action_characterization = "Material_Immaterial_only", golden_data = "v_2A1"))



def base_4_signals():
    # base_materiality, but with the 4-signal "material" behavioural-signal characterization.
    return make_experiment("4_signals_new", build_cfg(add_materiality=True, action_characterization = "4_signals_new"))

def base_3_signals():
    # base_materiality, but with the 4-signal "material" behavioural-signal characterization.
    return make_experiment("3_signals_new", build_cfg(add_materiality=True, action_characterization = "original_matteo"))




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
    # base_materiality, but sorting on all 6 Matteo signals together (3 immaterial +
    # 3 material) in one combined quantile sort.
    return make_experiment("base_materiality_combined_3_Matteo_Signals_counts", build_cfg(add_materiality=True, action_characterization = "Combined_Material_Immaterial_3_Matteo_Signals", signal_type="counts"))






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


def base_materiality_people_only():
    # 2 signals: Material_People vs Immaterial_People. A mirror pair, so High signal_1
    # is the same portfolio as Low signal_0 (mirror_pair_summary reports it).
    return _sdg_materiality("base_materiality_people_only",
                            "Materiality_People_SDG")


def base_materiality_people_only_alpha05_mcap99_k3():
    # base_materiality_people_only + alpha_bound=0.05 (halves the per-tail trim, so LESS
    # of sum_activities gets dropped than the 0.1 default), mktcap_covered=0.99 (covers
    # more of each currency-month's cap-weighted total, so the market-cap screen keeps
    # MORE, smaller listings than 0.95), and no_simple_quantiles=3 (3 buckets instead of
    # the 7 default -- coarser sort, wider/fewer portfolios per leg). No K=7 sibling is
    # registered -- only 3 and 5 are.
    return _sdg_materiality("base_materiality_people_only_alpha05_mcap99_k3",
                            "Materiality_People_SDG",
                            alpha_bound=0.05,
                            mktcap_covered_if_filter_by_cum_market_cap=0.99,
                            no_simple_quantiles=3)


def base_materiality_people_only_alpha05_mcap99_k5():
    # Same as _k3 but no_simple_quantiles=5.
    return _sdg_materiality("base_materiality_people_only_alpha05_mcap99_k5",
                            "Materiality_People_SDG",
                            alpha_bound=0.05,
                            mktcap_covered_if_filter_by_cum_market_cap=0.99,
                            no_simple_quantiles=5)




def base_materiality_people_only_min5():
    # base_materiality_people_only + a floor of 5 initiatives in People before the
    # material/immaterial split is allowed. Read against its unfloored twin: nothing else
    # differs, so the whole change is the 1/1-type firm-years leaving the sort.
    #
    # Choose the 5 from the run's own "Materiality split floor" audit table rather than by
    # eye -- it reports, for every candidate N, the firm-years and firms lost against the
    # pct_at_max bought. On the unfloored run 18.8% of firm-years sit at ratio exactly 1.0.
    return _sdg_materiality("base_materiality_people_only_min5",
                            "Materiality_People_SDG",
                            minimum_initatives_needed_to_split_by_materiality=5)


def base_materiality_one_health():
    # 2 signals: Material_One_Health vs its immaterial mirror. Health_SDGS_Groups'
    # "One_Health" group = SDGs 3, 6, 8, 11, 14, 15.
    return _sdg_materiality("base_materiality_one_health",
                            "Materiality_One_Health_SDGS")


def base_materiality_narrow_health():
    # 2 signals: Material_Narrow_Health vs its immaterial mirror. Health_SDGS_Groups'
    # "Narrow_Health" group = SDGs 3, 6, 11.
    return _sdg_materiality("base_materiality_narrow_health",
                            "Materiality_Narrow_Health_SDGS")


def base_materiality_health_and_work():
    # 2 signals: Material_Health_and_Work vs its immaterial mirror. Health_SDGS_Groups'
    # "Health_and_Work" group = SDGs 3, 6, 8, 11.
    return _sdg_materiality("base_materiality_health_and_work",
                            "Materiality_Health_and_Work_SDGS")


def base_materiality_people_plus_prosperity_only():
    # 2 signals: Material_People_Plus_Prosperity vs its immaterial mirror.
    return _sdg_materiality("base_materiality_people_plus_prosperity_only",
                            "Materiality_People_Plus_Prosperity_SDG")


def base_materiality_people_plus_prosperity_only_alpha05_mcap99_k3():
    # base_materiality_people_plus_prosperity_only + alpha_bound=0.05, mktcap_covered=0.99
    # (see base_materiality_people_only_alpha05_mcap99_k3 for what each knob does) and
    # no_simple_quantiles=3. No K=7 sibling is registered -- only 3 and 5 are.
    return _sdg_materiality("base_materiality_people_plus_prosperity_only_alpha05_mcap99_k3",
                            "Materiality_People_Plus_Prosperity_SDG",
                            alpha_bound=0.05,
                            mktcap_covered_if_filter_by_cum_market_cap=0.99,
                            no_simple_quantiles=3)


def base_materiality_people_plus_prosperity_only_alpha05_mcap99_k5():
    # Same as _k3 but no_simple_quantiles=5.
    return _sdg_materiality("base_materiality_people_plus_prosperity_only_alpha05_mcap99_k5",
                            "Materiality_People_Plus_Prosperity_SDG",
                            alpha_bound=0.05,
                            mktcap_covered_if_filter_by_cum_market_cap=0.99,
                            no_simple_quantiles=5)


def base_materiality_pp_action(action: str, **overrides):
    """People+Prosperity material vs immaterial, restricted to ONE behavioural action.

    Registered below as base_materiality_pp_<action> for all seven non-total actions.
    `pp_` abbreviates people_plus_prosperity deliberately -- spelled out in full, plus the
    action, the name runs past 50 characters, and this is a name you type at the CLI and
    pass to the dashboard.

    No pp_total is registered: action="total" is exactly
    base_materiality_people_plus_prosperity_only, which already exists.
    """
    return _sdg_materiality(f"base_materiality_pp_{action}",
                            "Materiality_PP_Action_SDG",
                            materiality_pp_action=action, **overrides)


def base_materiality_people_plus_prosperity_vs_planet():
    # 4 signals: material/immaterial x (People+Prosperity, Planet). Covers all 17 SDGs,
    # so each signal is a share of ALL initiatives -- not comparable one-for-one with
    # base_materiality_people_plus_prosperity_only, which has a within-group denominator.
    return _sdg_materiality("base_materiality_people_plus_prosperity_vs_planet",
                            "Materiality_People_Plus_Prosperity_VS_Planet_SDG")


def base_materiality_people_plus_prosperity_vs_planet_alpha05_mcap99():
    # base_materiality_people_plus_prosperity_vs_planet + alpha_bound=0.05,
    # mktcap_covered=0.99 -- see base_materiality_people_only_alpha05_mcap99 for what each
    # knob does. Still 4 signals / 2 mirror pairs, same denominator caveat as the base.
    return _sdg_materiality("base_materiality_people_plus_prosperity_vs_planet_alpha05_mcap99",
                            "Materiality_People_Plus_Prosperity_VS_Planet_SDG",
                            alpha_bound=0.05,
                            mktcap_covered_if_filter_by_cum_market_cap=0.99)


def base_materiality_single_sdg(x: int, **overrides):
    """One SDG, material vs immaterial. `x` is the SDG number (1-17).

    Registered below as base_materiality_sdg_1 .. _sdg_17, so
    `python -m New_Pipeline.run base_materiality_sdg_13` just works. Call this directly
    for a variant the loop does not cover, e.g.
    base_materiality_single_sdg(13, signal_type="counts").
    """
    return _sdg_materiality(f"base_materiality_sdg_{x}",
                            "Materiality_single_SDG",
                            materiality_single_sdg=x, **overrides)


def base_materiality_sdg_3_min3():
    """SDG 3 alone, material vs immaterial, with a 3-initiative floor on the split.

    NOT `base_materiality_single_sdg(3, minimum_...=3)`: that helper hardcodes the run
    name to f"base_materiality_sdg_{x}", so the floored run would archive under the SAME
    name as the unfloored one and overwrite parity/artifacts/new/base_materiality_sdg_3/.
    Spelled out here so the two are separately addressable and directly comparable.

  
    """
    return _sdg_materiality("base_materiality_sdg_3_min3",
                            "Materiality_single_SDG",
                            materiality_single_sdg=3,
                            minimum_initatives_needed_to_split_by_materiality=3)


def base_materiality_5_groups_brackets():
    # 10 signals: material/immaterial x the five SDG brackets.
    return _sdg_materiality("base_materiality_5_groups_brackets",
                            "Materiality_5_groups_SDG_brackets")


def base_materiality_5_groups_brackets_counts():
    return _sdg_materiality("base_materiality_5_groups_brackets_counts",
                            "Materiality_5_groups_SDG_brackets",
                            signal_type="counts")


def base_materiality_climate_vs_each_sdg_v_2C():
    # 30 signals: material/immaterial x (Climate & Natural Capital, then each of the
    # 14 non-climate SDGs on its own).
    return _sdg_materiality("base_materiality_climate_vs_each_sdg",
                            "Materiality_Climate_Natural_Capital_vs_All_SDGS", golden_data = "v_2C")

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
    "base_none_half_open": base_none_half_open,


    "base_materiality": base_materiality,
    "base_materiality_counts":base_materiality_counts,
    "base_materiality_per_revenue": base_materiality_per_revenue,
    "base_total_initiatives_counts": base_total_initiatives_counts,
    "base_total_initiatives_per_revenue": base_total_initiatives_per_revenue,


    "base_materiality_v_2C":base_materiality_v_2C,
    "base_materiality_v_2A1":base_materiality_v_2A1,
    "base_materiality_including_delisted": base_materiality_including_delisted,
 
    "4_signals_new": base_4_signals,
    "base_materiality_combined_4_Signals_counts": base_materiality_combined_4_Signals_counts,

    "base_3_signals": base_3_signals,
    "base_materiality_combined_3_Matteo_Signals": base_materiality_combined_3_Matteo_Signals,
    "base_materiality_combined_3_Matteo_Signals_counts": base_materiality_combined_3_Matteo_Signals_counts,
   

    "base_materiality_3_groups_ppp": base_materiality_3_groups_ppp,
    "base_materiality_3_groups_ppp_counts": base_materiality_3_groups_ppp_counts,

    "base_materiality_people_only": base_materiality_people_only,
    "base_materiality_people_only_alpha05_mcap99_k3": base_materiality_people_only_alpha05_mcap99_k3,
    "base_materiality_people_only_alpha05_mcap99_k5": base_materiality_people_only_alpha05_mcap99_k5,
    "base_materiality_people_plus_prosperity_only": base_materiality_people_plus_prosperity_only,
    "base_materiality_people_plus_prosperity_only_alpha05_mcap99_k3": base_materiality_people_plus_prosperity_only_alpha05_mcap99_k3,
    "base_materiality_people_plus_prosperity_only_alpha05_mcap99_k5": base_materiality_people_plus_prosperity_only_alpha05_mcap99_k5,
    "Materiality_People_Plus_Prosperity_VS_Planet_SDG": base_materiality_people_plus_prosperity_vs_planet,
    "Materiality_People_Plus_Prosperity_VS_Planet_SDG_alpha05_mcap99": base_materiality_people_plus_prosperity_vs_planet_alpha05_mcap99,

    "base_materiality_one_health": base_materiality_one_health,
    "base_materiality_narrow_health": base_materiality_narrow_health,
    "base_materiality_health_and_work": base_materiality_health_and_work,

    "base_materiality_5_groups_brackets": base_materiality_5_groups_brackets,
    "base_materiality_5_groups_brackets_counts": base_materiality_5_groups_brackets_counts,
    "base_materiality_climate_vs_each_sdg": base_materiality_climate_vs_each_sdg,
    
    "base_materiality_climate_vs_each_sdg_counts": base_materiality_climate_vs_each_sdg_counts,
    "base_materiality_climate_vs_each_sdg_v_2C":base_materiality_climate_vs_each_sdg_v_2C,


    #Below dont work
    "sdg_3_groups_ppp": sdg_3_groups_ppp,
    "sdg_5_groups_brackets": sdg_5_groups_brackets,
    "sdg_climate_vs_each_sdg": sdg_climate_vs_each_sdg,





   
}


# ---- one entry per SDG --------------------------------------------------- #
# base_materiality_sdg_1 .. base_materiality_sdg_17: material vs immaterial for a single
# SDG. Registered in a loop rather than as 17 hand-written thunks -- run.py only needs
# EXPERIMENTS[name] to be a zero-arg callable, and sweep.register_config already adds
# entries programmatically the same way. `x=_x` binds the value at definition time; a
# bare closure over the loop variable would leave all 17 pointing at SDG 17.
def _register_single_sdg_experiments():
    # SDG_5_BRACKETS is the authority on which SDGs exist (build_cfg imports the signal
    # definitions lazily, so it is not in module scope), keeping this loop and
    # Materiality_SDG_X's validation on the same source.
    from functions.signal_design.signal_definitions import SDG_5_BRACKETS

    for x in sorted({sdg for sdgs in SDG_5_BRACKETS.values() for sdg in sdgs}):
        EXPERIMENTS[f"base_materiality_sdg_{x}"] = (
            lambda x=x: base_materiality_single_sdg(x)
        )


_register_single_sdg_experiments()


# ---- one entry per behavioural action ------------------------------------ #
# base_materiality_pp_adaptation .. base_materiality_pp_upskilling: People+Prosperity
# material vs immaterial, restricted to a single action. Registered in a loop for the same
# reason the 17 single-SDG configs are -- run.py only needs a zero-arg callable, and
# `a=a` binds the value at definition time (a bare closure over the loop variable would
# leave all seven pointing at the last action).
#
# "total" is EXCLUDED: it is byte-identical to base_materiality_people_plus_prosperity_only
# (verified -- same columns, same untagged signal names), so registering it would give one
# config two names and two archive paths.
#
# DENSITY BY ACTION -- measured on the v_2A1 workbook (72,412 firm-years), NOT estimated.
# The denominator is material + immaterial for that action across the 11 People+Prosperity
# SDGs; "usable" is firm-years holding at least one such initiative (the rest have a 0/0
# ratio and cannot be sorted at all); "@1.0" and "@0.0" are the share of USABLE firm-years
# pinned to the ratio's two atoms.
#
#   action              mean  median      usable      @1.0    @0.0   distinct
#   total              21.01      12   69,543  96.0%   21.2%    6.4%     2,751
#   advocacy_new_def   12.32       7   65,338  90.2%   26.3%    9.7%     1,631
#   advocacy_old_def   11.81       7   63,985  88.4%   25.6%   10.8%     1,551
#   upskilling          5.19       3   57,845  79.9%   36.1%   16.8%       549
#   preparation         5.02       3   56,169  77.6%   41.4%   13.1%       540
#   adaptation          3.10       1   49,414  68.2%   59.2%   10.2%       301  <-- thin
#   transformation      2.66       1   45,795  63.2%   58.8%   11.5%       334  <-- thin
#   innovation          0.40       0   13,340  18.4%   58.7%   27.3%        92  <-- degenerate
#
# READ THE BOTTOM THREE AS CONTROLS, NOT RESULTS. adaptation and transformation have a
# MEDIAN denominator of 1 -- so for over half their usable firm-years the "material share"
# is literally 1/1 or 0/1, and ~59% of them sit at exactly 1.0. innovation is worse again:
# 4.2% of all initiatives, only 18.4% of firm-years usable, and 86% of those on one of the
# two atoms with 92 distinct values in the whole panel. A quantile sort on any of the three
# is mostly cutting ties, and its High leg is a coin-flip subset of the tie block rather
# than a ranked portfolio.
#
# The top five are real sorts. advocacy_new_def / advocacy_old_def are nearly as dense as
# __total__; upskilling and preparation are usable but already ~36-41% saturated at 1.0,
# which is where minimum_initatives_needed_to_split_by_materiality starts to earn its keep.
#
# Read each run's signal_sparsity and materiality_split_floor audits before trusting any of
# these sorts, and never report an alpha without its coverage_pct neighbour.
def _register_pp_action_experiments():
    # The signal module is the authority on which actions exist, so this loop and
    # Materiality_People_Plus_Prosperity_Action_SDG's validation share one source.
    from functions.signal_design.signal_definitions_materiality import _SDG_ACTIONS

    for a in _SDG_ACTIONS:
        if a == "total":
            continue
        EXPERIMENTS[f"base_materiality_pp_{a}"] = (lambda a=a: base_materiality_pp_action(a))


_register_pp_action_experiments()
