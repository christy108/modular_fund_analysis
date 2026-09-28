# Audit prompt — SASB materiality → alpha pipeline

Paste this to a fresh agent. It is written to be self-contained: it names the repos, the
entry points, the invariants, and the specific things already known to be wrong, so the
agent spends its budget on *finding new problems* rather than re-deriving the map.

---

## Your task

You are auditing a quantitative finance pipeline, spread across two repositories, that turns corporate
sustainability initiatives into long-short equity portfolios and reports factor alphas.
The result is intended for academic publication. Your job is to find **defects that would
change a number in the paper** — not style, not naming, not test coverage for its own sake.

**Scope.** Audit `Matchings` and `modular_fund_analysis` only. **`leonardo-nodes` is NOT a
target** — it is the instrumentation and dashboard layer (Contract, Process, RunRecord,
Manifest, VizSpec), it owns no numerics, and it is treated as trusted infrastructure here.
Read it only when you need to understand how a node is wired or where a number is recorded,
and raise it only in one case: when the pipeline computes something the framework does *not*
record, so a result cannot be traced back to its inputs. Framework bugs, framework test
coverage and framework design are out of scope.

Report findings ranked by *how much they could move a reported alpha, t-statistic, or
sample size*, and for each one give a concrete failure scenario: specific inputs or data
conditions → specific wrong output. If you cannot construct that scenario, say the finding
is speculative and rank it lower. Do not pad the list. A short list of confirmed,
reproducible defects is worth more than thirty maybes.

Work in a read-only manner unless explicitly asked to fix something. Use
`.venv/bin/python` (the system `python3` has no polars).

## The repositories

All under `~/Documents/GitHub/`:

| Repo | Role | Entry point |
|---|---|---|
| `Matchings` | Builds the SASB↔MSCI↔SDG↔GICS crosswalk and classifies every corporate initiative as material / immaterial / unmapped per (firm, year, SDG, behaviour bucket) | `Main/Main.py` (1,676 lines, top-to-bottom script) |
| `leonardo-nodes` | **Out of scope.** Instrumentation + dashboard layer that wraps the nodes and records what ran. Owns no numerics | `leonardo_nodes/`; spec in `docs/00`–`11` — reference only |
| `modular_fund_analysis` | The alpha study: builds the panel, sorts portfolios, runs FF3/FF5 regressions | `New_Pipeline/run.py`, 13 nodes in `New_Pipeline/nodes/`, numerics in `functions/` |

### The data chain

```
GOLDEN LC dataset (firm-year x "{action} - SDG {n}" initiative counts)
  → Matchings/Main/Main.py
  → Matched_SASB_GOLDEN_long_matchings_<GOLDEN_VERSION>_FirmYear_17SDGs_matching_v<VERSION>.csv
  → MANUALLY COPIED to ~/Documents/GitHub/Data/Materiality/
  → functions/data_functions/process_materiality.py  (INNER join on gvkey + rfyear)
  → New_Pipeline/nodes/01..13
  → alphas
```

Currently delivered file: `Matched_SASB_GOLDEN_long_matchings_v_2A1_FirmYear_17SDGs_matching_v2.csv`
— 72,412 firm-years, rfyear 1990–2030, 442 columns.

## Read these first, in this order

1. `modular_fund_analysis/New_Pipeline/README.md` — the DAG and the six registered experiments
2. `Matchings/Main/Main.py` sections 1–10 — the whole matching logic is in one file
3. `modular_fund_analysis/functions/data_functions/process_data.py` — FX conversion, market-cap screens
4. `modular_fund_analysis/functions/portfolio_strategy_design/univariate_sorting_preprocess.py` — panel construction, standardisation, factor alignment
5. `modular_fund_analysis/functions/portfolio_strategy_design/Univariate_Portfolio.py` — portfolio formation, t → t+1 convention
6. `modular_fund_analysis/functions/portfolio_metrics/fama_french.py` — the alpha regressions
7. `modular_fund_analysis/New_Pipeline/nodes/07_build_analyse_portfolios.py` — the node that assembles all of the above

## Already known — do not re-report these, but DO check whether they cause damage downstream

These were found in a prior pass. Confirm or refute the *consequence*, don't re-find the
cause.

1. **`Matchings/Main/Main.py` §5 "TOTAL CHECK" regex is dead.** It matches
   `(material|immaterial|unmapped)__(advocacy|upskilling|adaptation|innovation)$` but the
   bucket is named `advocacy_new_def`. The reconciliation between raw and aggregated
   initiative totals has therefore never passed. Question for you: *is the underlying
   conservation actually true?* Write the check properly and run it.
