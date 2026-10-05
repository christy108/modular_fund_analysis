"""The 12-cell BENCHMARK worklist — a fixed, repeatable sweep used to measure the
pipeline, not to answer a research question.

Run it, freeze the result with ``python -m New_Pipeline.benchmark capture``, change the
pipeline, run it again, and ``benchmark compare`` tells you whether every number is
bit-identical and whether the sweep got faster. That is its only job, so unlike the
other sweep_parameters_* files THIS ONE MUST NOT BE EDITED between a baseline and the
candidate it is compared against — the two sweeps have to be the same 12 runs or the
comparison means nothing. Changing it invalidates
``New_Pipeline/sweep_fixture_12_benchmark/`` and the baseline has to be re-captured.

The worklist is a faithful SLICE of the real US sweep (sweep_parameters_US.py): same
keys, same values, three of its five axes kept and two pinned. A benchmark on knobs
nobody sweeps would measure the wrong thing.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# SWEEP_NAME: names this sweep's output folder, `sweep_output/<UTC stamp>_<name>/`.
# Re-running RESUMES that folder; `--new-run` forces a fresh one, which is what you
# want when timing a candidate against the baseline (a resumed sweep runs nothing and
# times nothing).
# --------------------------------------------------------------------------- #
SWEEP_NAME: str = "sweep_fixture_12_benchmark"


# --------------------------------------------------------------------------- #
# WHAT THIS SWEEP IS
#
# The WIDE Planet materiality design at three behavioural cuts, crossed with the
# weighting scheme and the sort granularity, on the full 2016-2024 US sample.
#
#   3 behaviours x 2 weighting schemes x 2 quantile counts = 12 runs
#
# WHY THESE AXES. None of the three is read by nodes 01 (process_lc), 03
# (load_universes) or 05 (load_fama_french) -- those read only golden_data, the region
# block, start/end year, the sample filters and the factor region, all of which are
# pinned in FIXED below. So all 12 cells feed those three nodes identical inputs and
# every one of the 12 recomputes them from scratch. That redundancy is exactly what the
# caching work removes, and this sweep is the instrument that measures it.
#
# WHY WIDE PLANET ONLY. sweep_parameters_US.py:100-107 records that the NARROW Planet
# behavioural cells are thin everywhere (12.6-36.8% usable) and that a sibling config
# emptied the panel and died in node 02 with "cannot convert float NaN to integer". A
# cell that fails still burns minutes and still writes a ledger record, but its payloads
# are empty -- worthless as an output fixture, and it would make the timing comparison
# depend on which cells happened to survive.
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# GRID: expanded to its full cartesian product. All three axes are independent and
# every combination is valid, so they cross cleanly. No EXPLICIT block: the whole-group
# signals that one carries in sweep_parameters_US.py are a different
# action_characterization, and this benchmark holds that pinned.
# --------------------------------------------------------------------------- #
GRID: dict[str, list] = {
    # The Matteo 3-way behavioural split of the Planet SDGs (6, 7, 12, 13, 14, 15).
    # TRAP: advocacy_old_def is the Matteo advocacy leg; advocacy_new_def belongs to the
    # newer 4-way split and is deliberately NOT here -- same choice as the US sweep.
    "materiality_planet_action": ["advocacy_old_def", "preparation", "transformation"],
    # Cap-weighted first (also the build_cfg baseline), then equal-weighted.
    "portfolio_weighting": ["mktcap", "equal"],
    # Sort granularity: coarse 3-way and finer 5-way.
    "no_simple_quantiles": [3, 5],
}

EXPLICIT: list[dict] = []


# --------------------------------------------------------------------------- #
# FIXED: merged into EVERY combination. Copied from sweep_parameters_US.py's FIXED so
# the benchmark sits on the same universe as the sweep it is modelled on, plus the two
# axes that are GRID axes there and pinned here.
# --------------------------------------------------------------------------- #
FIXED: dict = {
    # ---- the two axes this benchmark pins that the US sweep varies -------- #
    # The WIDE Planet width, one behaviour at a time (the behaviour is the GRID axis).
    "action_characterization": "Materiality_Planet_Action_SDG",
    # The baseline market-cap screen. Pinned rather than swept because it is read by
    # node 04 (merge_esg_provider) via _common.mktcap_filter_kwargs -- varying it would
    # make node 04's inputs differ per cell and muddy what the benchmark is measuring.
    "mktcap_covered_if_filter_by_cum_market_cap": 0.95,

    # ---- everything below EQUALS sweep_parameters_US.py's FIXED ----------- #
    # THE REGION. Drives currency_filter=["USD"], region_filter=["United States and
    # Canada"], convert_to_USD=False and fama_factor_region="United_States" via the
    # region block at experiments.py:357. Every one of those is read by nodes 01/03/05,
    # which is precisely why it is pinned: a region axis would make those three nodes
    # genuinely differ per cell.
    "region_analysis": "United_States",

    # ADD BACK Real Estate and Utilities, which the build_cfg baseline drops. Both are
    # Planet-relevant by construction (utilities are the energy SDG 7, real estate the
    # built-environment side of SDGs 11/12), so a Planet sort that excludes them removes
    # much of the exposure it exists to measure.
    "drop_real_estate": False,
    "drop_utilities": False,

    # Percentile trim on sum_activities (the firm-year's total initiative count), per
    # tail. Equals the current baseline, so it reaches no run name.
    "alpha_bound": 0.05,

    # The materiality inner join is what makes a materiality design possible at all --
    # signal_0 is a MATERIAL share, read off the SASB workbook. Not optional here.
    "add_materiality": True,
    "materiality_version": 2,

    # NO materiality-split floor: a firm-year is split into material/immaterial however
    # few initiatives it has. Also baseline.
    "minimum_initatives_needed_to_split_by_materiality": 0,

    # Filter 2 ONLY (drop suspicious gvkeys), chosen over "all", which would additionally
    # switch on the ">= 3 fiscal years" survivorship screen. CONSEQUENCE: filter 3 is
    # SKIPPED under this mode (01_process_lc.py:398 gates it on `_all3`), so
    # min_initatives_annual_reports_if_execute_3_filters_true has NO EFFECT here.
    "execute_3_filters": "suspicious_only",

    # The thin-portfolio gate, at baseline. A High/Low leg is HIDDEN unless it holds at
    # least min_stocks_per_portfolio names in at least min_portfolio_coverage of
    # formation months.
    "min_stocks_per_portfolio": 25,
    "min_portfolio_coverage": 0.8,

    # portfolio_weighting and no_simple_quantiles are NOT pinned here -- they are GRID
    # axes, so a FIXED value would be overridden on all 12 cells and would only mislead
    # a reader of this file. start_year / end_year are absent: this is the FULL baseline
    # 2016-2024 sample.
}


# --------------------------------------------------------------------------- #
# Output settings
# --------------------------------------------------------------------------- #

# ONE rebuild, at the end. Every other sweep_parameters_* file uses 4, but _rebuild
# re-renders EVERY page of results.pdf from scratch each time it fires (sweep.py:270 ->
# sweep_report.build_pdf), so intermediate rebuilds add non-pipeline seconds to the
# sweep's wall clock. With 12 cells, PDF_EVERY=12 means that cost is paid once and lands
# outside the window the per-cell timings measure.
PDF_EVERY: int = 12

# Everything the sweep writes lives under here, relative to the repo root.
OUTPUT_DIR: str = "sweep_output"


# --------------------------------------------------------------------------- #
# How many experiments run at once (`--jobs N` overrides).
#
# 2, matching every other sweep_parameters_* file on this machine (10 cores / 64 GB),
# so the benchmark measures the configuration the sweeps actually run in.
#
# KEEP THIS THE SAME ACROSS A BASELINE AND ITS CANDIDATE. Each worker is a separate
# process holding its own copy of the Golden panel and the Compustat universe, so the
# job count changes both the memory pressure and -- once node outputs are cached
# in-process -- how many times each cached stage has to be computed. A baseline at
# JOBS=2 and a candidate at JOBS=4 is not a measurement.
# --------------------------------------------------------------------------- #
JOBS: int = 2


# --------------------------------------------------------------------------- #
# Presentation order for results.pdf / results.csv. Same keys as the US sweep, minus
# the two axes pinned above.
# --------------------------------------------------------------------------- #
SORT_BY: list[str] = [
    "materiality_planet_action",
    "portfolio_weighting",
    "no_simple_quantiles",
]

VALUE_ORDER: dict[str, list] = {
    # The Matteo 3-way split in the taxonomy's own order, not a density order.
    "materiality_planet_action": ["advocacy_old_def", "preparation", "transformation"],
    # Cap-weighted first.
    "portfolio_weighting": ["mktcap", "equal"],
}
