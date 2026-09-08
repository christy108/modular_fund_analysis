"""Alternate sweep definition — pure data, no logic. Run with:

    python -m New_Pipeline.sweep --params New_Pipeline.sweep_params_b

Same contract as ``sweep_parameters.py``: every key in ``GRID`` / ``EXPLICIT`` / ``FIXED``
must be a real ``build_cfg`` knob (baseline dict at ``New_Pipeline/experiments.py:38``),
and the sweep validates every combination through ``build_cfg(**overrides)`` BEFORE the
first pipeline run, so a typo raises in the first second rather than forty minutes in.

THIS FILE IS THE **EUROPE** HALF. Its mirror is ``sweep_parameters.py``, which is the
same eight cells on the US. The two are deliberately identical apart from
``region_analysis`` — keep any edit here in step with that file, or the regions stop
being comparable.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# SWEEP_NAME: names this sweep's output folder, `sweep_output/<UTC stamp>_<name>/`.
# Change it to start a NEW sweep; re-running with the same name RESUMES the existing
# folder (that is what makes --resume work). `--new-run` forces a fresh folder anyway,
# and `--out DIR` overrides the whole thing.
#
# Previous sweeps in this file, for reference:
#   "us_mktcap_weighted_6designs"  (completed -- output in
#                                   sweep_output/20260908T010352Z_*). Note that despite
#                                   living in the "_b" file it was a US sweep; this file
#                                   is now the EUROPE half of the US/EU pair.
# To add cells to that one, restore this file from git rather than editing the name back:
# --resume can only recognise what already ran if the worklist still matches.
# --------------------------------------------------------------------------- #
SWEEP_NAME: str = "eu_ff5_allsdg_pp_mcap_quantiles"


# --------------------------------------------------------------------------- #
# WHAT THIS SWEEP IS
#
# Kevin's FF5 request, EUROPE half: two materiality designs crossed with the sort
# granularity and the market-cap screen, on the FULL 2016-2024 sample.
#
#   2 designs  x  2 quantile counts  x  2 mcap screens  =  8 runs
#
# Identical to sweep_parameters.py except for region_analysis. Everything else is the
# build_cfg baseline, pinned in FIXED below.
#
# WHY 8 AND NOT 4. The request asked whether both quantile counts would be too many runs,
# and offered to drop to K=5 only. It is not too many: 8 cells here plus 8 on the US side
# is 16 runs at roughly five minutes each, and prior sweeps in this repo ran 36 and 128
# cells. So K=3 AND K=5 are both kept. Drop `3` from the GRID axis below to fall back to
# the 4-cell version.
#
# THE DESIGNS. Both are one-group MIRROR PAIRS: signal_0 is a material SHARE and
# signal_1 = 1 - signal_0, so High on one leg is Low on the other and the two High-Low
# spreads are exact negatives. On the risk panel that shows up as one green row and one
# red row per pair, which is expected, not a bug -- the colour is carrying the sign.
#
#   Material_Immaterial_only                "All SDGs Material" -- all 17 SDGs, every
#                                           action. The widest denominator in the set.
#   Materiality_People_Plus_Prosperity_SDG  "PP Material" -- People + Prosperity pooled,
#                                           i.e. every SDG except 6, 7, 12, 13, 14, 15.
#
# PP is a SUBSET of All-SDGs, so these are NOT two independent tests. Read a difference
# between them as "does narrowing the denominator to People+Prosperity concentrate or
# dilute the signal", not as two separate findings.
#
# WHAT "EUROPE" CHANGES, beyond the sample itself. region_analysis="Europe" derives
# currency_filter=["EUR","GBP","CHF","NOK","SEK","DKK"], region_filter=["Europe"],
# convert_to_USD=True and fama_factor_region="Europe" (experiments.py:385). Three things
# follow, none of which apply to the US half:
#   * CONVERSION IS LOAD-BEARING HERE. The sample spans six currencies, and market caps
#     are in the listing currency until converted. Cap weighting sums caps ACROSS
#     holdings, so summing an unconverted GBP cap with a SEK one would be wrong by the
#     exchange rate. convert_to_USD=True is what makes portfolio_weighting="mktcap" valid
#     on this region at all -- build_cfg raises on the multi-currency + unconverted +
#     cap-weighted combination precisely to catch this.
#   * THE FF FACTORS ARE THE EUROPE FILES: Europe_3_Factors.csv and Europe_5_Factors.csv,
#     not the US ones. Both exist and both cover 2016-2024 in full.
#   * THE MCAP LEVELS ARE THE US ONES, AND 0.99 IS NEW TERRITORY HERE. 0.95 / 0.99 were
#     requested for both regions, but no Europe sweep has ever run above 0.95 -- the three
#     in sweep_output/ used 0.85/0.95 (europe_mktcap_weighted_6designs, 40 cells each),
#     0.85/0.90/0.95 (europe_plain_action_signals) and 0.90/0.95
#     (europe_materiality_12_designs, 64 cells each). Europe has a longer small-cap tail
#     than the US, so 0.99 admits proportionally more of it. Expect a markedly wider
#     universe on those four cells, and read the mktcap_filter_audit panel rather than
#     assuming the screen behaves as it does on the US.
#
# THE MARKET-CAP AXIS. mktcap_covered_if_filter_by_cum_market_cap keeps the largest firms
# per region-year until this share of total market cap is covered. 0.95 is the baseline;
# 0.99 is LOOSER -- it admits a longer tail of small caps. Because cap weighting gives
# those extra small names very little weight, expect 0.99 to move a cap-weighted spread
# LESS than it would have moved an equal-weighted one. If 0.95 and 0.99 agree, that is the
# useful result: the spread is not an artefact of where the tail was cut.
#
# INTERACTION WORTH KNOWING. Cap weighting discards a bucket-month outright when
# `n * cap <= 1` -- ten names or fewer at the 10% ceiling -- because no weight vector can
# satisfy both the budget and the cap. The NaN is then booked by (1+r).cumprod() as a
# fabricated 0% month and feeds the thin-portfolio gate. This bites HARDER on Europe than
# on the US: the region is smaller, so a K=5 sort at the tighter 0.95 screen is the
# thinnest configuration in the whole 16-cell pair. Check
# `n_months_discarded_infeasible` in the coverage panel before reading a missing leg as a
# result.
#
# NAMES: experiment_name() builds each run name from the cfg DIFF against build_cfg().
# The baseline region is the US, so EVERY cell here carries region_analysis-Europe plus
# the two derived keys (convert_to_USD, fama_factor_region) in its diff. That makes these
# names long enough to be blake2b-truncated past 150 chars on the longer design -- the
# ledger and CSV keep the full cfg regardless, and the page TITLE stays readable, so this
# costs nothing but do not expect the folder names to be self-describing.
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# GRID: expanded to its full cartesian product.
#
# All three axes are genuinely INDEPENDENT, so the whole cross belongs here and EXPLICIT
# stays empty. (Contrast the pre/post-2020 sweep, where a window was a PAIR of keys
# (start_year, end_year) that had to move together and so had to be built in EXPLICIT.)
#
#   2 designs x 2 quantile counts x 2 mcap screens = 8 cells
# --------------------------------------------------------------------------- #
GRID: dict[str, list] = {
    # "All SDGs Material" first, then its "PP Material" subset.
    "action_characterization": [
        "Material_Immaterial_only",
        "Materiality_People_Plus_Prosperity_SDG",
    ],
    # Sort granularity: coarse 3-way and finer 5-way.
    "no_simple_quantiles": [3, 5],
    # Market-cap coverage of the screen. See the Europe note above: 0.99 is looser than
    # anything previously run on this region.
    "mktcap_covered_if_filter_by_cum_market_cap": [0.85, 0.95],
}

# --------------------------------------------------------------------------- #
# EXPLICIT: hand-picked combinations, appended after the grid, used verbatim.
# EMPTY -- the whole cross is a clean cartesian product, so it belongs in GRID.
# --------------------------------------------------------------------------- #
EXPLICIT: list[dict] = []

# --------------------------------------------------------------------------- #
# FIXED: merged into EVERY combination, grid and explicit alike. Use for knobs you want
# held constant across the whole sweep without repeating them in each entry.
# An entry in GRID/EXPLICIT wins over FIXED for the same key.
# --------------------------------------------------------------------------- #
FIXED: dict = {
    # THE REGION -- the ONLY line that differs from sweep_parameters.py. Drives
    # currency_filter=["EUR","GBP","CHF","NOK","SEK","DKK"], region_filter=["Europe"],
    # convert_to_USD=True and fama_factor_region="Europe" (experiments.py:385).
    # This is the one pin here that is NOT at the build_cfg baseline, so it (and its two
    # derived keys) appear in every run name.
    "region_analysis": "Europe",

    # ---- everything below EQUALS the build_cfg baseline ------------------- #
    # None of it reaches the cfg diff, so none of it pollutes a run name. Pinned anyway:
    # this file is the record of what the sweep was, and "it inherited whatever
    # experiments.py said that week" is not a record.
    #
    # That cuts both ways: a pin OVERRIDES the baseline, so when experiments.py moves,
    # a pin left behind silently freezes the sweep at the old value. That has already
    # happened once in the US file -- portfolio_weighting was pinned "equal" while the
    # baseline moved to "mktcap", which would have run every cell equal-weighted.
    # Re-check this block against build_cfg() before launching, not after.

    # Percentile trim on sum_activities (the firm-year's total initiative count), applied
    # per tail. Requested at 0.05, which is also the current baseline, so it does not
    # reach the cfg diff and appears in no run name.
    "alpha_bound": 0.05,

    # The materiality inner join is what makes a materiality design possible at all --
    # signal_0 is a MATERIAL share, read off the SASB workbook. Not optional here.
    "add_materiality": True,
    "materiality_version": 2,

    # NO materiality-split floor ("min initiatives 0"): a firm-year is split into
    # material/immaterial however few initiatives it has. Requested, and also baseline.
    "minimum_initatives_needed_to_split_by_materiality": 0,

    # Filter 2 ONLY (drop suspicious gvkeys). Chosen over "all", which would additionally
    # switch on "keep firms with >= 3 fiscal years of data" -- a survivorship screen.
    # CONSEQUENCE: filter 3, the min_initatives_annual_reports_if_execute_3_filters_true
    # floor, is SKIPPED under this mode (01_process_lc.py:398 gates it on `_all3`). That
    # knob therefore has NO EFFECT in this sweep at any value.
    "execute_3_filters": "suspicious_only",

    # CAP weighting ("Mkt Cap weights"): each holding gets its share of bucket market cap,
    # with a single-name ceiling of max_portfolio_weight_if_portfolio_weighting_equal
    # (baseline 0.10 = 10%), excess redistributed pro-rata by cap and re-checked
    # iteratively. Requested, and also the baseline as of 2026-09-08. Valid on this region
    # only because convert_to_USD=True -- see the Europe note in the header.
    "portfolio_weighting": "mktcap",

    # The thin-portfolio gate, at baseline. A High/Low leg is HIDDEN unless it holds at
    # least min_stocks_per_portfolio names in at least min_portfolio_coverage of formation
    # months. This is the knob most likely to hide a leg on Europe, which is the smaller
    # of the two regions.
    "min_stocks_per_portfolio": 25,
    "min_portfolio_coverage": 0.8,

    # no_simple_quantiles and mktcap_covered_if_filter_by_cum_market_cap are NOT pinned
    # here -- they are GRID axes, so a FIXED value would be overridden on all 8 cells and
    # would only mislead a reader of this file. start_year / end_year are likewise absent:
    # this sweep is the FULL baseline 2016-2024 sample, not the pre/post-2020 split.
}


# --------------------------------------------------------------------------- #
# Output settings
# --------------------------------------------------------------------------- #

# Rebuild results.pdf / results.csv from the ledger every N completed experiments.
# The ledger itself is appended after EVERY experiment regardless, so this only trades
# how fresh the two derived files are against the seconds each rebuild costs.
# Both are ALWAYS rebuilt once more when the sweep finishes (or is interrupted).
PDF_EVERY: int = 2

# Everything the sweep writes lives under here, relative to the repo root.
OUTPUT_DIR: str = "sweep_output"


# --------------------------------------------------------------------------- #
# How many experiments run at once (`--jobs N` overrides).
#
# Each worker is a separate PROCESS running one full pipeline, so this scales with cores
# AND with RAM -- every worker independently loads the Golden LC panel and the Compustat
# universe. On this machine (10 cores / 64 GB) 2 is demonstrated.
#
# NOTE this requires cfg.write_debug_csv=False (the default). Those dumps go to FIXED
# paths under ./data/debug/, so parallel workers would clobber each other's files.
# Do NOT run this file and sweep_parameters.py concurrently at JOBS=2 each: that is four
# pipelines, each holding its own copy of the Golden panel and the Compustat universe.
# --------------------------------------------------------------------------- #
JOBS: int = 2


# --------------------------------------------------------------------------- #
# Presentation order for results.pdf / results.csv.
#
# The ledger stays in completion order (it is append-only, and under --jobs N that order
# is not even deterministic), but the PDF and CSV are SORTED by these cfg keys before
# being written -- and by the same function, so "CSV row N describes PDF page N" holds.
# Identical to the US file, so page N here is the same cell as page N there.
# --------------------------------------------------------------------------- #
SORT_BY: list[str] = [
    # Outermost: the design, so the two denominators read as two blocks of four.
    "action_characterization",
    # Then the sort granularity.
    "no_simple_quantiles",
    # Innermost: the market-cap screen, so each design/K pair puts its 0.95 page directly
    # next to its 0.99 page -- the robustness comparison this axis exists to make.
    "mktcap_covered_if_filter_by_cum_market_cap",
]

VALUE_ORDER: dict[str, list] = {
    # Wide denominator first, then the People+Prosperity subset of it.
    "action_characterization": [
        "Material_Immaterial_only",                # all 17 SDGs, every action
        "Materiality_People_Plus_Prosperity_SDG",  # all SDGs except 6, 7, 12, 13, 14, 15
    ],
}