2. **`functions/portfolio_strategy_design/univariate_sorting_preprocess.py:119`
   `apply_optional_geo_filter` has its entire body commented out and returns
   `gu[~foreign_listed]` where both names are undefined** — guaranteed `NameError`. It is
   called at line 373 when `apply_geo_filter=True`. Question: does any config or sweep
   entry set that flag, and if so has that configuration ever produced a result that is
   being cited?
3. **`tests/test_parity.py` imports `pipeline.boundary` / `pipeline.registry`; the package
   is `New_Pipeline`.** Two tests die with `ModuleNotFoundError`, and four parity tests
   fail against a stale oracle. 6 failed / 28 passed / 2 skipped. Question: which of the
   four parity failures are the known Compustat-vintage drift, and which are real
   regressions? See `scripts/check_secstat_parity.py` — the overlap check is the
   substitute oracle.
4. **`univariate_sorting_preprocess.py` ~line 349 contains a bare `6` statement.** No-op;
   just evidence of an accidental edit. Look for sibling accidents in the same file.

## What to examine, by area

### A. Theory and research design — highest value

- **Look-ahead in the materiality vintage.** `Main.py` `vintage_for(year, years)` returns
  the latest vintage ≤ year, **else the earliest vintage**. Establish `MATERIALITY_YEARS`
  empirically from
  `Matchings/data/input/SASB_Materiality/Long_Format/SASB_Materiality_long_format_time.xlsx`.
  For every firm-year earlier than the first vintage, the classification uses a materiality
  map published *after* the fact. Quantify: what fraction of firm-years, and what fraction
  of *initiatives*, are classified with a forward-looking map? Does the alpha survive
  restricting to the non-forward-looking subsample?
- **Was the SASB map knowable at portfolio formation?** Even a vintage ≤ rfyear is only
  point-in-time if SASB published it by then. Find the publication dates. The signal also
  needs to be knowable at the *formation month*, which
  `process_data.py` handles with `last_year` = Y−2 for Jan–Jun, Y−1 for Jul–Dec. Check that
  the materiality vintage inherits the same lag.
- **Multiple testing / specification search.** `New_Pipeline/sweep_parameters_US.py` `GRID`
  alone is 2 × 3 × 2 × 2 × 2 = 48 specifications, and `sweep_output/` holds 20+ completed
  sweeps. Count the total number of distinct (signal design × weighting × quantile count ×
  screen × region) alphas that have been computed. Then assess: is any reported t-statistic
  corrected for that search? Is there a pre-registered primary specification? This is the
  single largest threat to the paper's validity.
- **Reporting-lag coverage collapse.** Firm-years by rfyear: 2022 → 9,725, 2023 → 7,545,
  2024 → 5,859, 2025 → 837. Initiative counts follow. Any count-based signal is mechanically
  depressed in recent years and the *sample* changes composition. Determine whether the
  study's end date truncates before this, and whether the share-based signals (material /
  (material+immaterial)) are genuinely immune or merely less exposed.
- **Selection on initiative disclosure.** The materiality merge into LC is an INNER join
  (`process_materiality.merge_materiality_into_lc`). Zero of the 72,412 firm-years have zero
  initiatives. Establish whether GOLDEN contains only firms that disclosed at least one
  initiative. If so, the entire study is conditioned on disclosure, which correlates with
  size, region and sector — describe the resulting bias in the long-short spread.
- **Standard errors.** `fama_french.py:72` uses `cov_type='HC1'` — heteroskedasticity-robust
  but **not** autocorrelation-robust. Monthly long-short returns driven by an annually
  updating signal are serially correlated. Re-estimate the headline alphas with
  Newey-West (`cov_type='HAC', cov_kwds={'maxlags': …}`) and report how much the
  t-statistics move. State the lag choice and why.
- **Non-stationarity of raw counts.** Initiatives per year go from 75 (1990) to 284,031
  (2022). Check that every signal is a *share* or a within-year-industry z-score and that
  no raw level ever enters a cross-sectional comparison spanning years.

### B. Currency and FX — `functions/data_functions/process_data.py`

- **Direction of conversion.** Both `process_row_universe` and `process_japan_universe` do
  `mktcap = mktcap_lcu / rate`. Establish from the FX source (`functions/data_functions/get_data.py`,
  the `fx_rates` query) whether `rate` is units-of-LCU-per-USD or the reciprocal. An inverted
  rate is invisible in a single-currency run and catastrophic in a pooled one.
