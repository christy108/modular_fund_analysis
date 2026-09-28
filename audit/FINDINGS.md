# Audit findings — executed 2026-09-25

Run against `audit/AUDIT_PROMPT.md`. Read-only; no code was changed. Every number below was
produced by running code against the real data, not inferred from reading it.

Scope: `Matchings` + `modular_fund_analysis`. `leonardo-nodes` not audited.

**Live study window.** `start_year=2016`, `end_year=2024` (`New_Pipeline/experiments.py:51`).
`start_year`/`end_year` are applied **twice, to two different things**: `process_lc.py:59-60`
filters LC by **fiscal** year (`rfyear >= start_year`), and `get_*_universe(start, end)` filters
the universe by **calendar** date. Since the panel merge is `last_year == rfyear` with
`last_year` = Y−2 (Jan–Jun) / Y−1 (Jul–Dec):

```
rfyear loaded by process_lc : 2016 .. 2024
rfyear that drives a return : 2016 .. 2023   (rfyear 2024 is live Jul 2025-Jun 2026,
                                              outside the calendar cap, so never matches)
first month with any signal : Jul 2017       (Jan 2016 - Jun 2017 finds no rfyear and drops)
```

So the run **silently starts 18 months after the date the config asks for**, and the effective
sample is rfyear 2016–2023 / formation Jul 2017 – Dec 2024. Every windowed figure below uses
that range. *Corrected 2026-09-28: an earlier version of this document said rfyear 2014–2023,
derived from the `last_year` lag alone without noticing that `start_year` also filters rfyear
directly. Findings 1.1, 1.3 and 1.5 were restated on the correct window.*

---

## P1 — could change a headline alpha, t-statistic, or sample size

### 1.1 The material-share signal is confounded with disclosure intensity — CONFIRMED

The long leg is systematically made of firms that disclosed **few** initiatives, because with
few initiatives it is arithmetically easy for all of them to be material.

```
signal_0 = material__total / (material__total + immaterial__total),  rfyear 2016-2023
  firm-years with a defined share : 46,790
  share exactly 1.0               :  7,340  (15.69%)
  share exactly 0.0               :  1,120  ( 2.39%)
  90th percentile of the share    :  1.0

median initiatives per quintile of the signal
  Q1 low   14      Q2  24      Q3  26      Q4  23      Q5 HIGH   8
  share == 1.0 group: median  6 initiatives
  share <  1.0 group: median 22 initiatives
```

The relationship is non-monotonic (14, 24, 26, 23, **8**) — the high leg is a sharp outlier.
A High−Low spread on this signal is therefore partly a short-disclosure-minus-long-disclosure
bet, and disclosure intensity correlates with size, region, sector and analyst coverage.

**Scenario.** A firm with 6 initiatives, all material, scores 1.0 and enters the long leg
every month of that fiscal year. A firm with 60 initiatives, 45 material, scores 0.75 and
sits mid-pack. The sort is ranking measurement precision, not corporate behaviour.

**The mitigation exists and is switched off.** `cfg.minimum_initatives_needed_to_split_by_materiality`
was written for exactly this ("so a ratio of two small integer counts is only formed where it
is estimable rather than letting `1/1 = 1.0` read as maximal materiality",
`New_Pipeline/nodes/02_derive_signals.py:113-118`). It is set to **0** in
`sweep_parameters_US.py:227`, `sweep_parameters_EU.py:235`, `sweep_parameters_PP_US.py:179`
and `experiments.py:216`. It is used once, at `experiments.py:1251`, with value 5.

**Do this:** re-run the headline design with the minimum at 5, 10 and 20 and report how the
alpha moves. If it dies at 10, the result was a disclosure proxy. This is the single most
informative hour in the whole audit.

### 1.2 The sweep ledger stores p-values rounded to 2 dp — CONFIRMED

`New_Pipeline/nodes/07_build_analyse_portfolios.py:1126` → `pd.concat(parts, axis=1).round(3)`,
and the risk table the sweep harvests from is rounded to 2 dp (the node docstring says so at
line 520). `sweep_report.py:668-669` copies those rounded values into `results.csv`.

```
Sweep_All_Signals_Materiality/results.csv
  p-values: 6,699 values, 101 distinct, 100.0% equal to round(p, 2)
  alphas  :               100.0% equal to round(a, 2)
  smallest non-zero p: 0.0100 ;  14 values are exactly 0.00
```

So **`p = 0.00` means `p < 0.005`, not a small p.** Across all 21 saved sweeps:

