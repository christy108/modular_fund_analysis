# Red-flag register — SASB materiality → alpha pipeline

Compiled 2026-09-25 from a read-through of `Matchings` and `modular_fund_analysis`.
Ordered by **how much a defect could move a reported number**, not by how hard it is to fix.

`leonardo-nodes` is **not audited here** — it owns no numerics; it wraps the nodes, records
what ran, and drives the dashboards. It appears in this register only where the pipeline
computes something the framework does not surface. See *Stage 3b* below for the audits worth
adding to it.

Status key: **CONFIRMED** = verified by running code or reading the delivered data.
**LIKELY** = the mechanism is present in the code; the consequence is not yet measured.
**LATENT** = wrong only under a configuration that may not currently be used.

---

## P0 — the safety net is down

### 0.1 The parity oracle is red. CONFIRMED

`.venv/bin/python -m pytest tests/ -q` → **6 failed, 28 passed, 2 skipped**.

Two of those failures are trivial and should be fixed today:

```
tests/test_parity.py::test_boundary_roundtrip             ModuleNotFoundError: pipeline.boundary
tests/test_parity.py::test_pipeline_validates_and_registers  ModuleNotFoundError: pipeline.registry
```

The package was renamed `pipeline` → `New_Pipeline`; the test file was not updated. The
assertion `len(register_processes()) == 13  # 12 nodes` is also stale — there are 13 nodes
now. These two tests are the *only* structural guard on the DAG, and they have been dead.

The other four (`base_none`, `esg_refinitiv`, `esg_msci`, `esg_full_universe`) fail against
a notebook oracle that drifted when Compustat data was re-downloaded. Symptoms:
`holdings_over_time` shape `(5629, 4)` → `(5531, 4)`; one constituent count moving 10 → 9 in
2019-11. That is consistent with universe drift, *not* proof of it. Until the substitute
oracle (`scripts/check_secstat_parity.py`, the secstat overlap check) is wired into `tests/`
and green, **every refactor to `functions/` is unguarded**.

**Do first.** Fix the two import errors (5 minutes), then promote the secstat overlap check
to a real test. Everything below is easier to investigate with a working net.

---

## P1 — could change a headline alpha, t-statistic, or sample size

### 1.1 Specification search is unbounded and uncorrected. CONFIRMED (scale), open (treatment)

`New_Pipeline/sweep_parameters_US.py` `GRID` is

```
action_characterization  x2   (Planet, Narrow_Planet)
materiality_planet_action x3  (advocacy_old_def, preparation, transformation)
portfolio_weighting      x2   (mktcap, equal)
no_simple_quantiles      x2   (3, 5)
mktcap_covered           x2   (0.95, 0.99)
= 48 specifications
```

…plus `EXPLICIT`, plus an EU twin, plus PP_US/PP_EU, and `sweep_output/` already holds 20+
completed sweeps (`us_health_sdg_pre_post_2020`, `sdg_min_initiatives_x_quantiles`,
`europe_materiality_12_designs`, …). Order of magnitude: several hundred to low thousands of
alphas computed on the same underlying panel.

With ~500 independent-ish tests, the largest |t| under the null is ≈ 3.5 by construction. A
t of 2.5 on a hand-picked design is **not evidence of anything**. Nothing in the repo applies
a multiple-testing correction, and there is no pre-registered primary specification.

This is the single largest threat to the study. It is a research-design problem, not a code
bug, and no test will catch it.

**Fix:** designate one primary specification in writing, before looking at its result. Report
everything else as robustness with a Harvey-Liu-Zhu style haircut or an explicit BH/Bonferroni
adjustment over the actual number of designs tried. Keep the sweep — just stop treating its
maximum as a discovery.

### 1.2 Standard errors are not autocorrelation-robust. CONFIRMED

`functions/portfolio_metrics/fama_french.py:72`

```python
fitted_model = mod.fit(cov_type='HC1')
```

