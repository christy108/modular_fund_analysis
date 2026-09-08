"""Sweep C -- EUROPE sample, MARKET-CAP WEIGHTED portfolios.

Fed to the sweep runner with:

    python -m New_Pipeline.sweep --params New_Pipeline.sweep_params_c

Same shape as ``New_Pipeline/sweep_parameters.py`` (which stays the default); this file
exists so B and C can be queued back to back unattended without editing that one between
runs. This is the EUROPE twin of ``sweep_params_b`` (US) and differs from it in exactly
two things: ``region_analysis`` and the two market-cap screen levels (0.85 / 0.95 here,
0.95 / 0.99 there). Everything else -- the six designs, the alpha and quantile axes, the
weighting, the presentation order -- is identical, deliberately, so the two sweeps'
PDFs are read side by side page for page.

The two market-cap levels are NOT comparable across the sweeps: 0.95 in Europe keeps a
different slice of a different universe than 0.95 in the US. Only the OVERLAP level, 0.95,
appears in both, and it is the only cross-region comparison in the pair that holds the
screen fixed.

# --------------------------------------------------------------------------------- #
# THE POINT OF THIS SWEEP
# --------------------------------------------------------------------------------- #
Every result in this project so far is EQUAL weighted: each holding gets 1/n, so a $200m
firm carries the same money as a $2tn one and the legs are driven by the small end of the
surviving universe. This sweep re-runs the design space with

    portfolio_weighting = "mktcap"
    max_portfolio_weight_if_portfolio_weighting_equal = 0.10

i.e. weight by `last_mktcap` at the FORMATION month, with a 10% single-name ceiling
enforced by the MSCI/S&P iterative rule (pin at the cap, redistribute the remainder
pro-rata by market cap among the still-free names, repeat). It is pinned in FIXED, so it
reaches the cfg diff and `portfolio_weighting-mktcap` appears in EVERY run name and page
title -- which is what makes these pages unmistakable against the equal-weighted ones.

THE ONE THING TO WATCH. Under cap weighting a bucket-month where `n * cap <= 1` -- 10
names or fewer at a 10% cap -- admits no weight vector at all, and is DISCARDED: no
return, hence no alpha and no contribution to cumulative performance. Because a NaN return
is booked by `(1+r).cumprod()` as a fabricated 0% month rather than skipped, the
thin-portfolio gate then hides that leg ENTIRELY. So a missing leg on a K=5 page is the
first thing to check in `portfolio_coverage` / `portfolio_gate_summary`, not a result.
Equal weighting has no ceiling to violate and is never gated this way, so an absence here
that is present in the equal-weighted sweep is a concentration artefact, not a signal.

Two knobs make that more likely at the same time, and both are swept below: K=5 cuts the
universe into narrower buckets than K=3, and a TIGHTER market-cap screen
(mktcap_covered=0.85 keeps far fewer, larger listings than 0.95) leaves fewer names to
fill them. The K=5 / mcap 0.85 cells are where discards are most likely, and the pp_action
designs are the thinnest denominators in the set. EXPECT THIS TO BITE HARDER THAN IN THE
US SWEEP: the European universe is smaller to begin with, and 0.85 is a tighter screen
than either US level.

# --------------------------------------------------------------------------------- #
# THE GRID:  (6 designs x 2 alpha x 2 mktcap x 2 K) + a floor axis on 4 of them
#            = 2*8 + 4*16 = 80 runs
# --------------------------------------------------------------------------------- #
alpha_bound          0.1, 0.05    percentile trim per tail on sum_activities; 0.1 is the
                                  baseline, 0.05 halves the trim so LESS is dropped
mktcap_covered       0.85, 0.95   share of aggregate market-cap VALUE the screen keeps.
                                  NOT a count: 0.95 discards ~65% of LISTINGS. 0.85 is
                                  tighter still -- a much smaller, larger-cap universe.
                                  0.95 is the baseline; 0.85 is not
no_simple_quantiles  3, 5         buckets per sort. No K=7 cell, as requested

Six signals, all of the form material / (material + immaterial) -- one-group MIRROR pairs,
so signal_1 = 1 - signal_0 and High on one leg is Low on the other (mirror_pair_summary
reports it). Read a pair as one test, not two.

  1. All SDGs together       Material_Immaterial_only          all 17 SDGs, all actions
  2. All People & Prosperity Materiality_People_Plus_Prosperity everything but the Planet
                                                               SDGs (6,7,12,13,14,15)
  3-5. Matteo's three actions on that same People+Prosperity cut, one run each. These read
     `material__<action>__SDG_n` columns instead of `material__total__SDG_n`, so the
     denominator is strictly thinner than design 2 -- check each run's signal_sparsity
     audit before trusting its sort. The action names are the workbook's, and
     `advocacy_old_def` is Matteo's original advocacy (NOT `advocacy_new_def`, which is the
     behavioural-4 one).
  6. "Narrow Health"         Materiality_Narrow_Health_SDGS    SDGs 3, 6, 11, all actions

Designs 3-5 are a partition-ish cut of design 2's numerator and 6 overlaps 1 and 2, so
these six are NOT six independent tests.

--------------------------------------------------------------------------------- 
THE SPLIT FLOOR -- a PER-DESIGN axis, not a global one
--------------------------------------------------------------------------------- 
`minimum_initatives_needed_to_split_by_materiality` is the minimum number of initiatives
a firm-year needs inside the group before it is allowed to be split into material and
immaterial at all. At 0 (the baseline) a firm with a single initiative gets a ratio of
exactly 1.0 or 0.0, and those degenerate firm-years pile up in the extreme buckets --
which is precisely what the sort is reading.

It is swept at {0, 3} on designs 3-6 ONLY. That is measured, not assumed: paired
comparisons on the two earlier sweeps that varied this knob (europe_materiality_12_designs,
64 pairs; sdg_min_initiatives_x_quantiles, 28 pairs), everything else held fixed, gave a
median |alpha| move of

    Material_Immaterial_only (design 1)        0.000   <- exactly zero, 8 pairs
    People + Prosperity      (design 2)        0.015
    one action within P+P    (designs 3-5)     0.045 - 0.090
    Narrow / One Health      (design 6)        0.070 - 0.100

i.e. the floor bites exactly where the DENOMINATOR IS THIN and does nothing where it is
wide -- with all 17 SDGs in play essentially every firm-year already clears 3 initiatives.
Sweeping it on designs 1-2 would spend a third of the queue re-deriving that.

Floor 5 was NOT included: the only evidence for it is 4 pairs on a single SDG, and every
step up costs sample on the designs that are already the thinnest here.

WHAT THE EARLIER SWEEPS CANNOT TELL US, and do not: whether the floor changes a
CONCLUSION. It never flipped significance across 360 pairs -- but not one spread in either
sweep was significant at 5% (min p = 0.070 Europe, 0.110 US), so there was nothing to flip.
Treat "the floor moves alpha a lot" as established and "it does/does not matter" as open.

TWO INTERACTIONS WITH CAP WEIGHTING, pulling opposite ways, which is the reason this axis
is worth its cells now and was not before:
  * the floor and value weighting do OVERLAPPING work. The floor exists to stop degenerate
    1/1 firm-years dominating the top bucket, and those are typically small firms that cap
    weighting already pushes towards zero weight. The floor may therefore matter LESS here
    than it did equal-weighted.
  * but the floor DROPS firm-years, so buckets get thinner, so the `n * cap <= 1` discard
    fires more often. Read the floor-3 narrow cells' portfolio_coverage before comparing
    them to their floor-0 twins -- a leg that vanished did not "get worse", it went away.
"""