```
  High-Low spread alpha tests on disk : 4,344
  p < 0.05                            :   335  (7.7%)   [5% expected under the null]
  p < 0.01                            :    18  (0.4%)
  Bonferroni threshold at n = 4,344   : p < 1.15e-05
  tests that can be SHOWN to survive it: 0 — the rounding makes it unknowable
```

Two consequences, both serious. First, the observed significance rate (7.7%) is barely above
chance (5%) across the recorded search. Second, **no multiple-testing correction can be
computed from the saved artifacts at all**, because the resolution needed (1e-5) is four
orders of magnitude finer than what is stored. The record of the search is lossy in exactly
the dimension the search needs to be defended in.

**Do this:** add `tstat__` and full-precision `pval__` columns to the sweep ledger. One line
in `sweep_report.py`. Without it, a referee asking "how many specifications did you try?"
cannot be answered quantitatively.

**Related, and worth knowing:** the 16 tests with `p = 0.00` are mostly *not* the material
designs and mostly have the *wrong sign* — `High − Low Material_Prosperity` at −0.40 to
−0.54 monthly, `High − Low Immaterial__Innovation` at −0.58 to −0.64, against
`High − Low advocacy` at +0.35 to +0.41. The strongest recorded effects are immaterial legs
and negative material legs.

### 1.3 The `sum_activities` winsor trim silently removes 1.4× to 3.6× what it is asked to — CONFIRMED

`functions/data_functions/process_lc.py:111`

```python
return lc[(lc[activities_col] > lower) & (lc[activities_col] < upper)].copy()
```

Strict inequalities on an integer-valued column. The quantile lands **on** an integer and the
comparison then deletes the entire tie block at that integer.

```
 alpha_bound   asked   actually removed   over-trim        (rfyear 2016-2023)
     0.00       0.0%        0.47%          +0.47 pp
     0.01       1.0%        3.78%          +2.78 pp   (3.8x)
     0.02       2.0%        5.77%          +3.77 pp   (2.9x)
     0.05       5.0%        7.28%          +2.28 pp   (1.5x)   <- production default
     0.10      10.0%       11.54%          +1.54 pp

The trim deletes whole integer tie blocks, concentrated on firm-years holding
exactly 2 initiatives -- the low-disclosure tail that drives finding 1.1.
```

Three problems. It removes an unintended amount; the amount is **non-monotone** in
`alpha_bound` (+2.78 → +3.77 → +2.28 → +1.54 pp), so a robustness sweep over `alpha_bound` is
varying the sample in a way nobody chose; and it deletes precisely the low-disclosure
firm-years that drive 1.1, so it is a partial, accidental, uncontrolled mitigation of a
separate bias.

Note `alpha_bound=0` still drops 0.47% — the function cannot express "trim nothing".

### 1.4 Standard errors are not autocorrelation-robust — CONFIRMED

`functions/portfolio_metrics/fama_french.py:72` → `mod.fit(cov_type='HC1')`.

Heteroskedasticity-robust only. The dependent variable is a monthly return from a signal that
updates once per fiscal year, so twelve consecutive residuals share a formation signal. HC1
understates the alpha standard error; every reported t-statistic is inflated by an unknown
amount.

**Fix:** `cov_type='HAC', cov_kwds={'maxlags': 6, 'use_correction': True}`, report both.

### 1.5 The materiality map is STATIC, and its compilation date is unknown — REWRITTEN 2026-09-28

*This finding replaces "Look-ahead from the backfilled materiality vintage". The backfill I
reported is not a live problem, for two independent reasons. What replaces it is larger.*

**The backfill exposure is zero, not 10.4%.** `vintage_for()` does backfill — it returns the
earliest vintage for any year before the first one — but `process_lc.py:59` filters
`rfyear >= start_year`, so with `start_year=2016` the affected fiscal years never enter the
study at all. I previously reported 26%, then 10.4%; both were wrong, because I derived the
rfyear window from the `last_year` lag without checking that `start_year` filters rfyear too.

```
actual sample : rfyear 2016-2023, 46,790 firm-years with a defined share
backfilled    : 0
```

**And the backfill could not have mattered anyway, because the three vintages are identical.**

```
SASB_Materiality_long_format_time.xlsx : 6,006 rows = 3 x 2,002
  rows per rfyear          : {2016: 2002, 2020: 2002, 2022: 2002}
  2016 block == 2020 block : True   (all columns, byte-for-byte)
  2016 block == 2022 block : True
  material (industry, issue) pairs per vintage : 420 / 420 / 420, jaccard 1.0000
```

`vintage_for()` is a **no-op**: whichever vintage it selects, the materiality answer is the
same. The file name promises time-varying materiality (`..._long_format_time.xlsx`), the
pipeline carries a whole vintage-selection mechanism for it, and the data has no time
variation at all.