`HC1` corrects for heteroskedasticity only. The dependent variable is a monthly long-short
return driven by a signal that updates **annually** (`rfyear` → `last_year`), so consecutive
months share a formation signal and the residuals are serially correlated by construction.
HC1 understates the alpha standard error, inflating every reported t-statistic.

**Fix:** `cov_type='HAC', cov_kwds={'maxlags': 6, 'use_correction': True}`. Report both, and
state the lag choice. Expect t-stats to fall; how far is the empirical question that matters.

### 1.3 Look-ahead in the materiality vintage. LIKELY — quantify urgently

`Matchings/Main/Main.py`:

```python
def vintage_for(year, years):
    """latest vintage <= year (ffill), else the earliest vintage (bfill)."""
    prior = [y for y in years if y <= year]
    return max(prior) if prior else min(years)
```

The `else min(years)` branch is a **backfill**: any firm-year earlier than the first SASB
materiality vintage is classified using a map published later. Every such classification uses
information unavailable at portfolio formation.

Two separate questions:

1. How early does `MATERIALITY_YEARS` start? Read it off
   `Matchings/data/input/SASB_Materiality/Long_Format/SASB_Materiality_long_format_time.xlsx`.
   If the first vintage is, say, 2018, then **every firm-year from 2000 to 2017 is
   forward-looking** — which is most of the sample.
2. Even a vintage ≤ rfyear is only point-in-time if SASB *published* it by then. SASB
   standards were provisional until 2018. `vintage_for` assumes a vintage labelled Y was
   knowable in Y.

**Fix:** re-run the headline result on the strictly point-in-time subsample and report both.
If the alpha lives only in the backfilled region, that is the finding.

### 1.4 Reporting-lag coverage collapse in recent years. CONFIRMED

From the delivered `..._v_2A1_..._v2.csv`:

| rfyear | firm-years | initiatives |
|---|---|---|
| 2021 | 7,488 | 221,748 |
| 2022 | 9,725 | 284,031 |
| 2023 | 7,545 | 226,739 |
| 2024 | 5,859 | 175,937 |
| 2025 | 837 | 18,270 |

Coverage peaks in 2022 and collapses by 91% into 2025 — that is scraping lag, not a change in
corporate behaviour. Consequences:

- Any **count**-based signal is mechanically depressed in the tail.
- The **sample composition** changes (late reporters are systematically different: smaller,
  non-US, less resourced IR).
- Share-based signals (`material/(material+immaterial)`) are less exposed but the *universe*
  still changes.

**Fix:** truncate the study at the last year with stable coverage (looks like 2022), or model
the lag explicitly. Plot firm-years by rfyear × region in the paper.

### 1.5 Conditioning on disclosure. CONFIRMED (mechanism), open (magnitude)

`functions/data_functions/process_materiality.py:merge_materiality_into_lc` is an **inner
join** on `(gvkey, rfyear)`. And in the delivered file, **zero of 72,412 firm-years have zero
initiatives across all three states** — meaning GOLDEN contains only firms that disclosed at
least one initiative.

So the entire study universe is "firms that published at least one sustainability initiative
in a given year". Disclosure correlates with size, region, sector and index membership. The
long-short spread is therefore measured inside a selected population, and the selection is
itself time-varying (see 1.4).

**Fix:** state this explicitly as the study population. Ideally show the zero-disclosure firms
as a fourth portfolio, or a Heckman-style correction if the claim is about all listed firms.

### 1.6 FX conversion direction is unverified and its gaps are silent. LIKELY

`functions/data_functions/process_data.py`:

```python
row_universe = pd.merge(row_universe, fx_rates, on=["date", "curcdd"], how="left")
row_universe["mktcap"] = row_universe["mktcap_lcu"] / row_universe["rate"]
```

Three separate hazards in four lines:

