"""A throwaway 5-cell PROBE for the node cache on the Developed region -- not a sweep
meant to answer a research question, and not a benchmark fixture to be captured and
compared later (see sweep_parameters_benchmark12.py for that). Delete this file once it
has served its purpose.

WHY THIS EXISTS. New_Pipeline/_node_cache.py was verified correct on the US benchmark
(sweep_parameters_benchmark12.py), but the Developed worklist (sweep_parameters_Developed.py)
exercises two things the US verify run never did:

  1. mktcap_covered_if_filter_by_cum_market_cap=0.99. Untested on this region even
     WITHOUT caching -- sweep_parameters_Developed.py's own "MEMORY" section says to run
     one 0.99 cell by hand before launching the full 128-cell file, because it is the
     heavier of the two values (keeps more listings, so bigger resident frames and
     bigger pickled bundles) and the region's pooled universe already crosses the
     structural 4 GiB-per-pickle-row limit at 0.95 (merge_esg_provider's bundle is
     4.27 GiB there per boundary.py's own measurement).

  2. Holding the 0.95 AND 0.99 variants of merge_esg_provider / mktcap_filter_audit's
     bundles in cache AT THE SAME TIME. Uncached, those two bundles are never resident
     together -- each cell's pipeline run discards its bundle once the next node
     consumes it. The whole point of _node_cache's 2-slot LRU is to keep BOTH alive for
     the sweep's duration, which is new exposure on top of the ~30 GB RSS
     sweep_parameters_Developed.py documents for a single uncached run.

This worklist is built to surface a cache bug if one exists, not to produce results
anyone should read: cells 1-3 share mktcap=0.95 but vary the SDG group, behaviour and
sector screen -- none of which DEPENDS_MERGE_ESG / DEPENDS_MKTCAP_AUDIT /
DEPENDS_LOAD_UNIVERSES list, so under SWEEP_CACHE_VERIFY=1 all three should hash-match
the one computed for cell 1. Cells 4-5 repeat that at mktcap=0.99 -- the untested value --
and, run after 1-3, are also the first real (non-simulated) test that the 2-slot cache
holds 0.95 and 0.99 together without evicting.

Run with:
    SWEEP_CACHE_VERIFY=1 .venv/bin/python -m New_Pipeline.sweep \\
        --params New_Pipeline.sweep_inputs.sweep_parameters_dev_cache_verify --new-run

JOBS=1 is not a style choice here -- see sweep_parameters_Developed.py's own "MEMORY"
section: the Developed universe keeps all three regional extracts resident
(~30 GB RSS uncached), so a second worker on this machine (64 GB) risks swapping even
before the cache adds anything.
"""

from __future__ import annotations

SWEEP_NAME: str = "dev_cache_verify_probe"

GRID: dict = {}

# (action_characterization, its action cfg key) -- same three of the four groups
# sweep_parameters_Developed.py defines, enough to vary the group without needing all four.
_PLANET = ("Materiality_Planet_Action_SDG", "materiality_planet_action")
_PP = ("Materiality_PP_Action_SDG", "materiality_pp_action")
_ALL = ("Materiality_All_Action_SDG", "materiality_all_action")

EXPLICIT: list[dict] = [
    # ---- three cells at mktcap=0.95, each varying group/behaviour/sector -------- #
    # Expect: load_universes, merge_esg_provider, mktcap_filter_audit all HIT after
    # cell 1 computes them, despite every other knob differing.
    {
        "action_characterization": _PLANET[0], _PLANET[1]: "advocacy_old_def",
        "portfolio_weighting": "mktcap",
        "mktcap_covered_if_filter_by_cum_market_cap": 0.95,
        "drop_real_estate": False, "drop_utilities": False,
    },
    {
        "action_characterization": _PP[0], _PP[1]: "preparation",
        "portfolio_weighting": "equal",
        "mktcap_covered_if_filter_by_cum_market_cap": 0.95,
        "drop_real_estate": True, "drop_utilities": True,
    },
    {
        "action_characterization": _ALL[0], _ALL[1]: "transformation",
        "portfolio_weighting": "mktcap",
        "mktcap_covered_if_filter_by_cum_market_cap": 0.95,
        "drop_real_estate": False, "drop_utilities": False,
    },
    # ---- two cells at mktcap=0.99: the untested value, and a cache-hit check on it -- #
    {
        "action_characterization": _PLANET[0], _PLANET[1]: "advocacy_old_def",
        "portfolio_weighting": "mktcap",
        "mktcap_covered_if_filter_by_cum_market_cap": 0.99,
        "drop_real_estate": False, "drop_utilities": False,
    },
    {
        "action_characterization": _PP[0], _PP[1]: "preparation",
        "portfolio_weighting": "equal",
        "mktcap_covered_if_filter_by_cum_market_cap": 0.99,
        "drop_real_estate": True, "drop_utilities": True,
    },
]

# FIXED, copied from sweep_parameters_Developed.py so this probe runs the same universe
# that file does.
FIXED: dict = {
    "region_analysis": "Developed",
    "no_simple_quantiles": 5,
    "alpha_bound": 0.05,
    "add_materiality": True,
    "materiality_version": 2,
    "minimum_initatives_needed_to_split_by_materiality": 0,
    "execute_3_filters": "suspicious_only",
    "min_stocks_per_portfolio": 25,
    "min_portfolio_coverage": 0.8,
}

PDF_EVERY: int = 5    # one rebuild, at the end -- this is a probe, not a report
OUTPUT_DIR: str = "sweep_output"
JOBS: int = 1          # mandatory on this machine -- see the module docstring