**So the real question is different, and bigger.** One static SASB map classifies every
firm-year from 1990 to 2030. Whether the study has look-ahead now depends entirely on **when
that single map was compiled**, which is a provenance question the data cannot answer.

The live formation window is Jul 2017 – Dec 2024, about 90 months.

| If the map encodes… | Consequence |
|---|---|
| SASB **provisional** standards (complete ~2016) | Clean. |
| SASB **codified** standards (November 2018 — codification did change industry-issue mappings) | The first ~16 months use a map that did not exist: ~18% of the series, and the early part, where cumulative returns compound from. |
| The SASB/ISSB materiality finder **as it stands today** | The entire sample is look-ahead. |

**Why "materiality is slow-moving, so it hardly matters" is weaker than it sounds here.** The
bias is not a level shift that could be argued away — it is a cross-sectional *reordering*. A
firm scoring high-material under a 2018+ map may have been mid-pack under a 2014 one, and that
reordering is exactly what the sort trades on. There is also a selection channel that no
version control would catch: whoever chose which SASB release to encode made that choice
already knowing which issues turned out to matter.

**Do this, in order:**

1. **Establish the provenance of `SASB_Materiality_long_format_time.xlsx`** — which SASB
   release, compiled when. Everything else depends on the answer, and nothing in the repo
   records it (see 3.6).
2. If it is the Nov-2018 codification or later, `start_year=2018` becomes correct — it puts the
   first formation month at Jul 2019, comfortably after. Report it as the **primary**
   specification, not a robustness check.
3. Either populate the three vintages with genuinely different maps, or delete `vintage_for`
   and the `rfyear` column and state plainly in the paper that materiality is held constant.
   Machinery that implies time variation where there is none is worse than no machinery.

**The same question applies upstream.** GOLDEN's initiative counts come from an LLM extraction
(`predicted_company_name`). If the action taxonomy or the extraction prompt was designed after
seeing the sample period, that is the same class of problem, equally invisible to the code, and
equally a provenance question rather than a testable one.

**What IS protected — worth crediting.** Every *mechanical* look-ahead channel is closed and
correctly implemented: the `last_year` lag makes fiscal data 7–30 months stale at formation and
`vintage_for(rfyear)` inherits it; the ESG merges use the same lag (2.10 argues too
conservatively); the portfolio convention is signal at t, return at t+1; and cap weights are
read at the formation row, not t+1. What remains is a data-provenance problem, which is why no
test will catch it.

---

## P2 — changes a number in a robustness table or an audit artifact

### 2.1 `Matchings` §5 "TOTAL CHECK" regex is dead — ✅ FIXED 2026-09-28

**It had two independent bugs, not the one originally reported.** (1) the regex matched
`(advocacy|…)$` after the bucket was renamed `advocacy_new_def`, dropping 3 of the 12
four-signal columns; (2) `raw_total = long["n_initiatives"].sum()` pooled *both* taxonomies
on the raw side while the aggregate covered only one. Together they reported a difference of
**3,279,850 on a 2,328,025 base** — a 141% discrepancy, every run. It also ran *after* the CSV
was written.

Replaced with a **CONSERVATION GUARD** before the 17-SDG grid and the export, with bucket
lists derived from `BEHAVIOUR_BUCKETS` / `BEHAVIOUR_BUCKETS_3_SIGNALS` and the two taxonomies
checked separately. Section 5 now restates its numbers. Replayed on real GOLDEN v_2A1:

```
=== CONSERVATION GUARD ===
  4-signal  melted=      2,328,025  aggregated=      2,328,025  diff=0  (12 columns)
  3-signal  melted=      2,119,052  aggregated=      2,119,052  diff=0  ( 9 columns)
  -> PASSES
negative control: inject 1 phantom initiative -> guard raises: True
```

`Matchings/Main/Main.py` has not been re-run end to end; the output CSV was deliberately
not regenerated.

<details><summary>Original finding, for the record</summary>


The regex matches `(advocacy|upskilling|adaptation|innovation)$` but the bucket is
`advocacy_new_def`, so the reconciliation has never run. **The conservation it was meant to
check does hold, exactly:**

```
GOLDEN 2D "{action} - SDG {n}" initiatives  : 2,328,025
  of which bucketed                         : 2,328,025  (100.00%)
  unbucketed / silently dropped             :         0
delivered CSV material+immaterial+unmapped  : 2,328,025   <- exact match
  material   1,584,943 | immaterial 733,132 | unmapped 9,950 (0.4%)
```