1. **Direction.** `/ rate` is correct iff `rate` is *units of local currency per USD*. If the
   FX source returns USD-per-LCU the conversion is inverted. Invisible in a single-currency
   run; catastrophic when pooled. Verify against `functions/data_functions/get_data.py`.
2. **Silent gaps.** `how="left"` — a missing rate yields `NaN` mktcap/tri, which
   `process_global_universe` then quietly drops (`global_universe["mktcap"].notna()`). No
   assertion, no count. A currency whose rates start late loses its early years with no log line.
3. **Row multiplication.** Duplicate `(date, curcdd)` rows in `fx_rates` would multiply the
   universe through a left merge. Uniqueness is never checked.

**Fix:** three assertions before and after the merge — `fx_rates` key is unique, `len` is
unchanged, and the post-merge NaN count is logged per currency per year.

### 1.7 The multi-currency pooling guard trusts a caller-supplied flag. LATENT→LIKELY

`process_global_universe` raises when the universe spans >1 currency and `convert_to_USD` is
falsy. But `convert_to_USD` is a **claim** threaded from `cfg["convert_to_USD"]` via
`New_Pipeline/_common.py: mktcap_filter_kwargs` — not a verified property of the frame. A
config that sets the flag `True` while the universe was never actually converted upstream
passes the guard and pools JPY caps with USD caps (~150× error) inside the market-cap screen.

**Fix:** make the guard structural — check for the presence of the `rate` column, or stamp a
`_numeraire` attribute on the frame at conversion time and assert on that.

### 1.8 No delisting returns. CONFIRMED

`compute_monthly_returns_long` computes `tri.pct_change()` masked to ≤36-day gaps. A firm that
delists simply stops producing returns; there is no −100% (or CRSP-style delisting-return)
month. This biases both legs upward, and asymmetrically: the short leg of a
sustainability-sorted spread plausibly contains more distressed names.

**Fix:** at minimum, measure it — count delistings by leg and year, and report the alpha with
a −30% delisting return imputed as a robustness check.

---

## P2 — changes a number in a robustness table or an audit artifact

### 2.1 The one reconciliation check in Matchings is dead code. CONFIRMED

`Matchings/Main/Main.py` §5 "TOTAL CHECK":

```python
bucket_pattern = (
    r"^(material|immaterial|unmapped)__"
    r"(advocacy|upskilling|adaptation|innovation)$"
)
```

The bucket is named **`advocacy_new_def`**, so `advocacy$` matches nothing. The printed
"Raw total vs Aggregated total vs Difference" has therefore always shown a spurious gap, and
whoever runs this has learned to ignore the only conservation check in the file.

Good news: the underlying conservation **does** hold. Measured on the delivered file, the four
4-signal buckets sum to exactly `material__total` (1,584,943). The check is broken, not the
maths — but it is broken in the direction that trains you to ignore it.

**Fix:** `(advocacy_new_def|upskilling|adaptation|innovation)`, and turn the print into a
`raise`.

### 2.2 `all_gics_in_db` is a union across vintages → silent "immaterial". LIKELY

```python
all_gics_in_db = set().union(*(d.keys() for d in gics_to_material_sdgs_by_year.values()))
...
if gics not in all_gics_in_db:  return "unmapped"
...
return "material" if sdg in table.get(gics, set()) else "immaterial"
```

A GICS key present in *one* vintage passes the `all_gics_in_db` test in *every* year. In a
year where it is absent, `table.get(gics, set())` returns the empty set and the initiative is
labelled **immaterial** rather than **unmapped**. That is a one-directional misclassification
straight into the denominator of every material-share signal.

**Fix:** test membership against `gics_to_material_sdgs_by_year[vintage]`, not the union.

### 2.3 The two behaviour taxonomies do not span the same initiatives. CONFIRMED

Measured on the delivered file:

```
4-signal buckets (adaptation, advocacy_new_def, innovation, upskilling)  = 1,584,943 = material__total  ✓
3-signal buckets (advocacy_old_def, preparation, transformation)         = 1,438,951  (−9.2%)
```

