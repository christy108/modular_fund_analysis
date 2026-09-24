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
SWEEP_NAME: str = "us_momentum_people_prosperity"


# --------------------------------------------------------------------------- #
# WHAT THIS SWEEP IS
#
# US half: five SDG-materiality designs crossed with the weighting scheme, the sort
# granularity and the market-cap screen, on the FULL 2016-2024 sample.
#
#   5 designs  x  2 weighting schemes  x  2 quantile counts  x  2 mcap screens
#   = 40 runs
#
# Everything else is the build_cfg baseline, pinned in FIXED below.
#
# THE DESIGNS. All five are one-group MIRROR PAIRS: signal_0 is a material SHARE of the
# group's SDGs and signal_1 = 1 - signal_0, so High on one leg is Low on the other and the
# two High-Low spreads are exact negatives. On the risk panel that shows up as one green
# row and one red row per pair, which is expected, not a bug -- the colour is carrying
# the sign. Listed widest denominator first, narrowing down:
#
#   Material_Immaterial_only                "All SDGs" -- material__total vs
#                                           immaterial__total, no SDG scoping at all.
#                                           This is the build_cfg BASELINE design; see
#                                           the NAMES note below for what that does to
#                                           the run names.
#   Materiality_People_Plus_Prosperity_SDG  "People+Prosperity" -- SDGs 1-5, 8-11, 16, 17
#                                           (everything but the six Planet SDGs).
#   Materiality_One_Health_SDGS             "One Health" -- Health_SDGS_Groups'
#                                           One_Health cut: SDGs 3, 6, 8, 11, 14, 15.
#   Materiality_One_Health_Ex_SDG_8_SDGS    "One Health ex SDG8" -- the same group with
#                                           SDG 8 (decent work) dropped: SDGs 3, 6, 11,
#                                           14, 15. Added at commit 6121b23.
#   Materiality_Narrow_Health_SDGS          "Narrow Health" -- the tightest cut: SDGs
#                                           3, 6, 11 only.
#
# THESE ARE NOT FIVE INDEPENDENT TESTS. The three health cuts are nested subsets of one
# another ({3,6,11} < {3,6,11,14,15} < {3,6,8,11,14,15}), so read a difference between
# them as "does narrowing the denominator concentrate or dilute the signal". All-SDGs and
# People+Prosperity are NOT nested inside the health cuts, but they share the same
# material/immaterial numerator construction, and All-SDGs is a strict superset of every
# other design's SDG set -- it is the reference line the four narrower cuts are read
# against, which is exactly why it is in this sweep.
#
# ONE DENOMINATOR CAVEAT. Every design here is a SINGLE group, so with
# signal_denominator="Sum_All_Signals" each one's denominator is its OWN group's material
# + immaterial count -- "material share WITHIN this SDG set", not "share of all
# initiatives". That is what keeps the five comparable as alphas. Do not read a
# People+Prosperity spread against an All-SDGs spread as if they shared a denominator;
# they do not. (The 4-signal Materiality_People_Plus_Prosperity_VS_Planet_SDG design does
# change the denominator to all-initiatives -- it is deliberately NOT in this sweep.)
#
# THE WEIGHTING AXIS ("Mkt cap weighted" and "EQ weights"). portfolio_weighting="mktcap"
# is the build_cfg baseline; "equal" is the classic unweighted High-minus-Low. Requested
# explicitly as both, so this sweep reports each design at both. Expect cap weighting to
# damp the spread relative to equal weighting whenever the material/immaterial split is
# correlated with size -- and to occasionally DISCARD a bucket-month outright (see the
# INTERACTION note below), which equal weighting never does.
#
# THE MARKET-CAP AXIS. mktcap_covered_if_filter_by_cum_market_cap keeps the largest firms
# per region-year until this share of total market cap is covered. 0.95 is the baseline;
# 0.99 is LOOSER -- it admits a longer tail of small caps. Both values have completed on
# the US before (the earlier 8-cell FF5 sweep ran clean at 0.99), so this axis is safe
# here. If 0.95 and 0.99 give the same answer, that is the useful result: the spread is
# not an artefact of where the tail was cut.
#
# INTERACTION WORTH KNOWING. Cap weighting discards a bucket-month outright when
# `n * cap <= 1` -- ten names or fewer at the 10% ceiling -- because no weight vector can
# satisfy both the budget and the cap. The NaN is then booked by (1+r).cumprod() as a
# fabricated 0% month and feeds the thin-portfolio gate. "Narrow Health" at K=5 is the
# thinnest configuration in this file (narrowest group, most buckets); check
# `n_months_discarded_infeasible` in the coverage panel before reading a missing leg as a
# result on any of its cap-weighted cells.
#
# WHY 40 AND NOT FEWER. Four independent axes, each genuinely worth seeing both sides of:
# dropping any one of them would leave a real question unanswered (which design, which
# weighting, which K, which mcap screen). 40 cells at roughly five minutes each is on the
# order of three and a half hours serial (under two hours at JOBS=2) -- still smaller than
# prior sweeps in this repo, which ran 36 and 128 cells.
#
# NAMES: experiment_name() builds each run name from the cfg DIFF against build_cfg().
# The baseline is action_characterization=Material_Immaterial_only, portfolio_weighting=
# mktcap, no_simple_quantiles=5, mktcap_covered_if_filter_by_cum_market_cap=0.95 and
# region_analysis="United_States". The US region choice therefore appears in no name.
#
# NOTE THE CHANGE FROM THE PREVIOUS VERSION OF THIS SWEEP: Material_Immaterial_only IS
# the baseline design, so its eight cells do NOT carry action_characterization in their
# names, and the one cell that matches the baseline on all four axes (All-SDGs, mktcap,
# K=5, 0.95) diffs to nothing and lands on a **base_parameters** page. That is correct,
# not a missing design -- the other seven All-SDGs cells are still named by whichever
# axes they move. Every cell of the other four designs carries its design in the name as
# before.
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# GRID: expanded to its full cartesian product.
#
# All four axes here are genuinely INDEPENDENT -- unlike the pre/post-2020 sweep this
# file used to hold, where a window was a PAIR of keys (start_year, end_year) that had to
# move together and so had to be built in EXPLICIT. Nothing is paired now, so GRID is the
# right tool and EXPLICIT stays empty.
#
#   5 designs x 2 weighting schemes x 2 quantile counts x 2 mcap screens = 40 cells
# --------------------------------------------------------------------------- #
GRID: dict[str, list] = {
    # Widest denominator first, narrowing down: all 17 SDGs, then People+Prosperity, then
    # the three nested health cuts.
    "action_characterization": [
        "Material_Immaterial_only",
        "Materiality_People_Plus_Prosperity_SDG",
        "Materiality_One_Health_SDGS",
        "Materiality_One_Health_Ex_SDG_8_SDGS",
        "Materiality_Narrow_Health_SDGS",
    ],
    # Cap-weighted first (also the build_cfg baseline), then equal-weighted.
    "portfolio_weighting": ["mktcap", "equal"],
    # Sort granularity: coarse 3-way and finer 5-way. K=5 is the baseline, so only the
    # K=3 cells carry no_simple_quantiles in their run name.
    "no_simple_quantiles": [3, 5],
    # Market-cap coverage of the screen. 0.95 is the baseline; 0.99 is the looser cut.
    # Both are safe on the US -- see the header note.
    "mktcap_covered_if_filter_by_cum_market_cap": [0.95, 0.99],
}

# --------------------------------------------------------------------------- #
# EXPLICIT: hand-picked combinations, appended after the grid, used verbatim.
# EMPTY -- the whole cross is a clean cartesian product, so it belongs in GRID.
# --------------------------------------------------------------------------- #
EXPLICIT: list[dict] = []

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
    # Outermost: the design, so the five groups read as five blocks of eight.
    "action_characterization",
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
    # Widest denominator first, narrowing down -- so the PDF reads as a progressive
    # tightening of the SDG set, with the All-SDGs reference block at the front.
    "action_characterization": [
        "Material_Immaterial_only",                # all 17 SDGs
        "Materiality_People_Plus_Prosperity_SDG",  # SDGs 1-5, 8-11, 16, 17
        "Materiality_One_Health_SDGS",             # SDGs 3, 6, 8, 11, 14, 15
        "Materiality_One_Health_Ex_SDG_8_SDGS",    # SDGs 3, 6, 11, 14, 15
        "Materiality_Narrow_Health_SDGS",          # SDGs 3, 6, 11
    ],
    # Cap-weighted first, matching Kevin's own ordering ("Mkt cap weighted" then
    # "And EQ weights").
    "portfolio_weighting": ["mktcap", "equal"],
}
