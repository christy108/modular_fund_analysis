"""Alternate sweep definition — pure data, no logic. Run with:

    python -m New_Pipeline.sweep --params New_Pipeline.sweep_params_b

Same contract as ``sweep_parameters.py``: every key in ``GRID`` / ``EXPLICIT`` / ``FIXED``
must be a real ``build_cfg`` knob (baseline dict at ``New_Pipeline/experiments.py:38``),
and the sweep validates every combination through ``build_cfg(**overrides)`` BEFORE the
first pipeline run, so a typo raises in the first second rather than forty minutes in.

THIS FILE IS THE **EUROPE** HALF. Its mirror is ``sweep_parameters.py``, which is the
same worklist on the US. The two are deliberately identical apart from
``region_analysis`` and the market-cap axis (see below) — keep any other edit here in
step with that file, or the regions stop being comparable. Each file writes to its own
``sweep_output/<stamp>_<name>/`` folder, so the US and EU results are always two separate
PDFs/CSVs, never merged.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# SWEEP_NAME: names this sweep's output folder, `sweep_output/<UTC stamp>_<name>/`.
# Change it to start a NEW sweep; re-running with the same name RESUMES the existing
# folder (that is what makes --resume work). `--new-run` forces a fresh folder anyway,
# and `--out DIR` overrides the whole thing.
#
# Previous sweeps in this file, for reference:
#   "eu_ff5_allsdg_pp_mcap_quantiles"  (8 cells requested, only 4 ever recorded -- see
#                                       below).
#   "us_mktcap_weighted_6designs"      (completed despite living in this file's slot at
#                                       the time -- see sweep_output/20260908T010352Z_*).
# To add cells to one of those, restore this file from git rather than editing the name
# back: --resume can only recognise what already ran if the worklist still matches.
#
# WHAT HAPPENED TO THE PRIOR EU SWEEP. Its grid included mktcap_covered=0.99, which
# panics the Rust polars binview allocator once Europe's universe at 99% coverage crosses
# ~4.29 GB pickled (`pack_obj` stores the whole global_universe dict as one binary cell,
# and that column type caps a single cell at u32::MAX bytes -- a structural limit,
# unrelated to available RAM). Confirmed against every EU ledger ever produced: 0.85 and
# 0.95 have both completed repeatedly; 0.99 never once has. Worse, a panic on one worker
# breaks the WHOLE ProcessPoolExecutor pool, so none of that sweep's records -- including
# cells that had already finished computing -- ever reached the ledger; results.csv came
# out as a bare header. This file now keeps 0.99 out of the EU grid entirely.
# --------------------------------------------------------------------------- #
SWEEP_NAME: str = "eu_health_sdgs_weighting_mcap_quantiles"


# --------------------------------------------------------------------------- #
# WHAT THIS SWEEP IS
#
# Kevin's health-alphas request, EUROPE half: three health-SDG materiality designs
# crossed with the weighting scheme and the sort granularity, on the FULL 2016-2024
# sample. The market-cap axis is narrower here than on the US -- see below.
#
#   3 designs  x  2 weighting schemes  x  2 quantile counts  x  2 mcap screens
#   = 24 runs
#
# Identical to sweep_parameters.py except for region_analysis and the mcap axis.
# Everything else is the build_cfg baseline, pinned in FIXED below.
#
# THE DESIGNS. All three are one-group MIRROR PAIRS: signal_0 is a material SHARE of the
# group's SDGs and signal_1 = 1 - signal_0, so High on one leg is Low on the other and the
# two High-Low spreads are exact negatives. On the risk panel that shows up as one green
# row and one red row per pair, which is expected, not a bug -- the colour is carrying
# the sign.
#
#   Materiality_One_Health_SDGS             "One Health" -- Health_SDGS_Groups'
#                                           One_Health cut: SDGs 3, 6, 8, 11, 14, 15.
#   Materiality_One_Health_Ex_SDG_8_SDGS    "One Health ex SDG8" -- the same group with
#                                           SDG 8 (decent work) dropped: SDGs 3, 6, 11,
#                                           14, 15.
#   Materiality_Narrow_Health_SDGS          "Narrow Health" -- the tightest cut: SDGs
#                                           3, 6, 11 only.
#
# "One Health ex SDG8" is a SUBSET of "One Health", and "Narrow Health" is a further
# subset of that. These are NOT three independent tests -- read a difference between them
# as "does narrowing the denominator concentrate or dilute the signal".
#
# THE WEIGHTING AXIS ("Mkt cap weighted" and "EQ weights"). portfolio_weighting="mktcap"
# is the build_cfg baseline; "equal" is the classic unweighted High-minus-Low. Cap
# weighting is valid on this region ONLY because convert_to_USD=True below -- build_cfg
# raises on the multi-currency + unconverted + cap-weighted combination precisely to
# catch a mis-pinned region. Expect cap weighting to damp the spread relative to equal
# weighting whenever the material/immaterial split correlates with size, and to
# occasionally DISCARD a bucket-month outright (see the INTERACTION note below), which
# equal weighting never does -- this bites harder on Europe than the US (smaller region,
# thinner buckets).
#
# WHAT "EUROPE" CHANGES, beyond the sample itself. region_analysis="Europe" derives
# currency_filter=["EUR","GBP","CHF","NOK","SEK","DKK"], region_filter=["Europe"],
# convert_to_USD=True and fama_factor_region="Europe" (experiments.py:385). Two things
# follow that do not apply to the US half:
#   * CONVERSION IS LOAD-BEARING HERE. The sample spans six currencies, and market caps
#     are in the listing currency until converted. Cap weighting sums caps ACROSS
#     holdings, so summing an unconverted GBP cap with a SEK one would be wrong by the
#     exchange rate.
#   * THE FF FACTORS ARE THE EUROPE FILES: Europe_3_Factors.csv and Europe_5_Factors.csv,
#     not the US ones. Both exist and both cover 2016-2024 in full.
#
# THE MARKET-CAP AXIS IS NARROWER THAN THE US FILE'S, AND DELIBERATELY SO. Kevin's
# request asked for 0.95/0.99 on both regions, but 0.99 is unusable on Europe -- see the
# SWEEP_NAME comment above for the mechanism (a hard ~4.29 GB pickling ceiling, not a RAM
# question, and one that has never once been crossed successfully here). This file runs
# 0.85/0.95 instead: both have completed repeatedly on Europe (europe_mktcap_weighted_
# 6designs, europe_plain_action_signals, europe_materiality_12_designs all used one or
# both), so this axis is safe. If 0.85 and 0.95 give the same answer, that is still the
# useful result: the spread is not an artefact of where the tail was cut. A widened cap
# axis on Europe would need `pack_obj`/`boundary.py` changed to chunk large payloads
# instead of one binary blob -- out of scope here.
#
# INTERACTION WORTH KNOWING. Cap weighting discards a bucket-month outright when
# `n * cap <= 1` -- ten names or fewer at the 10% ceiling -- because no weight vector can
# satisfy both the budget and the cap. The NaN is then booked by (1+r).cumprod() as a
# fabricated 0% month and feeds the thin-portfolio gate. "Narrow Health" at K=5, 0.95 mcap
# is the thinnest configuration in this file (narrowest group, most buckets, tightest
# screen); check `n_months_discarded_infeasible` in the coverage panel before reading a
# missing leg as a result on that cell.
#
# NAMES: experiment_name() builds each run name from the cfg DIFF against build_cfg().
# The baseline region is the US, so EVERY cell here carries region_analysis-Europe plus
# the two derived keys (convert_to_USD, fama_factor_region) in its diff, on top of the
# action_characterization diff every cell also carries (none of the three health designs
# equal the Material_Immaterial_only baseline). That makes these names long enough to be
# blake2b-truncated past 150 chars on some cells -- the ledger and CSV keep the full cfg
# regardless, and the page TITLE stays readable, so this costs nothing but do not expect
# the folder names to be self-describing.
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# GRID: expanded to its full cartesian product.
#
# All four axes are genuinely INDEPENDENT, so the whole cross belongs here and EXPLICIT
# stays empty.
#
#   3 designs x 2 weighting schemes x 2 quantile counts x 2 mcap screens = 24 cells
# --------------------------------------------------------------------------- #
GRID: dict[str, list] = {
    # Widest health group first, then its ex-SDG-8 variant, then the narrowest cut.
    "action_characterization": [
        "Materiality_One_Health_SDGS",
        "Materiality_One_Health_Ex_SDG_8_SDGS",
        "Materiality_Narrow_Health_SDGS",
    ],
    # Cap-weighted first (also the build_cfg baseline), then equal-weighted.
    "portfolio_weighting": ["mktcap", "equal"],
    # Sort granularity: coarse 3-way and finer 5-way.
    "no_simple_quantiles": [3, 5],
    # Market-cap coverage of the screen. 0.85/0.95, NOT 0.95/0.99 -- see the header note
    # on why 0.99 is out of scope for Europe.
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
    # THE REGION -- one of two lines that differ from sweep_parameters.py (the other
    # being the mcap axis above). Drives currency_filter=["EUR","GBP","CHF","NOK","SEK",
    # "DKK"], region_filter=["Europe"], convert_to_USD=True and
    # fama_factor_region="Europe" (experiments.py:385). This is NOT at the build_cfg
    # baseline, so it (and its two derived keys) appear in every run name.
    "region_analysis": "Europe",

    # ---- everything below EQUALS the build_cfg baseline ------------------- #
    # None of it reaches the cfg diff, so none of it pollutes a run name. Pinned anyway:
    # this file is the record of what the sweep was, and "it inherited whatever
    # experiments.py said that week" is not a record.
    #
    # That cuts both ways: a pin OVERRIDES the baseline, so when experiments.py moves,
    # a pin left behind silently freezes the sweep at the old value. Re-check this block
    # against build_cfg() before launching, not after.

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

    # The thin-portfolio gate, at baseline. A High/Low leg is HIDDEN unless it holds at
    # least min_stocks_per_portfolio names in at least min_portfolio_coverage of formation
    # months. This is the knob most likely to hide a leg on Europe, which is the smaller
    # of the two regions.
    "min_stocks_per_portfolio": 25,
    "min_portfolio_coverage": 0.8,

    # portfolio_weighting, no_simple_quantiles and
    # mktcap_covered_if_filter_by_cum_market_cap are NOT pinned here -- they are GRID
    # axes, so a FIXED value would be overridden on all 24 cells and would only mislead a
    # reader of this file. max_portfolio_weight_if_portfolio_weighting_equal is likewise
    # absent: it stays at the build_cfg baseline (0.10 = 10% single-name ceiling), which
    # applies only when portfolio_weighting="mktcap" and is silently ignored under
    # "equal". start_year / end_year are also absent: this sweep is the FULL baseline
    # 2016-2024 sample, not the pre/post-2020 split.
}


# --------------------------------------------------------------------------- #
# Output settings
# --------------------------------------------------------------------------- #

# Rebuild results.pdf / results.csv from the ledger every N completed experiments.
# The ledger itself is appended after EVERY experiment regardless, so this only trades
# how fresh the two derived files are against the seconds each rebuild costs.
# Both are ALWAYS rebuilt once more when the sweep finishes (or is interrupted).
PDF_EVERY: int = 4

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
# Identical to the US file, so page N here is the same cell as page N there (modulo the
# different mcap values on the innermost axis).
# --------------------------------------------------------------------------- #
SORT_BY: list[str] = [
    # Outermost: the design, so the three groups read as three blocks of eight.
    "action_characterization",
    # Then the weighting scheme, so each design's cap-weighted block sits directly above
    # its equal-weighted block.
    "portfolio_weighting",
    # Then the sort granularity.
    "no_simple_quantiles",
    # Innermost: the market-cap screen, so each design/weighting/K triple puts its 0.85
    # page directly next to its 0.95 page.
    "mktcap_covered_if_filter_by_cum_market_cap",
]

VALUE_ORDER: dict[str, list] = {
    # Widest health group first, narrowing down.
    "action_characterization": [
        "Materiality_One_Health_SDGS",             # SDGs 3, 6, 8, 11, 14, 15
        "Materiality_One_Health_Ex_SDG_8_SDGS",    # SDGs 3, 6, 11, 14, 15
        "Materiality_Narrow_Health_SDGS",          # SDGs 3, 6, 11
    ],
    # Cap-weighted first, matching Kevin's own ordering ("Mkt cap weighted" then
    # "And EQ weights").
    "portfolio_weighting": ["mktcap", "equal"],
}
