"""Sweep parameters — DEVELOPED, NET MATERIALITY PER REVENUE.

Run it with:

    python -m New_Pipeline.sweep --params New_Pipeline.sweep_parameters_Developed_net_revenue --jobs 1

``--jobs 1`` IS NOT OPTIONAL. ~30 GB RSS per worker on a 64 GB machine; see "MEMORY" below.

The revenue-scaled twin of sweep_parameters_Developed_net.py. Same region, same 16
(SDG group x behaviour) designs, same FIXED knobs -- the DENOMINATOR is the only thing that
changes, so the two files are directly comparable cell for cell at mktcap x 0.99.
"""

# --------------------------------------------------------------------------- #
# WHAT THIS SWEEP IS
#
#   SIGNAL             net materiality per revenue:  (material - immaterial) / sale_usd
#   SDG GROUP          All 17 SDGs | People+Prosperity | People | Planet
#   BEHAVIOUR          all (total) | advocacy_old_def | preparation | transformation
#   ------------------------------------------------------------------------
#   mktcap coverage    FIXED: 0.99          (the net sweep swept 0.95 and 0.99)
#   weighting          FIXED: mktcap        (the net sweep swept mktcap and equal)
#   sector screen      FIXED: Real Estate and Utilities KEPT
#   quantiles          FIXED: 5
#   alpha_bound        FIXED: 0.05 (keep the middle 95%)
#
# 4 groups x 4 behaviours = 16 cells, a quarter of the net sweep's 64.
#
# The two collapsed axes are pinned in FIXED rather than enumerated in EXPLICIT. Run names
# come from param_diff(cfg, build_cfg()) (sweep.py:179), i.e. the diff against BASELINE and
# not the override dict, so where a key is declared makes no difference to the name:
# portfolio_weighting="mktcap" IS the baseline and reaches no run name, while 0.99 is not
# (baseline 0.95) and appears in all 16. Each cell here therefore carries the same name as
# its net-sweep counterpart plus the signal_type/add_sales tokens.
#
# --------------------------------------------------------------------------- #
# THE REVENUE DENOMINATOR -- WHAT IT COST TO MAKE THIS ARM POSSIBLE
#
# sweep_parameters_Developed_net.py carries a "WHY THERE IS NO per_revenue ARM" block.
# That block is now OBSOLETE and this file is its resolution. What changed:
#
# 1. THE NORDICS WERE MISSING FOR A REASON NOBODY HAD FOUND. The documented cause was
#    download_sales.py's `curcdd` list, and widening it to the universe's six currencies
#    (commit 462956f4) changed almost nothing -- because the real cause was the OTHER
#    clause. The `row` CTE's exchg list was three codes short of get_data.py's:
#
#        144, 228, 256  =  Copenhagen, Oslo, Stockholm
#
#    A currency filter cannot admit a listing the exchange filter has already rejected, so
#    every Nordic firm was dropped before `curcdd` was ever evaluated. Measured: 9 of the
#    universe's 1,855 DKK/NOK/SEK firms had any row in the sales extract.
#
#    Both clauses are now synced (25 codes each, checked programmatically) and the extract
#    re-downloaded: 187,937 rows / 18,084 firms. Universe firms with any sales row --
#
#        SEK   0.0% -> 78.0%      EUR  63.5% -> 63.6%   (unchanged, as intended)
#        NOK   1.5% -> 74.1%      GBP  59.6% -> 59.6%
#        DKK   0.3% -> 59.9%      CHF  66.3% -> 66.3%
#
#    DIFF BOTH CLAUSES against get_data.py if either file is ever touched again. The drift
#    was silent, cost an entire analysis arm, and the docstring warning did not prevent it.
#
# 2. CANADA IS KNOWINGLY LEFT UNCONVERTED. FRB H.10 as bundled covers CHF/DKK/EUR/GBP/JPY/
#    NOK/SEK and has no CAD column, so CAD-reporting firm-years get fx_rate NaN. This was
#    NOT fixed, deliberately:
#
#      - The gain is small. On the universe-intersected Developed sample (26,371 LC
#        firm-years, 2016-2024) coverage is 87.6%; adding CAD recovers 276 firm-years,
#        i.e. +1.05pp to 88.7%.
#      - The risk is not. get_processed_fx_rates applies a HARDCODED POSITIONAL column
#        rename (get_data.py:331) and feeds market-cap conversion for every European and
#        Japanese firm in EVERY run. A wrong rate there is silent: wrong mktcap -> wrong
#        size screen -> wrong portfolios, with no error anywhere.
#
#    Skipping it required no config change -- it is the default. Canada stays in the region
#    and in the sample; its unconvertible firm-years simply get sale_usd = NaN, signal =
#    NaN, and leave the quantile sort. CAN was NOT removed from _REGION_LOCS: that would
#    change the sample for the share and net sweeps too and destroy the cell-for-cell
#    comparison this file exists to support.
#
# 3. SO THIS ARM'S SAMPLE IS NOT THE NET SWEEP'S SAMPLE. Coverage on the
#    universe-intersected Developed firm-years:
#
#        USA  96.0%      JPN  91.8%      DEU  86.4%      SWE  83.4%
#        GBR  80.7%      CAN  47.3%      overall 87.6%
#
#    CANADA IS THE ONE TO CARRY INTO THE READING. Every other country loses firm-years to
#    non-matches spread thinly; Canada loses roughly half, almost all of it to the missing
#    CAD rate. Its weight falls from ~2.1% of the sample to ~1.1% in this arm alone. That
#    is small enough to run on and too structured to leave unsaid -- do not read a
#    High-minus-Low difference between this file and the net sweep as a revenue effect
#    without checking it survives dropping CAN from both.
#
#    The residual Canadian gap is NOT an FX problem and no FX download would fix it:
#    Canada enters only through the USA query (exchg IN (11, 12, 14)), so the sample is the
#    US-LISTED Canadian subset and Toronto-only firms are in neither extract.
#
# --------------------------------------------------------------------------- #
# WHAT THE SIGNAL IS, AND HOW IT DIFFERS FROM THE OTHER TWO SWEEPS
#
#   share sweep        signal_0 = material / (material + immaterial)     bounded [0, 1]
#   net sweep          signal_0 = material - immaterial                  signed, unbounded
#   THIS sweep         signal_0 = (material - immaterial) / sale_usd     signed, unbounded
#
# net_materiality fixes the NUMERATOR (a count difference), so signal_type is reduced to
# picking the denominator: "weights" = none at all (the net sweep), "per_revenue" =
# sale_usd (here). build_cfg REFUSES signal_type="counts" on a net design, because with no
# denominator it would be an exact alias for "weights" and put two differently-labelled but
# numerically identical runs in the dashboard (experiments.py:892).
#
# signal_1 remains the exact NEGATION of signal_0: sale_usd > 0 scales both legs by the
# same positive number, so corr is still exactly -1.0 and node 07's decomposition gate
# applies unchanged (02_derive_signals.py:599).
#
# THREE CONSEQUENCES TO CARRY INTO THE READING:
#
# 1. THIS PUTS SIZE BACK IN, INVERTED. The net sweep's complaint is that a LEVEL ranks
#    partly on disclosure volume, which correlates with size. Dividing by revenue does not
#    remove size -- it moves it to the denominator and flips its sign, so small firms are
#    mechanically pushed toward the top of the sort. CHECK THE beta_smb ROW OF THE FF3
#    TABLE on every cell before reading anything into an alpha (experiments.py:124). A
#    High-minus-Low that is really a short-large/long-small bet will show up there.
#
# 2. ZERO IS STILL AMBIGUOUS, exactly as in the net sweep. A firm with 7 material and 7
#    immaterial scores 0, and so does a firm with NO initiatives in that group; the share
#    version separates them (0.500 vs NaN). Dividing by revenue does not help -- 0/x is
#    still 0. On the raw workbook that pile is 18.7% of firm-years, and with quintiles it
#    straddles a cutpoint whose side is decided by quantile_interval_bounds="closed", not
#    by the data. READ sort_cutpoint_summary ON THESE CELLS before trusting an alpha.
#
# 3. THE SIGNAL IS UNBOUNDED AND RIGHT-SKEWED -- a small denominator gives a huge ratio.
#    winsorise_signal_pct is left at the baseline 0.0 (OFF) to match the net sweep, but it
#    is the knob that matters most HERE and barely at all there (experiments.py:146). It is
#    rank-preserving, so it cannot move the quantile sort directly; its only channel is
#    standardize_pivot's (x - mean)/std, where one extreme value inflates its group's std.
#    A WORTHWHILE ROBUSTNESS CHECK, not a defect -- but run it before concluding that a
#    z-score difference against the net sweep is economic rather than one outlier.
#
# NOTE ON alpha_bound: it still runs, and still TRIMS on sum_activities -- but under
# per_revenue sum_activities is no longer the signal's denominator, so the trim no longer
# bounds the signal. It removes extreme disclosers from the sample (which is what it is
# for) and nothing more. The tail control on the signal itself is winsorise_signal_pct.
#
# --------------------------------------------------------------------------- #
# INHERITED FROM THE REGION -- unchanged from sweep_parameters_Developed_net.py
#
# 1. THE SIZE SCREEN IS POOLED AND NOT REGION-NEUTRAL. At 0.95 it keeps 56.4% of US firms
#    against 20.5% of Japanese and 15-22% of most European ones (3.7x spread, USA vs GRC).
#    Only 0.99 runs here, the more inclusive end, so this bites LESS than in the net sweep
#    -- but the composition is still not the region's.
#
# 2. THE Z-SCORE HAS NO COUNTRY KEY. cols_standardization is ["rfyear", "Industry"]
#    (06_prepare_panel.py), currency having been removed deliberately in 4ee0ad7. Measured
#    against a (rfyear, Industry, loc) alternative: Spearman 0.94, 33% of firm-years change
#    quintile, no extreme-bucket crossings, Japan's weight in the High bucket 13.2% ->
#    26.5%. MORE RELEVANT HERE THAN THERE: with no country key, a revenue-scaled signal
#    pools firms whose coverage differs by country (see CANADA above).
#
# 3. CANADA IS THE US-LISTED SUBSET ONLY (~60 firms, 3% of the net sweep's sample),
#    selected on size and uneven by sector. Not a basis for any Canada-specific claim --
#    and in THIS file it is half-covered on top of that.
#
# 4. THE FACTOR IS WIDER THAN THE SAMPLE: Ken French's Developed is 23 countries, this
#    holds 19. AUS, HKG, NZL, SGP are in the market return but unholdable here.
#
# --------------------------------------------------------------------------- #
# BEFORE YOU TRUST THE OUTPUT
#
# READ sales_coverage IN THE NODE-01 AUDIT ON THE FIRST CELL. It reports pct_matched (any
# sale row) and pct_usable (sale_usd > 0) -- the second is THE number, because anything
# else becomes a NaN signal and leaves the sort without erroring. It is measured on lc
# BEFORE the universe intersection, so expect it BELOW the 87.6% quoted above (that figure
# is universe-intersected); the LC-level equivalent is high-70s/low-80s and the materiality
# inner join shifts it further. The point is not the exact figure but the alarm: if it
# comes back materially lower, something is wrong with the merge and you want to know
# before 16 cells run, not after.
#
# THE BENCHMARK FIXTURE IS STALE. data/sales_all_regions.parquet was re-downloaded, so its
# sha256 in data_identity.json has changed and `benchmark compare` will fail with
# "source data changed: sales" (benchmark.py:269) until it is re-baselined. That failure is
# expected and says nothing about this sweep.
#
# --------------------------------------------------------------------------- #
# MEMORY -- WHY --jobs 1
#
# All three Compustat extracts stay resident (currency_filter spans eight currencies, so
# 03_load_universes can skip nothing): ~30 GB RSS per run. sweep.py's --jobs N is a
# ProcessPoolExecutor of full pipeline runs, so N workers cost ~30N GB. On 64 GB that is 1.
#
# Serial mode is also what makes this safe to leave unattended: _run_serial appends each
# record to results.jsonl with an fsync BEFORE starting the next cell, so a cell that dies
# costs that cell and --resume recovers the rest. (The parallel path does not have that
# property -- a worker panic breaks the whole pool and finished cells never reach the
# ledger, which is how a prior EU sweep lost everything.)
#
# RUNTIME: 28 MINUTES for all 16 cells (measured, 2026-10-05, all 16 ok).
#
#     cell 1      284s        <- cold: universe load + process_lc + prepare_panel
#     cells 2-16   92s median (84-101s)
#     total      1,664s = 27.7 min
#
# PINNING THE TWO AXES IS WHAT MAKES THIS FAST, far more than dropping to a quarter of the
# cells. The net sweep's 64 cells took 3h 52m at ~200s each with NO cold/warm gap (its
# cell 1 was 211s, in line with the rest), because mktcap_covered and portfolio_weighting
# VARIED -- and the expensive upstream nodes depend on them, so they were recomputed
# constantly. Here both are constant, so those nodes compute once in cell 1 and the other
# 15 cells reuse the cache: 8.4x faster overall against a 4x cut in cell count.
#
# THE COROLLARY IS A TRAP. Re-introducing either axis does NOT cost "one more pass" -- it
# re-arms the upstream recompute for every cell and takes you back toward 200s each. A
# 32-cell version of this file sweeping one extra weighting is ~1h 50m, not ~56 min.
#
# per_revenue itself is not the speedup: it adds only the sales merge in node 01 (a
# 188k-row parquet read) and drops ~12% of firm-years.
# --------------------------------------------------------------------------- #