So the check is broken, not the data. Fix the regex and promote the print to a `raise` — it is
the only end-to-end integrity check in the matching layer and it currently trains you to
ignore a permanent false alarm.

</details>

### 2.2 Listwise deletion vs zero-filling for thin legs — CONFIRMED, but NOT driving results

`_factor_regressions` drops NaN months; `(1+r).cumprod()` books them as 0%. Two samples in one
table. Live for 8.2% of leg-runs.

```
leg-runs with a coverage number : 9,294
  coverage == 100%              : 8,528 (91.8%)
  coverage <  90%               :   689 ( 7.4%)
  coverage <  50%               :   287 ( 3.1%)   minimum seen: 0.0%
```

**But significance does not concentrate in thin legs** — the opposite:

```
significance rate by minimum leg coverage
  50-90%  :  74 tests,  0.0% significant
  90-100% :  54 tests,  3.7%
  100%    : 4,216 tests, 7.9%
```

So the thin-portfolio gate is doing its job and this is a presentation inconsistency, not a
source of false positives. Fix the table, don't panic about the results.

### 2.3 The two behaviour taxonomies do not span the same initiatives — CONFIRMED, documented

```
4-signal buckets (adaptation, advocacy_new_def, innovation, upskilling) = 1,584,943 = material__total
3-signal buckets (advocacy_old_def, preparation, transformation)        = 1,438,951  (-9.2%)
```

`association` and `pricing` are in no 3-signal bucket, by design. So designs sorting on
`advocacy_old_def / preparation / transformation` (the US and EU sweep `GRID`s do) run on
90.8% of initiatives while `total`-based designs run on 100%. Internally consistent as long as
numerator and denominator come from the same family — worth an assertion in
`signal_definitions_materiality._signals_from_groups`, which currently has none.

### 2.4 FRB H.10 column names are assigned blind and positionally — CONFIRMED (latent)

`functions/data_functions/get_data.py:318`

```python
FRB_H10.columns = ['date','EUR','GBP','DKK','JPY','NOK','SEK','CHF']
```

The file is downloaded by hand from a URL in a comment. The order currently matches. If a
future download returns a different column order — the FRB lets you choose — **every currency
silently gets another currency's rate**, with no error anywhere. The file itself carries the
series IDs (`RXI$US_N.B.EU`, `RXI_N.B.JA`, …) on row 6; nothing reads them.

Also latent: the file covers **2009-01-01 to 2024-12-31 only**. `start_year=2016`/`end_year=2024`
fits inside it today. Move `end_year` to 2025 or `start_year` before 2009 on a converted
(European / Japanese) run and every out-of-range row gets a NaN rate → NaN mktcap → silently
dropped by `global_universe["mktcap"].notna()`, with no log line.

### 2.5 `standardize_pivot` has no zero-variance guard — CONFIRMED (code), unquantified

`functions/functions.py:126-128` divides by `group_stdev` with no guard. A singleton or
constant `(year, currency, industry)` cell gives `inf` or `NaN`, and an `inf` z-score lands in
the extreme quantile every month. The `min_group_size` guard exists **only** on the ESG path
(`prepare_esg_universe_sorting_inputs`), not on the LC path every materiality experiment uses.
Needs a real run to count; not measurable from the static data.

### 2.6 `apply_optional_geo_filter` raises `NameError` — CONFIRMED (known)

`univariate_sorting_preprocess.py:119`, body commented out, returns `gu[~foreign_listed]` with
both names undefined. Called at line 373 under `apply_geo_filter=True`. Dead code advertising a
filter that does not exist, next to a live `13_geography_audit.py` node.

---

### 2.7 Every run silently starts 18 months after the configured start_year — NEW 2026-09-28

`start_year` is applied to two different things: `process_lc.py:59` filters LC by **fiscal**
year, and `get_*_universe(start, end)` filters the universe by **calendar** date. Because the
panel merge is `last_year == rfyear`, the first 18 calendar months of any requested window ask
for fiscal years that `process_lc` has already deleted, find no match, and drop.

```
start_year=2016, end_year=2024
  Jan-Jun 2016 needs rfyear 2014  -> filtered out of LC -> no match -> dropped
  Jul-Dec 2016 needs rfyear 2015  -> filtered out of LC -> no match -> dropped
  Jan-Jun 2017 needs rfyear 2015  -> filtered out of LC -> no match -> dropped
  Jul-Dec 2017 needs rfyear 2016  -> first month with a signal
```

At the other end, `rfyear 2024` is loaded by `process_lc` but is live Jul 2025 – Jun 2026, past
the calendar cap, so it never drives a return either.

