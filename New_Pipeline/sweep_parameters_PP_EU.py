"""What ``python -m New_Pipeline.sweep --params New_Pipeline.sweep_parameters_PP_EU``
should run -- pure data, no logic.

Same contract as the Planet files (sweep_parameters_EU.py): every key in ``GRID`` /
``EXPLICIT`` / ``FIXED`` must be a real ``build_cfg`` knob (baseline dict at
``New_Pipeline/experiments.py:38``), and the sweep validates every combination through
``build_cfg(**overrides)`` BEFORE the first pipeline run, so a typo raises in the first
second rather than forty minutes in.

THIS FILE IS THE **EUROPE** HALF of the PEOPLE+PROSPERITY worklist. Its mirror is
sweep_parameters_PP_US.py. The two are deliberately identical apart from
``region_analysis`` and the market-cap axis -- keep any edit here in step with that file,
or the regions stop being comparable.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# SWEEP_NAME: names this sweep's output folder, `sweep_output/<UTC stamp>_<name>/`.
# Change it to start a NEW sweep; re-running with the same name RESUMES the existing
# folder (that is what makes --resume work).
# --------------------------------------------------------------------------- #
SWEEP_NAME: str = "eu_material_pp_behaviours_momentum"


# --------------------------------------------------------------------------- #
# WHAT THIS SWEEP IS
#
# EUROPE half: People+Prosperity on its own and at each of three behavioural cuts,
# crossed with the weighting scheme, the sort granularity and the market-cap screen, on the
# FULL 2016-2024 sample.
#
#   4 signals x 2 weighting schemes x 2 quantile counts x 2 mcap screens
#   = 32 runs  (24 from GRID, 8 from EXPLICIT)
#
# THE PEOPLE+PROSPERITY COUNTERPART of sweep_parameters_EU.py, which runs the same
# shape on the two Planet widths. Same axes, same FIXED block -- with ONE deliberate
# difference, the sector screen (see FIXED).
#
# THE SIGNALS. All four are one-group MIRROR PAIRS: signal_0 is a material SHARE of the
# group's SDGs and signal_1 = 1 - signal_0, so High on one leg is Low on the other and the
# two High-Low spreads are exact negatives. On the risk panel that shows up as one green
# row and one red row per pair, which is expected, not a bug -- the colour is carrying the
# sign.
#
#   Material_People_Plus_Prosperity                   SDGs 1-5, 8-11, 16, 17, all actions
#   Material_Advocacy_Old_Def_People_Plus_Prosperity  \
#   Material_Preparation_People_Plus_Prosperity        >  the same SDGs, one action each
#   Material_Transformation_People_Plus_Prosperity    /
#
# The three actions are the ORIGINAL "Matteo" 3-way split, so they partition one taxonomy
# rather than being three unrelated picks -- the same three the Planet sweep uses, which is
# what makes the two directly comparable on the behaviour axis.
# TRAP: advocacy_old_def is the Matteo advocacy leg; advocacy_new_def belongs to the newer
# 4-way split and is NOT here.
#
# ONE DENOMINATOR CAVEAT. Every signal here is a SINGLE group, so each one's denominator is
# its OWN group's material + immaterial count -- "material share WITHIN this SDG set and
# this action", not "share of all initiatives". The four therefore do NOT share a
# denominator: the whole-group signal is the widest, the other three are strictly thinner
# slices of it.
#
# DENSITY BY ACTION -- measured on the v_2A1 workbook (72,412 firm-years), NOT estimated.
# "usable" is firm-years holding at least one such initiative (the rest are a 0/0 ratio and
# cannot be sorted at all); "@1.0"/"@0.0" are the share of USABLE firm-years at the ratio's
# two atoms.
#
#   action              mean  median      usable      @1.0    @0.0   distinct
#   (whole group)      21.01      12   69,543  96.0%   21.2%    6.4%     2,751
#   advocacy_old_def   11.81       7   63,985  88.4%   25.6%   10.8%     1,551
#   preparation         5.02       3   56,169  77.6%   41.4%   13.1%       540
#   transformation      2.66       1   45,795  63.2%   58.8%   11.5%       334  <-- thin
#
# THE ACTION RANKING IS THE INVERSE OF THE PLANET SWEEP'S. There, transformation is the
# DENSEST action (79.1% usable, median 3) and advocacy the middle; here transformation is
# the thin control (63.2%, MEDIAN 1 -- so for over half its usable firm-years the material
# share is literally 0/1 or 1/1, and 58.8% sit at exactly 1.0) and advocacy_old_def is
# nearly as usable as the whole group. That is the substantive contrast the two sweeps
# exist to draw, not an artefact: People+Prosperity initiatives are largely communication
# and funding, Planet ones largely asset and procedure change.
#
# Read each run's signal_sparsity and materiality_split_floor audits before trusting any of
# these sorts, and never report an alpha without its coverage_pct neighbour.
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# GRID: expanded to its full cartesian product.
#
#   1 design x 3 behaviours x 2 weighting x 2 quantiles x 2 mcap = 24 cells
#   (+ the 8 whole-group cells in EXPLICIT below = 32 in total)
# --------------------------------------------------------------------------- #
GRID: dict[str, list] = {
    # THE SIGNALS (three of the four): People+Prosperity crossed with each behaviour.
    # The fourth -- the group on its own -- is in EXPLICIT below.
    "action_characterization": [
        "Materiality_PP_Action_SDG",             # SDGs 1-5, 8-11, 16, 17
    ],
    # NO "total" here. The group on its own is its OWN design
    # (Materiality_People_Plus_Prosperity_SDG) and lives in EXPLICIT, because it does not
    # read this key and so cannot be crossed with it -- see the note there.
    "materiality_pp_action": ["advocacy_old_def", "preparation", "transformation"],
    # Cap-weighted first (also the build_cfg baseline), then equal-weighted.
    "portfolio_weighting": ["mktcap", "equal"],
    # Sort granularity: coarse 3-way and finer 5-way.
    "no_simple_quantiles": [3, 5],
    # Market-cap coverage of the screen. 0.85/0.95, NOT 0.95/0.99 -- 0.99 panics the polars
    # binview allocator on Europe's universe (a hard ~4.29 GB pickling ceiling, not a RAM
    # question) and has never once completed. Same axis as sweep_parameters_EU.py.
    "mktcap_covered_if_filter_by_cum_market_cap": [0.85, 0.95],
}

# --------------------------------------------------------------------------- #
# EXPLICIT: hand-picked combinations, appended after the grid, used verbatim.
#
# THE FOURTH SIGNAL: People+Prosperity ON ITS OWN, no action split.
#
# WHY NOT IN GRID. Materiality_People_Plus_Prosperity_SDG is its own
# action_characterization and never reads materiality_pp_action. GRID is a strict cartesian
# product -- the runner has no skip rule, and it dedupes on the override dict rather than on
# the resulting signal -- so listing it there would cross it with all three actions and
# build THREE IDENTICAL runs: 40 cells instead of 32, 8 of them duplicate reruns under
# different names. Listed here it costs nothing and stays one clean 8-cell block.
#
# The three axes below are exactly GRID's, so all four signals are measured the same eight
# ways. FIXED supplies the region and the sector screen here too, so the universe is
# identical across all 32 cells and this signal is a clean reference line.
# --------------------------------------------------------------------------- #
EXPLICIT: list[dict] = [
    {"action_characterization": "Materiality_People_Plus_Prosperity_SDG",
     "portfolio_weighting": w, "no_simple_quantiles": k,
     "mktcap_covered_if_filter_by_cum_market_cap": m}
    for w in ("mktcap", "equal")
    for k in (3, 5)
    for m in (0.85, 0.95)
]

FIXED: dict = {
    # ---- everything here EQUALS the build_cfg baseline -------------------- #
    # None of it reaches the cfg diff, so none of it pollutes a run name. Pinned anyway:
    # this file is the record of what the sweep was, and "it inherited whatever
    # experiments.py said that week" is not a record.
    #
    # That cuts both ways: a pin OVERRIDES the baseline, so when experiments.py moves,
    # a pin left behind silently freezes the sweep at the old value. Re-check this block
    # against build_cfg() before launching, not after.

    # THE REGION. Drives currency_filter=["EUR","GBP","CHF","NOK","SEK","DKK"],
    # region_filter=["Europe"], convert_to_USD=True and fama_factor_region="Europe"
    # (experiments.py:385). NOT at the build_cfg baseline, so it and its two derived keys
    # appear in every run name here.
    "region_analysis": "Europe",

    # ---- THE SECTOR SCREEN: the one line that differs from the Planet sweep ---------- #
    # Real Estate and Utilities stay DROPPED here. Both equal the build_cfg baseline, so
    # neither reaches the cfg diff and neither appears in a run name -- pinned anyway,
    # because this is the knob the Planet sweep deliberately inverts and "it inherited
    # whatever experiments.py said that week" is not a record.
    #
    # CONSEQUENCE: these results are NOT directly comparable with the Planet ones cell for
    # cell. The two sweeps differ in the UNIVERSE as well as the signal -- Planet keeps both
    # sectors because utilities are the energy SDG (7) and real estate the built-environment
    # side of SDGs 11/12, exposure a Planet sort exists to measure.
    "drop_real_estate": True,
    "drop_utilities": True,

    # Percentile trim on sum_activities (the firm-year's total initiative count), applied
    # per tail. Requested at 0.05, which is also the current baseline, so it does not
    # reach the cfg diff and appears in no run name.
    "alpha_bound": 0.05,

    # The materiality inner join is what makes a materiality design possible at all --
    # signal_0 is a MATERIAL share, read off the SASB workbook. Not optional here.
    "add_materiality": True,
    "materiality_version": 2,

    # NO materiality-split floor ("min initiatives 0"): a firm-year is split into
    # material/immaterial however few initiatives it has. Requested, and also baseline.
    "minimum_initatives_needed_to_split_by_materiality": 0,

    # Filter 2 ONLY (drop suspicious gvkeys). Chosen over "all", which would additionally
    # switch on "keep firms with >= 3 fiscal years of data" -- a survivorship screen.
    # CONSEQUENCE: filter 3, the min_initatives_annual_reports_if_execute_3_filters_true
    # floor, is SKIPPED under this mode (01_process_lc.py:398 gates it on `_all3`). That
    # knob therefore has NO EFFECT in this sweep at any value.
    "execute_3_filters": "suspicious_only",

    # The thin-portfolio gate, at baseline. A High/Low leg is HIDDEN unless it holds at
    # least min_stocks_per_portfolio names in at least min_portfolio_coverage of formation
    # months. Under cap weighting this is a count test on a weighted portfolio -- the
    # effective N is lower than the raw count implies.
    "min_stocks_per_portfolio": 25,
    "min_portfolio_coverage": 0.8,

    # portfolio_weighting, no_simple_quantiles and
    # mktcap_covered_if_filter_by_cum_market_cap are NOT pinned here -- they are GRID
    # axes, so a FIXED value would be overridden on all 24 cells and would only mislead a
    # reader of this file. max_portfolio_weight_if_portfolio_weighting_equal is likewise
    # absent: it stays at the build_cfg baseline (0.10 = 10% single-name ceiling), which
    # applies only when portfolio_weighting="mktcap" and is silently ignored under
    # "equal". start_year / end_year are also absent: this sweep is the FULL baseline
    # 2016-2024 sample, not the pre/post-2020 split.
}

# --------------------------------------------------------------------------- #
# Output settings
# --------------------------------------------------------------------------- #

# Rebuild results.pdf / results.csv from the ledger every N completed experiments.
PDF_EVERY: int = 4

# Everything the sweep writes lives under here, relative to the repo root.
OUTPUT_DIR: str = "sweep_output"


# --------------------------------------------------------------------------- #
# How many experiments run at once (`--jobs N` overrides). Each worker is a separate
# PROCESS running one full pipeline, so this scales with cores AND with RAM. 2 is
# demonstrated on this machine (10 cores / 64 GB).
#
# NOTE this requires cfg.write_debug_csv=False (the default). Those dumps go to FIXED paths
# under ./data/debug/, so parallel workers would clobber each other's files. Do NOT run two
# params modules concurrently at JOBS=2 each -- that is four pipelines, each holding its own
# copy of the Golden panel and the Compustat universe. run_sweeps.sh queues them instead.
# --------------------------------------------------------------------------- #
JOBS: int = 2


# --------------------------------------------------------------------------- #
# Presentation order for results.pdf / results.csv.
# --------------------------------------------------------------------------- #
SORT_BY: list[str] = [
    # Outermost: the design, so the whole-group block precedes the behavioural ones.
    "action_characterization",
    # Then the behavioural action, so the three cuts read in taxonomy order.
    "materiality_pp_action",
    # Then the weighting scheme, so each signal's cap-weighted block sits directly above
    # its equal-weighted block.
    "portfolio_weighting",
    # Then the sort granularity.
    "no_simple_quantiles",
    # Innermost: the market-cap screen, so each signal/weighting/K triple puts its two mcap
    # pages side by side -- the robustness comparison this axis exists to make.
    "mktcap_covered_if_filter_by_cum_market_cap",
]

VALUE_ORDER: dict[str, list] = {
    # The WHOLE-GROUP signal first, then its three behavioural cuts -- so the PDF reads
    # "here is People+Prosperity, and here is what each behaviour does to it".
    "action_characterization": [
        "Materiality_People_Plus_Prosperity_SDG",  # Material_People_Plus_Prosperity
        "Materiality_PP_Action_SDG",               # the same SDGs, one action at a time
    ],
    # The Matteo 3-way split in the taxonomy's own order -- not a density order, so the
    # three read as one split. None on the whole-group signal, which _sort_key ranks after
    # these rather than raising.
    "materiality_pp_action": ["advocacy_old_def", "preparation", "transformation"],
    # Cap-weighted first, matching Kevin's own ordering ("Mkt cap weighted" then
    # "And EQ weights").
    "portfolio_weighting": ["mktcap", "equal"],
}
