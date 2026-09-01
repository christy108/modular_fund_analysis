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
SWEEP_NAME: str = "per_revenue_winsorise"


# --------------------------------------------------------------------------- #
# GRID: expanded to its full cartesian product.
#   {"a": [1, 2], "b": ["x", "y"]}  ->  4 experiments (a=1,b=x), (a=1,b=y), ...
# Set to {} to disable and use EXPLICIT only.
# --------------------------------------------------------------------------- #
GRID: dict[str, list] = {
    # Every signal design, each at three winsorisation levels. signal_type is pinned to
    # "per_revenue" in FIXED, so this measures what winsorising does to an UNBOUNDED,
    # right-skewed signal -- the case it was built for. (On "weights", a share bounded in
    # [0,1], it clipped ~0.9% of values and moved std by only ~2.4%.)
    "action_characterization": [
        "Material_Immaterial_only",
        "Materiality_3_groups_people_planet_prosperity_SDG",
        "Materiality_5_groups_SDG_brackets",
        "Materiality_Climate_Natural_Capital_vs_All_SDGS",
        "Combined_Material_Immaterial_3_Matteo_Signals",
        "Combined_Material_Immaterial_4_Behavioural_Signals",
        "total_initiatives",
    ],
    "winsorise_signal_pct": [0.0, 0.01, 0.02],
}

# --------------------------------------------------------------------------- #
# EXPLICIT: hand-picked combinations, appended after the grid, used verbatim.
# For knobs that must move together (add_materiality + a materiality-only
# action_characterization, say) a grid cannot express the constraint — put them here.
# --------------------------------------------------------------------------- #
EXPLICIT: list[dict] = [
    # total_initiatives as a raw COUNT, at the same three winsorise levels. Identical
    # numerator to its per_revenue twin in the grid, so each pair isolates exactly one
    # thing: the revenue denominator.
    # (total_initiatives + signal_type="weights" is rejected by build_cfg -- one group
    # covering every initiative gives sum_with_0/sum_activities == 1.0 for every firm.)
    {"action_characterization": "total_initiatives",
     "signal_type": "counts", "winsorise_signal_pct": w}
    for w in [0.0, 0.01, 0.02]
]

# --------------------------------------------------------------------------- #
# FIXED: merged into EVERY combination, grid and explicit alike. Use for knobs you want
# held constant across the whole sweep without repeating them in each entry.
# An entry in GRID/EXPLICIT wins over FIXED for the same key.
# --------------------------------------------------------------------------- #
FIXED: dict = {
    "add_materiality": True,
    # per_revenue REQUIRES add_sales -- the denominator is the `sale_usd` column the
    # sales merge attaches in process_lc (build_cfg raises otherwise).
    "add_sales": True,
    "signal_type": "per_revenue",
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
    "signal_type",
    "winsorise_signal_pct",
    "no_simple_quantiles",
    "alpha_bound",
    "mktcap_covered_if_filter_by_cum_market_cap",
]

VALUE_ORDER: dict[str, list] = {
    # Within each design: the per_revenue pages (this sweep's subject) first, then the
    # counts reference. "weights" is listed for older ledgers that still contain it.
    "signal_type": ["per_revenue", "counts", "weights"],
    # Pages group by signal design, in this order; within each group they run through
    # every no_simple_quantiles x alpha_bound combination.
    "action_characterization": [
        "Material_Immaterial_only",
        "Materiality_3_groups_people_planet_prosperity_SDG",
        "Materiality_5_groups_SDG_brackets",
        "Materiality_Climate_Natural_Capital_vs_All_SDGS",
        "Combined_Material_Immaterial_3_Matteo_Signals",
        "Combined_Material_Immaterial_4_Behavioural_Signals",
        "total_initiatives",
    ],
}
