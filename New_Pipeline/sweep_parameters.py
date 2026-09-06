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
# RENAMED from "pp_action_sdg" deliberately. That sweep ran on region_analysis =
# United_States; this one runs on Europe. Keeping the old name would have RESUMED the US
# folder and appended EU cells to the same ledger, and results.csv / results.pdf would
# then interleave two regions with nothing in the row or the page title to tell them
# apart (region_analysis is pinned in FIXED below, so it equals the baseline and never
# reaches the cfg diff the names are built from).
# --------------------------------------------------------------------------- #
SWEEP_NAME: str = "europe_materiality_12_designs"


# --------------------------------------------------------------------------- #
# ELEVEN material-share designs on the EUROPE sample, each crossed against the
# materiality-split floor, the alpha-bound trim, the market-cap screen and the bucket
# count.
#
#   11 designs  x  N = 0,3  x  alpha = .05,.1  x  mcap = .875,.9,.95  x  K = 3,5,7  ->  396
#
# Every design is the same quantity in a different slice: Material / (Material +
# Immaterial), i.e. signal_0 is a material SHARE and signal_1 is its exact mirror
# (corr = -1). What varies is the denominator — which SDGs, and whether it is the SDG
# total or one behavioural action within it. Read across designs as "does the material
# share still sort when you narrow what counts", not as eleven independent signals.
#
# THESE ARE NOT ELEVEN DISJOINT SLICES. Three separate overlaps are baked in, and each
# one is a comparison you can and cannot make:
#
#  * #1 is ALL 17 SDGs; #2 is the People+Prosperity subset of it (SDGs 1-5, 8-11, 16, 17
#    — everything except Planet 6, 7, 12, 13, 14, 15). #2 is nested inside #1.
#  * #3-#5 (Matteo) and #6-#8 (Behavioural) are TWO ALTERNATIVE CLASSIFICATION SCHEMES
#    over the SAME initiatives, both cut to People+Prosperity, and #2 is the total they
#    both partition. So "Matteo Advocacy" vs "Behavioural Advocacy" compares two
#    DEFINITIONS of one concept, not two behaviours. Verified on the v_2A1 workbook: the
#    Behavioural FOUR sum to the total EXACTLY (row-wise, every row, per SDG); the Matteo
#    three do NOT — they recover ~91% in aggregate and match row-wise on ~84-88% of rows,
#    so ~8-9% of initiatives carry no Matteo label at all.
#    NOTE the decomposition argument ("where does #2's alpha come from?") needs all FOUR
#    Behavioural actions, and innovation is NOT swept here (see below), so #6-#8 leave a
#    residual rather than adding back up to #2. The residual is small — innovation is
#    ~2% of the total by mean count — but the decomposition is no longer exact, so state
#    it as "three of the four" if you use it.
#  * #9-#11 are three nested health cuts (Narrow ⊂ Health+Work ⊂ One Health) and they
#    cross the People/Planet line — SDG 6, 14 and 15 are Planet — so they are NOT
#    subsets of #2. They are subsets of #1 only.
#
# SIGNAL DENSITY — measured on the v_2A1 workbook, US-era numbers (72,412 firm-years).
# They are the best available guide to which designs are sortable, but the EUROPE panel
# is roughly a fifth the size (~950-2,050 LC firms a year overlap the Compustat extract
# BEFORE the market-cap screen, which at 0.95 discards ~65% of listings by count), so
# read every row below as an upper bound on what Europe will deliver. "usable" is
# firm-years holding at least one initiative in that denominator (the rest are 0/0 and
# cannot be sorted); "@1.0"/"@0.0" are the share of usable firm-years sitting on the
# ratio's atoms:
#
#   design (P+P action)  mean  median      usable      @1.0    @0.0   distinct
#   #2  total (P+P)     21.01      12   69,543  96.0%   21.2%    6.4%     2,751
#   #6  advocacy_new     12.32       7   65,338  90.2%   26.3%    9.7%     1,631
#   #3  advocacy_old     11.81       7   63,985  88.4%   25.6%   10.8%     1,551
#   #8  upskilling        5.19       3   57,845  79.9%   36.1%   16.8%       549
#   #4  preparation       5.02       3   56,169  77.6%   41.4%   13.1%       540
#   #7  adaptation        3.10       1   49,414  68.2%   59.2%   10.2%       301  <-- thin
#   #5  transformation    2.66       1   45,795  63.2%   58.8%   11.5%       334  <-- thin
#   --  innovation        0.40       0   13,340  18.4%   58.7%   27.3%        92  <-- NOT SWEPT
#
# READ THE BOTTOM THREE AS CONTROLS, NOT RESULTS — and that judgement is about the
# SIGNAL, so it does not soften at K=3. adaptation and transformation have a median
# denominator of 1, so for over half their usable firm-years the "material share" is
# literally 1/1 or 0/1. A quantile sort on either is mostly cutting ties, and its High
# leg is a coin-flip subset of the tie block rather than a ranked portfolio. A spread
# that appears there and not in the dense designs is evidence of the tie-breaking.
#
# BEHAVIOURAL INNOVATION IS NOT SWEPT, on measured grounds. On the larger US panel at
# the DEFAULT cell (alpha=0.1, mcap=0.95) it is 765 firm-years and 34 assets a month
# post-trim — about 4 names per bucket at K=7, i.e. every K cell under the 25-name
# presentation gate — and the floor annihilates it: N=3 leaves 17 firm-years. The
# workbook row above says 13,340 usable, which is why it looks sweepable; the alpha-bound
# trim then removes almost all of them, because it trims on sum_activities and innovation
# IS the low-count tail. Europe is thinner again. Nothing to sweep, so it is out — which
# costs the exact Behavioural decomposition noted above, and is why that argument is now
# "three of the four" rather than a partition.
#
# The gate is PRESENTATION-ONLY (the exported parquets always hold every portfolio), so
# the sweep still reports an alpha for a thin leg. Read every alpha__ column next to its
# coverage_pct__ neighbour — that is the evidence for whether the leg is thick enough to
# believe. alpha_bound=0.05 trims LESS than 0.1 (halved per tail, 2.5% vs 5% each side),
# so the 0.05 cells run at least as large as the 0.1 ones, never smaller.
#
# NAMES: experiment_name() builds the run name from the cfg DIFF against build_cfg(), so
# two quirks are worth knowing before reading a page title:
#   * design #1 IS the baseline action_characterization, so its pages are titled by the
#     numeric axes alone with no design token — and its (alpha=0.1, mcap=0.95, K=7) cell
#     has an empty diff and lands as "base_parameters". Identify it by its signal names
#     (Material / Immaterial) or by its position: SORT_BY puts it first.
#   * the long characterizations plus three numeric axes run past the 150-char cap, so
#     many runs land as a 140-char prefix + `__h<blake2b>` suffix. Unique and
#     deterministic (so --resume works), but not readable — use the PDF page titles and
#     the CSV columns to identify a cell, not the directory name.
# --------------------------------------------------------------------------- #

