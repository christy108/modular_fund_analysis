"""Sweep parameters — DEVELOPED (US + Canada + FF-Europe-16 + Japan).

Run it with:

    python -m New_Pipeline.sweep --params New_Pipeline.sweep_inputs.sweep_parameters_Developed --jobs 1

``--jobs 1`` IS NOT OPTIONAL HERE. See "MEMORY" below.

THE THIRD REGION FILE, alongside sweep_parameters_US.py and sweep_parameters_EU.py, but
NOT a third half of the same comparison: those two sweep one region each with the size
screen calibrated per region, whereas this one POOLS all three currency areas into a
single universe and a single cross-section. Read the two caveats under "WHAT THIS IS NOT"
before treating a cell here as the US/EU pair's global counterpart.
"""

# --------------------------------------------------------------------------- #
# WHAT THIS SWEEP IS
#
# The materiality signal cut four ways by SDG group and four ways by behaviour, each
# measured under eight parameter combinations:
#
#   SDG GROUP          All 17 SDGs | People+Prosperity | People | Planet
#   BEHAVIOUR          all (total) | advocacy_old_def | preparation | transformation
#   ----------------------------------------------------------------------------
#   mktcap coverage    0.95, 0.99
#   weighting          mktcap, equal
#   sector screen      with RE/Utilities, without RE/Utilities
#
# 4 groups x 4 behaviours x 2 x 2 x 2 = 128 cells.
#
# Quantiles are FIXED at 5 and alpha_bound at 0.05 (= keep the middle 95%), so neither is
# a grid axis -- both were requested at a single value.
#
# --------------------------------------------------------------------------- #
# ONE DESIGN PER (GROUP, BEHAVIOUR) CELL, AND WHY THE FOUR GROUPS USE FOUR DIFFERENT KEYS
#
# Each SDG group reads its OWN action cfg key. They are not interchangeable, and a value
# set on the wrong key is inert -- the run does not fail, it just sorts on the group total:
#
#   Planet             Materiality_Planet_Action_SDG      materiality_planet_action
#   People+Prosperity  Materiality_PP_Action_SDG          materiality_pp_action
#   People             Materiality_People_Action_SDG      materiality_people_action
#   All 17 SDGs        Materiality_All_Action_SDG         materiality_all_action
#
# The People and All-SDG pairs were added for this sweep (experiments.py, and
# signal_definitions_materiality.py::Materiality_People_Action_SDG /
# Materiality_All_Action_SDG). The underlying data always supported them -- the materiality
# merge loads the whole {material|immaterial} x 8 actions x 17 SDGs cube (272 columns,
# process_materiality.py::MATERIALITY_SDG_COLUMNS) -- only the wiring was missing.
#
# THE "ALL BEHAVIOURS" CELL USES action="total", which is NUMERICALLY IDENTICAL to
# Material_Immaterial_only. Verified on the workbook, all 72,412 rows, zero differences:
# `material__total` == sum(`material__total__SDG_1..17`) exactly, and likewise immaterial.
# (An earlier version of this comment claimed they differ on multi-SDG and SDG-unmapped
# initiatives. They do not -- that was reasoned from the column naming, not measured.)
#
# So this cell is a re-run of Material_Immaterial_only under region_analysis="Developed",
# and IS directly comparable to the base_materiality_* runs. Useful as a cross-check.
#
# It is written as Materiality_All_Action_SDG("total") rather than Material_Immaterial_only
# purely for NAMING: it emits Material_All_SDGs / Immaterial_All_SDGs, so all four cells of
# the All-SDGs block share one convention in run names, ledger rows and portfolio labels.
# A presentation choice, not a numerical one -- swapping it for Material_Immaterial_only
# would change the signal NAMES and nothing else.
#
# SEPARATELY, AND THIS ONE IS REAL: "total" means ALL initiatives, NOT the sum of the three
# behaviours in this sweep. The workbook carries TWO independent classifications of the same
# initiatives -- the original 3-way split used here (advocacy_old_def / preparation /
# transformation) and a newer 4-way one (adaptation / advocacy_new_def / innovation /
# upskilling). `total` equals the NEW 4-way sum exactly; the three behaviours swept here
# cover only part of it, measured on the material leg:
#
#     All 17 SDGs  90.8%      People+Prosperity  92.8%
#     People       93.6%      Planet             87.4%
#
# So the three behaviour cells DO NOT decompose the total cell -- they miss 6-13%, and the
# residual varies by group (worst on Planet). Read the total cell as "all initiatives",
# never as "the three behaviours added up".
#
# --------------------------------------------------------------------------- #
# WHAT THIS IS NOT: two things to settle before reading results
#
# 1. THE SIZE SCREEN IS POOLED, AND IT IS NOT REGION-NEUTRAL. `percent_total_mcap` ranks
#    every listing in ONE pooled distribution spanning all eight currencies, so the
#    implied floor is set by US mega-caps. Measured on base_none_Developed at 0.95, it
#    keeps 56.4% of US firms against 20.5% of Japanese and 15-22% of most European ones --
#    a 3.7x retention spread (USA vs GRC). The US share of the sample rises from 22.8% of
#    the screened universe to 42.1%; Japan falls from 24.4% to 16.3%.
#
#    So sweeping mktcap_covered on this region sweeps the REGIONAL COMPOSITION as much as
#    the size cut. If the question is "does the result survive a size screen", an absolute
#    floor (market_cap_filter="percent_stocks" with a vacuous count share and
#    floor_if_percent_stocks_true) is the numeraire-comparable axis -- see the
#    base_materiality_*_floor2bn block in experiments.py.
#
# 2. THE SIGNAL IS Z-SCORED WITH NO COUNTRY OR CURRENCY KEY. cols_standardization is
#    ["rfyear", "Industry"] (06_prepare_panel.py) -- currency was removed deliberately in
#    4ee0ad7 "stopping the normalisation by currency", when the widest arm was Europe.
#    Pooled across three regions it means a firm is scored against every other developed
#    firm in its industry-year, and mean initiatives per firm-year vary 5.0x across the 19
#    countries (PRT 55.7, FRA 51.0, USA 32.1, JPN 32.1, GBR 22.9, SWE 11.2). The High
#    bucket will tilt toward high-disclosure countries and the Low toward the Nordics and
#    Japan, and a country tilt INSIDE one region is not something the Developed factors
#    absorb. Every cell in this sweep inherits that.
#
# 3. CANADA IS THE US-LISTED SUBSET ONLY, ~60 firms (3% of the sample). The usa extract is
#    NYSE/AMEX/NASDAQ, so TSX-only firms are in no extract: 109 of LC's 599 Canadian firms
#    survive, selected on size and unevenly by sector (0% of Consumer Staples). Fine as a
#    3% slice of a pooled sample; NOT a basis for any Canada-specific claim.
#
# 4. THE FACTOR IS WIDER THAN THE SAMPLE. Ken French's Developed is 23 countries; this
#    holds 19. Australia, Hong Kong, New Zealand and Singapore are in the factor's market
#    return but in none of the three extracts, so no portfolio here can hold them.
#
# --------------------------------------------------------------------------- #
# MEMORY -- WHY --jobs 1
#
# base_none_Developed peaks at ~30 GB RSS: unlike a single-region run, ALL THREE extracts
# stay resident (currency_filter spans all eight currencies, so 03_load_universes can skip
# nothing). sweep.py's --jobs N is a ProcessPoolExecutor of full pipeline runs, so N
# workers cost ~30N GB. On a 64 GB machine that means 1. Two would sit on the ceiling and
# swap; three would not finish.
#
# mktcap_covered=0.99 IS IN THIS GRID, and it is the heavier of the two: a 99%-of-value
# screen keeps far more listings than 95%, so both the resident frames and the pickled
# node bundles grow. RUN ONE 0.99 CELL BY HAND BEFORE LAUNCHING THE WHOLE FILE.
#
# A NOTE ON 0.99 AND THE OLD EU FAILURE. sweep_parameters_EU.py excludes 0.99 because it
# "panics the Rust polars binview allocator once Europe's universe at 99% coverage crosses
# ~4.29 GB pickled". That was NOT an out-of-memory condition -- it was pack_obj storing a
# whole node bundle as ONE binary cell, which Arrow caps at u32::MAX (4 GiB), a structural
# limit independent of RAM. boundary.py::pack_obj now splits an oversized pickle across
# rows (objects <= 1 GiB are still written as a single row, byte-identical to before), so
# that specific panic is fixed -- Developed already crosses it at 0.95, where
# merge_esg_provider's bundle is 4.27 GiB, and base_none_Developed runs clean.
#
# THAT FIX IS WHY 0.99 IS ALLOWED HERE. It has NOT been verified at 0.99 on this region,
# and RAM remains a separate and real constraint. The old failure mode also destroyed
# whole sweeps rather than single cells -- a worker panic breaks the entire
# ProcessPoolExecutor pool, so finished cells never reach the ledger and results.csv comes
# out a bare header. --resume reads that ledger, so a sweep that dies this way cannot be
# resumed. Hence: test one 0.99 cell first.
# --------------------------------------------------------------------------- #

