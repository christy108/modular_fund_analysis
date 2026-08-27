# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A fund-analysis pipeline (ESG/behavioural-signal portfolio sorts) that started as a single
notebook (`Main.ipynb`) calling into `functions/`, and is being re-implemented as an auditable,
content-addressed node pipeline in `New_Pipeline/`, built on the sibling framework package
`leonardo_nodes` (checked out at `../leonardo-nodes`, installed editable). **Bit-parity with the
frozen notebook output is the acceptance test for every change** — `New_Pipeline/` is a wrapper
around the *same* `functions/` code, not a rewrite of the numerics.

Three source trees, three states — know which is which before touching anything:

| Dir | State |
|---|---|
| `functions/` | The frozen numeric core. Called unchanged from inside every node. **Never edit this** — both `Main.ipynb` and `New_Pipeline/` import it, so any change moves the parity oracle and the thing being tested against it simultaneously. |
| `New_Pipeline/` | The active pipeline. All new work goes here. |
| `pipeline/` | Dead. Fully superseded by `New_Pipeline/`, and currently **empty** (no files) — despite `tests/test_parity.py` still importing `pipeline.boundary` / `pipeline.registry`, which means `pytest tests/` currently fails to collect. Don't resurrect it; if you need the old test layer working, point it at `New_Pipeline` instead. |

`New_Pipeline/README.md` is detailed but **stale** in places — its node table and DAG diagram
describe an older 12-node layout (`load_signal_lc`, `build_portfolios`, `ff3_alphas`,
`performance_tables`, `build_constituents` as separate nodes). The real current DAG is 10 nodes
(see below); trust `New_Pipeline/registry.py` over the README's node table and diagram. The
README's conceptual sections (Contract/Process/Node/Pipeline/Experiment, config-as-data, the
pandas↔polars boundary, provenance/manifests, "How to extend it") are accurate and worth reading.

## Commands

```bash
# one-time setup — leonardo_nodes is a sibling checkout, not on PyPI
pip install -e ../leonardo-nodes
pip install -r requirements.txt          # curated deps; requirements-3.14.lock.txt is a full freeze

# point at the Golden LC dataset (defaults to ~/Documents/GitHub/data/Golden_Data)
export GOLDEN_LOCATION=/path/to/Golden_Data
# optional, only when add_materiality=True: SASB workbook location (see Gotchas)
export MATERIALITY_LOCATION=/path/to/Materiality

# structure-only DAG check — no data touched, seconds
.venv/bin/python -m New_Pipeline.registry

# run one experiment; writes runs/<ts>_<config>/ (archived) + parity/artifacts/new/<config>/ (latest)
.venv/bin/python -m New_Pipeline.run base_none

# verify pipeline output == frozen notebook oracle, per artifact
.venv/bin/python -m parity.compare base_none      # non-zero exit on failure
.venv/bin/python -m parity.compare                # every config under parity/artifacts/new/
.venv/bin/python -m parity.show base_none         # print pipeline vs notebook tables side by side

# audit dashboard (Taipy — NOT in requirements.txt; see New_Pipeline/DASHBOARD.md for the
# uv-override install recipe needed to run it on this project's Python 3.14 .venv)
.venv/bin/python -m New_Pipeline.dashboard base_none esg_msci     # http://localhost:8080
.venv/bin/python -m New_Pipeline.dashboard base_none --port 8090  # run alongside another instance
.venv/bin/python -m New_Pipeline.dashboard base_none --markdown   # text only, no server

# parameter sweep -> one-page-per-experiment PDF + one-row-per-experiment CSV
# (what to run lives in New_Pipeline/sweep_parameters.py; see "The sweep runner" below)
.venv/bin/python -m New_Pipeline.sweep                    # run everything in sweep_parameters.py
.venv/bin/python -m New_Pipeline.sweep --dry-run          # list what would run, run nothing
.venv/bin/python -m New_Pipeline.sweep --only base_none   # named EXPERIMENTS entries instead
.venv/bin/python -m New_Pipeline.sweep --rebuild          # rebuild PDF/CSV from the ledger only

# tests (NOTE: currently broken — see "pipeline/ is dead" above)
.venv/bin/python -m pytest tests/ -v
```

