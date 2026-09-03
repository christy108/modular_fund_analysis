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
SWEEP_NAME: str = "sdg_min_initiatives_x_quantiles"


# --------------------------------------------------------------------------- #
# Single-SDG material/immaterial sorts: the materiality split FLOOR crossed against the
# bucket count, the alpha-bound trim and the market-cap screen. EVERY AXIS IS PER-SDG,
# because the three SDGs do not support the same ranges.
#
#   SDG 3  : N = 0,2,3,5  x  K = 3,5,7  x  alpha = .05,.1  x  mcap = .95,.99  -> 48
#   SDG 5  : N = 0,2      x  K = 3      x  alpha = .05,.1  x  mcap = .95,.99  ->  8
#   SDG 10 : N = 0,2      x  K = 3      x  alpha = .05,.1  x  mcap = .95,.99  ->  8
#                                                                             == 64
#
# WHY THE RANGES DIFFER PER SDG -- this asymmetry IS the design; do not "tidy" it into a
# uniform cross. Measured on the pre-floor panel, converting firm-years to monthly assets
# at the rate calibrated on the People design (~0.0437 assets/firm-year, which predicted
# 275 against an actual 284), then dividing by K to get names per bucket:
#
#                  assets    K=3    K=5    K=7      (gate = min_stocks_per_portfolio = 25)
#   SDG 3  N=0       262      87     52     37
#          N=2       222      74     44     32
#          N=3       183      61     37     26
#          N=5       128      43     26     18 <-- fails
#   SDG 5  N=0       137      46     27     20 <-- fails
#          N=2        86      29     17 <-- fails
#   SDG 10 N=0       149      50     30     21 <-- fails
#          N=2        96      32     19 <-- fails
#
# So SDG 5 and SDG 10 are held at K=3 ONLY: at K=5 their N=2 legs fall to 17-19 names and
# at K=7 to 12-14, which is idiosyncratic noise rather than a portfolio. SDG 3 carries
# enough firm-years (5,999 post-trim vs 3,139 and 3,410) to take the full K range, and the
# floors up to 5 -- only its N=5/K=7 corner fails, and that one cell is kept deliberately
# (see below). Their floors stop at 2 for the same reason: N=3 leaves SDG 5 and SDG 10 with
# 45 and 56 assets, i.e. 15-19 names per bucket even at K=3.
#
# alpha_bound=0.05 trims LESS than 0.1 (the bound is halved per tail, so 2.5% vs 5% each
# side), so every cell runs slightly LARGER than the table above -- never smaller. The
# table is therefore the pessimistic side of this sweep.
#
# The few gate-failing cells are KEPT rather than pruned: the gate is PRESENTATION-ONLY
# (the exported parquets always keep every portfolio), so the sweep would happily report an
# alpha for a 12-name leg. Including them means results.csv carries their coverage_pct__*
# columns, which is the evidence for why they are unreadable. Read every alpha__ column
# next to its coverage_pct__ neighbour.
#
# EXPECTED RESULT: the floor should NOT reduce saturation here. Firm-years at ratio exactly
# 1.0 go 69.9 -> 70.1 -> 70.5 -> 71.3% for SDG 3 as N rises, and similarly for 5 and 10 --
# because within ONE SDG the initiative count and the material share are POSITIVELY
# correlated (a firm with many SDG-3 initiatives is focused on SDG 3, and focused firms are
# all-material there). This sweep is therefore a ROBUSTNESS check -- evidence that the
# single-SDG results are not an artefact of thin denominators -- not a fix for the atom.
# --------------------------------------------------------------------------- #
_SDG_SPECS: list[dict] = [
    {"sdg": 3,
     "floors":       [0, 2, 3, 5],
     "quantiles":    [3, 5, 7],
     "alpha_bounds": [0.05, 0.1],
     "mcap":         [0.95, 0.99]},
    {"sdg": 5,
     "floors":       [0, 2],
     "quantiles":    [3],
     "alpha_bounds": [0.05, 0.1],
     "mcap":         [0.95, 0.99]},
    {"sdg": 10,
     "floors":       [0, 2],
     "quantiles":    [3],
     "alpha_bounds": [0.05, 0.1],
     "mcap":         [0.95, 0.99]},
]

# --------------------------------------------------------------------------- #
# GRID: expanded to its full cartesian product.
# Left empty -- every axis here is PER-SDG (SDG 5 and 10 take only K=3, and only floors up
# to 2), which a single cartesian GRID cannot express: it would force one shared K list on
# all three SDGs. EXPLICIT does a separate cross per SDG instead.
# --------------------------------------------------------------------------- #
GRID: dict[str, list] = {}

# --------------------------------------------------------------------------- #
# EXPLICIT: hand-picked combinations, appended after the grid, used verbatim.
# For knobs that must move together (add_materiality + a materiality-only
# action_characterization, say) a grid cannot express the constraint — put them here.
#
# One full cross per _SDG_SPECS entry, using that entry's own lists: 48 + 8 + 8 = 64.
# --------------------------------------------------------------------------- #
EXPLICIT: list[dict] = [
    {"action_characterization": "Materiality_single_SDG",
     "materiality_single_sdg": spec["sdg"],
     "minimum_initatives_needed_to_split_by_materiality": n,
     "no_simple_quantiles": k,
     "alpha_bound": alpha,
     "mktcap_covered_if_filter_by_cum_market_cap": mcap}
    for spec in _SDG_SPECS
    for n in spec["floors"]
    for k in spec["quantiles"]
    for alpha in spec["alpha_bounds"]
    for mcap in spec["mcap"]
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
    "min_portfolio_coverage":0.70,
    # alpha_bound and mktcap_covered are NOT pinned here -- they are swept per SDG in
    # _SDG_SPECS above, and every EXPLICIT entry sets both, so a FIXED value would be
    # overridden on all 64 combinations and only mislead a reader of this file.
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
    # The two axes under test, outermost-last so pages read as: all of SDG 3's floors in
    # ascending order, each with its K=3/5/7 triple adjacent -- which is the comparison
    # you actually make (does the spread survive raising the floor, at a fixed K).
    "minimum_initatives_needed_to_split_by_materiality",
    "no_simple_quantiles",
    "alpha_bound",
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