SWEEP_NAME: str = "developed_materiality_sdg_groups_x_behaviours"


# --------------------------------------------------------------------------- #
# GRID: strict cartesian product of every axis below.
#
# The SDG group and its behaviour CANNOT be two independent axes here, because each group
# reads a different cfg key -- a cartesian product of {4 characterizations} x {4 actions on
# one key} would build 16 combinations of which 12 are either duplicates or silently
# ignore the action. So the (group, behaviour) pair is enumerated as ONE axis of 16 entries
# in EXPLICIT below, and GRID is left for the axes that really are independent.
#
# Kept empty rather than deleted: sweep.py reads GRID unconditionally, and an empty dict is
# the honest statement that every combination in this sweep is spelled out.
# --------------------------------------------------------------------------- #
GRID: dict = {}


# --------------------------------------------------------------------------- #
# EXPLICIT: the full worklist, 128 cells.
#
#   16 (group, behaviour) designs x 2 mktcap x 2 weighting x 2 sector screen
#
# Each entry carries BOTH the action_characterization and the one action key that
# characterization reads, so a reader can see at a glance which knob drives which design
# and no entry depends on a FIXED value that another entry ignores.
# --------------------------------------------------------------------------- #

# (action_characterization, its action cfg key). One row per SDG group.
_GROUPS = [
    ("Materiality_All_Action_SDG", "materiality_all_action"),                  # all 17 SDGs
    ("Materiality_PP_Action_SDG", "materiality_pp_action"),                    # 1-5, 8-11, 16, 17
    ("Materiality_People_Action_SDG", "materiality_people_action"),            # PEOPLE_PLANET_PROSPERITY["People"]
    ("Materiality_Planet_Action_SDG", "materiality_planet_action"),            # 6, 7, 12, 13, 14, 15
]