# The eleven designs, in the order they were requested (which is also the PDF order —
# see VALUE_ORDER at the bottom). Each entry is a complete override dict for the DESIGN
# only; the numeric axes are crossed on below.
#
# Six of the eleven go through the single `Materiality_PP_Action_SDG` branch, which
# reads WHICH action from the separate `materiality_pp_action` cfg key
# (experiments.py:503). The other five ignore that key entirely and leave it None.
#
# NAMING TRAP, and it is a silent one: `advocacy_old_def` is the advocacy leg of the
# ORIGINAL "Matteo" 3-way split (advocacy_old_def / preparation / transformation), while
# `advocacy_new_def` is the one from the newer 4-way Behavioural split (adaptation /
# advocacy_new_def / innovation / upskilling). Both are real, different columns in the
# same workbook — picking the wrong one sorts on a different quantity with no error.
_DESIGNS: list[dict] = [
    # 1. All SDGs together (the base_materiality design): material__total /
    #    (material__total + immaterial__total), across all 17 SDGs.
    {"action_characterization": "Material_Immaterial_only"},

    # 2. All People & Prosperity: the same share restricted to SDGs 1-5, 8-11, 16, 17.
    #    This is the dense reference the seven action designs below decompose.
    {"action_characterization": "Materiality_People_Plus_Prosperity_SDG"},

    # # 3-5. Matteo (old 3-way) actions, within People & Prosperity.
    # {"action_characterization": "Materiality_PP_Action_SDG",
    #  "materiality_pp_action": "advocacy_old_def"},

    # {"action_characterization": "Materiality_PP_Action_SDG",
    #  "materiality_pp_action": "preparation"},

    # {"action_characterization": "Materiality_PP_Action_SDG",
    #  "materiality_pp_action": "transformation"},

    # 6-8. Behavioural (new 4-way) actions, within People & Prosperity, MINUS innovation
    #      (not sortable -- see the header). The full four sum to design #2 exactly; these
    #      three leave a small residual.
    {"action_characterization": "Materiality_PP_Action_SDG",
     "materiality_pp_action": "advocacy_new_def"},
    {"action_characterization": "Materiality_PP_Action_SDG",
     "materiality_pp_action": "adaptation"},
    {"action_characterization": "Materiality_PP_Action_SDG",
     "materiality_pp_action": "upskilling"},


    # 9-11. The three health cuts — ALL activities of those SDGs (the __total__ count
    #        family, not an action split). Nested: Narrow ⊂ Health+Work ⊂ One Health.
    #        SDG 6, 14 and 15 are Planet SDGs, so none of these sits inside design #2.
    {"action_characterization": "Materiality_One_Health_SDGS"},        # SDG 3,6,8,11,14,15
    {"action_characterization": "Materiality_Narrow_Health_SDGS"},     # SDG 3,6,11
    {"action_characterization": "Materiality_Health_and_Work_SDGS"},   # SDG 3,6,8,11
]