- **Silent FX gaps.** The merge is `how="left"` on `(date, curcdd)`. A missing rate yields
  `NaN` mktcap/tri, which `process_global_universe` then drops via
  `global_universe["mktcap"].notna()`. Count the rows lost this way per currency per year.
  There is no assertion on merge coverage — add one mentally and report the number.
- **Row multiplication.** If `fx_rates` has duplicate `(date, curcdd)` rows the left merge
  multiplies the universe. Verify uniqueness of the FX key.
- **The multi-currency pooling guard.** `process_global_universe` raises if
  `len(currencies) > 1 and not convert_to_USD`. But `convert_to_USD` is a *claim* passed by
  the caller (`New_Pipeline/_common.py: mktcap_filter_kwargs`), not a verified property of
  the frame. Trace every call site and confirm the flag can never be `True` while the frame
  is unconverted.
- **`convert_factors_to_jpy`.** Check the algebra: market factor is
  `(1 + mktrf + rf) * FX_t/FX_{t-1} - 1 - rf_jp`; zero-cost factors scale by the ratio only.
  Confirm the FX ratio direction matches the `mktcap_lcu / rate` convention. Then check
  `jpy.resample('ME').last()` — if a month has no FX observation, `shift(1)` compares
  non-adjacent months and the ratio is a multi-month return. Both merges are `how='left'`
  with no coverage assertion, so a gap becomes a `NaN` factor month that is later dropped
  listwise by the regression.
- **`esg` rescaling in `process_global_universe`.** `esg_choice == "none"` still executes
  `global_universe["esg"] /= 100`. Establish what `esg` is on that branch and whether the
  division is correct or a leftover.

### C. The matching layer — `Matchings/Main/Main.py`

- **Behaviour bucket coverage.** `BEHAVIOUR_BUCKETS` (4-signal) and
  `BEHAVIOUR_BUCKETS_3_SIGNALS` (3-signal, requires 3D data) are hardcoded lists matched by
  `action.strip().lower()`. Any GOLDEN action string outside the lookup is silently skipped
  (a `[WARN]` line, not an exception). Enumerate the actual distinct action strings in the
  GOLDEN file and diff against the union of both bucket dicts. Report every unbucketed
  action and the initiative volume it represents.
- **The two taxonomies do not span the same initiatives.** Measured on the delivered file:
  the 4-signal buckets sum to `material__total` exactly (1,584,943), but the 3-signal
  buckets sum to 1,438,951 — 9.2% short, because `association` and `pricing` belong to no
  3-signal bucket. Confirm every signal design that mixes the two families uses a consistent
  denominator, in `functions/signal_design/signal_definitions_materiality.py`.
- **`all_gics_in_db` is a union across vintages.** A GICS key present in *one* vintage is
  treated as "mapped" in *all* years; `table.get(gics, set())` then returns an empty set and
  the initiative is classified **immaterial** rather than **unmapped**. That is a silent
  one-directional misclassification that biases the material/immaterial ratio. Quantify it.
- **`parse_sdg_number`** uses `re.search(r"\b(\d{1,2})\b", label)` — the first 1–2 digit
  number anywhere in the label. Dump the distinct `Issue 2` labels and confirm none has a
  leading number that is not the SDG.
- **Merging on nullable metadata.** `full_grid.merge(company_year_sdg_bucket, on=id_cols + ["sdg"], how="left")`
  joins on *all* identifier columns — `predicted_company_name`, `conml`, `loc`,
  `MacroRegion`, `GICS_level_4_name` — not just `(gvkey, rfyear, sdg)`. Both sides derive
  metadata from the same `groupby().first()`, so it should match, but any dtype or NaN
  asymmetry silently zero-fills every metric column for the affected firm-years, and every
  QA guard in the file checks only *row counts*, which would still pass. Construct the
  failure case and check whether it is live.
- **Conservation.** There is no end-to-end assertion that
  `Σ(material + immaterial + unmapped)` over the output equals `Σ` of the bucketed
  `"{action} - SDG {n}"` columns in GOLDEN. Write it and run it.
- **`rfyear` sanity.** The delivered file contains one firm-year with `rfyear = 2030` and 179
  with `rfyear < 2000`. Trace where a 2030 fiscal year comes from and whether it reaches the
  panel.
- **`YEAR_MIN = 2000`** silently converts every pre-2000 initiative to `unmapped`. Confirm
  the study window starts after that.

### D. Panel construction — `univariate_sorting_preprocess.py`, `functions.py`

- **gvkey key formats.** The codebase uses at least three: `astype(float).astype(str)` →
  `"1004.0"`; `astype(float).astype(int).astype(str)` → `"1004"`; `astype(str).str.zfill(6)`
  → `"001004"`. Trace every merge and confirm both sides are in the same format at the point
  of the join. A format mismatch produces a silent empty or partial join, not an error.
