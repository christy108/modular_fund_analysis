"""Sweep definition — pure data, no logic. Run with:

    python -m New_Pipeline.sweep --params New_Pipeline.sweep_inputs.sweep_parameters_coop_index

Same contract as every file in ``New_Pipeline/sweep_inputs/``: every key in ``GRID`` /
``EXPLICIT`` / ``FIXED`` must be a real ``build_cfg`` knob (baseline dict at
``New_Pipeline/experiments.py:38``), and the sweep validates every combination through
``build_cfg(**overrides)`` BEFORE the first pipeline run, so a typo raises in the first
second rather than forty minutes in.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# SWEEP_NAME: names this sweep's output folder, `sweep_output/<UTC stamp>_<name>/`.
# Change it to start a NEW sweep; re-running with the same name RESUMES the existing
# folder (that is what makes --resume work). `--new-run` forces a fresh folder anyway,
# and `--out DIR` overrides the whole thing.
#
# Previous worklists in this file, for reference. Neither is resumed by this one -- the
# grids differ, so --resume would have nothing to match. Both stay readable in their own
# sweep_output/ folders:
#   "coop_index"                        3 regions x per-region mcap x 2 alpha x 2 weighting,
#                                       K=5. Only the 3 Developed cells ever ran.
#   "coop_index_no_alpha_bound_filter"  the same 3 regions at a fixed alpha_bound=0.0,
#                                       K=5. Never launched.
# --------------------------------------------------------------------------- #
SWEEP_NAME: str = "coop_index_developed_K5_K10_startyears"


# --------------------------------------------------------------------------- #
# WHAT THIS SWEEP IS
#
# ONE signal -- prop_cooperation, the LC column used directly as the sort -- on ONE
# region, crossed with the market-cap screen, the alpha-bound trim and the weighting
# scheme, at a DECILE sort.
#
#   Developed x 3 mcap x 3 alpha x 2 weighting x 3 start_year x 2 K = 108 cells
#
# At ~1.1 min/cell (measured on the completed mcap-0.99 cells) that is roughly 2 hours at
# JOBS=1. The 1.0 cells will be slower than that mean -- they carry every listing.
#
# THE SIGNAL. action_characterization="prop_cooperation" maps the single LC column
# prop_cooperation to one group, and signal_type="counts" makes signal_0 that column
# verbatim -- nothing aggregated, ratio'd or rescaled. Note "counts" names the BRANCH
# (take the level, do not divide by sum_activities), not the data: the signal is a
# proportion. That is also where the output label "Prop_Cooperation_counts" comes from.
# One signal, so there is no signal_1 mirror and no High/Low sign pairing across rows.
#
# VINTAGE-BOUND. prop_cooperation ships only in the HQ extract, so golden_data is pinned
# to "HQ_LC_dataseet_v_1_1O1" in FIXED and build_cfg raises on any other vintage. That
# vintage carries no SASB matching file, so add_materiality is False. CONSEQUENCE: these
# cells are not comparable with any materiality sweep -- they differ in signal, in sample
# AND in the underlying extract.
#
# ---- BOTH K VALUES ARE FEASIBLE, measured ---------------------------------- #
# Read off the Developed cells that have actually run (mcap 0.99, K=5, start_year 2016):
# sortable assets per month run 942 (2017) to 1,807 (2023), thinnest month 942. That is
# 188 names per bucket at K=5 and 94 at K=10, both comfortably clear of the
# min_stocks_per_portfolio=25 gate in every month. The looser screens only enlarge the
# universe. Post-standardisation tie blocks on this signal measure 1.5-2.3%, under the
# 1/K = 10% at K=10 (and 20% at K=5) where a cutpoint could land inside a tie block and
# collapse a bucket. The early start_year=2012 cells are the thinnest cut here -- LC
# coverage at fiscal 2012 is ~1,479 Developed-region firms against 2,426 at 2016, about
# 61% -- which still leaves roughly 50+ names per decile after the universe merge's
# measured ~34% retention. The gate is not the binding constraint anywhere in this file.

# ---- WHAT start_year=2012 AND 2020 ACTUALLY BUY ---------------------------- #
# start_year floors BOTH the LC fiscal year and the universe date range, and the two have
# different limits.
#
# 2012 IS PARTLY UNAVAILABLE. The cached universes do not all reach back that far:
#   data/usa_universe_all_secstat.parquet        2013-01-02 .. 2024-12-31
#   data/japan_universe_all_secstat.parquet      2013-01-04 .. 2024-12-30
#   data/row_universe_all_secstat_new.parquet    2009-01-02 .. 2026-09-03
# So US and Japan -- two of the three legs of Developed -- have NO return data before
# 2013, and the 2012 cells get Europe-only months at the very start. The point-in-time lag
# softens this (fiscal 2012 forms portfolios in Jul-Dec 2013 / Jan-Jun 2014, which IS
# covered), so the practical effect is a thin, Europe-weighted first few months rather
# than an empty one. Read the earliest months of a 2012 cell as a different regional mix,
# not just a longer sample.
#
# 2020 IS SHORT. With end_year=2024 it leaves fiscal years 2020-2024, which the lag maps
# to roughly mid-2021 through the end of the return data -- on the order of 42 formation
# months. That is thin for a factor regression, and the 24-month rolling-alpha panel gets
# only ~18 points. Treat the 2020 alphas as indicative, not as a second independent test.
#
# The Fama-French Developed factors are not a constraint: 3-factor 199007..202602,
# 5-factor and momentum 199007/199011..202608, all well before any start_year here.
#
# ---- READ THIS BEFORE LAUNCHING: 0.999 AND 1.0 ARE UNCHARTED --------------- #
# mktcap_covered=1.0 is NOT a 100% screen, it is NO screen. The rule keeps listings where
# cumulative_mktcap > (1 - mktcap_covered) * total_mktcap (process_data.py:261), so at 1.0
# the test is cumulative_mktcap > 0, which every listing with a positive cap passes. 0.999
# removes only the very smallest 0.1% of aggregate value. Both therefore carry FAR more
# listings than 0.99, and listings -- not value -- are what drives memory: at 0.95 the
# screen already discards ~65% of listings on cap concentration alone.
#
# Only 0.99 has ever been run on Developed (3 cells, status ok). 0.999 and 1.0 have not.
# sweep_parameters_Developed.py documents why that matters: merge_esg_provider's bundle is
# already 4.27 GiB at 0.95, pack_obj used to cap a single Arrow cell at u32::MAX (4 GiB)
# and panicked the Rust allocator when crossed, and although pack_obj now splits an
# oversized pickle across rows, RAM is a separate and still-real constraint. A worker
# panic breaks the WHOLE ProcessPoolExecutor pool, so finished cells never reach the
# ledger, results.csv comes out a bare header, and --resume has nothing to read.
#
# So: run ONE 1.0 cell alone before launching the file, and keep JOBS at 1 until it has
# been seen to pass.
#
# EXECUTION ORDER is the GRID cartesian product below, NOT the SORT_BY/VALUE_ORDER at the
# foot of this file -- those only sort results.pdf/.csv once cells have finished. The mcap
# axis is listed 0.99 first deliberately: the six VERIFIED cells run and reach the ledger
# before the sweep touches 0.999 or 1.0, so if a loose-screen cell dies there are already
# six complete results on disk and --resume can pick up from them.
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# GRID: expanded to its full cartesian product.
#
# A genuine product this time, unlike the earlier three-region version of this file: with
# ONE region the market-cap screen is no longer paired to the region, so all three axes
# cross cleanly and nothing needs hand-listing in EXPLICIT.
#
#   3 mcap x 3 alpha x 2 weighting x 3 start_year x 2 K = 108 cells
# --------------------------------------------------------------------------- #
GRID: dict[str, list] = {
    # Market-cap coverage. 0.99 is the only one verified on this region; see the header.
    # 1.0 is effectively no screen at all.
    "mktcap_covered_if_filter_by_cum_market_cap": [0.99, 0.999, 1.0],
    # Percentile trim on sum_activities, applied PER TAIL (lower_exclude = upper_exclude =
    # alpha_bound / 2). 0.05 is the build_cfg baseline, so those cells carry no
    # alpha_bound in their run name; 0.0 and 0.1 do and will appear in every name they
    # produce.
    #
    # 0.0 IS NOT THE SAME AS NO TRIM, and the difference is silent. use_alpha_bound stays
    # True (baseline), so node 02 still calls
    # filter_sum_activities_by_fiscal_year_quantiles(lower_exclude=0.0, upper_exclude=0.0),
    # and that function keeps a STRICT open interval: (x > q_lower) & (x < q_upper). At 0.0
    # those quantiles are the per-fiscal-year MIN and MAX of sum_activities, so every
    # firm-year sitting exactly at either extreme is still dropped -- 1,177 of 43,397
    # (2.7%) on the 2016-2024 sample, median denominator 2. For a genuine no-trim the knob
    # is "use_alpha_bound": False, which skips the call and drops 0 rows.
    "alpha_bound": [0.05, 0.10],
    # Cap-weighted first (also the build_cfg baseline), then equal-weighted.
    "portfolio_weighting": ["mktcap", "equal"],
    # Sample start. 2016 is the build_cfg baseline, so those cells carry no start_year in
    # their run name; 2012 and 2020 do. See the coverage note in the header -- these are
    # NOT three equivalent windows. end_year stays 2024 for all three (FIXED below).
    "start_year": [2012, 2016, 2020],
    # Sort granularity: quintiles and deciles.
    "no_simple_quantiles": [5, 10],
}


# --------------------------------------------------------------------------- #
# EXPLICIT: nothing to hand-list -- GRID above is the whole worklist.
# --------------------------------------------------------------------------- #
EXPLICIT: list[dict] = []


# --------------------------------------------------------------------------- #
# FIXED: merged into EVERY combination. An entry in GRID/EXPLICIT wins over FIXED for the
# same key.
# --------------------------------------------------------------------------- #
FIXED: dict = {
    # ---- THE REGION -------------------------------------------------------- #
    # The pooled US + Canada(US-listed) + FF-Europe-16 + Japan arm, priced against Ken
    # French's Developed factors. build_cfg derives convert_to_USD=True and
    # fama_factor_region="Developed" from it (experiments.py:385 onward). Momentum ships
    # for Developed (data/FAMA/Developed_Momentum_Factor.csv), so the baseline
    # Add_Momentum_Factor=True holds and both specifications carry it -- FF3 becomes
    # Carhart 4-factor and FF5 the 6-factor model.
    "region_analysis": "Developed",

    # ---- THE DESIGN -------------------------------------------------------- #
    # All three keys are load-bearing and build_cfg enforces them together:
    # prop_cooperation requires signal_type="counts" (under "weights" the signal would be
    # sum_with_0 / sum_activities == 1.0 for every firm -- a constant, unsortable) and
    # requires this vintage (the column exists nowhere else).
    "golden_data": "HQ_LC_dataseet_v_1_1O1",
    "action_characterization": "prop_cooperation",
    "signal_type": "counts",

    # NOT the "Sum_All_Signals" baseline, and this is deliberate. It does not touch the
    # signal -- under "counts" nothing is divided -- it picks what `sum_activities` is,
    # and sum_activities is the variable the alpha-bound trim cuts on. Left at the
    # baseline, sum_activities would BE prop_cooperation (the single group's only column),
    # so the trim would drop the top and bottom alpha/2 of the SIGNAL within each fiscal
    # year -- deleting exactly the firm-years the High/Low sort is built from, before the
    # sort runs. Pointed at n_predicted_initiatives it trims total activity instead.
    #
    # THAT IS STILL NOT INDEPENDENT OF THE SIGNAL, and with alpha now an axis it matters.
    # prop_cooperation IS coop_initiatives_count / total_initiatives_count (verified
    # exactly, on 100% of non-null rows), and total_initiatives_count is what
    # n_predicted_initiatives renames to here -- so the trim cuts on the signal's own
    # DENOMINATOR. That is a deliberate precision floor, not a bug: a firm-year with 2
    # total initiatives can only score 0, 0.5 or 1, and the repo already applies the same
    # logic in minimum_initatives_needed_to_split_by_materiality.
    #
    # But the trim is SYMMETRIC, and only the lower half is a precision argument. At
    # alpha=0.05 it removes 2,277 firm-years with median denominator 2 and just FOUR
    # distinct signal values (the floor -- what you want gone), and also 1,114 firm-years
    # with median denominator 86 and 766 distinct values (the best-measured ratios in the
    # sample, with no precision rationale for dropping them). At alpha=0.10 the upper tail
    # is 2,210 firm-years. Read the alpha axis accordingly: it varies measurement
    # precision at the bottom AND discards well-measured high-activity firms at the top,
    # so it is not a clean "is this robust to an arbitrary trim" check.
    "signal_denominator": "Sum_All_Initiatives",

    # No SASB workbook: the signal is a raw LC column, and no
    # Matched_SASB_GOLDEN_long_matchings_* file exists for this vintage anyway
    # (load_materiality builds that filename from golden_data).
    "add_materiality": False,

    # The market-cap screen's MODE. The coverage values in GRID are read only under
    # "percent_total_mcap"; this is the build_cfg baseline, pinned so the coverage axis
    # cannot be silently inert.
    "market_cap_filter": "percent_total_mcap",

    # ---- everything below EQUALS the build_cfg baseline -------------------- #
    # None of it reaches the cfg diff, so none of it pollutes a run name. Pinned anyway:
    # this file is the record of what the sweep was, and "it inherited whatever
    # experiments.py said that week" is not a record. That cuts both ways -- a pin
    # OVERRIDES the baseline, so when experiments.py moves, a pin left behind silently
    # freezes the sweep at the old value. Re-check this block against build_cfg() before
    # launching, not after.
    # start_year is a GRID axis, not pinned here. end_year is held at the baseline for all
    # three windows, so the three start years are nested right-aligned samples.
    "end_year": 2024,

    # Filter 2 only (drop suspicious gvkeys), not "all" -- which would additionally switch
    # on the ">= 3 fiscal years of data" survivorship screen.
    #
    # It also keeps the annual-report floor OFF, which matters more than usual on this
    # vintage: under "all", 01_process_lc raises here by design, because the HQ extract
    # stores report_type lowercase ("annual report") while the filter compares to
    # "Annual Report", so the cut would silently match zero rows.
    "execute_3_filters": "suspicious_only",

    # The thin-portfolio gate, at baseline. A High/Low leg is HIDDEN unless it holds at
    # least min_stocks_per_portfolio names in at least min_portfolio_coverage of formation
    # months. Not binding here -- see the K=10 feasibility note in the header.
    "min_stocks_per_portfolio": 25,
    "min_portfolio_coverage": 0.8,

    # Not pinned, deliberately: mktcap_covered_if_filter_by_cum_market_cap, alpha_bound,
    # portfolio_weighting, start_year and no_simple_quantiles are the GRID axes, so a
    # FIXED value would be overridden on all 108 cells and would only mislead a reader.
    # max_portfolio_weight_if_portfolio_weighting_equal is likewise absent: it stays at the
    # build_cfg baseline (0.10 single-name ceiling), which applies only under
    # portfolio_weighting="mktcap" and is silently ignored under "equal".
}


# --------------------------------------------------------------------------- #
# Output settings
# --------------------------------------------------------------------------- #

# Rebuild results.pdf / results.csv from the ledger every N completed experiments. The
# ledger is appended after EVERY experiment regardless, so this only trades how fresh the
# two derived files are against the seconds each rebuild costs. Both are ALWAYS rebuilt
# once more when the sweep finishes (or is interrupted).
PDF_EVERY: int = 4

# Everything the sweep writes lives under here, relative to the repo root.
OUTPUT_DIR: str = "sweep_output"


# --------------------------------------------------------------------------- #
# How many experiments run at once (`--jobs N` overrides).
#
# ONE. Each worker is a separate PROCESS holding its own copy of the Golden panel and the
# Compustat universe, and two thirds of this file sits at market-cap screens heavier than
# anything previously run on Developed -- see the header. Raise it with --jobs 2 only
# after a 1.0 cell has completed.
# --------------------------------------------------------------------------- #
JOBS: int = 1


# --------------------------------------------------------------------------- #
# Presentation order for results.pdf / results.csv.
#
# The ledger stays in completion order (append-only), but the PDF and CSV are SORTED by
# these keys before being written -- and by the same function, so "CSV row N describes PDF
# page N" holds.
# --------------------------------------------------------------------------- #
SORT_BY: list[str] = [
    # Outermost: the sample window, so each start_year reads as its own block rather than
    # interleaving three different samples.
    "start_year",
    # Then the sort granularity, so a window's K=5 pages precede its K=10 pages.
    "no_simple_quantiles",
    # Then the weighting scheme, so the cap-weighted block sits above the
    # equal-weighted one.
    "portfolio_weighting",
    # Then the trim, so a given weighting's three alphas are consecutive pages.
    "alpha_bound",
    # Innermost: the market-cap screen.
    "mktcap_covered_if_filter_by_cum_market_cap",
]

VALUE_ORDER: dict[str, list] = {
    # Cap-weighted first, matching the ordering the other sweep files use.
    "portfolio_weighting": ["mktcap", "equal"],
    # Tightest screen first, matching GRID's order, so a page's position in the PDF
    # follows the same axis order the cells ran in.
    "mktcap_covered_if_filter_by_cum_market_cap": [0.99, 0.999, 1.0],
}
