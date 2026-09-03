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
SWEEP_NAME: str = "pp_action_sdg"


# --------------------------------------------------------------------------- #
# Every behavioural ACTION of the People+Prosperity material/immaterial split, each
# crossed against the alpha-bound trim, the market-cap screen and the bucket count.
#
#   6 actions  x  N = 0,3,5  x  alpha = .05,.1  x  mcap = .95,.99  x  K = 3,5,7  ->  216
#
# (innovation and total dropped, a floor axis added, mcap held at .95 --
#  see _PP_ACTIONS and _FLOORS below.)
#
# The design is `action_characterization="Materiality_PP_Action_SDG"` throughout (pinned
# in FIXED). WHICH action is the cfg key `materiality_pp_action`, not a separate
# characterization string -- one branch in experiments.py covers all eight, which is
# exactly what makes the action a sweepable axis here rather than eight hand-written
# entries. Each cell is a ONE-GROUP design: signal_0 is that action's material share
# across the 11 People+Prosperity SDGs and signal_1 is its exact mirror (corr = -1), the
# same two-signal shape as Materiality_People_SDG on a strictly thinner denominator
# (material__<action>__SDG_n instead of material__total__SDG_n).
#
# `total` is EXCLUDED: it is byte-identical to
# base_materiality_people_plus_prosperity_only (untagged signal names, same columns), so a
# `total` row would spend runs re-deriving a config that already exists. It is still the
# right dense reference to read the six action rows against -- just take it from that
# existing run rather than from this sweep.
#
# THE EIGHT ACTIONS ARE NOT EIGHT DISJOINT SLICES. They are TWO alternative classification
# schemes over the SAME initiatives, plus the total both share (process_materiality.py:23):
#
#   new 4-category split : adaptation, advocacy_new_def, innovation, upskilling
#   old 3-category split : advocacy_old_def, preparation, transformation   ("Matteo")
#
# Verified on the v_2A1 workbook: the new-4 sum to __total__ EXACTLY -- row-wise, every
# row, per SDG (material 1,584,943 = 1,584,943; max per-row gap 0 on the SDGs checked).
# The old-3 do NOT: they recover ~91% of __total__ in aggregate and match row-wise on only
# ~84-88% of rows, so ~8-9% of initiatives carry no old-scheme label at all.
#
# So: (a) the seven action rows DOUBLE-COUNT the panel -- advocacy_new_def vs
# advocacy_old_def compares two DEFINITIONS of one concept, not two behaviours, and the
# 96 pages are not one ranking of eight distinct actions; (b) a decomposition argument
# ("where does total's alpha come from?") is available for the new-4 and NOT for the
# old-3, because only the new-4 add back up to the row they would be decomposing.
#
# FEASIBILITY -- measured on the v_2A1 workbook (72,412 firm-years), not extrapolated.
# Denominator is material + immaterial for that action across the 11 P+P SDGs; "usable"
# is firm-years holding at least one such initiative (the rest are 0/0 and cannot be
# sorted at all); "@1.0"/"@0.0" are the share of USABLE firm-years on the ratio's atoms:
#
#   action              mean  median      usable      @1.0    @0.0   distinct
#   total              21.01      12   69,543  96.0%   21.2%    6.4%     2,751
#   advocacy_new_def   12.32       7   65,338  90.2%   26.3%    9.7%     1,631
#   advocacy_old_def   11.81       7   63,985  88.4%   25.6%   10.8%     1,551
#   upskilling          5.19       3   57,845  79.9%   36.1%   16.8%       549
#   preparation         5.02       3   56,169  77.6%   41.4%   13.1%       540
#   adaptation          3.10       1   49,414  68.2%   59.2%   10.2%       301  <-- thin
#   transformation      2.66       1   45,795  63.2%   58.8%   11.5%       334  <-- thin
#   innovation          0.40       0   13,340  18.4%   58.7%   27.3%        92  <-- degenerate
#
# READ THE BOTTOM THREE AS CONTROLS, NOT RESULTS -- and that judgement is about the
# SIGNAL, so it does not soften at K=3. adaptation and transformation have a median
# denominator of 1, so for over half their usable firm-years the "material share" is
# literally 1/1 or 0/1; innovation has 92 distinct values in the whole panel and only
# 18.4% of firm-years usable. A quantile sort on any of the three is mostly cutting ties,
# and its High leg is a coin-flip subset of the tie block rather than a ranked portfolio.
# They are swept on the full cross anyway, deliberately: a spread that appears there and
# not in the dense actions is evidence of the tie-breaking, not of materiality.
#
# The thin actions also drive the K axis hardest -- innovation's usable pool is ~1/5 of
# total's, so its K=7 legs are the thinnest cells in the whole sweep and some will fall
# under the 25-name presentation gate. Those cells are KEPT, not pruned: the gate is
# PRESENTATION-ONLY (the exported parquets always hold every portfolio), so the sweep
# still reports an alpha for a thin leg -- read every alpha__ column next to its
# coverage_pct__ neighbour, which is the evidence for whether that leg is thick enough to
# believe. alpha_bound=0.05 trims LESS than 0.1 (halved per tail, 2.5% vs 5% each side),
# so the 0.05 cells run at least as large as the 0.1 ones, never smaller.
#
# minimum_initatives_needed_to_split_by_materiality IS swept here, over 0/3/5 -- see
# _FLOORS below for the measured cost per action and for which action x N x K cells fall
# under the presentation gate.
#
# NAMES: experiment_name() builds the run name from the cfg diff, and
# "Materiality_PP_Action_SDG" plus the action plus three numeric axes runs past the
# 150-char cap, so most runs land as a 140-char prefix + `__h<blake2b>` suffix. Unique and
# deterministic (so --resume works), but not readable -- use the PDF page titles and the
# CSV columns to identify a cell, not the directory name.
# --------------------------------------------------------------------------- #
# innovation is REMOVED, on measured grounds rather than taste. Run at the default cell
# its post-trim panel is 765 firm-years / 34 assets a month -- 4 names per bucket at K=7,
# every K x N cell under the 25-name gate -- and the floor annihilates it: N=2 leaves 81
# firm-years, N=3 leaves 17, N=5 leaves ZERO. Its @1.0 "improving" to 29.4% at N=3 is 17
# firm-years, not a signal. The workbook table above says 13,340 usable, which is why it
# looked sweepable: the alpha-bound trim then removes almost all of them, because it trims
# on sum_activities and innovation IS the low-count tail. Nothing to sweep, so it is out.
_PP_ACTIONS: list[str] = [
    # "total" removed: it is byte-identical to base_materiality_people_plus_prosperity_only
    # (same columns, same untagged signal names), so its cells would re-run a config that
    # already exists rather than produce a new result. Read the six action rows against
    # that existing run for the dense-reference comparison.
    "advocacy_new_def",
    "advocacy_old_def",
    "upskilling",
    "preparation",
    "adaptation",
    "transformation",
]