`association` and `pricing` belong to no 3-signal bucket — documented in `Main.py`, and
`{state}__total` deliberately sums only the 4-signal family so the two are not double-counted.
That is all correct. The risk is **downstream**: the US sweep `GRID` sorts on
`advocacy_old_def / preparation / transformation`, so those designs run on 90.8% of
initiatives while the `total`-based designs run on 100%. If any signal mixes families in a
numerator/denominator pair, the share is not on [0,1].

**Fix:** an assertion in `signal_definitions_materiality._signals_from_groups` that numerator
and denominator come from the same family. Check `signal_denominator="Sum_All_Signals"` call
sites.

### 2.4 Matchings joins on nullable metadata columns. LIKELY

```python
company_year_sdg_bucket_17sdgs = full_grid.merge(
    company_year_sdg_bucket, on=id_cols + ["sdg"], how="left",
)
```

`id_cols` includes `predicted_company_name`, `conml`, `loc`, `MacroRegion`,
`GICS_level_4_name` — all nullable. Both sides derive metadata from the same
`groupby().first()` so they *should* be identical, but any dtype or NaN asymmetry silently
fails the join for those firm-years, and the very next block does
`.fillna(0)` on every metric column.

The failure is invisible: **every QA guard in the file checks row counts only**
(`!= 17` rows per company-year, duplicate `(gvkey, rfyear)`, each `total` equalling its 17
SDG parts). An all-zero output passes all of them.

**Fix:** join on `[COMPANY_COL, YEAR_COL, "sdg"]` and re-attach metadata afterwards. Add a
conservation assertion (see 2.1) that would have caught it.

### 2.5 `standardize_pivot` has no zero-variance guard. CONFIRMED

`functions/functions.py:126`

```python
group_stdev = df_merged.groupby(cols_standardization)['value'].transform('std')
df_merged['value'] = (df_merged['value'] - group_mean) / group_stdev
```

A singleton or constant `(year, currency, industry)` cell gives `std = 0` or `NaN` → `inf` or
`NaN` z-scores. The `min_group_size` guard exists **only** on the ESG path
(`prepare_esg_universe_sorting_inputs`), not on the LC path that every materiality experiment
uses. An `inf` z-score lands in the extreme quantile every month.

**Fix:** port the `min_group_size` guard to the LC path, or mask cells with `std == 0` to NaN
and log the count.

### 2.6 Positional factor alignment by convention, not assertion. LIKELY

`fama_french.py:_factor_regressions` builds `dependent_data` on a fresh `RangeIndex` and
concatenates it with `fama_french[factors]` on `axis=1` — relying on every caller having
passed `reset_index(drop=True)`. The docstring says so; nothing enforces it. A caller that
forgets gets either an all-NaN regression (loud) or, worse, a partially-overlapping index
(silent misalignment of returns and factors).

**Fix:** one line — `assert independent_data.index.equals(pd.RangeIndex(len(independent_data)))`.

### 2.7 Listwise deletion vs zero-filling: two samples, one table. CONFIRMED

`_factor_regressions` drops months where any variable is NaN, so a thin bucket's alpha is
estimated on an endogenously selected subsample. Meanwhile `(1+r).cumprod()` **skips** NaN,
booking those same months as a fabricated 0% return in the cumulative table. The alpha and the
cumulative return in the same row of the same table describe different samples.

The thin-portfolio gate in `07_build_analyse_portfolios.py` is meant to hide the worst cases.
Verify it catches every `InfeasibleCapError` month, not just empty buckets.

### 2.8 `apply_optional_geo_filter` will raise `NameError`. CONFIRMED

`functions/portfolio_strategy_design/univariate_sorting_preprocess.py:119`

```python
def apply_optional_geo_filter(global_universe: pd.DataFrame) -> pd.DataFrame:
    """Exclude selected domiciles and foreign-currency listings within macro regions."""
    # gu = global_universe.copy()
    # ... entire body commented out ...
    return gu[~foreign_listed]      # both names undefined
```

