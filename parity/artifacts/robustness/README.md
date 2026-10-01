# parity/artifacts/robustness

Frozen `base_none` baselines, three regions. Re-run them after a code change; if every
artifact says PASS, the change moved nothing.

```bash
.venv/bin/python -m New_Pipeline.parity_robustness            # re-run all three, diff
.venv/bin/python -m New_Pipeline.parity_robustness base_none_JP
.venv/bin/python -m New_Pipeline.parity_robustness --write    # re-freeze (numbers moved on purpose)
```

## The three configs

Each is `build_cfg()` with ONLY `region_analysis` changed (plus momentum for Japan), so a
diff between two runs is attributable to the code under test, not to config drift.

| config | region_analysis | Add_Momentum_Factor | specifications |
|---|---|---|---|
| `base_none_US` | `United_States` | True  | FF3+Mom (Carhart 4), FF5+Mom (6-factor) |
| `base_none_EU` | `Europe`        | True  | FF3+Mom (Carhart 4), FF5+Mom (6-factor) |
| `base_none_JP` | `Japan`         | False | plain FF3, plain FF5 |

Japan has no momentum: Ken French ships that series for Europe and United_States only, and
`05_load_fama_french` raises rather than silently dropping the factor. `ff5_parts_df` IS
still produced for Japan (`data/FAMA/Japan_5_Factors.csv` exists) -- it is the plain
5-factor model, not the 6-factor one the other two carry.

## What is stored

Per config, the four artifacts `New_Pipeline.run` exports:

- `ff3_parts_df.parquet` / `ff5_parts_df.parquet` -- alpha, betas, p-values, Adj. R^2
- `table_returns.parquet` / `table_excess.parquet` -- the monthly returns behind them

Plus `checksums.json` (SHA256 per file) and a per-config `headline_tables.txt`, which is
the two stat frames as text so the baseline is readable in a `git diff` without opening
parquet. The parquet files are the authority; the text is a convenience.

## How this differs from `parity/`

`parity/` asks "does the pipeline still reproduce the ORIGINAL NOTEBOOK?" -- its
`artifacts/old/` is frozen notebook output that is never regenerated. This folder asks
"did MY CHANGE move the numbers?" -- both sides are the current pipeline, and the baseline
is re-frozen deliberately whenever numbers are meant to move. The comparison itself is
`parity.compare._compare_frame`, so a PASS means the same thing in both.

## Provenance

Frozen 2026-09-24 on branch `leonardo-pipeline`. Two caveats on that vintage:

1. Frozen AFTER the FF stat frames went from 2dp to 3dp rounding
   (`07_build_analyse_portfolios.py::_level_parts`). These files therefore cannot detect a
   regression in that change itself -- they are the guard for what comes after it.
2. `base_none_JP` is the FIRST Japan run that has ever existed. `region_analysis="Japan"`
   raised KeyError before this (`experiments.py` read `fama_factors_currency`, a name left
   behind by commit df07f25's rename to `fama_factors_currency_if_Japan`). The config now
   builds and the pipeline runs end to end, but the Japan numbers have NOT been validated
   against any external reference -- treat this baseline as "what the code does today",
   not as "what is economically correct".
