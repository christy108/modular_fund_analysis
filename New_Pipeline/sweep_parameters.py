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
# The previous sweep in this file was "europe_materiality_12_designs" (128 cells, all
# completed — sweep_output/20260906T085424Z_europe_materiality_12_designs/). Renaming is
# what keeps this sweep's ledger separate from it. To go back and add cells to that one,
# restore this file from git (commit 2d3c752) rather than editing the name back: the
# worklist has to match or --resume cannot recognise what already ran.
# --------------------------------------------------------------------------- #
SWEEP_NAME: str = "europe_plain_action_signals"


# --------------------------------------------------------------------------- #
# The two ORIGINAL behavioural signal designs on the EUROPE sample — no materiality
# split, no SDG cut — crossed against the alpha-bound trim, the market-cap screen and
# the bucket count.
#
#   2 designs  x  alpha = .05,.1  x  mcap = .85,.9,.95  x  K = 3,5,7  ->  36
#
# This is the plain-signal counterpart to the materiality sweep that just finished. There
# the signal was always a material SHARE, Material / (Material + Immaterial), cut by SDG
# group or behavioural action. Here the signal is the firm's initiative MIX: each
# signal_i is that action's share of the firm's total initiatives, keyed directly on the
# raw `TYPE:` / `TYPE_SREC:` columns of the Golden dataset. The SASB workbook is not
# consulted for the signal at all.
#
# So the pair of sweeps answers "does the behavioural mix sort returns on its own, before
# materiality enters" — which is the right baseline to read the materiality results
# against, and the reason the sample is held identical (see add_materiality in FIXED).
#
# THE TWO DESIGNS ARE ALTERNATIVE CUTS OF THE SAME INITIATIVES, NOT TWO DATASETS. Both
# partition a firm's initiatives; they disagree about the partition:
#
#   original_matteo  (3) : advocacy / preparation / transformation
#   4_signals_new    (4) : Advocacy / Upskilling / Adaptation-change / Innovation
#
# They also key on DIFFERENT COLUMN VOCABULARIES, which is the trap here. original_matteo
# reads the fine-grained `TYPE_SREC: <action> - <stakeholder>` columns (donation,
# volunteerism, communication/training/incentives/organizational-structuring split by
# stakeholder) alongside `TYPE:` ones; 4_signals_new reads only the coarse `TYPE:`
# columns (`TYPE: communication`, `TYPE: training`, `TYPE: incentives`, ...). They are
# not a relabelling of one another and their denominators are not the same set of
# initiatives, so a difference between the two designs is a difference in what was
# counted as well as in how it was grouped. Do not read them as a 3-way vs 4-way split of
# one fixed pie.
#
# NOTE both designs are MULTI-SIGNAL, unlike every design in the materiality sweep (which
# were one-group mirror pairs, signal_1 = 1 - signal_0). Consequences worth expecting:
#   * 3 signals -> 6 legs, 4 signals -> 8 legs, each with its own High/Low sort and its
#     own row in every table. The pages are wider than the last sweep's.
#   * the signals sum to 1 across groups (signal_denominator="Sum_All_Signals"), so they
#     are compositional: one action's share can only rise if another's falls. Treat the
#     legs as relative-mix bets, not independent signals.
#   * there is no mirror pair, so High - Low on one signal is NOT the negative of another
#     signal's spread the way it was last time.
#
# NO MINIMUM-INITIATIVES AXIS, and neither candidate knob could have provided one:
#   * minimum_initatives_needed_to_split_by_materiality gates the material/immaterial
#     SPLIT, so build_cfg RAISES on it for both designs here (they have no such pair).
#     It is materiality-only by construction and has no meaning for a plain action
#     design. Pinned at 0 in FIXED; it cannot be anything else.
#   * min_initatives_annual_reports_if_execute_3_filters_true runs only under
#     execute_3_filters="all" (01_process_lc.py:398 gates it on `_all3`). This sweep pins
#     "suspicious_only" to avoid "all"'s 3-fiscal-year survivorship filter, so that knob
#     is inert here -- sweeping it would have produced 108 duplicate runs of 36 distinct
#     configs. Left at its baseline.
# The sample screen that IS live on this sweep is alpha_bound, which trims the tails of
# sum_activities (the firm-year's total initiative count) -- a percentile trim rather
# than an absolute floor, and it is a swept axis.
#
# NAMES: experiment_name() builds the run name from the cfg DIFF against build_cfg().
# Neither design equals the baseline action_characterization (Material_Immaterial_only),
# so both appear in every name and page title — no "base_parameters" cell this time, and
# the names stay well inside the 150-char cap.
# --------------------------------------------------------------------------- #
_DESIGNS: list[dict] = [
    # 1. The original "Matteo" 3-way action split.
    #    advocacy = donation & funding, volunteerism, and the local-communities SREC
    #      actions (communication / training / incentives / organizational structuring)
    #    preparation = adoption of standards and rules, assessment and measurement, and
    #      the employee-facing SREC actions
    #    transformation = asset modification, modification of procedures, new products,
    #      r&d investments, and the customer / shareholder / supplier SREC actions
    {"action_characterization": "original_matteo"},

    # 2. The newer 4-way behavioural split (pre-Nikkei), on the coarse TYPE: columns.
    #    Advocacy = donation & funding, communication, association
    #    Upskilling = training, volunteerism
    #    Adaptation-change = standards and rules, assessment and measurement, incentives,
    #      organizational structuring, asset modification, modification of procedures
    #    Innovation = new products, r&d investments
    {"action_characterization": "4_signals_new"},
]