_ALPHA_BOUNDS: list[float] = [0.05, 0.1]
_MCAP: list[float] = [0.95, 0.99]
_QUANTILES: list[int] = [3, 5, 7]

# The materiality-split floor: require at least N (material + immaterial) initiatives in
# the action before the firm-year may be split into a material share at all. 0 = off.
#
# 0/3/5 rather than 0/2/3/5: N=2 buys the least de-saturation per firm-year spent (measured
# N=0->2 vs N=0->3 on every action), and a fourth value would take this sweep to 168 runs.
#
# MEASURED COST, from each action's own materiality_split_floor audit at the default cell
# (alpha=0.1, mcap=0.95) -- post-trim firm-years, and @1.0 = % of them at ratio exactly 1.0:
#
#                     N=0                N=3                N=5
#   action        firm-yrs  @1.0    firm-yrs  @1.0     firm-yrs  @1.0
#   total*           --      --        --      --         --      --
#   advocacy_new_def  7,296  25.4%     6,357  20.3%      5,574  17.9%
#   advocacy_old_def  7,281  24.8%     6,336  19.7%      5,567  17.1%
#   upskilling        6,701  38.8%     4,985  30.9%      3,706  27.7%
#   preparation       6,474  45.0%     4,581  36.2%      3,285  33.0%
#   adaptation        5,868  64.5%     3,332  54.9%      1,891  49.3%
#   transformation    5,177  68.0%     2,579  57.4%      1,343  52.5%
#   (*total not run standalone; it is base_materiality_people_plus_prosperity_only)
#
# THE FLOOR IS NOT UNIFORMLY WORTH IT, and the K axis is where that shows up:
#   - advocacy_new_def / advocacy_old_def clear the 25-name gate at EVERY N x K. Safe.
#   - upskilling / preparation clear everything except the N=5 x K=7 corner (23 and 20).
#   - adaptation / transformation are where it backfires: at N=5 they are STILL 49% and 53%
#     saturated -- worse than preparation is for free at N=0 -- having given up 68% and 74%
#     of their sample. Their N=3/K=7 and N=5/K=5+ cells fall under the gate.
# Those failing cells are kept for the same reason the rest of this file keeps them (the
# gate is presentation-only), but do not read a floored adaptation/transformation spread as
# a de-saturation success: check @1.0 moved before crediting the floor.
_FLOORS: list[int] = [0, 3, 5]