from __future__ import annotations

import itertools

# --------------------------------------------------------------------------- #
# Names `sweep_output/<UTC stamp>_<name>/`. Re-running with the same name RESUMES that
# folder, which is what makes an interrupted overnight queue restartable.
# --------------------------------------------------------------------------- #
SWEEP_NAME: str = "europe_mktcap_weighted_6designs"


# The six signal designs. `materiality_pp_action` is only meaningful for
# Materiality_PP_Action_SDG and is left unset elsewhere, so it falls back to the baseline
# None -- which is also why this is an EXPLICIT product rather than a GRID: a GRID over
# action_characterization x materiality_pp_action would generate nonsense combinations
# (a pp_action on Material_Immaterial_only) and a None action on the design that requires
# one, which build_cfg rejects.
# Each entry is (design keys, floors to sweep for THAT design) -- see the "THE SPLIT
# FLOOR" block in the docstring for why the floor is per-design rather than a global axis.
_DESIGNS: list[tuple[dict, list[int]]] = [
    # 1. All 17 SDGs, every action. The widest denominator in the set -- and the one the
    #    floor provably does nothing to (0.000 median alpha move over 8 matched pairs).
    ({"action_characterization": "Material_Immaterial_only"}, [0]),
    # 2. People + Prosperity pooled (all SDGs except 6, 7, 12, 13, 14, 15). Still wide;
    #    median move 0.015, and its own alpha is about that size. Not worth doubling.
    ({"action_characterization": "Materiality_People_Plus_Prosperity_SDG"}, [0]),
    # 3-5. The same People+Prosperity cut restricted to ONE of Matteo's three actions.
    #    Thin single-action denominators: the floor moved these by 0.045-0.090, against
    #    alphas of 0.025-0.065. Swept.
    ({"action_characterization": "Materiality_PP_Action_SDG",
      "materiality_pp_action": "advocacy_old_def"}, [0, 3]),
    ({"action_characterization": "Materiality_PP_Action_SDG",
      "materiality_pp_action": "preparation"}, [0, 3]),
    ({"action_characterization": "Materiality_PP_Action_SDG",
      "materiality_pp_action": "transformation"}, [0, 3]),
    # 6. Narrow Health: SDGs 3, 6, 11, every action. The largest observed floor effect in
    #    the set (0.100 median). Swept.
    ({"action_characterization": "Materiality_Narrow_Health_SDGS"}, [0, 3]),
]

