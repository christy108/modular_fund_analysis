"""Sweep parameters — DEVELOPED, NET MATERIALITY.

Run it with:

    python -m New_Pipeline.sweep --params New_Pipeline.sweep_parameters_Developed_net --jobs 1

``--jobs 1`` IS NOT OPTIONAL. ~30 GB RSS per worker on a 64 GB machine; see "MEMORY" below.

The net twin of sweep_parameters_Developed.py. Same region, same 16 (SDG group x behaviour)
designs, same mktcap and weighting axes -- the signal is the only thing that changes, so the
two files are directly comparable cell for cell.
"""

# --------------------------------------------------------------------------- #
# WHAT THIS SWEEP IS
#
#   SIGNAL             net materiality:  material - immaterial   (a signed LEVEL)
#   SDG GROUP          All 17 SDGs | People+Prosperity | People | Planet
#   BEHAVIOUR          all (total) | advocacy_old_def | preparation | transformation
#   ------------------------------------------------------------------------
#   mktcap coverage    0.95, 0.99
#   weighting          mktcap, equal
#   sector screen      FIXED: Real Estate and Utilities KEPT
#   quantiles          FIXED: 5
#   alpha_bound        FIXED: 0.05 (keep the middle 95%)
#
# 4 groups x 4 behaviours x 2 mktcap x 2 weighting = 64 cells.
#
# The sector screen is NOT an axis here (it was two values in the share sweep). Both knobs
# are pinned False in FIXED, i.e. Real Estate and Utilities are KEPT in the sample.
#
# --------------------------------------------------------------------------- #
# WHY THERE IS NO per_revenue ARM
#
# It was requested and then dropped, because the sales extract cannot support it on this
# region. scripts/download_sales.py:91 pulls the RoW fundamentals with
#
#     curcdd IN ('CHF', 'GBP', 'EUR')
#
# while the RoW UNIVERSE (get_data.py:235) pulls
#
#     curcdd IN ('CHF', 'GBP', 'EUR', 'NOK', 'SEK', 'DKK')
#
# so NOK/SEK/DKK fundamentals were never downloaded, and `sale_usd` is absent for almost
# every Nordic firm (118 SEK rows in the whole file against 1,458 Swedish LC firm-years).
# JPY is unaffected -- Japan has its own query (exchg = 264, curcdd = 'JPY', 27,229 rows).
# CAD is hit twice: it is outside that currency list AND absent from FRB H.10, so
# add_sale_usd leaves its fx_rate NaN.
#
# Measured cost on the Developed-19 LC sample, 2016-2024, had per_revenue been used:
#
#     SWE  99.1% of firm-years lost      CAN  81.0%
#     DNK  99.1%                         DEU  28.7%
#     NOR  98.7%                         GBR  25.1%
#     overall 26.7% of firm-years, 31.7% of firms (2,568 of 8,097)
#
# Those firm-years do not error -- `sale_usd` is NaN, the signal is NaN, and they leave the
# sort silently. A per_revenue arm would therefore be a sweep on "Developed minus
# Scandinavia minus most of Canada" wearing the Developed label. Re-run download_sales.py
# with the six currencies (and CAD added to data/FRB/FRB_H10_2024.csv) before adding it.
#
# --------------------------------------------------------------------------- #
# WHAT NET MATERIALITY IS, AND HOW IT DIFFERS FROM THE SHARE SWEEP
#
#   share sweep   signal_0 = material / (material + immaterial)     bounded [0, 1]
#   THIS sweep    signal_0 = material - immaterial                  signed, unbounded
#
# Both read the SAME columns -- net_materiality is a modifier on the same group x action
# designs, not a different column set. Only the numerator arithmetic changes
# (02_derive_signals.py). signal_1 is the exact NEGATION here, where in the share designs
# it is 1 - signal_0; both give corr = -1.0, so node 07's decomposition gate still applies.
#
# TWO CONSEQUENCES TO CARRY INTO THE READING:
#
# 1. NET IS A LEVEL, SO IT RANKS PARTLY ON DISCLOSURE VOLUME. A firm at +2 (2 material,
#    0 immaterial) sits beside one at +2 from 40 vs 38. On the measured Developed sample
#    the range is modest (-16..+16 for Planet x advocacy_old_def, far tighter than the
#    -229..+291 of the raw workbook, because the size screen and the alpha-bound trim
#    remove the extreme disclosers), so this is a real property rather than a fatal one --
#    but it is the thing the share version does not have.
#
# 2. ZERO IS AMBIGUOUS. A firm with 7 material and 7 immaterial scores 0, and so does a
#    firm with NO initiatives in that group at all. The share version separates them
#    cleanly: 0.500 vs NaN, and NaN leaves the sort. Here both sit in the same bucket, and
#    on the raw workbook that bucket is 18.7% of firm-years. With quintiles, the zero pile
#    straddles a cutpoint and which side it falls on is decided by
#    quantile_interval_bounds="closed", not by the data. READ sort_cutpoint_summary ON
#    THESE CELLS before trusting an alpha.
#
# NOT RUN HERE, and deliberately: weighted_net_materiality, i.e.
# (material - immaterial) / (material + immaterial). That is 2*share - 1, a positive
# linear transform of the share signal, and the (rfyear, Industry) z-score cancels it
# exactly -- measured Spearman 1.0 against the share, max|z difference| 1.1e-15. It would
# reproduce sweep_parameters_Developed.py cell for cell under a different name.
#
# --------------------------------------------------------------------------- #
# INHERITED FROM THE REGION -- unchanged from sweep_parameters_Developed.py
#
# 1. THE SIZE SCREEN IS POOLED AND NOT REGION-NEUTRAL. At 0.95 it keeps 56.4% of US firms
#    against 20.5% of Japanese and 15-22% of most European ones (3.7x spread, USA vs GRC).
#    The US share of the sample rises from 22.8% of the screened universe to 42.1%; Japan
#    falls from 24.4% to 16.3%. Sweeping mktcap_covered sweeps regional composition as
#    much as the size cut.
#
# 2. THE Z-SCORE HAS NO COUNTRY KEY. cols_standardization is ["rfyear", "Industry"]
#    (06_prepare_panel.py), currency having been removed deliberately in 4ee0ad7. Measured
#    against a (rfyear, Industry, loc) alternative on this sample: Spearman 0.94, 33% of
#    firm-years change quintile, no extreme-bucket crossings, and Japan's weight in the
#    High bucket moves 13.2% -> 26.5%. A robustness check worth running, not a defect.
#
# 3. CANADA IS THE US-LISTED SUBSET ONLY (~60 firms, 3% of the sample), selected on size
#    and uneven by sector. Not a basis for any Canada-specific claim.
#
# 4. THE FACTOR IS WIDER THAN THE SAMPLE: Ken French's Developed is 23 countries, this
#    holds 19. AUS, HKG, NZL, SGP are in the market return but unholdable here.
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
# mktcap_covered=0.99 is the heavier half of this grid and has now run 64 times in the
# share sweep without incident, so it is no longer the unknown it was there.
# --------------------------------------------------------------------------- #

