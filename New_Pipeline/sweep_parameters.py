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
SWEEP_NAME: str = "sdg_designs_alpha_quantile_mcap"


# --------------------------------------------------------------------------- #
# The seven signal designs this sweep covers:
#   - three one-group materiality designs (each a mirror pair: signal_0 is that
#     group's material share, signal_1 its exact complement)
#   - Materiality_SDG_X for SDG 1, 3, 5, 10 (the single-SDG design, via the cfg knob
#     materiality_single_sdg rather than a distinct action_characterization per SDG --
#     see functions/signal_design/signal_definitions_materiality.py)
#
# materiality_single_sdg is ignored by every action_characterization except
# "Materiality_single_SDG" (build_cfg does not raise on the unused key for the other
# six), but a GRID cross of action_characterization x materiality_single_sdg would still
# waste 3 designs x 4 SDGs = 12 runs re-deriving identical cfgs. That is exactly the
# "knobs that must move together" case the EXPLICIT section below exists for.
# --------------------------------------------------------------------------- #
_SDGS_TO_SWEEP: list[int] = [3, 5, 10]

DESIGNS: list[dict] = [
    {"action_characterization": "Materiality_People_SDG"},
    {"action_characterization": "Materiality_People_Plus_Prosperity_SDG"},
    {"action_characterization": "Materiality_People_Plus_Prosperity_VS_Planet_SDG"},
] + [
    {"action_characterization": "Materiality_single_SDG", "materiality_single_sdg": sdg}
    for sdg in _SDGS_TO_SWEEP
]

# --------------------------------------------------------------------------- #
# GRID: expanded to its full cartesian product.
# Left empty and disabled here -- the design/SDG pairing above has to move together with
# each design, which GRID cannot express; EXPLICIT does the full cross instead.
# --------------------------------------------------------------------------- #
GRID: dict[str, list] = {}

# The three sweep parameters, each requested at these levels:
_ALPHA_BOUNDS: list[float] = [0.5, 0.1]
_QUANTILES: list[int] = [3, 5, 7]
_MCAP_COVERED: list[float] = [0.95, 0.99]

# --------------------------------------------------------------------------- #
# EXPLICIT: hand-picked combinations, appended after the grid, used verbatim.
# For knobs that must move together (add_materiality + a materiality-only
# action_characterization, say) a grid cannot express the constraint — put them here.
#
# Full cross of DESIGNS x alpha_bound x no_simple_quantiles x mcap_covered:
# 7 designs x 2 x 3 x 2 = 84 experiments. At JOBS=2 that is a long sweep -- raise
# --jobs if you have the RAM (each worker loads the full Golden LC + Compustat universe
# independently; see the JOBS comment below), or trim _SDGS_TO_SWEEP / the parameter
# lists above for a quicker pass.
# --------------------------------------------------------------------------- #
EXPLICIT: list[dict] = [
    {**design, "alpha_bound": alpha, "no_simple_quantiles": k,
     "mktcap_covered_if_filter_by_cum_market_cap": mcap}
    for design in DESIGNS
    for alpha in _ALPHA_BOUNDS
    for k in _QUANTILES
    for mcap in _MCAP_COVERED
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
    "action_characterization",
    # None for the three group designs, 1/3/5/10 for Materiality_single_SDG -- _sort_key
    # coerces None to the string "None" and groups it with the other unlisted values, so
    # it sorts safely alongside the SDG numbers without a value_order entry.
    "materiality_single_sdg",
    "alpha_bound",
    "no_simple_quantiles",
    "mktcap_covered_if_filter_by_cum_market_cap",
]

VALUE_ORDER: dict[str, list] = {
    # Pages group by signal design, in this order; within each group they run through
    # every SDG (where applicable) x alpha_bound x no_simple_quantiles x mcap combination.
    "action_characterization": [
        "Materiality_People_SDG",
        "Materiality_People_Plus_Prosperity_SDG",
        "Materiality_People_Plus_Prosperity_VS_Planet_SDG",
        "Materiality_single_SDG",
    ],
}