# --------------------------------------------------------------------------- #
# GRID: expanded to its full cartesian product.
#
# All four axes belong here this time (unlike the Health_SDGS sweep this file replaced,
# where the design list had to sit in EXPLICIT). The design itself does NOT vary --
# action_characterization is constant and pinned in FIXED alongside add_materiality /
# materiality_version, which is where that coupling lives. What varies is
# materiality_pp_action, a plain scalar cfg key that is genuinely independent of the
# other three, so a cross expresses it honestly.
#
#   6 actions x 3 floors x 2 alpha x 2 mcap x 3 K = 216 combinations.
#
# The floor belongs in the cross rather than in EXPLICIT because it is legal on every one
# of these designs: each is ONE-GROUP, and build_cfg only raises on a non-zero floor when
# the design has more than one materiality group (which would make the floor mean "drop
# unless EVERY group clears N" -- see apply_cross_signal_nan_mask). Verified: all 18
# action x floor pairs build.
# --------------------------------------------------------------------------- #
GRID: dict[str, list] = {
    "materiality_pp_action": _PP_ACTIONS,
    "minimum_initatives_needed_to_split_by_materiality": _FLOORS,
    "alpha_bound": _ALPHA_BOUNDS,
    "mktcap_covered_if_filter_by_cum_market_cap": _MCAP,
    "no_simple_quantiles": _QUANTILES,
}

# --------------------------------------------------------------------------- #
# EXPLICIT: hand-picked combinations, appended after the grid, used verbatim.
# For knobs that must move together (add_materiality + a materiality-only
# action_characterization, say) a grid cannot express the constraint — put them here.
#
# Empty: the whole sweep is one uniform cross, which GRID above states directly.
# --------------------------------------------------------------------------- #
EXPLICIT: list[dict] = []

# --------------------------------------------------------------------------- #
# FIXED: merged into EVERY combination, grid and explicit alike. Use for knobs you want
# held constant across the whole sweep without repeating them in each entry.
# An entry in GRID/EXPLICIT wins over FIXED for the same key.
# --------------------------------------------------------------------------- #
FIXED: dict = {
    # The design under test. Held constant: materiality_pp_action (in GRID) is what
    # selects which of the eight actions this characterization sorts on, and build_cfg
    # RAISES if that key is None here -- the two must move together, which is why the
    # characterization is pinned rather than swept.
    "action_characterization": "Materiality_PP_Action_SDG",
    # Already the build_cfg baseline, but pinned explicitly: every cell keys on the
    # per-SDG per-action material__<action>__SDG_n / immaterial__<action>__SDG_n columns,
    # which only the v2 SASB workbook carries.
    "add_materiality": True,
    "materiality_version": 2,
    "min_portfolio_coverage": 0.8,
    # alpha_bound, mktcap_covered and no_simple_quantiles are NOT pinned here -- they are
    # swept axes, and every GRID cell sets all three, so a FIXED value would be overridden
    # on all 216 combinations and only mislead a reader of this file.
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
    # Outermost: all 18 of advocacy_new_def's cells, then advocacy_old_def's, and so on down the
    # density table -- ordered by VALUE_ORDER below, not alphabetically.
    "materiality_pp_action",
    # Then the floor, so within one action its N=0/3/5 blocks are contiguous: the
    # comparison the floor axis exists for is "same action, same alpha/mcap/K, does the
    # spread survive raising N", and that reads best with N as the outer sub-key.
    "minimum_initatives_needed_to_split_by_materiality",
    # Then alpha_bound / mcap / K, innermost-last, so within one action+floor the pages
    # read as each (alpha, mcap) pair carrying its K=3/5/7 triple adjacent -- which is the
    # comparison you actually make (does the spread survive a finer sort, at fixed trim
    # and market-cap screen).
    "alpha_bound",
    "mktcap_covered_if_filter_by_cum_market_cap",
    "no_simple_quantiles",
]

VALUE_ORDER: dict[str, list] = {
    # Pages run in DESCENDING signal density (the table above), not alphabetically: the
    # dense, trustworthy sorts first, the tie-dominated controls last. Read top-down and
    # the denominator thins as you go, which is the right frame for judging whether a
    # spread further down is signal or tie-breaking.
    # "total" and "innovation" are both absent because neither is swept -- see
    # _PP_ACTIONS for why (one is a duplicate config, the other has no sortable panel).
    "materiality_pp_action": [
        "advocacy_new_def",
        "advocacy_old_def",
        "upskilling",
        "preparation",
        "adaptation",
        "transformation",
    ],
}
