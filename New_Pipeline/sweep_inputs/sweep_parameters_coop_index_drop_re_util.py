"""Sweep definition — pure data, no logic. Run with:

    python -m New_Pipeline.sweep --params New_Pipeline.sweep_inputs.sweep_parameters_coop_index_drop_re_util

ONE question: does excluding Real Estate and Utilities from the LC sample move the
prop_cooperation High-Low alpha, and does it move it far enough to reach significance?

It is a PAIRED test. Every cell below exists twice -- once at the build_cfg baseline
(drop_real_estate=False, drop_utilities=False, which is what every coop_index cell run so
far carried) and once with both flags True -- and nothing else differs. Both arms are
re-run here rather than pairing the drop arm against
`sweep_output/20261006T114114Z_coop_index_developed_K5_K10_startyears/`, so the comparison
cannot be contaminated by anything that moved in experiments.py between the two dates.
The baseline arm doubles as a reproduction check on that earlier sweep.
"""

from __future__ import annotations

SWEEP_NAME: str = "coop_index_drop_re_util"


# --------------------------------------------------------------------------- #
# WHICH CELLS, AND WHY THESE EIGHT
#
# Not the full 108-cell grid of sweep_parameters_coop_index.py -- at the 70-290 s/cell
# measured there, mirroring all of it would be ~7 hours for both arms. These are the only
# cells where the drop could plausibly change a conclusion, read off that sweep's
# results.csv:
#
#   2016 / K=5 / mktcap   the largest POSITIVE High-Low alphas in the whole file
#                         (+0.170 to +0.205 pp/month, p 0.186-0.235) -- the closest thing
#                         to a result the signal has.
#   2012 / K=10 / equal   the smallest p-value in the whole file (-0.223, p=0.083), and
#                         negative, so it is the cell where a sign-flip would matter.
#
# crossed with both alpha_bound values and the two market-cap screens that completed
# cleanly on every cell. mktcap_covered=1.0 is deliberately absent: six of its twelve 2012
# cells came back with a null High-Low in the earlier sweep (coverage_pct 93-94%, under
# the min_portfolio_coverage=0.8 gate... in fact over it -- the nulls are the thin-leg
# gate firing on the K=5 2012 cells), so it contributes no paired comparison there and
# only costs the slowest runtime in the file.
#
#   2 (design) x 2 alpha_bound x 2 mcap x 2 drop-arms = 16 cells
# --------------------------------------------------------------------------- #
GRID: dict[str, list] = {}


_DESIGNS = [
    # The best positive alpha in the completed sweep.
    {"start_year": 2016, "no_simple_quantiles": 5, "portfolio_weighting": "mktcap"},
    # The smallest p-value in the completed sweep.
    {"start_year": 2012, "no_simple_quantiles": 10, "portfolio_weighting": "equal"},
]

# BOTH arms, spelled out. drop_real_estate and drop_utilities always move together: the
# question asked was about the pair, and splitting them would double the worklist to answer
# a question nobody asked.
#
# NOTE the two flags cut at DIFFERENT points in 01_process_lc and on different columns.
# drop_real_estate tests GICS_level_1 != "Real Estate" (line 532) BEFORE the industry map;
# drop_utilities tests Industry != "Utilities" (line 549) AFTER it. At the baseline
# industry_level=0, map_sectors sends Real Estate -> "Financial" and passes Utilities
# through unchanged, so both cuts land where the names say -- but only because
# drop_real_estate runs first. Do not reorder them.
_ARMS = [
    {"drop_real_estate": False, "drop_utilities": False},   # build_cfg baseline
    {"drop_real_estate": True, "drop_utilities": True},
]

EXPLICIT: list[dict] = [
    {**design, **arm, "alpha_bound": ab,
     "mktcap_covered_if_filter_by_cum_market_cap": mcap}
    for design in _DESIGNS
    for ab in (0.05, 0.10)
    for mcap in (0.99, 0.999)
    for arm in _ARMS
]


# --------------------------------------------------------------------------- #
# FIXED: copied verbatim from sweep_parameters_coop_index.py's FIXED block, minus the
# keys that are EXPLICIT axes here. Every justification for these values lives in that
# file; this one only repeats the values so the two sweeps are comparable cell for cell.
# --------------------------------------------------------------------------- #
FIXED: dict = {
    "region_analysis": "Developed",

    # prop_cooperation ships only in the HQ extract, and build_cfg raises on any other
    # vintage for this action_characterization. That vintage has no SASB matching file,
    # hence add_materiality=False.
    "golden_data": "HQ_LC_dataseet_v_1_1O1",
    "action_characterization": "prop_cooperation",
    "signal_type": "counts",
    "signal_denominator": "Sum_All_Initiatives",
    "add_materiality": False,

    "market_cap_filter": "percent_total_mcap",
    "end_year": 2024,
    "execute_3_filters": "suspicious_only",
    "min_stocks_per_portfolio": 25,
    "min_portfolio_coverage": 0.8,
}


# --------------------------------------------------------------------------- #
# Output settings
# --------------------------------------------------------------------------- #
PDF_EVERY: int = 4
OUTPUT_DIR: str = "sweep_output"

# TWO. Both market-cap screens here completed on all 48 of their cells in the earlier
# coop_index sweep, so the memory profile is measured rather than guessed -- unlike the
# mktcap_covered=1.0 cells that file warns about, which this one does not run.
JOBS: int = 2


# --------------------------------------------------------------------------- #
# Presentation order: put the two arms of a pair on ADJACENT pages, which is the whole
# point of the sweep. Everything that defines a pair sorts first; the drop flag sorts last.
# --------------------------------------------------------------------------- #
SORT_BY: list[str] = [
    "start_year",
    "no_simple_quantiles",
    "portfolio_weighting",
    "alpha_bound",
    "mktcap_covered_if_filter_by_cum_market_cap",
    "drop_real_estate",
]

VALUE_ORDER: dict[str, list] = {
    "portfolio_weighting": ["mktcap", "equal"],
    "mktcap_covered_if_filter_by_cum_market_cap": [0.99, 0.999],
    # Baseline page first, then the page that drops the two sectors.
    "drop_real_estate": [False, True],
}