_ALPHAS: list[float] = [0.1, 0.05]
_MKTCAPS: list[float] = [0.85, 0.95]      # Europe levels; sweep B uses 0.95 / 0.99
_QUANTILES: list[int] = [3, 5]


# --------------------------------------------------------------------------- #
# GRID is empty and the whole cross is built in EXPLICIT, because a design is a PAIR of
# keys (action_characterization, materiality_pp_action) that must move together.
# --------------------------------------------------------------------------- #
GRID: dict[str, list] = {}

EXPLICIT: list[dict] = [
    {
        **design,
        "minimum_initatives_needed_to_split_by_materiality": floor,
        "alpha_bound": alpha,
        "mktcap_covered_if_filter_by_cum_market_cap": mcap,
        "no_simple_quantiles": k,
    }
    # The floor is nested INSIDE the design rather than crossed with it: designs 1-2 sweep
    # [0] and designs 3-6 sweep [0, 3], so this is 2*8 + 4*16 = 80 cells, not the 96 a
    # uniform two-value axis would give.
    for design, floors in _DESIGNS
    for floor, alpha, mcap, k in itertools.product(
        floors, _ALPHAS, _MKTCAPS, _QUANTILES
    )
]

# --------------------------------------------------------------------------- #
# FIXED: merged into every combination. An EXPLICIT entry wins for the same key.
# --------------------------------------------------------------------------- #
FIXED: dict = {
    # ---- THE POINT OF THE SWEEP ------------------------------------------- #
    # Not at baseline, so both reach the cfg diff and appear in every run name.
    "portfolio_weighting": "mktcap",
    "max_portfolio_weight_if_portfolio_weighting_equal": 0.10,

    # ---- the region ------------------------------------------------------- #
    # Drives currency_filter=['CHF','GBP','EUR','NOK','SEK','DKK'], region_filter=
    # ["Europe"], convert_to_USD=True and fama_factor_region="Europe" (experiments.py,
    # region if/elif).
    #
    # CONVERSION IS LOAD-BEARING HERE, not incidental. Cap weighting SUMS market caps across
    # a portfolio's holdings, and `mktcap` is in the LISTING currency unless the universe was
    # converted upstream -- so pooling a GBP cap with a DKK one would be wrong by roughly the
    # FX rate, and unlike a currency-neutral equal weighting that error lands directly in the
    # weights. build_cfg raises on exactly this combination (portfolio_weighting="mktcap" +
    # convert_to_USD=False + a multi-currency filter), which is why "Europe" is safe and a
    # hand-rolled multi-currency region with conversion off would not be. The baseline is
    # United_States, so this DOES reach the cfg diff and appears in every run name.
    "region_analysis": "Europe",

    # ---- everything below already EQUALS the build_cfg baseline ------------ #
    # None of it pollutes a run name. Pinned anyway: this file is the record of what the
    # sweep was, not "whatever experiments.py said that week".
    "add_materiality": True,
    "materiality_version": 2,

    # Filter 2 only (drop suspicious gvkeys), NOT "all", which would add a >= 3-fiscal-year
    # survivorship screen. CONSEQUENCE: filter 3's
    # min_initatives_annual_reports_if_execute_3_filters_true floor is SKIPPED under this
    # mode, so that knob has no effect anywhere in this sweep.
    "execute_3_filters": "suspicious_only",

    # The screen this sweep varies; the mode is fixed, only its level is swept.
    "market_cap_filter": "percent_total_mcap",

    # The thin-portfolio gate, at baseline. Calibrated at 25 names FOR EQUAL WEIGHTING --
    # under cap weighting the number that matters is the EFFECTIVE N (1/sum w^2), which the
    # run's portfolio_weight_summary reports and which is materially lower than the nominal
    # count. Read that table before concluding a leg was thick enough.
    "min_stocks_per_portfolio": 25,
    "min_portfolio_coverage": 0.8,

    # Full sample. This sweep varies weighting and the design space, not the window.
    "start_year": 2016,
    "end_year": 2024,

    # alpha_bound, mktcap_covered_..., no_simple_quantiles, action_characterization,
    # materiality_pp_action and minimum_initatives_needed_to_split_by_materiality are NOT
    # pinned here -- every EXPLICIT cell sets them, so a FIXED value would be overridden
    # on all 80 and would only mislead a reader of this file.
}


