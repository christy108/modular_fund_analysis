"""What `python -m New_Pipeline.sweep` should run — pure data, no logic.

This file is meant to be edited between sweeps. Nothing imports it except
``New_Pipeline/sweep.py``, and it never runs anything itself, so a bad edit here can
only break the sweep runner — never a normal ``New_Pipeline.run`` / ``.dashboard``
invocation.

Every key you put in ``GRID`` / ``EXPLICIT`` / ``FIXED`` must be a real ``build_cfg``
knob (see the baseline dict at ``New_Pipeline/experiments.py:38``). The sweep validates
every combination through ``build_cfg(**overrides)`` BEFORE the first pipeline run, so a
typo raises in the first second rather than forty minutes in.
"""

from __future__ import annotations

import itertools

# --------------------------------------------------------------------------- #
# SWEEP_NAME: names this sweep's output folder, `sweep_output/<UTC stamp>_<name>/`.
# Change it to start a NEW sweep; re-running with the same name RESUMES the existing
# folder (that is what makes --resume work). `--new-run` forces a fresh folder anyway,
# and `--out DIR` overrides the whole thing.
#
# Previous sweeps in this file, for reference:
#   "europe_materiality_12_designs"  (128 cells, completed)
#   "europe_plain_action_signals"    ( 36 cells)
# To add cells to one of those, restore this file from git rather than editing the name
# back: --resume can only recognise what already ran if the worklist still matches.
# --------------------------------------------------------------------------- #
SWEEP_NAME: str = "us_health_sdg_pre_post_2020"


# --------------------------------------------------------------------------- #
# WHAT THIS SWEEP IS
#
# Three health-SDG materiality designs on the US sample, each run on TWO sample windows
# that split at 2020 -- i.e. does the health-materiality spread look different before
# Covid than after it.
#
#   3 designs  x  2 windows  =  6 runs
#
# Everything else is the build_cfg baseline ("base parameters"), pinned in FIXED below.
#
# THE DESIGNS. All three are one-group MIRROR PAIRS: signal_0 is the material share of a
# health SDG group, signal_1 = 1 - signal_0, so High on one leg is Low on the other and
# the spreads are exact negatives of each other. Two designs, differing only in K:
#
#   Materiality_One_Health_SDGS     SDGs 3, 6, 8, 11, 14, 15   (K = 3 and K = 5)
#   Materiality_Narrow_Health_SDGS  SDGs 3, 6, 11              (K = 5)
#
# Narrow_Health is a SUBSET of One_Health, so the two are not independent tests -- read a
# difference between them as "does widening the group beyond health/water/cities add or
# dilute signal", not as two separate findings. The K=3 vs K=5 pair on One_Health is the
# sort-granularity check at fixed group and fixed trim.
#
# THE WINDOWS. `start_year` / `end_year` bound the LC sample on rfyear
# (01_process_lc.py:324-329) and the universe on year, so they cut the analysis panel:
#
#   2016 - 2019   pre-Covid
#   2019 - 2024   Covid and after
#
# 2019 is deliberately in BOTH windows (as the requested boundary year), so these are
# overlapping samples, not a partition. The overlap is one rfyear at each window's edge.
#
# TWO THINGS TO EXPECT ON THE 2016-2019 CELLS, both consequences of the short window
# rather than of the signal:
#   * the return panel is roughly a third the length of the full-sample runs, so every
#     alpha t-stat is correspondingly weaker. A spread that "disappears" pre-2020 may
#     only be losing power.
#   * the thin-portfolio gate (min_stocks_per_portfolio=25 in >= 80% of formation months)
#     is calibrated on the FULL sample. If a leg is hidden on a short window, check
#     `portfolio_coverage` / `portfolio_gate_summary` before concluding anything -- it is
#     held at baseline here on purpose, but it is the knob most likely to bite.
#
# NAMES: experiment_name() builds each run name from the cfg DIFF against build_cfg().
# The baseline is start_year=2016, end_year=2024, so the pre-Covid cells carry
# `end_year-2019` and the post cells carry `start_year-2019` -- exactly one of the two
# appears per cell. region_analysis="United_States" is already the baseline, so the US
# choice does NOT appear in any run name or page title (it is pinned in FIXED as the
# record). No cell equals the baseline, so there is no "base_parameters" page.
# --------------------------------------------------------------------------- #
_DESIGNS: list[dict] = [
    # 1. One_Health (SDGs 3, 6, 8, 11, 14, 15), coarse 3-way sort.
    {"action_characterization": "Materiality_One_Health_SDGS", "no_simple_quantiles": 3},
    # 2. Same group, finer 5-way sort.
    {"action_characterization": "Materiality_One_Health_SDGS", "no_simple_quantiles": 5},
    # 3. Narrow_Health (SDGs 3, 6, 11), 5-way sort. No K=3 counterpart was asked for.
    {"action_characterization": "Materiality_Narrow_Health_SDGS", "no_simple_quantiles": 5},
]

# (start_year, end_year) for each sample window.
_WINDOWS: list[tuple[int, int]] = [
    (2016, 2019),   # pre-Covid
    (2019, 2024),   # Covid and after
]


# --------------------------------------------------------------------------- #
# GRID: expanded to its full cartesian product. EMPTY -- the cross is built in EXPLICIT
# instead, because a window is a PAIR of keys (start_year, end_year) that must move
# together. A GRID over the two independently would give 4 windows, two of them nonsense.
# --------------------------------------------------------------------------- #
GRID: dict[str, list] = {}