This does not bias anything — it is a reporting-accuracy problem. A paper stating a 2016–2024
sample would be describing a window that is really **Jul 2017 – Dec 2024**, 18 months shorter
than claimed, and the discrepancy recurs at every `start_year` anyone sets. Nothing in the
funnel audits reports it as a distinct stage.

**Fix:** either offset the LC filter by the lag (`rfyear >= start_year - 2`) so the requested
calendar window is actually covered, or have the run print its realised first and last
formation month and carry them into the manifest.

---

## P3 — hygiene and latent

| # | Finding | Evidence |
|---|---|---|
| 3.1 | `rfyear = 2030`, `conml = None`, gvkey 036995, 26 initiatives — an impossible fiscal year that passes every guard in both repos. Outside the study window, so harmless today. | GOLDEN parquet |
| 3.2 | 179 GOLDEN firm-years have `rfyear < 2000` and are silently relabelled `unmapped` by `YEAR_MIN`. | GOLDEN parquet |
| 3.3 | 2,423 firm-years disappear between GOLDEN (74,835) and the output grid (72,412) — the deliberate gvkey zero-padding alias merge. Conservation holds, so nothing is lost; just be able to explain the number. | both files |
| 3.4 | `results.csv` alphas are also 2 dp (0.01% monthly ≈ 0.12%/yr granularity). Fine for display, not for inference. | 21 sweep files |
| 3.5 | `Matchings/Main/Main.py` hardcodes `USER = "cbruce1"` and absolute `/Users/...` paths. | source |
| 3.6 | The output filename records only `GOLDEN_VERSION` and `VERSION`. `FRAMEWORK`, `ACCEPTED_MATCH_LEVELS`, `MSCI_THRESHOLD` and `YEAR_MIN` are recorded nowhere. Two files with the same name can mean different things. | source |
| 3.7 | Stray bare `6` statement at `univariate_sorting_preprocess.py:349`. | source |
| 3.8 | `process_global_universe` builds the panel with `row_universe.reindex(columns=usa_universe.columns)` — any column present on ROW/Japan but not USA is dropped with no warning. | `process_data.py` |
| 3.9 | No delisting returns. `secstat` inactive rows ARE retained (2.8M of 8.8M in the US extract), so the firms are present; the −100% month is not. | `get_data.py`, US extract |
| 3.10 | No transaction costs or turnover anywhere. | repo-wide |

---

## Checked and REFUTED — do not spend time here

Recording these matters as much as the findings: each was a plausible hazard that the data
disproves.

| Hypothesis | Verdict |
|---|---|
| FX conversion direction may be inverted | **Correct.** EUR/GBP are `RXI$US` (USD-per-unit) and are explicitly inverted; DKK/JPY/NOK/SEK/CHF are `RXI` (units-per-USD) and left alone. Verified 2024-12-31: EUR 0.9661, GBP 0.7987, JPY 157.37 per USD. `mktcap_lcu / rate` is right. |
| FX merge may multiply rows | **No.** 0 duplicate `(date, curcdd)` keys in 29,218 rows. |
| FX `ffill` may carry stale rates | **No.** Longest fill is 2 consecutive days (holidays), every currency. 7 NaNs, all on 2009-01-01. |
| Unbucketed GOLDEN actions silently dropped | **None.** 238 action-SDG columns, 14 actions, all bucketed. 0 initiatives dropped. |
| End-to-end conservation may be broken | **Exact.** 2,328,025 in GOLDEN = 2,328,025 in the delivered CSV. |
| `all_gics_in_db` union → silent "immaterial" | **Cannot occur.** All three vintages carry the identical 76 GICS keys, each with ≥1 material SDG. |
| `parse_sdg_number` may grab the wrong number | **No.** All 17 `Issue 2` labels are `"N - Name"`; 0 unparsed. |
| Matchings joins on nullable metadata → silent zero-fill | **Not live** — conservation is exact, so nothing is being zero-filled. Still fragile by construction. |
| `_factor_regressions` positional alignment | **Every caller** passes `reset_index(drop=True)` (3 sites in node 07, 1 in `fama_french.py:205`). Latent only. |
| Materiality CSV may have drifted between repos | **Byte-identical** for all three vintages (`v_2A1`, `v_2C`, `v2c`). |
| `esg /= 100` on the `esg_choice="none"` branch | **Correct.** `esg_none_v1` attaches a constant `esg = 100`; the division normalises it to 1.0. |
| Duplicate `(gvkey, rfyear)` in GOLDEN | **Zero.** 74,835 rows, 74,835 unique keys. |
| Multiple share classes double-counted | **No.** The US extract is primary-issue filtered: 2,580 gvkeys, 2,580 listings on the last date. |
| Thin portfolios drive the significant results | **No** — the opposite. 0% significant at 50–90% coverage vs 7.9% at 100%. |
| 2023–2025 coverage collapse contaminates the study | **Outside the window.** The rfyears that actually drive a return are 2016–2023, so the live effect is the 2022 → 2023 step, −22%, not the −91% visible in the raw file. rfyear 2024 is loaded but never matches a calendar month inside `end_year`. |
| Materiality is time-varying across the sample | **It is not.** All three vintages in the materiality file are byte-identical copies (see 1.5). |