SWEEP_NAME: str = "developed_net_materiality_revenue_sdg_groups_x_behaviours"


# --------------------------------------------------------------------------- #
# GRID: empty on purpose. The (group, behaviour) pair cannot be two independent axes --
# each group reads a DIFFERENT cfg key, so a cartesian product would build 16 combinations
# of which 12 are duplicates or silently ignore the action. The pair is enumerated as one
# axis of 16 in EXPLICIT instead. sweep.py reads GRID unconditionally.
# --------------------------------------------------------------------------- #
GRID: dict = {}


# (action_characterization, the ONE action cfg key it reads). One row per SDG group.
# IDENTICAL to sweep_parameters_Developed_net.py -- the designs are the comparison.
_GROUPS = [
    ("Materiality_All_Action_SDG", "materiality_all_action"),        # SDGs 1-17
    ("Materiality_PP_Action_SDG", "materiality_pp_action"),          # 1-5, 8-11, 16, 17
    ("Materiality_People_Action_SDG", "materiality_people_action"),  # 1-5, 8, 10
    ("Materiality_Planet_Action_SDG", "materiality_planet_action"),  # 6, 7, 12, 13, 14, 15
]

# "total" is the ALL-BEHAVIOURS cell. NOTE it means ALL INITIATIVES, not the sum of the
# three behaviours below it: the workbook carries two independent classifications of the
# same initiatives, and `total` equals the NEWER 4-way split (adaptation /
# advocacy_new_def / innovation / upskilling) exactly. The three old-split behaviours here
# cover 90.8% (All), 92.8% (PP), 93.6% (People) and 87.4% (Planet) of it on the material
# leg -- so they do NOT decompose the total cell.
_BEHAVIOURS = ["total", "advocacy_old_def", "preparation", "transformation"]