# "total" is the ALL-BEHAVIOURS cell -- see the note above on why it is action="total"
# rather than Material_Immaterial_only.
_BEHAVIOURS = ["total", "advocacy_old_def", "preparation", "transformation"]

# The sector screen, as a PAIR of knobs moved together. build_cfg defaults both to True
# (drop Real Estate and Utilities); False adds them back. Paired rather than crossed: the
# request is "with RE/Utilities" vs "without", not four sector variants.
_SECTORS = [
    {"drop_real_estate": False, "drop_utilities": False},   # WITH Real Estate + Utilities
    {"drop_real_estate": True, "drop_utilities": True},     # WITHOUT (the build_cfg baseline)
]

EXPLICIT: list[dict] = [
    {
        "action_characterization": ac,
        action_key: behaviour,
        "portfolio_weighting": w,
        "mktcap_covered_if_filter_by_cum_market_cap": m,
        **sectors,
    }
    for ac, action_key in _GROUPS
    for behaviour in _BEHAVIOURS
    for w in ("mktcap", "equal")
    for m in (0.95, 0.99)
    for sectors in _SECTORS
]


# --------------------------------------------------------------------------- #
# FIXED: merged into every combination. An EXPLICIT entry wins for the same key.
# --------------------------------------------------------------------------- #
FIXED: dict = {
    # THE REGION. Drives currency_filter to all eight listing currencies, region_filter to
    # the three MacroRegions, convert_to_USD=True and fama_factor_region="Developed", plus
    # the 19-country loc whitelist in 01_process_lc.py::_REGION_LOCS. Not the build_cfg
    # baseline (that is United_States), so it and its derived keys appear in every run name.
    "region_analysis": "Developed",

    # ---- the two single-valued axes from the request ---------------------- #
    # Sort granularity: 5-way only (the US/EU files sweep 3 and 5; this one was requested
    # at 5). NOT baseline, so it appears in every run name.
    "no_simple_quantiles": 5,

    # "Alpha 0.95" = keep the middle 95% of sum_activities, i.e. a 0.05 trim PER TAIL,
    # which is what alpha_bound means here. Also the build_cfg baseline, so it does not
    # reach the cfg diff and appears in no run name.
    "alpha_bound": 0.05,

    # ---- materiality: what makes these designs possible at all ------------ #
    "add_materiality": True,
    "materiality_version": 2,

    # No materiality-split floor: a firm-year splits into material/immaterial however few
    # initiatives it has. Baseline.
    "minimum_initatives_needed_to_split_by_materiality": 0,

    # Filter 2 ONLY (drop suspicious gvkeys), matching the US/EU sweeps. Chosen over "all",
    # which would also switch on the ">= 3 fiscal years" survivorship screen.
    # CONSEQUENCE, same as in those files: filter 3
    # (min_initatives_annual_reports_if_execute_3_filters_true) is SKIPPED under this mode
    # (01_process_lc.py gates it on _all3), so that knob has NO EFFECT here at any value.
    "execute_3_filters": "suspicious_only",

    # The thin-portfolio gate, at baseline. A High/Low leg is HIDDEN unless it holds at
    # least min_stocks_per_portfolio names in at least min_portfolio_coverage of formation
    # months. Pooling three regions makes the sample LARGER than either single-region
    # sweep, so this should bind less often here -- but the narrow designs (People x one
    # action) are the thinnest signals in the file and are where to check it first.
    "min_stocks_per_portfolio": 25,
    "min_portfolio_coverage": 0.8,

    # NOT pinned, deliberately: portfolio_weighting, mktcap_covered_if_filter_by_cum_market_cap,
    # drop_real_estate and drop_utilities are all EXPLICIT axes -- a FIXED value would be
    # overridden on all 128 cells and would only mislead a reader of this file.
    # max_portfolio_weight_if_portfolio_weighting_equal likewise stays at the build_cfg
    # baseline (0.10, and applied only under portfolio_weighting="mktcap").
    # start_year / end_year are absent: this is the full 2016-2024 sample.
}
