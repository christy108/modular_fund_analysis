# fund_analysis — Method Prerequisites & Assumptions

Every precondition the pipeline silently (or explicitly) assumes, grouped by stage.
Each entry: **the assumption → what breaks if violated → where it lives**.
**⚠️ UNGUARDED** = nothing in the code raises or warns if the assumption is violated; the result is silently wrong or silently empty. Guarded items say how they fail loudly.

---

## 1. Fama-French factor regressions (most important)

| # | Prerequisite | If violated | Where | Guarded? |
|---|---|---|---|---|
| FF1 | **Factors and portfolio returns in the SAME currency/numeraire.** Japan+JPY runs must convert USD Ken-French factors via `convert_factors_to_jpy`; US/NA use USD natively and returns are not converted. | Alpha absorbs the FX drift between numeraire mismatch → biased alpha and betas. | `convert_factors_to_jpy` (`process_data.py:197`); gate in Main.ipynb cell 27 (`region_analysis=="Japan" and fama_factors_currency=="JPY"`) | ⚠️ UNGUARDED — no assertion compares currencies; correctness relies on the cell-3 region derivation being run after any parameter injection |
| FF2 | **Date alignment: factor months must equal return months, row for row.** Alignment is positional (`ff.index = global_returns.index`), so equal length AND same calendar months are required. | Returns regressed on the wrong month's factors — plausible-looking but meaningless output. | LC path: `prepare_univariate_sorting_inputs` prints the month-by-month comparison and **raises ValueError** on mismatch (`univariate_sorting_preprocess.py` ~l.317). ESG path: month-intersection then positional check | Guarded (both paths raise) |
| FF3 | **Factors arrive in PERCENT and are divided by 100 exactly once** (`get_famafrench_factors` line ~752: `.div(100)`). Regressions then multiply everything ×100 (`100 * pd.concat(...)`) so alphas print in %/month. | A pre-scaled (already-decimal) factor file gets ÷100 twice → betas ~100× off; a percent file skipped → ×100 off. | `get_data.py:752`, `fama_french.py:33` | ⚠️ UNGUARDED — no magnitude sanity check on loaded factors |
| FF4 | **Dependent series are EXCESS returns** (`excrt`). `signal_quantiles` are made excess before the FF cells; spreads are High−Low so rf cancels. | Alpha absorbs the risk-free rate → overstated intercepts. | Notebook cell ~41 (rf subtraction), spread construction cell 47 | ⚠️ UNGUARDED — the regression cannot tell excess from total returns |
| FF5 | **Regional factor CSVs must exist on disk** (`data/FAMA/<Region>_{3,5}_Factors.csv`); only the *Developed* set can be auto-downloaded. | `FileNotFoundError` at load; a sweep pinned to `ff_factors_number=5` needs the 5-factor file for that region. | `get_famafrench_factors` (`get_data.py:682`) | Guarded (hard error) but only at run time |
| FF6 | **Enough observations vs regressors** (FF5 = 6 params; first return row is NaN by construction). Rows with any NaN are dropped before OLS. | Short windows (late `start_year` + tight filters) can leave an empty/near-empty regression; the code `continue`s and leaves the column as **NaN** | `fama_french.py:42-45` | ⚠️ semi-guarded — empty → silent NaN column, no warning |
| FF7 | **HC1 (White) standard errors, no autocorrelation correction.** Assumes serially uncorrelated residuals; monthly overlapping effects are not Newey-West adjusted. | Understated SEs / overstated significance if residuals autocorrelate. | `fama_french.py:51` (`cov_type='HC1'`) | Design choice — document, don't rely on p-values being HAC-robust |


## 2. Standardization / industry-neutral normalization