_ALPHA_BOUNDS: list[float] = [0.05, 0.1]
_MCAP: list[float] = [0.9, 0.95]
_QUANTILES: list[int] = [3, 5]

# The materiality-split floor: require at least N (material + immaterial) initiatives in
# the design's denominator before a firm-year may be split into a material share at all.
# 0 = off, so the N=0 arm of every pair is the unfloored baseline and each design's two
# rows are a clean before/after on the floor alone.
#
# 0/3 rather than the previous sweep's 0/3/5: N=3 is where the de-saturation earns its
# keep, and dropping N=5 keeps this at 396 runs instead of 594.
#
# WHY IT EXISTS: the signal is material / (material + immaterial), a ratio of small
# integer counts, so a firm-year with one initiative can only score 1/1 or 0/1. Those
# atoms pile up on the sort's cutpoints and the High leg becomes a coin-flip subset of a
# tie block. The floor drops the firm-years too sparse to carry a meaningful share.
#
# MEASURED COST on the US panel at the default cell (alpha=0.1, mcap=0.95) -- post-trim
# firm-years, and @1.0 = the share of them sitting at a material share of exactly 1.0:
#
#                       N=0                N=3
#   design         firm-yrs  @1.0     firm-yrs  @1.0
#   advocacy_new_def  7,296  25.4%       6,357  20.3%
#   advocacy_old_def  7,281  24.8%       6,336  19.7%
#   upskilling        6,701  38.8%       4,985  30.9%
#   preparation       6,474  45.0%       4,581  36.2%
#   adaptation        5,868  64.5%       3,332  54.9%
#   transformation    5,177  68.0%       2,579  57.4%
#
# THE TRADE IS NOT UNIFORMLY WORTH IT, and it is worst exactly where saturation is worst:
# adaptation and transformation give up 43% and 50% of their sample to move @1.0 by ~10
# points, landing at 55-57% saturated -- still worse than preparation is for free at N=0.
# Do not read a floored spread on those two as a de-saturation success without checking
# @1.0 actually moved. Europe is a smaller panel again, so expect the N=3 arm to bite
# harder here than these US numbers suggest, and read every alpha next to coverage_pct.
#
# LEGAL ON ALL ELEVEN DESIGNS: build_cfg raises on a non-zero floor only when the design
# has MORE THAN ONE material/immaterial group (experiments.py:604), because the frozen
# common-universe mask would silently turn a per-group floor into "drop unless EVERY
# group clears N". Every design in _DESIGNS is a one-group mirror pair, so all 22
# design x floor pairs build -- verified, not assumed.
_FLOORS: list[int] = [0, 3]

# --------------------------------------------------------------------------- #
# GRID: expanded to its full cartesian product. EMPTY this time — the design axis is
# RAGGED and a cross cannot express it.
#
# `materiality_pp_action` is meaningful for exactly six of the eleven designs. Putting
# both it and `action_characterization` in GRID would build 6 x 6 = 36 design cells, of
# which the 5 non-action characterizations x 6 actions = 30 are the SAME config carrying
# an unread key. They would not even be deduplicated: build_worklist fingerprints the
# override dict (sweep.py:124), and those 35 differ in `materiality_pp_action`, so each
# would run — and get its OWN name and PDF page, because the key reaches the cfg diff.
# That is 30 wasted runs per numeric cell. So the designs are enumerated above and the
# numeric cross is applied to each in EXPLICIT below.
# --------------------------------------------------------------------------- #
GRID: dict[str, list] = {}