# --------------------------------------------------------------------------- #
# Output settings
# --------------------------------------------------------------------------- #
# Rebuild results.pdf/.csv/.xlsx every N completed runs. The ledger is appended after
# EVERY run regardless, and all three are rebuilt once more when the sweep ends or is
# interrupted -- so this only trades freshness against a few seconds each time. 80 cells,
# so every 4 gives 20 checkpoints.
PDF_EVERY: int = 4

OUTPUT_DIR: str = "sweep_output"

# Separate processes, each loading its own copy of the Golden panel and the Compustat
# universe -- bounded by RAM as much as by cores. 2 is demonstrated on this machine
# (10 cores / 64 GB). Requires write_debug_csv=False (the default): those dumps go to
# fixed paths under ./data/debug/ and parallel workers would clobber each other.
JOBS: int = 2


# --------------------------------------------------------------------------- #
# Presentation order for results.pdf / results.csv. The ledger stays in completion order
# (non-deterministic under JOBS > 1); the PDF and CSV are sorted by these keys, by the same
# function, so "CSV row N describes PDF page N" holds.
# --------------------------------------------------------------------------- #
SORT_BY: list[str] = [
    # Outermost: the design, so the six blocks read in the order they were requested.
    "action_characterization",
    "materiality_pp_action",
    # Then the sort granularity, then the two screen knobs -- innermost is alpha, so each
    # design/K/mcap cell shows its 0.1 and 0.05 pages side by side.
    "no_simple_quantiles",
    "mktcap_covered_if_filter_by_cum_market_cap",
    "alpha_bound",
    # Innermost, so a design's floor-0 and floor-3 pages are ADJACENT: the whole point of
    # the axis is reading one against the other, and on designs 1-2 there is only one page
    # to read, so nothing is left dangling.
    "minimum_initatives_needed_to_split_by_materiality",
]

VALUE_ORDER: dict[str, list] = {
    # Widest denominator first, narrowing down: all SDGs -> People+Prosperity -> one action
    # within it -> the Narrow Health subset last.
    "action_characterization": [
        "Material_Immaterial_only",                 # all 17 SDGs
        "Materiality_People_Plus_Prosperity_SDG",   # all but the Planet SDGs
        "Materiality_PP_Action_SDG",                # ditto, one action
        "Materiality_Narrow_Health_SDGS",           # SDGs 3, 6, 11
    ],
    # Matteo's own order, not alphabetical.
    "materiality_pp_action": ["advocacy_old_def", "preparation", "transformation"],
}
