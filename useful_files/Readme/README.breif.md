# Fund analysis

## What it is

This repo joins a firm-year initiative panel (Golden LC) to WRDS-style monthly returns and evaluates quantile and sector-split strategies against MSCI and Fama–French factors.

## How to run

Open `[Main.ipynb](Main.ipynb)`, set `golden_location` and `./data/` paths, then execute cells in order.

## LC data and signals

The notebook cleans LC, maps GICS to coarse industries, buckets activity types, trims extreme activity counts by fiscal year, and forms share signals (`signal_0`, `signal_1`, `signal_2`).

## Equities and factors

`functions/data_functions/` loads or downloads USA and ROW universes, FX, builds a cap-filtered `global_universe`, and pulls Fama–French for the same calendar as returns.

## Univariate portfolios

`prepare_univariate_sorting_inputs` merges LC on publication-lagged fiscal year, builds monthly returns and z-scored signals, then `UnivariateQuantilePortfolio` sorts each month and takes next-month returns. Sorts using the signals. It takes the x-th split of stocks ranked by the signal, depending on how you define it.

## Sector split and benchmark

`SectorPortfolio` picks top x names per industry on one signal, equal-weights industries, and the notebook subtracts the risk-free rate and aligns MSCI for comparison. It will take the top x stocks per sector ranked by the transformation signal.

## Attribution and performance

`fama_french.py` runs FF3 regressions and rolling alphas; `Strategy_Perfomance.py` compounds returns, risk tables, and saves figures under `./output/`.

## Constituents

`PortfolioConstituents` plots who sits in quantile buckets over time by industry, country, and macro region.

## Code layout

Shared implementation lives in `[functions/](functions/)`; a full step-by-step map is in `[README.detailed.md](README.detailed.md)`.