---

## If you do five things

1. Re-run the headline design with `minimum_initatives_needed_to_split_by_materiality` at
   5 / 10 / 20 (**1.1**). This is the one that could invalidate the result.
2. Switch `cov_type` to HAC and report both t-statistics (**1.4**).
3. Store full-precision p-values and t-stats in the sweep ledger (**1.2**), then count the
   search honestly.
4. Change `>`/`<` to `>=`/`<=` in `filter_sum_activities_by_fiscal_year_quantiles` and re-run
   the `alpha_bound` robustness row (**1.3**).
5. Establish when the SASB materiality map was compiled (**1.5**) — it is static across the
   whole sample, so that one date decides whether the study has look-ahead at all.

Nothing in this list is more than a few lines of code. Four of the five change a number you
would report.

---
---

# Passes 2–5 — additional findings and re-validation

Same rules: read-only, every number produced by running code. This section both **adds new
findings** and **re-tests the ones above**. Two of my earlier claims were wrong; they are
corrected here rather than quietly dropped.

## Corrections to pass 1

### ✗ 1.2 was WRONG on the detail — precision is 3 dp, and it changed mid-history

I tested only `Sweep_All_Signals_Materiality` and generalised. Testing all 21 files:

```
17 older sweeps (to 2026-09-21)  : 100% of p-values equal round(p,2)   [2 dp]
 4 newest sweeps (2026-09-24/25) : ~10-17% at 2 dp, 100% at 3 dp        [3 dp]
POOLED n=13,090  : 93.6% at 2dp, 100.00% at 3dp, smallest non-zero = 0.001
```

Current code (`Strategy_Perfomance.py`, `_format_num(x, dp=3)`) emits **3 dp**. Someone
already improved this; the 2 dp files are historical runs.

**The conclusion still stands, for a different reason.** Bonferroni at n=4,344 needs
`p < 1.15e-05`; the finest value stored is `0.001`, which is **87× coarser**. Survival is
still unknowable from the saved artifacts, and the ledger now mixes two precisions, so the
21 sweeps cannot be pooled for a correction even in principle.

**Corrected multiple-testing picture:**

```
High-Low spread alpha tests on disk : 4,344
  p < 0.05 : 335  (7.71%)   vs 217 expected  ->  excess +118 = +8.2 binomial SE
  p < 0.01 :  18  (0.41%)   vs  43 expected  ->  DEFICIT
```

That shape — **excess at the loose threshold, deficit at the strict one** — is the signature
of many weak effects rather than a few strong ones. It is also exactly what you would expect
if HC1 (finding 1.4) is inflating t-statistics near the margin: it pushes borderline cases
across 0.05 without creating anything at 0.01. My pass-1 phrasing ("barely above chance")
undersold the 5% excess; this is the more accurate reading. The tests are positively dependent
(one panel, overlapping designs), so +8.2 SE is an upper bound on the evidence.

### ✗ 2.5 is REFUTED — no degenerate z-score cells exist on the LC path

`cols_standardization = ["rfyear", "Industry"]` (`06_prepare_panel.py:365`), and `map_sectors`
folds 11 GICS sectors into 7 buckets. Measured on the real window:

```
(rfyear, Industry) cells : 70 | min 141 | median 619 | max 2,280
cells < 5 firm-years : 0     cells < 30 : 0
firm-years with no GICS_level_1 : 197 (0.38%)
```

A zero or NaN standard deviation needs a cell of size 1 or a constant cell. Neither exists.
The missing `min_group_size` guard is a latent code smell, not a live defect. Withdrawn.

### ✓ Everything else from pass 1 re-confirmed

1.1, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.6 all stand as written.

---

## New P1

### N1.1 `use_alpha_bound=False` does not turn the trim off — it makes it 3.6× harsher

`New_Pipeline/nodes/02_derive_signals.py:424-434`

