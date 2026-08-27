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
# GRID: expanded to its full cartesian product.
#   {"a": [1, 2], "b": ["x", "y"]}  ->  4 experiments (a=1,b=x), (a=1,b=y), ...
# Set to {} to disable and use EXPLICIT only.
# --------------------------------------------------------------------------- #
GRID: dict[str, list] = {
    # "no_simple_quantiles": [5,7],
    # "alpha_bound": [0.1],
}



# { "action_characterization": ["Material_Immaterial_only", 
#                                  "Materiality_3_groups_people_planet_prosperity_SDG", "Materiality_5_groups_SDG_brackets",
#                                   "Materiality_Climate_Natural_Capital_vs_All_SDGS",
#                                  "Combined_Material_Immaterial_3_Matteo_Signals",
#                                  "Combined_Material_Immaterial_4_Behavioural_Signals"],

#     "no_simple_quantiles": [3, 5, 7],
#      "alpha_bound": [0, 0.05, 0.1],
#    

#     "mktcap_covered_if_filter_by_cum_market_cap": [0.95, 0.99, 0.999, 1.0],
   
# }

# --------------------------------------------------------------------------- #
# EXPLICIT: hand-picked combinations, appended after the grid, used verbatim.
# For knobs that must move together (add_materiality + a materiality-only
# action_characterization, say) a grid cannot express the constraint — put them here.
# --------------------------------------------------------------------------- #
EXPLICIT: list[dict] = [
    {"add_materiality": True, "action_characterization": "Materiality_Climate_Natural_Capital_vs_All_SDGS"},
]


# --------------------------------------------------------------------------- #
# FIXED: merged into EVERY combination, grid and explicit alike. Use for knobs you want
# held constant across the whole sweep without repeating them in each entry.
# An entry in GRID/EXPLICIT wins over FIXED for the same key.
# --------------------------------------------------------------------------- #
FIXED: dict = {"add_materiality": True}


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
JOBS: int = 3


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
    "action_characterization",
    "no_simple_quantiles",
    "alpha_bound",
]

VALUE_ORDER: dict[str, list] = {
    # Pages group by signal design, in this order; within each group they run through
    # every no_simple_quantiles x alpha_bound combination.
    "action_characterization": [
        "Material_Immaterial_only",
        "Materiality_3_groups_people_planet_prosperity_SDG",
        "Materiality_5_groups_SDG_brackets",
        "Materiality_Climate_Natural_Capital_vs_All_SDGS",
        "Combined_Material_Immaterial_3_Matteo_Signals",
        "Combined_Material_Immaterial_4_Behavioural_Signals",
    ],
}