EXPLICIT: list[dict] = [
    {
        "action_characterization": ac,
        action_key: behaviour,
    }
    for ac, action_key in _GROUPS
    for behaviour in _BEHAVIOURS
]


# --------------------------------------------------------------------------- #
# FIXED: merged into every combination. An EXPLICIT entry wins for the same key.
# --------------------------------------------------------------------------- #
FIXED: dict = {
    # THE REGION. Drives currency_filter (all eight listing currencies), region_filter (the
    # three MacroRegions), convert_to_USD=True, fama_factor_region="Developed", and the
    # 19-country loc whitelist in 01_process_lc.py::_REGION_LOCS -- which INCLUDES CAN.
    # Left in deliberately; see "CANADA IS KNOWINGLY LEFT UNCONVERTED" above.
    "region_analysis": "Developed",

    # ---- THE SIGNAL: numerator and denominator are set separately -------- #
    # net_materiality fixes the NUMERATOR: signal_0 = sum_with_0 - sum_with_1 instead of
    # sum_with_0 / sum_activities. A modifier on the group x action designs above, not a
    # design of its own. Applies to all 16 cells.
    "net_materiality": True,
    # signal_type then picks the DENOMINATOR. This -- and only this -- is what separates
    # this file from sweep_parameters_Developed_net.py, which leaves it at the baseline
    # "weights" (no denominator). Signal names gain a _per_rev suffix.
    "signal_type": "per_revenue",
    # The denominator column itself. build_cfg REFUSES per_revenue without this
    # (experiments.py:881): add_sales LEFT-merges data/sales_all_regions.parquet onto lc at
    # (gvkey, rfyear) <- (gvkey, fyear), no lag, both fiscal years. LEFT, so it cannot
    # change the sample -- an unmatched firm-year keeps its row with sale_usd NaN, and only
    # per_revenue (which divides by it) then loses it from the sort.
    "add_sales": True,
    # sales_path left at the baseline "data/sales_all_regions.parquet". The pipeline reads
    # the PARQUET, not the CSV that download_sales.py writes beside it -- regenerate both.

    # ---- THE SECTOR SCREEN: one value, not an axis ------------------------ #
    # KEEP Real Estate and Utilities, which the build_cfg baseline drops (both default
    # True). Requested. Neither is at baseline, so both appear in EVERY run name here.
    "drop_real_estate": False,
    "drop_utilities": False,

    # ---- the two collapsed axes ------------------------------------------ #
    # The net sweep swept both; this file pins one value of each, which is what takes 64
    # cells down to 16. 0.99 is NOT the baseline (0.95) so it reaches every run name;
    # "mktcap" IS the baseline so it reaches none.
    "mktcap_covered_if_filter_by_cum_market_cap": 0.99,
    "portfolio_weighting": "mktcap",

    # ---- the two single-valued analysis knobs ----------------------------- #
    "no_simple_quantiles": 5,
    # "Alpha 0.95" = keep the middle 95%, i.e. a 0.05 trim PER TAIL on sum_activities.
    # Also the build_cfg baseline, so it reaches no run name. NOTE it no longer bounds the
    # SIGNAL here -- see "NOTE ON alpha_bound" above.
    "alpha_bound": 0.05,

    # ---- materiality: what makes these designs possible at all ------------ #
    "add_materiality": True,
    "materiality_version": 2,
    "minimum_initatives_needed_to_split_by_materiality": 0,

    # Filter 2 ONLY (drop suspicious gvkeys), matching the US/EU/Developed share sweeps and
    # the net sweep. CONSEQUENCE: filter 3 (min_initatives_annual_reports_...) is SKIPPED
    # under this mode (01_process_lc.py gates it on _all3), so that knob has NO EFFECT here
    # at any value.
    "execute_3_filters": "suspicious_only",

    # The thin-portfolio gate, at baseline. A High/Low leg is HIDDEN unless it holds at
    # least min_stocks_per_portfolio names in at least min_portfolio_coverage of formation
    # months. WATCH THIS MORE CLOSELY THAN IN THE NET SWEEP: per_revenue drops every
    # firm-year without a usable sale_usd (~12% overall, ~53% of Canada), so the narrow
    # cells (People x one action) are thinner here than their net-sweep counterparts and
    # are the likeliest to trip the gate.
    "min_stocks_per_portfolio": 25,
    "min_portfolio_coverage": 0.8,

    # NOT pinned: winsorise_signal_pct, left at the baseline 0.0 (off) to match the net
    # sweep. It is the knob that matters most under per_revenue -- see consequence 3 above.
}