_ALPHA_BOUNDS: list[float] = [0.05, 0.1]
_MCAP: list[float] = [0.85, 0.9, 0.95]
_QUANTILES: list[int] = [3, 5, 7]


# --------------------------------------------------------------------------- #
# GRID: expanded to its full cartesian product. EMPTY — kept that way for symmetry with
# the cross built in EXPLICIT below, so there is exactly one place to read the design
# list and one place to read the numeric axes. With only a single design key this time
# (no ragged materiality_pp_action), a GRID would in fact work; EXPLICIT is used anyway
# so that adding a design that DOES carry a second key needs no restructuring.
# --------------------------------------------------------------------------- #
GRID: dict[str, list] = {}

# --------------------------------------------------------------------------- #
# EXPLICIT: hand-picked combinations, appended after the grid, used verbatim.
#
# The full cross: 2 designs x 2 alpha x 3 mcap x 3 K = 36 combinations.
# --------------------------------------------------------------------------- #
EXPLICIT: list[dict] = [
    {
        **design,
        "alpha_bound": alpha,
        "mktcap_covered_if_filter_by_cum_market_cap": mcap,
        "no_simple_quantiles": k,
    }
    for design, alpha, mcap, k in itertools.product(
        _DESIGNS, _ALPHA_BOUNDS, _MCAP, _QUANTILES
    )
]

# --------------------------------------------------------------------------- #
# FIXED: merged into EVERY combination, grid and explicit alike. Use for knobs you want
# held constant across the whole sweep without repeating them in each entry.
# An entry in GRID/EXPLICIT wins over FIXED for the same key.
#
# Every key here already equals the build_cfg baseline, so none of them reaches the cfg
# diff and none pollutes a run name or page title. They are pinned anyway: this file is
# the record of what the sweep was, and "it inherited whatever experiments.py said that
# week" is not a record.
# --------------------------------------------------------------------------- #
FIXED: dict = {
    # THE REGION. Drives currency_filter (CHF/GBP/EUR/NOK/SEK/DKK), region_filter
    # (MacroRegion == "Europe" plus the 16 FF-Europe domiciles), convert_to_USD=True and
    # fama_factor_region="Europe" via the region block at experiments.py:315.
    "region_analysis": "Europe",
    # KEPT ON DELIBERATELY, even though neither design reads a materiality column. It is
    # an INNER JOIN onto the SASB workbook, so it defines the SAMPLE: leaving it True
    # holds the firm-years identical to the materiality sweep, which is the whole point
    # of running these two designs (a plain-signal result on a wider sample would
    # confound the signal change with a sample change).
    # It is also free here: measured on the v_2A1 workbook, the materiality v2 file
    # covers 100% of the European 2016-2024 firm-years (14,265 of 14,265), so the inner
    # join drops nothing on this region. Setting it False would therefore change little
    # in practice -- but "little" is not "nothing", and comparability is worth more.
    "add_materiality": True,
    "materiality_version": 2,
    "min_portfolio_coverage": 0.8,
    # Filter 2 ONLY (drop suspicious gvkeys). This equals the build_cfg baseline and is
    # chosen deliberately over "all": "all" would additionally switch on filter 1, "keep
    # firms with >= 3 fiscal years of data", a survivorship screen that changes the sample
    # and would break comparability with the materiality sweep.
    #
    # CONSEQUENCE, and it is the important one: filter 3 -- the
    # min_initatives_annual_reports_if_execute_3_filters_true floor -- is SKIPPED under
    # this mode. 01_process_lc.py:398 gates it on `_all3`, which is False here. So that
    # knob has NO EFFECT in this sweep at any value.
    "execute_3_filters": "suspicious_only",

    # PINNED OFF, and it cannot be anything else on these designs. build_cfg raises for
    # both at any non-zero value: the floor gates the split of a group into material vs
    # immaterial, and a plain action design has no material/immaterial group pair
    # (experiments.py:611). Pinned explicitly so the constraint is on the record here
    # rather than discovered as a traceback.
    "minimum_initatives_needed_to_split_by_materiality": 0,
    # alpha_bound, mktcap_covered and no_simple_quantiles are NOT pinned here -- they are
    # swept axes, and every EXPLICIT cell sets all three, so a FIXED value would be
    # overridden on all 36 combinations and only mislead a reader of this file.
}


# --------------------------------------------------------------------------- #
# Output settings
# --------------------------------------------------------------------------- #

# Rebuild results.pdf / results.csv from the ledger every N completed experiments.
# The ledger itself is appended after EVERY experiment regardless, so this only trades
# how fresh the two derived files are against the seconds each rebuild costs.
# Both are ALWAYS rebuilt once more when the sweep finishes (or is interrupted).
PDF_EVERY: int = 10

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
    # Outermost: the design. ONE key is enough this time -- unlike the materiality sweep,
    # no two designs share an action_characterization, so materiality_pp_action (None
    # throughout) would add nothing.
    "action_characterization",
    # Then alpha_bound / mcap / K, innermost-last, so within one design the pages read as
    # each (alpha, mcap) pair carrying its K=3/5/7 triple adjacent -- which is the
    # comparison you actually make (does the spread survive a finer sort, at fixed trim
    # and market-cap screen).
    "alpha_bound",
    "mktcap_covered_if_filter_by_cum_market_cap",
    "no_simple_quantiles",
]

VALUE_ORDER: dict[str, list] = {
    # The 3-way split first, then the 4-way, matching how they were asked for.
    "action_characterization": [
        "original_matteo",   # 1. advocacy / preparation / transformation
        "4_signals_new",     # 2. Advocacy / Upskilling / Adaptation-change / Innovation
    ],
}
