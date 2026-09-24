"""What `python -m New_Pipeline.sweep` should run — pure data, no logic.

This file is meant to be edited between sweeps. Nothing imports it except
``New_Pipeline/sweep.py``, and it never runs anything itself, so a bad edit here can
only break the sweep runner — never a normal ``New_Pipeline.run`` / ``.dashboard``
invocation.

Every key you put in ``GRID`` / ``EXPLICIT`` / ``FIXED`` must be a real ``build_cfg``
knob (see the baseline dict at ``New_Pipeline/experiments.py:38``). The sweep validates
every combination through ``build_cfg(**overrides)`` BEFORE the first pipeline run, so a
typo raises in the first second rather than forty minutes in.

THIS FILE IS THE **US** HALF. Its mirror is ``sweep_params_b.py``, which is the same
worklist on Europe. The two are deliberately identical apart from ``region_analysis`` and
the market-cap axis (see the header there) — keep any other edit here in step with that
file, or the regions stop being comparable. Each file writes to its own
``sweep_output/<stamp>_<name>/`` folder, so the US and EU results are always two separate
PDFs/CSVs, never merged.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# SWEEP_NAME: names this sweep's output folder, `sweep_output/<UTC stamp>_<name>/`.
# Change it to start a NEW sweep; re-running with the same name RESUMES the existing
# folder (that is what makes --resume work). `--new-run` forces a fresh folder anyway,
# and `--out DIR` overrides the whole thing.
#
# Previous sweeps in this file, for reference:
#   "us_ff5_allsdg_pp_mcap_quantiles"      (8 cells, completed -- output in
#                                           sweep_output/20260908T115744Z_*)
#   "us_health_sdg_pre_post_2020"          (6 cells, completed -- committed at c5584ec)
#   "us_health_sdgs_weighting_mcap_quantiles"
#                                          (24 cells: the three health designs only,
#                                           completed -- output in
#                                           sweep_output/20260908T150454Z_*). THIS sweep
#                                           is that worklist plus All-SDGs and
#                                           People+Prosperity, under a new name, so the
#                                           24 finished cells are NOT resumed -- all 40
#                                           run fresh. The old folder stays readable.
# To add cells to one of those, restore this file from git rather than editing the name
# back: --resume can only recognise what already ran if the worklist still matches.
# --------------------------------------------------------------------------- #
SWEEP_NAME: str = "us_material_planet_behaviours"


# --------------------------------------------------------------------------- #
# WHAT THIS SWEEP IS
#
# US half: the PLANET materiality designs at two SDG widths, each at four
# behavioural cuts, crossed with the weighting scheme, the sort granularity and the
# market-cap screen, on the FULL 2016-2024 sample.
#
#   2 widths x (1 whole-group + 3 behavioural cuts) x 2 weighting schemes
#     x 2 quantile counts x 2 mcap screens
#   = 64 runs  (48 from GRID, 16 from EXPLICIT)
#
# This REPLACES the five-design People+Prosperity / health worklist this file used to
# hold (SWEEP_NAME "us_momentum_people_prosperity", 40 cells). That sweep's output stays readable in its own
# sweep_output/ folder; nothing here resumes it.
#
# Everything else is the build_cfg baseline, pinned in FIXED below -- EXCEPT the sector
# screen, which is the one deliberate departure. See FIXED.
#
# THE DESIGNS. All eight (2 widths x 4 actions) are one-group MIRROR PAIRS: signal_0 is a
# material SHARE of the group's SDGs and signal_1 = 1 - signal_0, so High on one leg is Low
# on the other and the two High-Low spreads are exact negatives. On the risk panel that
# shows up as one green row and one red row per pair, which is expected, not a bug -- the
# colour is carrying the sign.
#
#   Materiality_Planet_Action_SDG         wide Planet  -- SDGs 6, 7, 12, 13, 14, 15
#   Materiality_Narrow_Planet_Action_SDG  narrow Planet -- SDGs 13, 14, 15
#
# crossed with materiality_planet_action:
#
#   total             the whole group -- identical to Materiality_Planet_SDG /
#                     Materiality_Narrow_Planet_SDG (same columns, same untagged signal
#                     names, verified), which is why those two designs are not listed
#                     separately.
#   advocacy_old_def  \
#   preparation        >  the ORIGINAL "Matteo" 3-way split, covering 87.7% of Planet
#   transformation    /   initiatives -- one taxonomy, not three unrelated picks.
#
# THESE ARE NOT EIGHT INDEPENDENT TESTS. Narrow Planet is a strict SUBSET of wide Planet
# (13,14,15 of 6,7,12,13,14,15), so read a difference between the two widths as "is this
# carried by climate and natural capital, or by the resource SDGs 6/7/12". Measured on the
# v_2A1 workbook, narrow Planet is 91.9% SDG 15 by initiative count -- SDG 13 is only 5.4%
# of it -- so do NOT read the narrow cut as "the climate cut".
#
# ONE DENOMINATOR CAVEAT. Every design here is a SINGLE group, so each one's denominator is
# its OWN group's material + immaterial count -- "material share WITHIN this SDG set and
# this action", not "share of all initiatives". The four actions therefore do NOT share a
# denominator with each other: "total" is the whole group, the other three are strictly
# thinner slices of it.
#
# DENSITY WARNING -- measured, not estimated. See the table at
# experiments.py::_register_planet_action_experiments.
#   WIDE Planet is usable at every action: total 89.5% of firm-years usable,
#   transformation 79.1%, advocacy_old_def 57.4%, preparation 51.2%.
#   NARROW Planet is thin EVERYWHERE: total is already only 46.3% usable with a MEDIAN
#   denominator of 0, and the actions run 36.8% (advocacy_old_def), 12.9%
#   (transformation), 12.6% (preparation). Treat the narrow action cells as CONTROLS.
#   A sibling config (narrow x innovation, thinner still) emptied the panel outright and
#   died in node 02 with "cannot convert float NaN to integer". These three carry 3-8x that
#   support, so they will probably survive, but that is not tested -- expect some narrow
#   cells to FAIL rather than return, and read every cell's signal_sparsity before its
#   alpha.
#
# THE SECTOR SCREEN IS THE OTHER HALF OF THIS SWEEP. Real Estate and Utilities are kept
# here and dropped in the People+Prosperity sweeps. Both are Planet-relevant by
# construction -- utilities are the energy SDG (7) and real estate the built-environment
# side of SDGs 11/12 -- so excluding them from a Planet sort removes much of the exposure
# the sort exists to measure. That also means these results are NOT directly comparable
# with the People+Prosperity ones cell for cell: they differ in the universe as well as
# the signal.


# --------------------------------------------------------------------------- #
# GRID: expanded to its full cartesian product.
#
# The five axes here are genuinely INDEPENDENT and every one of the 2 x 3 design
# combinations is valid, so they cross cleanly. The two WHOLE-GROUP signals are the one
# thing that cannot go in a cross -- see EXPLICIT below for why.
#
#   2 widths x 3 behaviours x 2 weighting x 2 quantiles x 2 mcap = 48 cells
#   (+ the 16 whole-group cells in EXPLICIT below = 64 in total)
# --------------------------------------------------------------------------- #
GRID: dict[str, list] = {
    # THE SIGNALS (six of the eight): each Planet width crossed with each behaviour.
    # The other two -- each width on its own -- are in EXPLICIT below.
    "action_characterization": [
        "Materiality_Planet_Action_SDG",         # SDGs 6, 7, 12, 13, 14, 15
        "Materiality_Narrow_Planet_Action_SDG",  # SDGs 13, 14, 15
    ],
    # NO "total" here. A width on its own is its OWN design -- Materiality_Planet_SDG /
    # Materiality_Narrow_Planet_SDG -- and those two live in EXPLICIT below, because they do
    # not read this key and so cannot be crossed with it. These three are the ORIGINAL
    # "Matteo" 3-way split, so they partition one taxonomy (87.7% of Planet initiatives)
    # rather than being three unrelated picks.
    # TRAP: advocacy_old_def is the Matteo advocacy leg; advocacy_new_def belongs to the
    # newer 4-way split and is deliberately NOT here.
    "materiality_planet_action": ["advocacy_old_def", "preparation", "transformation"],
    # Cap-weighted first (also the build_cfg baseline), then equal-weighted.
    "portfolio_weighting": ["mktcap", "equal"],
    # Sort granularity: coarse 3-way and finer 5-way.
    "no_simple_quantiles": [3, 5],
    # Market-cap coverage of the screen. 0.95 is the baseline; 0.99 is the looser cut.
    # Both are safe on the US -- see the header note.
    "mktcap_covered_if_filter_by_cum_market_cap": [0.95, 0.99],
}

# --------------------------------------------------------------------------- #
# EXPLICIT: hand-picked combinations, appended after the grid, used verbatim.
# THE OTHER TWO SIGNALS: each width ON ITS OWN, no action split.
#
# WHY NOT IN GRID. These two are their own action_characterization and never read
# materiality_planet_action. GRID is a strict cartesian product -- the runner has no skip
# rule, and it dedupes on the override dict rather than on the resulting signal -- so
# listing them there would cross each with all three actions and build THREE IDENTICAL runs
# each: 96 cells instead of 64, 32 of them duplicate reruns under different names. Listed
# here they cost nothing and stay one clean 8-cell block each.
#
# So the full worklist is eight signals, 8 cells each:
#
#   GRID      Material_Advocacy_Old_Def_Planet         Material_Advocacy_Old_Def_Narrow_Planet
#             Material_Preparation_Planet              Material_Preparation_Narrow_Planet
#             Material_Transformation_Planet           Material_Transformation_Narrow_Planet
#   EXPLICIT  Material_Planet                          Material_Narrow_Planet
#
# The three axes below are exactly GRID's, so every signal is measured the same eight ways.
# FIXED supplies the region and the sector screen to these as well, so the universe is
# identical across all 64 cells and the two whole-group signals are a clean reference line.
# --------------------------------------------------------------------------- #
EXPLICIT: list[dict] = [
    {"action_characterization": ac,
     "portfolio_weighting": w, "no_simple_quantiles": k,
     "mktcap_covered_if_filter_by_cum_market_cap": m}
    for ac in ("Materiality_Planet_SDG",           # SDGs 6, 7, 12, 13, 14, 15
               "Materiality_Narrow_Planet_SDG")    # SDGs 13, 14, 15
    for w in ("mktcap", "equal")
    for k in (3, 5)
    for m in (0.95, 0.99)
]

# --------------------------------------------------------------------------- #
# FIXED: merged into EVERY combination, grid and explicit alike. Use for knobs you want
# held constant across the whole sweep without repeating them in each entry.
# An entry in GRID/EXPLICIT wins over FIXED for the same key.
# --------------------------------------------------------------------------- #
FIXED: dict = {
    # ---- everything here EQUALS the build_cfg baseline -------------------- #
    # None of it reaches the cfg diff, so none of it pollutes a run name. Pinned anyway:
    # this file is the record of what the sweep was, and "it inherited whatever
    # experiments.py said that week" is not a record.
    #
    # That cuts both ways: a pin OVERRIDES the baseline, so when experiments.py moves,
    # a pin left behind silently freezes the sweep at the old value. Re-check this block
    # against build_cfg() before launching, not after.

    # THE REGION. Drives currency_filter=["USD"], region_filter=["United States and
    # Canada"], convert_to_USD=False and fama_factor_region="United_States" via the region
    # block at experiments.py:357. This is the ONLY line that differs from
    # sweep_params_b.py, which runs the same worklist on Europe (plus its own, tighter
    # market-cap axis).
    "region_analysis": "United_States",

    # ---- THE SECTOR SCREEN: the one place this file departs from the baseline -------- #
    # ADD BACK Real Estate and Utilities, which the build_cfg baseline drops (both default
    # True). Neither is at baseline, so both appear in EVERY run name here -- which is what
    # keeps these results visibly distinct from the People+Prosperity sweeps, where Real
    # Estate stays dropped.
    "drop_real_estate": False,
    "drop_utilities": False,

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
# The ledger itself is appended after EVERY experiment regardless, so this only trades
# how fresh the two derived files are against the seconds each rebuild costs.
# Both are ALWAYS rebuilt once more when the sweep finishes (or is interrupted).
PDF_EVERY: int = 4

# Everything the sweep writes lives under here, relative to the repo root.
OUTPUT_DIR: str = "sweep_output"


# --------------------------------------------------------------------------- #
# How many experiments run at once (`--jobs N` overrides).
#
# Each worker is a separate PROCESS running one full pipeline, so this scales with cores
# AND with RAM -- every worker independently loads the Golden LC panel and the Compustat
# universe. On this machine (10 cores / 64 GB) 2 is demonstrated: two concurrent runs on
# the current 1.5 GB row extract completed comfortably. 3 is probably fine and untested.
#
# 1 = the old serial behaviour.
#
# NOTE this requires cfg.write_debug_csv=False (the default). Those dumps go to FIXED
# paths under ./data/debug/, so parallel workers would clobber each other's files.
# Do NOT run this file and sweep_params_b.py concurrently at JOBS=2 each: that is four
# pipelines, each holding its own copy of the Golden panel and the Compustat universe.
# --------------------------------------------------------------------------- #
JOBS: int = 2


# --------------------------------------------------------------------------- #
# Presentation order for results.pdf / results.csv.
#
# The ledger stays in completion order (it is append-only, and under --jobs N that order
# is not even deterministic), but the PDF and CSV are SORTED by these cfg keys before
# being written -- and by the same function, so "CSV row N describes PDF page N" holds.
#
# SORT_BY lists the cfg keys to sort on, outermost first.
# VALUE_ORDER pins the order of specific values; anything not listed sorts after those
# (numerically for numbers, alphabetically otherwise).
# --------------------------------------------------------------------------- #
SORT_BY: list[str] = [
    # Outermost: the SDG width, so the wide block precedes the narrow one.
    "action_characterization",
    # Then the behavioural action -- the second half of the design, so each width reads as
    # four blocks of eight in taxonomy order.
    "materiality_planet_action",
    # Then the weighting scheme, so each design's cap-weighted block sits directly above
    # its equal-weighted block.
    "portfolio_weighting",
    # Then the sort granularity.
    "no_simple_quantiles",
    # Innermost: the market-cap screen, so each design/weighting/K triple puts its 0.95
    # page directly next to its 0.99 page -- the robustness comparison this axis exists
    # to make.
    "mktcap_covered_if_filter_by_cum_market_cap",
]

VALUE_ORDER: dict[str, list] = {
    # Each width's WHOLE-GROUP signal first, then its three behavioural cuts -- so the PDF
    # reads "here is Planet, and here is what each behaviour does to it", twice.
    "action_characterization": [
        "Materiality_Planet_SDG",                  # Material_Planet
        "Materiality_Planet_Action_SDG",           # the same SDGs, one action at a time
        "Materiality_Narrow_Planet_SDG",           # Material_Narrow_Planet
        "Materiality_Narrow_Planet_Action_SDG",    # the same SDGs, one action at a time
    ],
    # The Matteo 3-way split in the taxonomy's own order -- not a density order, so the
    # three read as one split. None on the two whole-group signals, which _sort_key ranks
    # after these rather than raising.
    "materiality_planet_action": ["advocacy_old_def", "preparation", "transformation"],
    # Cap-weighted first, matching Kevin's own ordering ("Mkt cap weighted" then
    # "And EQ weights").
    "portfolio_weighting": ["mktcap", "equal"],
}