```python
if C["use_alpha_bound"]:
    lc_df = filter_...(lc_df, lower_exclude=(C["alpha_bound"]/2), upper_exclude=(C["alpha_bound"]/2))
else:
    lower_exclude = 0.2 * 2        # -> 20% off the BOTTOM
    upper_exclude = 0.05 * 2       # ->  5% off the top
    lc_df = filter_...(lc_df, lower_exclude=(lower_exclude/2), upper_exclude=(upper_exclude/2))
```

Measured on the study window:

```
use_alpha_bound=True , alpha_bound=0.05  ->  removes  7.16%   (symmetric)
use_alpha_bound=FALSE (hardcoded)        ->  removes 26.13%   (asymmetric, 20% off the bottom)
```

Turning the bound **off** deletes **3.6× more** of the sample than turning it on, and takes it
almost entirely from the small-disclosure tail — the exact population that drives finding 1.1.

The node's own comment at line 510 says so ("there is no inactive case"). But
`dashboard_viz.py:885` documents the knob as *"Whether the alpha_bound trim runs at all."*
That description is **wrong**, and it is what the dashboard shows the reader.

Currently latent for results (`experiments.py:229` sets `use_alpha_bound=True` and no sweep
overrides it). Live for anyone who reads the dashboard.

### N1.2 MSCI ESG can be matched to only 12% of the US universe

Identifier overlap, measured directly:

```
universe firms: USA 4,610 cusips | ROW 10,430 isins

MSCI      (9,263 issuers, 795 US-prefixed)   USA  554 (12.0%)   ROW 2,022 (19.4%)
LSEG      (16,504 isins / 6,009 cusips)      USA 2,673 (58.0%)  ROW 2,524 (24.2%)
S&P       keyed on gvkey directly            -- no identifier loss
```

`esg_msci` experiments therefore run on roughly an eighth of the US universe and a fifth of
ROW — before any market-cap or coverage filter. Whatever that sample is, it is not the sample
the materiality designs run on, so `esg_msci` results and materiality results are not
comparable and the ESG-vs-behaviour correlation tables (`08_esg_signal_corr`) are computed on
the intersection of two very differently-sized sets.

Worth a second look at the extract itself: MSCI ESG Ratings covers ~2,900 US issuers in
reality; this file has 795. The USA path also relies on `cusip = isin[2:11]`, which is correct
(both sides are 9-char, verified) but only works for `US`-prefixed ISINs — a US-listed firm
with a non-US ISIN is unmatchable by construction.

---

## New P2

### N2.1 The US run benchmarks a 17.4%-non-US portfolio against US-only factors

`experiments.py:372` pairs `region_filter=["United States and Canada"]` with
`fama_factor_region="United_States"`.

```
composition of that region, study window (12,722 firm-years)
  USA 10,505 | CAN 2,081 | BMU 118 | GBR 11 | CHE 7
  non-USA: 2,217 = 17.4%
```

Ken French's `United_States` factors do not span Canada. `North_America_3_Factors.csv` and
`North_America_5_Factors.csv` are both present, and `region="North_America_and_Canada"`
resolves to them correctly (`get_data.py:815`). The alpha absorbs whatever Canada−US return
differential exists over the window. One-line fix; re-run and compare.

### N2.2 70 merges in the pipeline, 3 with `validate=`

```
total .merge()/pd.merge() calls across functions/, New_Pipeline/, Matchings/ : 70
...carrying validate= : 3
```

In a codebase whose dominant failure mode is silent row multiplication and silent non-match,
67 unguarded joins is the single systemic weakness. Most take one keyword.

### N2.3 `GICS_level_1` means two different things in two places

```
materiality CSV / GOLDEN / LC  : NAMES   -> 'Industrials', 'Capital Goods', 'Aerospace & Defense'
data/GICS/gics_comp_*.csv      : CODES   -> 20, 2030, 203020, 20302010  (int64)
```

Both consumers are currently correct — the LC path uses `map_sectors` (names), the ESG path
uses `pd.to_numeric(...).map(_GICS_SECTOR_NAME)` (codes). But nothing asserts which it has.
Feed the name-based frame to `prepare_esg_universe_sorting_inputs` and `pd.to_numeric` returns
all-NaN, `Industry` becomes all-NaN, and `gu.dropna(subset=cols_standardization)` **silently
empties the panel**. The only signal is a `print` of the dropped-row count; nothing raises.

### N2.4 The WRDS GICS cache has no Europe file

```
data/GICS/  ->  gics_comp_United_States_2024.csv, gics_comp_Japan_2024.csv
```

`esg_full_universe` on Europe has no industry classification source, so its standardisation
key cannot be built.

### N2.5 ESG scores inherit the accounting-reporting lag they do not need