There is no single-test / single-config shortcut beyond what's shown: `parity.compare <config>`
and `New_Pipeline.run <config>` both take exactly one config name at a time; the seven registered
configs are `base_none`, `esg_refinitiv`, `esg_msci`, `esg_snp`, `esg_full_universe`, `show_corr`,
`base_materiality` (source of truth: `EXPERIMENTS` dict in `New_Pipeline/experiments.py`).

## Architecture

**Five concepts** (framework-level, defined in `../leonardo-nodes`):
- **Contract** — top of each `nodes/NN_*.py`: a prose `intent` (purpose + mandatory measures +
  what it surfaces, never the algorithm), input/output schemas, and `audits` (dashboard VizSpecs).
- **Process** — one `@process(tag="...@v1")` function implementing a Contract. Content-addressed
  into `.leonardo_nodes_store/` on registration, so deleting it from the working tree doesn't lose
  the ability to reconstruct a past run. **A Process body must be fully self-contained** — all
  imports inside the function, no module-level helpers/globals — because archived Processes are
  re-executed in a fresh namespace when replayed.
- **Node** — `NODE = Node(...)` at the bottom of the file: name + ports only. Nodes never
  reference or import each other.
- **Pipeline** — `New_Pipeline/registry.py` owns every edge (the `EDGES` list) and node ordering
  (`_NODE_ORDER`, discovered from the `nodes/NN_*.py` filenames on disk, not hand-listed).
- **Experiment** — `New_Pipeline/experiments.py`: a Pipeline + a derived `cfg` frame +
  `process_selection` (which Process/version runs at each node, e.g. which of the four ESG-provider
  Processes `merge_esg_provider` uses).

