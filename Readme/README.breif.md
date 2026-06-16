# Fund analysis

## What it is

This repo builds **initiative-based firm signals** from a “Golden LC” panel, merges them into a **tradable equity universe** (USA + ROW + Japan), then evaluates **monthly portfolio sorts** (univariate quantiles; optional sector-split) vs **MSCI World** and **Fama–French (FF3)** attribution.

## How to run

1. Open `Main.ipynb`
2. Update the file paths (Golden LC + MSCI) and choose analysis switches (region / ESG / accounting)
3. Run the notebook top-to-bottom

## Key notebook switches (you will edit these)

- **Sample window**: `start_year`, `end_year`
- **Region preset**: `region_analysis` (drives `currency_filter`, `convert_to_USD`, and `fama_factor_region`)
- **Universe filters**: `mktcap_covered` (top market-cap coverage per currency area), `alpha_bound` (trim LC extremes by fiscal year)
- **Signals**:
  - Choose a signal definition in `functions/signal_design/signal_definitions.py`
  - `lc_signals` controls which LC-derived signals are used (default `signal_0/1/2`)
- **ESG merge (optional)**: `esg_choice` in `{ "none", "refinitiv", "s&p", "refinitiv_n_s&p" }`
- **Accounting merge (optional)**: `add_accounting_data` (adds `roa*`, `ros*`, etc. via `get_accounting_data`)
- **Portfolio formation**: `no_simple_quantiles`, `first_conditioning_set`, `take_extremes`
- **Sector split (optional)**: `show_sector_portfolio`, `top_x_by_industry_even_split`

## Inputs (expected on disk)

- **Golden LC**: folder set by `golden_location` inside `Main.ipynb`
- **MSCI World benchmark**: `./data/MSCI/MSCI_World.xlsx`
- **WRDS-style universes / caches**: loaded via `functions/data_functions/get_data.py` (with `download_wrds_data=False` by default)
- **FX**: downloaded from FRB H.10 by `get_processed_fx_rates(end_year)`
- **Fama–French factors**: pulled by `get_famafrench_factors(start_year, end_year, fama_factor_region, ...)`

## Outputs

- **Global universe snapshot**: `./data/Global_Universe/Global_Universe_{region_analysis}_{end_year}.csv`
- **Tables**: `./output/{region_analysis}-strategy_*.csv`
- **Figures**: `./output/img/{region_analysis}-*.png`

## Code layout (where the logic lives)

- **Signals**: `functions/signal_design/`
- **Data** (universes, FX, FF, ESG, accounting): `functions/data_functions/`
- **Portfolio construction**: `functions/portfolio_strategy_design/`
- **Attribution + reporting**: `functions/portfolio_metrics/`
- **Extras** (e.g. `play_done_sound` end-of-run audio cue): `functions/extra_functions/`

A full step-by-step walkthrough aligned to the notebook is in `Readme/README.detailed.md`.