SWEEP_NAME: str = "developed_net_materiality_sdg_groups_x_behaviours"


# --------------------------------------------------------------------------- #
# GRID: empty on purpose. The (group, behaviour) pair cannot be two independent axes --
# each group reads a DIFFERENT cfg key, so a cartesian product would build 16 combinations
# of which 12 are duplicates or silently ignore the action. The pair is enumerated as one
# axis of 16 in EXPLICIT instead. sweep.py reads GRID unconditionally.
# --------------------------------------------------------------------------- #
GRID: dict = {}


# (action_characterization, the ONE action cfg key it reads). One row per SDG group.
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
        "portfolio_weighting": w,
        "mktcap_covered_if_filter_by_cum_market_cap": m,
    }
    for ac, action_key in _GROUPS
    for behaviour in _BEHAVIOURS
    for w in ("mktcap", "equal")
    for m in (0.95, 0.99)
]


# --------------------------------------------------------------------------- #
# FIXED: merged into every combination. An EXPLICIT entry wins for the same key.
# --------------------------------------------------------------------------- #
FIXED: dict = {
    # THE REGION. Drives currency_filter (all eight listing currencies), region_filter (the
    # three MacroRegions), convert_to_USD=True, fama_factor_region="Developed", and the
    # 19-country loc whitelist in 01_process_lc.py::_REGION_LOCS.
    "region_analysis": "Developed",

    # THE SIGNAL. A modifier on the group x action designs above, not a design of its own:
    # signal_0 becomes sum_with_0 - sum_with_1 instead of sum_with_0 / sum_activities.
    # Applies to all 64 cells.
    "net_materiality": True,

    # ---- THE SECTOR SCREEN: one value, not an axis ------------------------ #
    # KEEP Real Estate and Utilities, which the build_cfg baseline drops (both default
    # True). Requested. Neither is at baseline, so both appear in EVERY run name here.
    "drop_real_estate": False,
    "drop_utilities": False,

    # ---- the two single-valued analysis knobs ----------------------------- #
    "no_simple_quantiles": 5,
    # "Alpha 0.95" = keep the middle 95%, i.e. a 0.05 trim PER TAIL on sum_activities.
    # Also the build_cfg baseline, so it reaches no run name.
    "alpha_bound": 0.05,

    # ---- materiality: what makes these designs possible at all ------------ #
    "add_materiality": True,
    "materiality_version": 2,
    "minimum_initatives_needed_to_split_by_materiality": 0,

    # Filter 2 ONLY (drop suspicious gvkeys), matching the US/EU/Developed share sweeps.
    # CONSEQUENCE: filter 3 (min_initatives_annual_reports_...) is SKIPPED under this mode
    # (01_process_lc.py gates it on _all3), so that knob has NO EFFECT here at any value.
    "execute_3_filters": "suspicious_only",

    # The thin-portfolio gate, at baseline. A High/Low leg is HIDDEN unless it holds at
    # least min_stocks_per_portfolio names in at least min_portfolio_coverage of formation
    # months. Worth watching on the narrow cells (People x one action), which are the
    # thinnest signals in this file.
    "min_stocks_per_portfolio": 25,
    "min_portfolio_coverage": 0.8,

    # NOT pinned: portfolio_weighting and mktcap_covered_if_filter_by_cum_market_cap are
    # EXPLICIT axes. signal_type is left at the build_cfg baseline "weights", which for a
    # net design means NO DENOMINATOR (the raw net count) -- it is the per_revenue value
    # that would divide by sale_usd, and that arm is out of scope here.
    # add_sales is likewise left off: nothing in this sweep reads sale_usd.
}