Called at line 373 when `apply_geo_filter=True`. Any config setting that flag dies. Harmless
if nothing sets it — but then it is dead code advertising a filter that does not exist, and
`New_Pipeline/nodes/13_geography_audit.py` suggests geography *is* a live concern.

**Fix:** either restore the body or delete the function and the flag.

---

## P3 — hygiene, latent, and reproducibility

| # | Flag | Where | Note |
|---|---|---|---|
| 3.1 | Cross-repo handoff is a manual file copy | `Data/Materiality/` | The one provenance link `leonardo_nodes` exists to make auditable is the only one outside it. Model the CSV as an ingest Node so its content hash lands in the Manifest. |
| 3.2 | Output filename records only `GOLDEN_VERSION` and `VERSION` | `Matchings/Main/Main.py` | `FRAMEWORK`, `ACCEPTED_MATCH_LEVELS`, `MSCI_THRESHOLD`, `YEAR_MIN` are **not** recorded anywhere in the output. Two files with the same name can have different semantics. Write a sidecar JSON. |
| 3.3 | `USER = "cbruce1"` and absolute `/Users/...` paths | `Matchings/Main/Main.py` | Not reproducible on another machine. |
| 3.4 | `rfyear = 2030` in the delivered data | `..._v_2A1_..._v2.csv` | One firm-year, 26 initiatives, an impossible fiscal year that survived every guard. 179 firm-years are pre-2000 and silently become `unmapped` via `YEAR_MIN`. |
| 3.5 | Stray `6` statement | `univariate_sorting_preprocess.py` ~349 | No-op. Evidence of an accidental edit — look for siblings. |
| 3.6 | `esg /= 100` on the `esg_choice == "none"` branch | `process_data.py` | A rescale on the branch that is supposed to use no ESG provider. Verify it is intentional. |
| 3.7 | Three gvkey string formats in one codebase | throughout | `"1004.0"` / `"1004"` / `"001004"`. Every mismatch is a silent partial join. |
| 3.8 | `to_monthly_last_trading_date` stamps panel-wide month-end dates | `univariate_sorting_preprocess.py` | A stock that stopped trading mid-month carries a stale price at the month-end timestamp. |
| 3.9 | No transaction costs or turnover anywhere | — | The monthly rebalance of an annually-updating signal has low but non-zero turnover. State the break-even cost. |
| 3.10 | Unbucketed GOLDEN actions warn, never raise | `Matchings/Main/Main.py` | A renamed action string in a new GOLDEN vintage silently drops its initiatives with one `[WARN]` line. |
| 3.11 | `parse_sdg_number` takes the first 1–2 digit number in the label | `Matchings/Main/Main.py` | Fine for `"7 - Affordable..."`. Verify no `Issue 2` label has a leading number that is not the SDG. |
| 3.12 | `leonardo-nodes` ships `.cursor/skills/` only | `leonardo-nodes/.cursor/` | Seven authoring skills invisible to Claude Code. Port to `.claude/skills/`. Tooling only — the framework itself is out of audit scope. |

---

# How to search this pipeline yourself

A strategy, in the order that buys you the most confidence per hour.

## Stage 0 — restore the net (half a day)

You cannot safely investigate anything while the test suite is red, because you cannot tell
your changes from the existing breakage.

1. Fix the two `ModuleNotFoundError`s in `tests/test_parity.py` (`pipeline` → `New_Pipeline`)
   and the stale `== 13` count.
2. Decide what the oracle is now. Bit-parity against `Main.ipynb` is dead — the Compustat
   vintage moved and you cannot get it back. Promote `scripts/check_secstat_parity.py` into
   `tests/` as the replacement and mark the four notebook-parity tests `xfail` with a comment
   saying why, so the suite goes green and *stays* meaningful.