`get_msci_esg_merge_to_universe` collapses the monthly MSCI panel to December of each year and
merges on `last_year`. `last_year` is Y−2 for Jan–Jun and Y−1 for Jul–Dec, so the score in use
is **7 to 30 months old**, and it jumps forward by a year at every 1 July.

This is point-in-time **safe** — no look-ahead, and the docstring says that is the intent. But
`last_year` exists to model *fiscal reporting delay*, and ESG ratings have none: MSCI publishes
monthly with no embargo. So the ESG leg is handicapped against the materiality leg by an
artificial 7–30 month delay, and the ESG-vs-materiality comparison is not like-for-like.

### N2.6 "Europe" is the six-currency bloc, not Europe

`currency_filter=['CHF','GBP','EUR','NOK','SEK','DKK']` — because those are the only European
currencies in the FRB H.10 file. European domiciles listing elsewhere are dropped:

```
POL 365 | GRC 243 | HUN 53 | CZE 41   firm-years in the Europe region
```

~700 firm-years, ~4.5% of the European sample. Defensible, but it should be stated as a sample
definition rather than left implicit in an FX file's column list.

---

## New P3

| # | Finding |
|---|---|
| N3.1 | `low_high()` takes `df.columns[0]` / `[-1]` as Low/High. At K ≥ 10 a lexical sort makes `p_10` sort between `p_1` and `p_2`, so High silently becomes `p_9`. `no_simple_quantiles` is only ever 3 or 5 today, and the spread itself indexes `f"p_{K}"` by name, so this is latent — but `boundary.py` does `sort_index(axis=1)` elsewhere, so the ingredient is in the building. |
| N3.2 | `process_lc.add_missing_gvkeys` hardcodes three company-name → gvkey patches (`Artner Co Ltd`, `TDK Corp`, `StemCell Institute Inc`). Undocumented provenance, matched on `conml` string equality. |
| N3.3 | `region="Developed"` is an accepted `fama_factor_region`, but `data/FAMA/` has `Developed_3_Factors.csv` and **no** `Developed_5_Factors.csv`. Any FF5 run on Developed fails at the file check. |
| N3.4 | `get_processed_fx_rates` wraps everything in `except Exception as e: print(...)` and falls through returning `None`. A malformed FX file becomes a `TypeError` inside a merge rather than a clear message. |
| N3.5 | 12 `except Exception`/bare `except` blocks across the live code paths. |

---

## Verified CLEAN — worth knowing where the code is strong

| Area | Result |
|---|---|
| `capped_weights` (MSCI/S&P capping algorithm) | **0 violations in 2,000 adversarial random portfolios** — heavy-tailed caps, n from 2 to 400, cap from 0.02 to 1.0. Sum-to-one to 1e-12, no cap breach, no negative weight, rank order preserved, infeasibility boundary exact (`n*cap <= 1`). This module is genuinely well-built. |
| ESG merge timing | Point-in-time safe. Dec-of-year-Y collapse merged on `last_year` — no look-ahead in any of the three providers. |
| `rolling_ff_alphas` | Length, window and column checks all present; `reset_index(drop=True)` applied. Returns alphas only — no p-values — so overlapping windows cannot be misused for inference. |
| `univariate_portfolio_sorting` tie handling | The `half_open` / `closed` distinction is explicitly designed for atomic signals, with a documented K<3 guard against a tie block being held long and short simultaneously. The author clearly thought this through. |
| `standardize_pivot` cell sizes | 70 cells, min 141 (see the 2.5 retraction above). |
| Cross-repo file identity | Byte-identical for all three vintages. |
| `secstat` handling | Inactive securities ARE retained (2.8M of 8.8M US rows), with an explicit `active_only` vs full-sample choice and a survivorship warning in the docstring. |

---

## Updated priority list

1. **1.1** — disclosure-intensity confound. Re-run with the materiality floor at 5/10/20.
2. **1.4** — HC1 → HAC. The p<0.05-excess/p<0.01-deficit pattern above is what you would
   expect if this is doing real work.
3. **1.3 + N1.1** — the trim: fix the strict inequalities, and fix the dashboard text that
   says the bound can be turned off.
4. **1.2** — full-precision p-values and t-stats in the ledger.
5. **N1.2** — decide whether MSCI at 12% US coverage can carry any comparative claim.
6. **1.5** — establish the SASB map's compilation date. The map is static, so that date alone
   determines whether the sample is point-in-time.
7. **N2.1** — North America factors for a universe that contains Canada.
8. **N2.2** — `validate=` on the merges, starting with the FX and materiality joins.