# --------------------------------------------------------------------------- #
# EXPLICIT: hand-picked combinations, appended after the grid, used verbatim.
#
# The full cross: 11 designs x 2 floors x 2 alpha x 3 mcap x 3 K = 396 combinations.
# A comprehension rather than 396 literals — this file is data, but the data here is a
# product, and writing it out by hand is how a cell goes missing unnoticed.
# --------------------------------------------------------------------------- #
EXPLICIT: list[dict] = [
    {
        **design,
        "minimum_initatives_needed_to_split_by_materiality": floor,
        "alpha_bound": alpha,
        "mktcap_covered_if_filter_by_cum_market_cap": mcap,
        "no_simple_quantiles": k,
    }
    for design, floor, alpha, mcap, k in itertools.product(
        _DESIGNS, _FLOORS, _ALPHA_BOUNDS, _MCAP, _QUANTILES
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
# week" is not a record. If someone flips a baseline back, these keep the sweep intact —
# loudly, because the cell names would then change and --resume would re-run everything
# under new names rather than silently mixing two configurations in one ledger.
# --------------------------------------------------------------------------- #
FIXED: dict = {
    # THE REGION. This is the whole point of this sweep — it is the Europe re-run of the
    # US design work. Drives currency_filter (CHF/GBP/EUR/NOK/SEK/DKK), region_filter
    # (MacroRegion == "Europe" plus the 16 FF-Europe domiciles), convert_to_USD=True and
    # fama_factor_region="Europe" via the region block at experiments.py:315.
    "region_analysis": "Europe",
    # Every design here keys on the material__* / immaterial__* columns, per-SDG and
    # per-action, which only the v2 SASB workbook carries.
    "add_materiality": True,
    "materiality_version": 2,
    "min_portfolio_coverage": 0.8,
    # minimum_initatives_needed_to_split_by_materiality, alpha_bound, mktcap_covered and
    # no_simple_quantiles are NOT pinned here -- they are swept axes, and every EXPLICIT
    # cell sets all four, so a FIXED value would be overridden on all 396 combinations
    # and only mislead a reader of this file.
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
    # Outermost: the design. TWO keys are needed, not one — the seven action designs all
    # share action_characterization="Materiality_PP_Action_SDG" and are told apart only
    # by materiality_pp_action, which is None on the other five (it sorts last within its
    # characterization block, which is harmless: each block holds one or the other).
    "action_characterization",
    "materiality_pp_action",
    # Then the floor, so within one design its N=0 and N=3 blocks are contiguous: the
    # comparison the floor axis exists for is "same design, same alpha/mcap/K, does the
    # spread survive raising N", and that reads best with N as the outer sub-key.
    "minimum_initatives_needed_to_split_by_materiality",
    # Then alpha_bound / mcap / K, innermost-last, so within one design the pages read as
    # each (alpha, mcap) pair carrying its K=3/5/7 triple adjacent -- which is the
    # comparison you actually make (does the spread survive a finer sort, at fixed trim
    # and market-cap screen).
    "alpha_bound",
    "mktcap_covered_if_filter_by_cum_market_cap",
    "no_simple_quantiles",
]

VALUE_ORDER: dict[str, list] = {
    # The requested order, which is also broad-to-narrow: all 17 SDGs, then the
    # People+Prosperity total, then its six action decompositions, then the three
    # health cuts. Read top-down and the denominator thins as you go, which is the right
    # frame for judging whether a spread further down is signal or tie-breaking.
    "action_characterization": [
        "Material_Immaterial_only",                 # 1. all SDGs
        "Materiality_People_Plus_Prosperity_SDG",   # 2. all People & Prosperity
        "Materiality_PP_Action_SDG",                # 3-8. one action within P+P
        "Materiality_One_Health_SDGS",              # 9.  SDG 3,6,8,11,14,15
        "Materiality_Narrow_Health_SDGS",           # 10. SDG 3,6,11
        "Materiality_Health_and_Work_SDGS",         # 11. SDG 3,6,8,11
    ],
    # Within the action block: the Matteo three first, then the Behavioural three, as
    # requested. NOT density order (that would be advocacy_new, advocacy_old, upskilling,
    # preparation, adaptation, transformation, innovation) -- keeping the two schemes
    # contiguous matters more here, because comparing across schemes is the one
    # comparison the overlap note above says you must be careful with.
    "materiality_pp_action": [
        "advocacy_old_def",     # 3. Matteo Advocacy
        "preparation",          # 4. Matteo Preparation
        "transformation",       # 5. Matteo Transformation
        "advocacy_new_def",     # 6. Behavioural Advocacy
        "adaptation",           # 7. Behavioural Adaptation
        "upskilling",           # 8. Behavioural Upskilling
        # Listed but NOT in _DESIGNS -- kept so re-adding innovation needs no edit here.
        "innovation",
    ],
}