| # | Prerequisite | If violated | Where | Guarded? |
|---|---|---|---|---|
| S1 | **Each `(rfyear/last_year, curcdd, Industry)` group needs ≥ 2 stocks.** With exactly 1 stock, `std` (ddof=1) is **NaN** → the value becomes NaN (silently dropped later). | Sample silently shrinks; a signal can vanish for thin industries/years. | `standardize_pivot` (`functions.py:65`, `transform('std')`) | ⚠️ UNGUARDED on the LC path; the **ESG full-universe path enforces `min_group_size`** (default 5) — an asymmetry to be aware of |
| S2 | **Within a group, values must not all be identical.** Identical values (n≥2) → std = 0 → division → **±inf**. | Inf values propagate into sorting; the notebook's inf-check cell (cell 33) exists to detect and drop such columns. | `functions.py` standardize; Main.ipynb cell 33 | Semi-guarded (detected + dropped post-hoc, with a print) |
| S3 | **`Industry`, `rfyear`/`last_year`, `curcdd` non-null** for every row entering standardization. | Rows are silently dropped by `dropna(subset=cols_standardization)` before pivoting. | `dropna_std_cols_and_build_pivots` (`univariate_sorting_preprocess.py:151`) | Silent by design (ESG path prints the dropped count; LC path doesn't) |

## 3. Signal construction

| # | Prerequisite | If violated | Where |
|---|---|---|---|
| G1 | **`sum_activities > 0`** (or `n_predicted_initiatives > 0` for `Sum_All_Initiatives`) — signals are ratios. | Division by zero → inf/NaN signals. ⚠️ UNGUARDED at the division itself; the `alpha_bound` trim and filters remove most zero rows incidentally. | cell 16/21, `normalize_category_shares` |
| G2 | **TYPE_SREC and SDG_SREC stakeholder totals must agree** in the golden data. | `process_lc` **raises ValueError** with the diff — a data-integrity gate on the LC file. | `process_lc.py:28-35` (guarded) |
| G3 | **`signal_names` keys must match `signal_quantiles` keys** — names are attached only at label time (`signal_names[col]`). | `KeyError` at the FF-table/plot labeling step. | cells 47/48/50/53/54 (guarded by crash) |


## 4. Portfolio sorting & returns

| # | Prerequisite | If violated | Where |
|---|---|---|---|
| P1 | **Per month: `n_stocks_with_signal ≥ no_simple_quantiles`** (e.g. ≥ 6 stocks for a 6-way split — otherwise some bucket is empty). Stricter in practice: **`n_DISTINCT_signal_values ≥ no_simple_quantiles`**, because buckets are cut at quantile *values*; if many stocks tie on the same value (e.g. lots of zeros), adjacent cut-points collapse and a bucket is empty even with plenty of stocks. | Empty bucket → that month's `p_i` return is NaN (mean of empty set), silently. ⚠️ UNGUARDED — no per-month count or distinct-value check. | `univariate_portfolio_sorting` (`functions.py:6`) |
| P2 | **Form on month *t*'s signal → earn month *t+1*'s return** (Jan signal → Feb return). So: needs ≥ 2 months; first return row = NaN (zeroed only for cumulative plots); last month's signal unused. | Breaking it = earning the same month as the signal → **look-ahead bias**, no error raised. | `Univariate_Portfolio.compute_returns` (~l.99: `returns.iloc[i+1]`) |
| P3 | **A selected stock must have a next-month return** — NaN next returns are dropped from the bucket (`reindex().dropna()`), i.e. **no delisting-return handling** (survivorship-friendly). | Bucket mean quietly computed over survivors only. ⚠️ UNGUARDED / known design caveat. | `Univariate_Portfolio.py:118` |
| P4 | **Gap between a stock's consecutive observations must be ≤ 36 days**, else the return **stamped on the LATER month** (computed t−1 → t) is masked NaN — e.g. obs on 31 Jan then 31 Mar: the *March* return (really a 2-month return) is nulled. Prevents multi-month returns posing as one-month returns. | Long gaps (halts, staleness) silently become NaNs — correct behaviour, but the sample shrinks. | `compute_monthly_returns_long` (`tr.where(date_diff ≤ 36)`) |


## 5. Merges, identifiers, timing

| # | Prerequisite | If violated | Where |
|---|---|---|---|
| M1 | **gvkey must be normalized to a zero-filled 6-char string on BOTH sides of every merge** — the repo carries three encodings ("10275", "10275.0", "010275"). | Silent merge misses → NaN ESG/GICS/accounting, shrunken sample, **no error**. ⚠️ UNGUARDED — this is the most dangerous silent failure in the repo. | zfill calls scattered: cell 25 end, `get_accounting_data`, `get_gics_by_gvkey`, `intersect_gvkeys_and_filter`, `_norm_gvkey` |
| M2 | **cusip/isin read as strings** (leading zeros, check characters). | Numeric coercion breaks ESG identifier matches silently. | `dtype={'cusip': str, 'isin': str}` in ESG loaders (guarded by dtype args) |
| M3 | **One row per (gvkey, iid, month)** after `to_monthly_last_trading_date`; the wide pivot `pivot(index=date, columns=gvkey_iid)` **raises** on duplicates. | Duplicate rows → `ValueError: Index contains duplicate entries`. | `dropna_std_cols_and_build_pivots` (guarded by pandas) |
| M4 | **`last_year` must reference reports that are actually published by the trading month** (US/ROW: fixed June split; Japan: `japan_year_adjustment_split_month`). Too-early a split month = look-ahead bias; too late = stale data. | Biased alphas, not a crash. ⚠️ UNGUARDED — economic assumption, verify against filing calendar (JP annual reports file ~June for March FYE). | `process_data.py:5/38/75` |
| M5 | **ESG scale must match its rescale branch** (LSEG 0–1 as-is, S&P ÷100, MSCI ÷10). A new/changed source file must be checked here first. | Scores off by 10–100× feed the sort; ranks survive but any raw-value analysis breaks. ⚠️ UNGUARDED — no range assertion. | `process_global_universe` (`process_data.py:127-137`) |
| M6 | **`mktcap` is within one currency per (month, currency) group** — Mixing currencies in one group would rank firms on incomparable numbers. | `process_data.py:158-187` (structurally guarded by groupby key) |
| M7 | **`secstat='A'` keeps only currently-active securities** → survivorship bias baked into the universe; worst for long windows and Low-ESG legs. | Overstated performance of surviving losers. Known design caveat, ⚠️ inherent. | universe SQL (`get_data.py:51/112/171`) |

## 6. Sweep harness

| # | Prerequisite | If violated | Where |
|---|---|---|---|
| W1 | **`SWEEP_TAG` unique per script** → separate `output/Sweeps/SWEEP_<tag>/` folders and run_ids. | Concurrent sweeps overwrite each other's pickles/CSVs. | `sweep_ff_*.py` header (unguarded by code; enforced by convention)|
| W2 | **`Main.ipynb` must not be edited/saved while sweeps run** — every combo re-reads it from disk. | Later combos silently execute a different notebook than earlier ones. ⚠️ UNGUARDED. | papermill `execute_notebook(NB_IN, ...)` |
| W3 | **`end_year − start_year ≥ min_available_fyears`** — the only combo-validity rule enforced. | Combo silently skipped by `is_valid_combo`. | `sweep_ff_*.py::is_valid_combo` (guarded) |

## 7. Performance metrics (interpretation caveats)

- **Sharpe is computed on `portfolio_returns` with rf added back** (total, not excess, for the long legs) → long-leg Sharpe overstated; spreads unaffected (rf cancels). `Strategy_Perfomance.py` ⚠️ known caveat.
- **No return winsorization by default** — checked empirically (1% winsorization moved alphas ≤0.05 %/mo, no significance flips), but single extreme TRI observations (e.g. +136% months) exist in the raw data.
- **Correlation/regression p-values are pooled OLS** (no within-month clustering) → significance reads optimistic. `signal_correlation.py`.

---

### The short list to check before trusting any new run
1. Factors and returns in the same currency (FF1) — and month-aligned (FF2, will raise).
2. gvkey zfill-6 on both sides of any new merge (M1).
3. Any new/updated ESG file matches its rescale branch (M5).
4. Standardization groups aren't degenerate — watch the inf-check cell output and the ESG path's drop counts (S1/S2).
5. If sweeping: parameters tag intact, region cell post-injection, notebook untouched while running (W1/W2/W4).