- **`standardize_pivot`** (`functions/functions.py:113`) divides by `group_stdev` with no
  zero/NaN guard. A singleton or constant `(year, currency, industry)` cell yields `inf` or
  `NaN`. The `min_group_size` guard exists only on the ESG path
  (`prepare_esg_universe_sorting_inputs`), not the LC path. Count degenerate cells in a real
  run.
- **Survivorship in the normalisation.** The z-score cross-section is the *surviving* panel.
  Confirm delisted firms are present in the formation-date cross-section.
- **Delisting returns.** `compute_monthly_returns_long` computes `tri.pct_change()` masked
  to ≤36-day gaps. There is no delisting-return handling. A firm that goes to zero simply
  stops producing returns. Assess the direction of the bias on the long and short legs
  separately — this matters most for the short leg.
- **`to_monthly_last_trading_date`** stamps every issue with the *panel-wide* last trading
  date of the month, then takes `.last()` per issue-month. A stock that stopped trading
  mid-month carries a stale price at the month-end timestamp. Quantify how often.
- **Positional factor alignment.** `fama_french.py:_factor_regressions` concatenates a
  fresh-`RangeIndex` dependent series with `fama_french[factors]` on `axis=1` and relies on
  the caller having passed `reset_index(drop=True)`. There is no assertion. Find every call
  site; any that does not reset the index produces silent misalignment or an all-NaN
  regression.
- **Listwise deletion asymmetry.** `_factor_regressions` drops months where any variable is
  NaN, so a thin bucket's alpha is estimated on an endogenously selected subsample, while
  the cumulative-return path treats the same NaN month as 0%. Two different samples are
  reported side by side. Quantify for the thinnest legs.

### E. Portfolio construction — `Univariate_Portfolio.py`, `cap_weights.py`

- The t → t+1 convention (`current_signal = signal.iloc[i]`, `next_ret = returns.iloc[i+1]`)
  and the formation-row cap weights look correct. **Verify, do not assume.**
- `out.iat[i + 1, j] += val` accumulates into a frame pre-filled with `0.0`. Confirm each
  cell is written exactly once.
- An `InfeasibleCapError` bucket-month becomes `NaN`, which `(1+r).cumprod()` skips —
  booking a fabricated 0% month. The thin-portfolio gate in `07_build_analyse_portfolios.py`
  is supposed to hide those legs. Confirm it catches every case.
- **Transaction costs and turnover are not modelled anywhere.** Compute realised monthly
  turnover for the headline long-short strategy and state the break-even cost.
- Check the quantile cutpoint rule (`univariate_portfolio_sorting`,
  `quantile_interval_bounds`) for tie handling when the signal is a discrete count ratio with
  many ties at 0 and 1 — a mass point at the cutpoint can put most of the universe in one
  bucket. `New_Pipeline/nodes/12_sort_cutpoint_audit.py` exists for this; read its output.

### F. Cross-repo integrity

- The materiality CSV crosses repositories as a **manual file copy** into
  `~/Documents/GitHub/Data/Materiality/`. This is the one input to the study whose content
  hash never reaches a Manifest, so a dashboard can show a number without being able to say
  which materiality file produced it. That gap is in scope (the framework is not). Confirm the file in
  `Data/Materiality/` is byte-identical to the one in `Matchings/data/output/` and that the
  `GOLDEN_VERSION` / `VERSION` tokens in the filename actually correspond to the
  `ACCEPTED_MATCH_LEVELS`, `FRAMEWORK` and `MSCI_THRESHOLD` used to produce it. Nothing
  records those three settings in the output.
- `Matchings/Main/Main.py` hardcodes `USER = "cbruce1"` and absolute `/Users/...` paths.
  Assess reproducibility.
- `process_materiality.MATERIALITY_COLUMNS` requires all 24 `{state}__{bucket}` columns to
  exist. A Matchings run without 3D data produces a narrower file. Confirm the failure is
  loud (KeyError) and not a silent NaN column.

## Output format

For each finding:

```
[P1|P2|P3] <one-line claim>
  File:        path:line
  Mechanism:   why the code does the wrong thing
  Scenario:    specific data condition → specific wrong number
  Blast radius: which reported results change, and roughly by how much
  Confirmed:   how you verified it (command + output), or "speculative"
```

P1 = could change a headline alpha, t-stat or sample size.
P2 = changes a number in a robustness table or an audit artifact.
P3 = latent — wrong only under a configuration not currently used.

Finish with the five checks you would add to `tests/` to stop each P1 from recurring.