3. Add a `make test` (or a one-line script) so running it is frictionless.

**Rule from here on:** the suite is green before you start and green when you finish, or you
know exactly which test you broke.

## Stage 1 — conservation tests (highest value per line of code)

These are the tests that catch silent data loss, which is the dominant failure mode in this
codebase. They are cheap and they would have caught most of P2.

Write these as a new `tests/test_conservation.py`, each running on a small fixture:

```python
def test_matchings_conserves_initiatives():
    """Σ(material + immaterial + unmapped) over the output == Σ of every bucketed
    "{action} - SDG {n}" column in GOLDEN."""

def test_materiality_merge_loses_no_columns():
    """All 24 {state}__{bucket} columns present, no all-zero column."""

def test_fx_merge_preserves_row_count():
    """len(universe) unchanged by the fx_rates left merge; fx key is unique."""

def test_no_silent_mktcap_loss():
    """Rows dropped by .notna() are logged and below a threshold, per currency per year."""

def test_gvkey_format_at_every_join():
    """Both sides of every merge use the same gvkey format."""
```

The pattern: **assert the invariant, not the value.** Invariants survive a data refresh;
frozen values do not. This is the lesson of the dead parity oracle.

## Stage 2 — golden-path property tests

Build one tiny synthetic fixture — 20 firms, 5 years, 3 SDGs, 2 currencies, hand-computed
expected output — and check into the repo. Then:

| Property | Why it catches a real bug |
|---|---|
| A firm with identical initiative counts in every SDG gets the same z-score regardless of industry | catches standardisation group errors |
| Doubling every count leaves every *share* signal unchanged | catches normalisation-denominator mixing (2.3) |
| Converting the whole universe to a currency and back is the identity | catches FX direction (1.6) |
| A single-currency universe gives the same result with `convert_to_USD` on and off | catches 1.6 and 1.7 together |
| Shifting every return forward one month shifts every alpha's sample, not its value | catches t/t+1 convention drift |
| A constant signal produces an empty or NaN spread, never a finite alpha | catches 2.5 |
| Portfolio returns with one name removed change by less than that name's weight | catches weighting bugs |

Hypothesis (`pip install hypothesis`) is worth it for the FX and weighting ones — generate
random rate vectors and random cap vectors and assert the invariants.

## Stage 3 — differential testing against yourself

You have a rare advantage: `leonardo_nodes` stores a `Process` per node and lets you swap
implementations. Use it as a **differential oracle**, not just an audit log.

- Write a deliberately naive, slow, obviously-correct second implementation of the two or
  three riskiest steps — the materiality classification, the market-cap screen, the
  standardisation — as alternative Processes. Run both on the same Experiment and assert the
  outputs match. A 50-line `for` loop that takes ten minutes is a perfectly good oracle.
- This is much stronger than a frozen artifact, because it survives a data refresh.

## Stage 3b — make the dashboard show the failure

`leonardo_nodes` is not under audit — it owns no numerics. But it is how you *see* the
pipeline, and that cuts both ways: **a quantity with no VizSpec is a quantity you cannot
notice going wrong.** Every audit in this register that is currently invisible on the
dashboard should become a declared audit on the relevant node's Contract, so it appears
beside the results instead of in a file nobody opens.

Worth surfacing, in rough order of value:

| Add to | Node | Shows |
|---|---|---|
| Conservation delta | `01_process_lc` | initiatives in GOLDEN vs initiatives in the merged panel — should be a flat zero line (2.1, 2.4) |
| Firm-years by rfyear × region | `11_sample_funnel_audit` | the 2023–2025 coverage cliff, as a chart rather than a number you have to go looking for (1.4) |
| Forward-looking share | `01_process_lc` | % of firm-years classified with a backfilled materiality vintage (1.3) |
| FX merge coverage | `03_load_universes` | rows with no FX rate, per currency per year (1.6) |
| Degenerate z-score cells | `06_prepare_panel` | count of `(year, currency, industry)` cells with std 0 or NaN (2.5) |
| Alpha t-stat, HC1 vs HAC | `07_build_analyse_portfolios` | both side by side, so the gap is never invisible (1.2) |