# --------------------------------------------------------------------------- #
# EXPLICIT: hand-picked combinations, appended after the grid, used verbatim.
#
# 3 designs x 2 windows = 6 combinations.
# --------------------------------------------------------------------------- #
EXPLICIT: list[dict] = [
    {
        **design,
        "start_year": start_year,
        "end_year": end_year,
    }
    for design, (start_year, end_year) in itertools.product(_DESIGNS, _WINDOWS)
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
    # a pin left behind silently freezes the sweep at the old value. That happened here
    # -- portfolio_weighting was pinned "equal" while the baseline moved to "mktcap",
    # which would have run all six cells equal-weighted. Re-check this block against
    # build_cfg() before launching, not after.

    # Percentile trim on sum_activities (the firm-year's total initiative count), applied
    # per tail, requested at 0.05 for all six runs. This USED to be a non-baseline value
    # that showed up in every run name; the baseline is now 0.05 too, so it no longer
    # reaches the cfg diff and no longer appears in any name.
    "alpha_bound": 0.05,

    # THE REGION. Drives currency_filter=["USD"], region_filter=["United States and
    # Canada"], convert_to_USD=False and fama_factor_region="United_States" via the region
    # block at experiments.py:357.
    "region_analysis": "United_States",

    # The materiality inner join is what makes a materiality design possible at all --
    # signal_0 is a MATERIAL share, read off the SASB workbook. Not optional here.
    "add_materiality": True,
    "materiality_version": 2,

    # NO materiality-split floor: a firm-year is split into material/immaterial however
    # few initiatives it has. Baseline. Worth revisiting only if the run's own
    # "Materiality split floor" audit table shows a large mass sitting at ratio exactly 1.
    "minimum_initatives_needed_to_split_by_materiality": 0,

    # Filter 2 ONLY (drop suspicious gvkeys). Chosen over "all", which would additionally
    # switch on "keep firms with >= 3 fiscal years of data" -- a survivorship screen, and
    # a particularly bad one on a 4-year window like 2016-2019.
    # CONSEQUENCE: filter 3, the min_initatives_annual_reports_if_execute_3_filters_true
    # floor, is SKIPPED under this mode (01_process_lc.py:398 gates it on `_all3`). That
    # knob therefore has NO EFFECT in this sweep at any value.
    "execute_3_filters": "suspicious_only",

    # CAP weighting: each holding gets its share of bucket market cap, with a single-name
    # ceiling of max_portfolio_weight_if_portfolio_weighting_equal (baseline 0.10 = 10%),
    # excess redistributed pro-rata and re-checked iteratively. This is the baseline as of
    # 2026-09-08 and is deliberate, so "base parameters" now means cap-weighted, not
    # equal-weighted. Pinned explicitly to keep it on the record.
    # CONSEQUENCE for the short window: under cap weighting a bucket where n * cap <= 1
    # (10 names or fewer at a 10% cap) has NO feasible weight vector, so the bucket-month
    # is DISCARDED as NaN -- and a NaN return is booked by (1+r).cumprod() as a fabricated
    # 0% month, which feeds the thin-portfolio gate. On 2016-2019 that is a second way for
    # a leg to vanish from a page, on top of the full-sample-calibrated gate itself. Check
    # n_months_discarded_infeasible in the coverage panel before reading an absence.
    # Set to "equal" to go back to 1/n; the ceiling knob is then ignored.
    "portfolio_weighting": "mktcap",

    # The market-cap screen and the thin-portfolio gate, both at baseline. See the window
    # note in the header block: the gate is calibrated on the full sample, so it is the
    # most likely reason a 2016-2019 leg goes missing from a page.
    "mktcap_covered_if_filter_by_cum_market_cap": 0.95,
    "min_stocks_per_portfolio": 25,
    "min_portfolio_coverage": 0.8,

    # no_simple_quantiles, start_year and end_year are NOT pinned here -- they are set by
    # every EXPLICIT cell, so a FIXED value would be overridden on all 6 combinations and
    # would only mislead a reader of this file.
}


# --------------------------------------------------------------------------- #
# Output settings
# --------------------------------------------------------------------------- #

# Rebuild results.pdf / results.csv from the ledger every N completed experiments.
# The ledger itself is appended after EVERY experiment regardless, so this only trades
# how fresh the two derived files are against the seconds each rebuild costs.
# Both are ALWAYS rebuilt once more when the sweep finishes (or is interrupted).
# Set to 2 here: with only 6 cells, waiting 10 runs would mean never rebuilding mid-sweep.
PDF_EVERY: int = 2

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
    # Outermost: the design, then the sort granularity. This puts the three designs in
    # blocks, so the pages read as One_Health K=3, One_Health K=5, Narrow_Health K=5.
    "action_characterization",
    "no_simple_quantiles",
    # Innermost: the window, so each design's pre-2020 page sits directly next to its
    # post-2020 page -- which is the comparison this sweep exists to make.
    "start_year",
    "end_year",
]

VALUE_ORDER: dict[str, list] = {
    # Wide group first, then the narrow subset of it.
    "action_characterization": [
        "Materiality_One_Health_SDGS",      # SDGs 3, 6, 8, 11, 14, 15
        "Materiality_Narrow_Health_SDGS",   # SDGs 3, 6, 11
    ],
}
