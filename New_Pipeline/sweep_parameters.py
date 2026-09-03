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

# --------------------------------------------------------------------------- #
# SWEEP_NAME: names this sweep's output folder, `sweep_output/<UTC stamp>_<name>/`.
# Change it to start a NEW sweep; re-running with the same name RESUMES the existing
# folder (that is what makes --resume work). `--new-run` forces a fresh folder anyway,
# and `--out DIR` overrides the whole thing.
# --------------------------------------------------------------------------- #
SWEEP_NAME: str = "health_sdg_groups"


# --------------------------------------------------------------------------- #
# The three Health_SDGS_Groups material/immaterial sorts, each crossed against the
# alpha-bound trim, the market-cap screen and the bucket count. One uniform cross this
# time -- unlike the per-SDG sweep this replaced, all three designs pool enough SDGs to
# take the full K range, so there is no per-design asymmetry to encode.
#
#   3 designs  x  alpha = .05,.1  x  mcap = .95,.99  x  K = 3,5,7  ->  36
#
# The three designs (membership from Health_SDGS_Groups in signal_definitions.py):
#
#   Materiality_One_Health_SDGS        SDGs 3, 6, 8, 11, 14, 15
#   Materiality_Narrow_Health_SDGS     SDGs 3, 6, 11
#   Materiality_Health_and_Work_SDGS   SDGs 3, 6, 8, 11
#
# Each is a ONE-GROUP design, so signal_0 is that group's material share and signal_1 is
# its exact mirror (corr = -1) -- the same two-signal shape as Materiality_People_SDG, and
# it qualifies for the initiative-decomposition PDF on the same empirical mirror check.
#
# FEASIBILITY -- measured, not extrapolated. Each design was run once at the default cell
# (alpha=.1, mcap=.95, K=7) and its monthly sort pool read off sort_buckets_by_month:
#
#                       n_assets/month            min_stocks    (gate = 25 names)
#                    p25   median   p75            at K=7
#   One_Health        251    304    385              35        clears everywhere
#   Health_and_Work   180    239    284              25        exactly at the gate
#   Narrow_Health     172    231    274              22        dips under in some months
#
# So all three clear the gate at K=3 and K=5 comfortably. At K=7 Narrow_Health's thinnest
# months fall to ~22 names and Health_and_Work sits exactly on 25. Those cells are KEPT
# rather than pruned: the gate is PRESENTATION-ONLY (the exported parquets always hold
# every portfolio), so the sweep will still report an alpha for a 22-name leg -- read every
# alpha__ column next to its coverage_pct__ neighbour, which is the evidence for whether
# that leg is thick enough to believe.
#
# alpha_bound=0.05 trims LESS than 0.1 (the bound is halved per tail, so 2.5% vs 5% each
# side), so every cell runs at least as large as the table above -- never smaller. The
# table is therefore the pessimistic side of this sweep.
#
# NOT swept here: minimum_initatives_needed_to_split_by_materiality. It stays at its
# default 0 on all 36 combinations. The per-SDG sweep this file replaced established that
# the floor does not reduce ratio-1.0 saturation within a single SDG (count and material
# share are positively correlated there), and these pooled designs carry enough
# initiatives per firm-year that the 1/1 case is largely trimmed already. Add a "floors"
# axis back if that needs re-testing on the pooled groups.
# --------------------------------------------------------------------------- #
_HEALTH_DESIGNS: list[str] = [
    "Materiality_One_Health_SDGS",
    "Materiality_Narrow_Health_SDGS",
    "Materiality_Health_and_Work_SDGS",
]

_ALPHA_BOUNDS: list[float] = [0.05, 0.1]
_MCAP: list[float] = [0.95, 0.99]
_QUANTILES: list[int] = [3, 5, 7]

# --------------------------------------------------------------------------- #
# GRID: expanded to its full cartesian product.
# Left empty -- action_characterization has to move together with add_materiality and
# materiality_version (pinned in FIXED below), and putting the design list in GRID would
# read as though the three designs were an independent axis rather than the subject of the
# sweep. EXPLICIT does the same cross and keeps that coupling visible.
# --------------------------------------------------------------------------- #
GRID: dict[str, list] = {}

# --------------------------------------------------------------------------- #
# EXPLICIT: hand-picked combinations, appended after the grid, used verbatim.
# For knobs that must move together (add_materiality + a materiality-only
# action_characterization, say) a grid cannot express the constraint — put them here.
#
# The full 3 x 2 x 2 x 3 cross = 36 combinations.
# --------------------------------------------------------------------------- #
EXPLICIT: list[dict] = [
    {"action_characterization": ac,
     "alpha_bound": alpha,
     "mktcap_covered_if_filter_by_cum_market_cap": mcap,
     "no_simple_quantiles": k}
    for ac in _HEALTH_DESIGNS
    for alpha in _ALPHA_BOUNDS
    for mcap in _MCAP
    for k in _QUANTILES
]

# --------------------------------------------------------------------------- #
# FIXED: merged into EVERY combination, grid and explicit alike. Use for knobs you want
# held constant across the whole sweep without repeating them in each entry.
# An entry in GRID/EXPLICIT wins over FIXED for the same key.
# --------------------------------------------------------------------------- #
FIXED: dict = {
    # Already the build_cfg baseline, but pinned explicitly: every design in this sweep
    # keys on the per-SDG material__total__SDG_N / immaterial__total__SDG_N columns,
    # which only the v2 SASB workbook carries.
    "add_materiality": True,
    "materiality_version": 2,
    "min_portfolio_coverage":0.8,
    # alpha_bound, mktcap_covered and no_simple_quantiles are NOT pinned here -- they are
    # the swept axes, and every EXPLICIT entry sets all three, so a FIXED value would be
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
# universe. On this machine (10 cores / 64 GB) 3-4 is the useful range; past that the
# runs contend for memory bandwidth and the wall-clock stops improving.
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
    # Outermost: all 12 of One_Health's cells, then Narrow_Health's, then
    # Health_and_Work's -- ordered by VALUE_ORDER below, not alphabetically.
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
    # Pages group by signal design, in this order -- widest SDG membership first, so the
    # pool shrinks as you read down (One_Health 6 SDGs -> Health_and_Work 4 -> Narrow 3).
    # Within each group they run through every alpha_bound x mcap x K combination.
    "action_characterization": [
        "Materiality_One_Health_SDGS",
        "Materiality_Health_and_Work_SDGS",
        "Materiality_Narrow_Health_SDGS",
    ],
}