**Config is data, not a kwarg.** A Process receives only its declared input frames — never
`exp.config`. `build_cfg(**overrides)` in `experiments.py` derives the whole config dict (mirroring
the original notebook's config cells, in order — that order is deliberate), `cfg_frame(cfg)` packs
it into a one-row `{"json": [...]}` frame, and every node starts with
`C = json.loads(cfg["json"][0])`. Because the cfg frame is hashed like any other input, a config
change shows up as a hash change in the manifest.

**The pandas↔polars boundary** is the one place containers convert: `New_Pipeline/boundary.py`.
All this project's numerics are pandas; `leonardo_nodes` hashes/validates `pl.DataFrame` at node
boundaries. The helpers (`pd_to_pl`/`pl_to_pd` for tidy tables, `wide_to_long_blocks`/
`long_blocks_to_wide` for heterogeneous pivots, `pack_obj`/`unpack_obj` for pickled plumbing
bundles, `empty_sentinel` for gated/off diagnostics) are lossless, order-preserving Arrow round
trips — verified by `python -m New_Pipeline.boundary`'s self-test. Fitted statsmodels models and
pandas `MultiIndex` must not cross this boundary (flatten first).

**Current DAG** (10 nodes; `python -m New_Pipeline.registry` prints the live topological order):

```
process_lc → derive_signals ─────────────┐
load_universes → merge_esg_provider ─────┼→ prepare_panel → build_analyse_portfolios
load_fama_french ─────────────────────────┘   │            → esg_signal_corr
                                              │            → esg_coverage
                                              └→ mktcap_filter_audit
```

(`esg_coverage` also takes `merge_esg_provider`'s `universe` and `process_lc`'s `lc` directly, not
only `prepare_panel`'s output — omitted above for the ASCII diagram's sake; see `EDGES` in
`registry.py` for the exact wiring.)

- `process_lc` / `derive_signals` — former single `load_signal_lc` node, split: load + sample
  filters + industry mapping, then category aggregation + alpha-bound trim + `signal_i` ratio.
  `esg_coverage` reads from `process_lc` (not `derive_signals`) because it needs
  `lc_raw_for_coverage`, snapshotted *before* the sample filters.
- `load_universes` / `merge_esg_provider` — former single `build_global_universe` node, split:
  raw per-region ingestion (identical across configs), then **four interchangeable Processes**
  (`esg_none`/`esg_refinitiv`/`esg_msci`/`esg_snp`), one per ESG provider, picked via
  `process_selection` rather than an if/elif inside one Process.
- `prepare_panel` — the one node with two interchangeable Processes: `prepare_lc@v1` (LC-merged
  signals; every config except one) and `prepare_esg_universe@v1` (full ESG universe, ESG score as
  sole signal; `esg_full_universe`).
- `build_analyse_portfolios` — folds the former `build_portfolios` / `ff3_alphas` /
  `performance_tables` / `build_constituents` into one node; all portfolio-level analytics
  (quantile sorts, FF3 alphas, cumulative returns, risk metrics, constituent counts) live here.
  `run.py`'s `_MERGED_EXPORTS` maps its bundle keys back onto the original per-artifact parquet
  filenames that `parity.compare`/`parity.show` expect.
- `mktcap_filter_audit` — audit-only. Replays whichever market-cap filter method ran inside
  `process_global_universe` on the five columns that filter reads, and reports per currency-month:
  listings in / dropped / % dropped, the effective per-listing size floor (smallest market cap
  kept), and the method-specific cutoff numbers. The replay is needed because the filter's own
  output cannot reveal the
  *pre*-filter count — the dropped rows are gone — so it re-derives the security-month set and then
  **cross-checks itself** against the real post-filter `global_universe` (`matches_actual` /
  `cross_check_all_match`; expected vacuously true, it's a regression canary for a pandas upgrade
  changing groupby/sort semantics). Nothing downstream reads it; its three parquets are exported
  next to the other diagnostics and appear in `parity.compare` only as an informational
  `(only in new: ...)` line. Gated by `cfg.show_mktcap_filter_audit` (default **True**).
  Its per-currency-month numbers are deliberately **not** a dashboard widget (144+ rows read
  badly there) — read `mktcap_filter_by_month.parquet` for the exact figures.

**Two market-cap filter methods, picked by `cfg.market_cap_filter`** (in
`process_global_universe`; the audit node replays whichever ran):
- `"percent_total_mcap"` (**default**, the frozen behaviour) — per currency-**month**, keep the
  largest listings covering `mktcap_covered_if_filter_by_cum_market_cap` (0.95) of the cell's total
  cap. That percentage is a share of aggregate **value**, and because cap is concentrated it
  discards ~65% of listings.
- `"percent_stocks"` — per currency-**year**, decided on each listing's last cap in Y−1: drop iff
  both among the smallest `percentage_stocks_removed_if_percent_stocks_true` (0.01) of listings **by
  count** *and* below `floor_if_percent_stocks_true` ($100mn). A share of **count**, so ~67× gentler
  than it looks next to the other knob. Config: `base_pct_stocks`. Two consequences: a listing with
  no Y−1 cap is dropped, so **the whole first data year (2013) disappears**; and the absolute floor
  makes this **single-currency only** (it raises otherwise — a JPY cap against a USD floor is out by
  ~150×).

Gotchas when touching this: **every** call site of `process_global_universe` passes **positionally**
(4× in `04_merge_esg_provider.py` — now keyword, via `_common.mktcap_filter_kwargs` — plus
`plot_coverage.py`, `scripts/download_us_gics.py`, and both notebooks), so new parameters must be
appended with defaults or arguments silently mis-bind. `mktcap_covered` was renamed to
`mktcap_covered_if_filter_by_cum_market_cap` in the pipeline, but **not** in
`plot_coverage.py` (the notebooks pass it as a keyword) or `output_paths.py`'s `RUN_PARAM_NAMES`
(resolved against the notebook's namespace) — those two keep the old name deliberately. `build_cfg`
now **raises on unknown override keys**, which is what turns the rename from a silent dead-key into
an error.

**Dashboard section order ≠ DAG order.** The framework orders both the Taipy page and
`to_markdown()` by `Pipeline.topological_order()`, and no edge arrangement can push an
audit-only node to the bottom (it depends on one early node, so Kahn's algorithm makes it ready
long before the analysis nodes). `New_Pipeline/dashboard_viz.py` therefore defines
`OrderedDashboard`, which overrides `_ordered_nodes()` to render `_DEFERRED_SECTIONS`
(currently just `mktcap_filter_audit`) last — used by both `dashboard.py` and `run.py`'s
`dashboard.md` snapshot. Add a node name there rather than faking an edge, which would lie in
the pipeline graph the dashboard itself draws.

**Provenance**: every run archives to `runs/<UTC-timestamp>_<config>/` (never overwritten;
`manifest.json` + human-readable `manifest.md` recording which Process/contract-version ran each
node and the content-hash of every input/output) and overwrites the "latest" snapshot at
`parity/artifacts/new/<config>/` that `parity.compare`/`parity.show` read. `.leonardo_nodes_store/`,
`runs/`, and `parity/artifacts/` are all gitignored — generated, not source.

**Descriptive-stats audits**: several nodes (`process_lc`, `prepare_panel`) also compute and
bundle `sample_descriptives`/`firms_and_initiatives` frames purely for dashboard widgets
(`BundleTableViz`/`BundleDualAxisViz` in `New_Pipeline/dashboard_viz.py`) — additive, audit-only,
never read by downstream numeric nodes. Adding more of these does not risk parity, but multiple
unkeyed `BundleTableViz` instances on one Contract *will* collide (the default key always
collapses to the same literal string) — always pass an explicit `key=`.

**The sweep runner** (`New_Pipeline/sweep.py` + `sweep_report.py` + `sweep_parameters.py`) is a
pure *consumer* of the pipeline — it adds no node, edits nothing existing, and cannot affect
parity. Three things to know before touching it:
- **`sweep_output/results.jsonl` is the database.** It is append-only, fsync'd after every
  experiment; `results.pdf` and `results.csv` are *derived views* rebuilt from it in full (atomic
  `os.replace`). The CSV is rebuilt rather than appended precisely because the column set grows —
  a later `action_characterization` introduces `alpha__<portfolio>` columns earlier rows lack.
  `--resume` (default) skips names already in the ledger, so a killed sweep resumes cleanly.
- **Every page panel is an existing dashboard widget payload**, read back out of the run's
  manifest via `manifest.record_for(node).audit_stats[key]` — the seven `(slug, node, key, title)`
  entries in `sweep_report.SECTIONS`. Nothing is recomputed. If a Contract's `key=` changes, the
  matching panel silently goes blank ("no data"); grep `SECTIONS` when renaming a VizSpec key.
- **The sweep passes `--out sweep_output/artifacts/<name>` deliberately.** Without it `run.run`
  would overwrite `parity/artifacts/new/<name>/`, and a 100-config sweep would bury the parity
  area that `parity.compare` reads.

## Gotchas specific to this repo

- **pandas chained-assignment `FutureWarning`s are a known pandas 2.2 false positive** here, not
  real bugs: they fire on ordinary `df[col] = df[col].some_method()` patterns purely because of a
  refcount heuristic inside function scopes (verified — neither `.copy()` nor Copy-on-Write mode
  changes the warning count). They're globally filtered in `New_Pipeline/_common.py`. Don't chase
  them with `.copy()` insertions; if you hit a *new* one, check whether it's this same pattern
  before assuming a real bug.
- **`add_materiality` (optional SASB merge in `process_lc`) changes the sample** — it inner-joins
  on exact `(gvkey, rfyear)`, so it must default `False` and stay off for `base_none` parity. The
  SASB workbook (`functions/data_functions/process_materiality.py`, from a sibling `../Data/`
  checkout) only covers `rfyear <= 2022` and was built from a different Golden-data vintage than
  `New_Pipeline` loads, so coverage gaps are a real, expected data-provenance mismatch, not a merge
  bug — confirm against `functions/data_functions/process_materiality.py`'s own source comments
  before assuming a coverage number is wrong.
- **The point-in-time accounting lag** (`last_year` in `functions/data_functions/process_data.py`:
  Jan–Jun → fiscal year Y−2, Jul–Dec → Y−1) means the final panel's last reachable `rfyear` is
  always one year behind the max `rfyear` present in `lc` at that point — this is why, e.g.,
  `base_none`'s raw LC reaches 2024 but the final sorted panel stops at 2023.
- **Two `runs/`/`parity/artifacts/` writers can collide.** If `pipeline/` is ever repopulated (or
  another package runs alongside `New_Pipeline/`), both write to the same `parity/artifacts/new/<config>/`
  path since it's relative to repo root, not the package. Use `--out` on `New_Pipeline.run` to keep
  snapshots apart if this ever matters again.
- **Node/`functions/` diagnostic `print()`s never reach the console.** `New_Pipeline/run.py`
  captures all stdout during `run_experiment(...)` (the single call site — `dashboard.py` reuses
  `run.run()`, so this covers it too) and writes it to `runs/<ts>_<config>/debug_prints.log`
  instead, even on failure. If you need to see what a node printed (shapes, `value_counts`, the
  FF/returns date-alignment table), read that file rather than expecting it on screen.