These are cheap — a `BarComparisonViz` or `BundleSeriesViz` on an existing Contract — and
they convert a one-off audit into a standing one. That is the whole point of the framework;
it is currently under-used for exactly the quantities most likely to be wrong.

## Stage 4 — adversarial data probes

Rather than reading code, ask the *data* questions whose answers are forced if the code is
right. Each of these is a script in `scripts/`, run against the real panel, output checked
into `audit/`:

1. **Funnel.** Rows at every stage: GOLDEN → melt → classify → 17-SDG grid → CSV → LC inner
   join → market-cap screen → z-score → portfolio. One table, absolute and percentage. Any
   stage dropping >5% unexpectedly is a finding. (`11_sample_funnel_audit.py` starts this —
   extend it back into Matchings.)
2. **Coverage heatmap.** Firm-years by (rfyear × region × GICS sector). Look for the
   2023–2025 cliff (1.4) and for whole sectors missing.
3. **Signal distribution by year.** Histogram of the material share per year. If the mass
   point at 0 or 1 moves over time, your quantile cutpoints are measuring coverage, not
   behaviour. (`12_sort_cutpoint_audit.py` exists — read its output properly.)
4. **Leg composition.** For the headline long-short: top 20 names by weight, by year. If the
   long leg is the same ten mega-caps every year, the "alpha" is a sector or size bet.
5. **Placebo signal.** Replace the materiality signal with a random permutation of itself
   *within year*, re-run the entire pipeline, record the alpha. Do it 200 times. That
   distribution is your real null, and it costs nothing but compute. **If your headline alpha
   is not outside the 95th percentile of this distribution, you have nothing.** This single
   experiment is worth more than every unit test in Stage 1.
6. **Sub-period stability.** Alpha by 5-year block. A result that lives entirely in 2020–2022
   is a COVID artifact.

## Stage 5 — read the code, but read it in the right order

Only now, and only these paths, in this order. Read for *joins, filters, and fillna* — that
is where every bug in this codebase lives.

1. Every `pd.merge` / `.join` in the repo. For each: are both key columns the same dtype and
   format? Is `validate=` set? Is the row count asserted after?
   ```bash
   grep -rn "pd.merge\|\.merge(" --include='*.py' functions New_Pipeline ../Matchings | wc -l
   ```
   Work through every one. This is the highest-yield hour you will spend.
2. Every `fillna`, `dropna`, `.notna()` filter. For each: how many rows, and is it logged?
3. Every `except` and every bare `pass`.
4. Every boolean flag that a caller *asserts* rather than the code *verifies* (1.7 is the
   template).

## Stage 6 — the theory review, which no test can do

Book an afternoon with no editor open. Write down, in prose:

- What is the economic hypothesis, stated so it could be false?
- What is the **one** primary specification? Write it down before you look at its result.
- For every design choice — 3 vs 5 quantiles, 0.95 vs 0.99 coverage, Planet vs Narrow_Planet,
  cap- vs equal-weight — what is the *ex ante* justification? Any choice you cannot justify
  without looking at the result is a researcher degree of freedom, and it belongs in the
  multiple-testing count (1.1).
- What would the result look like if the effect were pure disclosure propensity (1.5)? Can
  you distinguish those two worlds with the data you have? If not, say so in the paper.

## What *not* to do

- Don't write unit tests for `functions/` in bulk. Most of it is thin pandas glue; the tests
  would assert the implementation back to itself.
- Don't chase the four notebook-parity failures. That oracle is gone; see Stage 0.2.
- Don't add more sweep dimensions until 1.1 has an answer. Every one you add makes the
  multiple-testing problem worse and the paper weaker.
