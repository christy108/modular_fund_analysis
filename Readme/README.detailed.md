# Fund analysis — `Main.ipynb` walkthrough

This repository wires together **initiative / sustainability signals** from a “Golden” longitudinal company panel (LC) with **WRDS-style price + market-cap panels** (USA + ROW + Japan), then runs **monthly univariate quantile portfolios** (and an optional **sector-split** strategy), **Fama–French (FF3)** attribution, and **performance diagnostics**. The notebook is the orchestration layer; reusable logic lives under `functions/`.

---

## What the pipeline is trying to achieve

1. **Define interpretable signals** from granular initiative types (mapped into a small number of buckets, e.g. “advocacy / preparation / transformation”), expressed as **shares of total counted activities** per firm-year.
2. **Intersect** that panel with a **tradable equity universe** (USA + ROW + Japan; then filtered to the currencies you choose), with **publication-lagged** merges from fiscal year to price dates.
3. **Sort stocks each month** into quantile portfolios on standardized signals and measure **next-month** returns (classic portfolio-sort timing).
4. **Compare** strategies to a **broad benchmark (MSCI)** and to **FF3-adjusted** metrics, and **inspect who is in the portfolios** (industry, country, macro region).

---

## Prerequisites and inputs

- **Python**: NumPy, pandas, matplotlib; regressions use **statsmodels** (see `functions/portfolio_metrics/fama_french.py`).
- **Golden LC CSV**: path in the notebook (`golden_location`). The filename is versioned (e.g. `LC_dataset_v_2B1_20260409.csv`).
- **WRDS extracts / caches**: used by `get_usa_universe`, `get_row_universe`, and `get_japan_universe` (see `functions/data_functions/get_data.py`). The notebook currently calls these with `download_wrds_data=False` (cached/local unless you change it).
- **FX**: Federal Reserve H.10–style series consumed by `get_processed_fx_rates` (see `get_data.py`).
- **Fama–French factors**: downloaded or cached as expected by `get_famafrench_factors`.
- **MSCI file**: `./data/MSCI/MSCI_World.xlsx` for benchmark alignment in the notebook.
- **Outputs**: `./output/` CSVs and `./output/img/` figures from performance and plots.

---

## `functions/` map (where to read the implementation)

| Area | Module | Role |
|------|--------|------|
| Small utilities | `functions/functions.py` | `conditional_pct_change`, `standardize_pivot`, `low_high`, `set_first_row_to_zero` |
| Signal design | `functions/signal_design/signal_definitions.py` | defines `categories_dict` + user-facing signal names used in the notebook (`signal_0/1/2`) |
| LC panel | `functions/data_functions/process_lc.py` | `process_lc`, `map_sectors`, `filter_sum_activities_by_fiscal_year_quantiles` |
| WRDS / FX / FF / ESG / accounting | `functions/data_functions/get_data.py` | `get_usa_universe`, `get_row_universe`, `get_japan_universe`, `get_processed_fx_rates`, ESG merges, `get_famafrench_factors`, `get_processed_index`, `get_accounting_data` |
| Universe construction | `functions/data_functions/process_data.py` | `process_usa_universe`, `process_row_universe`, `process_japan_universe`, `process_global_universe` |
| Signal + returns prep | `functions/portfolio_strategy_design/univariate_sorting_preprocess.py` | `prepare_univariate_sorting_inputs` and helpers (merge LC, monthly returns, masking, z-scores) |
| Quantile portfolios | `functions/portfolio_strategy_design/Univariate_Portfolio.py` | `UnivariateQuantilePortfolio` |
| Sector strategy | `functions/portfolio_strategy_design/Sector_Portfolio.py` | `SectorPortfolio` |
| FF tables / rolling alpha | `functions/portfolio_metrics/fama_french.py` | `ff3_regressions`, `ff5_regressions`, `rolling_ff_alphas` (`n_factors` 3 or 5), plotting helper |
| Performance tables / charts | `functions/portfolio_metrics/Strategy_Perfomance.py` | `StrategyPerformance` |
| Constituent analytics | `functions/portfolio_metrics/Portfolio_Constituents.py` | `PortfolioConstituents` |

---

## Section-by-section: what happens in `Main.ipynb`

### 1. Dependencies

- Imports **NumPy**, **pandas**, **matplotlib**, and project modules.
- From `functions.functions`: `low_high` (keeps low/high quantile columns for compact FF tables), `set_first_row_to_zero` (aligns cumulative return paths).
- From `functions.signal_design.signal_definitions`: chooses the LC category dictionary and the display names for `signal_0/1/2`.
- From `functions.data_functions.get_data`: universe loaders (including Japan), FX, ESG merges, accounting merges, Fama–French factors, and index helper.
- From `functions.data_functions.process_data`: transforms that turn raw WRDS frames into a single `global_universe`.
- From `functions.portfolio_strategy_design.univariate_sorting_preprocess`: `prepare_univariate_sorting_inputs`, the “econometrics prep” step before sorting.

### Manual configuration (immediately after dependencies)

- **`start_year` / `end_year`**: sample window (comment notes ESG sources align for `start_year == 2013`).
- **`region_analysis`**: preset that drives currencies + FF region (e.g. `Europe_and_North_America_and_Japan` keeps `['EUR','USD','JPY']` and uses `fama_factor_region="Developed"`).
- **`esg_choice`**: `"none"`, `"refinitiv"`, `"s&p"`, `"refinitiv_n_s&p"` (controls ESG merges into the universe; `"none"` sets a constant ESG field).
- **`add_accounting_data`**: if true, merges accounting features into `global_universe` (reduces sample).
- **`top_x_by_industry_even_split`**: how many names to keep per industry in the sector-split strategy (`SectorPortfolio`).
- **`no_simple_quantiles`**: number of univariate quantile portfolios (columns `p_1` … `p_K`).
- **`alpha_bound`**: total tail mass trimmed from `sum_activities` **within each fiscal year** (split equally below/above; see `filter_sum_activities_by_fiscal_year_quantiles` in `process_lc.py`).
- **`mktcap_covered`**: keep names that cumulatively cover this fraction of **total market cap within (year, month, currency)** after sorting by cap (see `process_global_universe`).

### Golden Data

- Loads the **LC** dataset from disk. This is the initiative / disclosure panel that supplies `gvkey`, fiscal year `rfyear`, geography, GICS, and activity-type columns.

### Filters (region, currency, factor set)

- **`currency_filter`**: restricts `global_universe` to listings in those currencies (e.g. EUR and USD).
- **`convert_to_USD`**: controls FX conversion in ROW/Japan processing.
- **`drop_real_estate`**: drops Real Estate from LC before mapping industries.

---

### 2. Data

#### 2.1 LC dataset

**Cleaning and scope (`process_lc`)**

- Drops rows without `gvkey`; casts `gvkey` to string and `rfyear` to nullable integer.
- Requires core fields: `loc`, `MacroRegion`, GICS levels.
- Keeps macro regions: Asia-Pacific, Europe, United States and Canada.
- Restricts `rfyear` to `[start_year, end_year]`.

**Industry mapping (`map_sectors`)**

- Collapses some GICS level-1 sectors into broader groups (e.g. Energy + Materials → “Primary Industries”, discretionary + staples → “Consumer”, comms + IT → “ICT”, Financials + Real Estate → “Financial” when Real Estate is not dropped earlier).

**Optional filters**

- Real Estate drop; optional `loc` filter; commented options for stable panel or single-industry experiments.

**Category dictionary and activity aggregation**

- `categories_dict_*` maps each **raw LC column** (specific `TYPE` / `TYPE_SREC` labels) to an integer bucket **0, 1, 2, …**.
- The notebook aggregates into `sum_with_{k}` and **`sum_activities`** = sum of selected raw columns. That is the denominator for signal construction.

**Winsor-style trim on activity intensity**

- `filter_sum_activities_by_fiscal_year_quantiles` removes, **within each fiscal year**, the lowest `alpha_bound/2` and highest `alpha_bound/2` fraction of `sum_activities`. This reduces sensitivity to extreme reporting counts.

**Signals**

- For each bucket index `i`, **`signal_i` = `sum_with_i` / `sum_activities`**. These are **within-firm-year shares** (compositional signals), comparable across firms after later standardization.

**Diagnostic**

- Counts distinct `gvkey` for USA or Europe in LC before WRDS-driven filters narrow the tradable set.

#### 2.2 WRDS, Fama–French, FX, ESG, accounting

**FX (`get_processed_fx_rates`)**

- Loads/processes exchange rates so ROW market cap and total return index can be expressed in a common currency basis (see `process_row_universe`).

**USA / ROW / Japan universes**

- `get_usa_universe` loads or downloads primary US listings with market cap and total return index `tri`.
- `process_usa_universe` parses dates, string `gvkey`, sets `curcdd = USD`, and computes **`last_year`**: fiscal year used to merge LC fundamentals — **Jan–Jun** maps to **calendar_year − 2**, **Jul–Dec** to **calendar_year − 1** (publication / availability lag).

- `get_row_universe` loads or downloads global listings (with local-currency `mktcap_lcu`, `tri_lcu` and `curcdd`).
- `process_row_universe` merges FX, builds USD (or base) `mktcap` and `tri`, and applies the same **`last_year`** convention.
- `get_japan_universe` / `process_japan_universe` add Japan as a third leg of the investable universe, using the same conventions.

**ESG**

- If `esg_choice == 'none'`, the notebook sets `esg` to a constant so downstream code paths that expect the column still run.
- Otherwise, the notebook merges S&P / Refinitiv ESG signals into the USA/ROW universes via helpers in `get_data.py`.

**Accounting data (optional)**

- If `add_accounting_data == True`, the notebook calls `get_accounting_data(...)` after building the combined universe. This reduces the sample and adds features like `roa*`, `ros*`, `sales_intensity` used for diagnostics / extensions.

**Fama–French**

- `get_famafrench_factors` returns factor panels (notebook keeps both a base and five-factor object; the main pipeline uses the aligned FF frame after prep).

**Global universe (`process_global_universe`)**

- Concatenates USA and ROW with aligned columns; rescales `esg`; drops missing `mktcap`.
- Filters to **`currency_filter`**.
- Within each **(year, month, currency)**, sorts firms by market cap and keeps the **top `mktcap_covered`** of aggregate cap (drops the long tail of tiny names per currency area).
- Normalizes `gvkey` formatting for merges.

---

### 3. Univariate portfolio sorting

**`prepare_univariate_sorting_inputs`** (core; see `univariate_sorting_preprocess.py`)

1. **`intersect_gvkeys_and_filter`**: only securities with `gvkey` in **both** LC and WRDS-derived panel.
2. **`merge_lc_into_global_universe`**: merges initiative data on **`(gvkey, last_year) = (gvkey, rfyear)`** so signals align with information timing relative to month-end prices.
3. **`add_gvkey_iid_sort_clean`**: builds `gvkey_iid`, sorts, drops rows without `tri`.
4. **`to_monthly_last_trading_date`**: one row per security per month (last trading date in that calendar month).
5. **`compute_monthly_returns_long`**: month-on-month `tr` from `tri` with **`conditional_pct_change`** masking breaks longer than ~1 month (avoids spurious returns across gaps).
6. **`normalize_category_shares`**: converts raw activity columns to shares (again dividing by `sum_activities` in the long panel).
7. Optional **`apply_geo_filter`** (off in the notebook: `apply_geo_filter=False`).
8. **`dropna_std_cols_and_build_pivots`**: drops rows missing standardization keys, then builds wide matrices: **`global_returns`**, **`global_signal_0/1/2`**.
9. **`align_fama_french_to_returns`**: trims and reindexes FF to the return calendar.
10. **`apply_cross_signal_nan_mask`**: for each (date, asset), if **return or any requested signal** is NaN, all are set NaN — enforcing a **common sorting universe**.
11. **`standardize_all_signals`**: cross-sectionally z-scores each signal using groups defined by **`cols_standardization`** (notebook: `rfyear`, `curcdd`, `Industry`) — compares firms **within the same fiscal year, listing currency, and mapped industry**.
12. Returns a long merged frame plus aligned FF factors and a filename suffix used by downstream outputs.

**Manual sorting controls**

- `first_conditioning_set`: skip initial months before portfolio formation (useful when early data are thin).
- `take_extremes` / `no_simple_extremes_quantiles`: alternative slicing mode delegated to `univariate_portfolio_sorting` in `functions.py`.

#### 3.1 Univariate sorting (`UnivariateQuantilePortfolio`)

- For each formation date `i`, sorts the cross-section of the signal and forms **quantile portfolios**; assigns **realized return at `i+1`** (`compute_returns`). So outputs are **next-month return** series for `p_1…p_K`.
- **`get_constituents_over_time`** stores, for each date, which `gvkey_iid` fall in each bucket — used later for **portfolio composition charts**.

The notebook builds **three** sorters **U0, U1, U2** on `global_signal_0`, `global_signal_1`, and `global_signal_2`.

---

### 4. Sector split

**Intent**

- Instead of only global quantiles, form a portfolio that each month takes the **top X names per mapped `Industry`** on **`global_signal_2`**, then averages **industry-level next-month returns** with **equal weight across industries** (`equal_weight_mean_return`). This mitigates sector concentration in a single quantile strategy.

**Implementation notes (`Sector_Portfolio.py`)**

- Requires `global_universe` with `Industry` over time; the notebook builds `global_industry` pivot for alignment (commented alternative paths exist in the class).
- **`sector_split`**: target count per industry when using automatic even split (`manual_input_split=False`).

**Return preprocessing and MSCI**

- Loads MSCI World via `get_processed_index`, aligned to one of the return panels for dating.
- Subtracts **risk-free** from quantile returns, MSCI, and sector portfolio (`fama_french['rf']`).
- **`set_first_row_to_zero`**: sets initial row to zero on return panels so **cumulative plots** start from a common origin (MSCI and sector series are zeroed similarly in the notebook).

---

### 5. Fama–French

- Wraps sector returns in a single-column DataFrame for consistent labeling.
- **`ff3_regressions`**: for each return series column, runs **OLS** of **100 × excess return** on **mktrf, smb, hml** with **HC1** robust covariance; records alphas, betas, p-values, adjusted R².
- **`low_high`**: collapses each signal’s full quantile regression table to **low vs high** columns only, with readable labels (typo “pdvocacy” in label for signal 0).
- Concatenates into **`ff3_parts_df`** for use in performance reporting.

#### Rolling alpha

- **`rolling_ff_alphas`**: rolling window (notebook: **40 months**) of FF3 or FF5 alpha (`n_factors` matches `ff_factors_number`) for selected series — e.g. **high transformation** quantile (`p_{no_simple_quantiles}`) and the **sector equal-split** strategy. Aliases: `rolling_ff3_alphas`, `rolling_ff5_alphas`.
- **`plot_rolling_alpha_function`**: saves a time-series figure under `./output/img/`.

---

### 6. Performance metrics

- Builds **`global_gross_portfolio_returns`**: columns include **equal-weight market** from `global_returns`, **high transformation** quantile, **sector equal-split**, **MSCI benchmark** — constructed as **1 + excess** then converted back to simple **`portfolio_returns`** for compounding APIs.
- **`StrategyPerformance`**:
  - **`cumulative_performance_table`**: horizons (1m, 3m, YTD, 1yr, …, since launch) using **geometric compounding** of monthly simple returns.
  - **`performance_risk_metrics_table`**: risk summaries (see module for full metric set).
  - **`plot_cumulative_returns`**, **`plot_rolling_sharpe`** for multiple windows — outputs saved under `./output/img/`.
- Displays tables and repeats rolling-alpha plot with the prepared `rolling_alphas`.

---

### 7. Portfolio constituents

- **`PortfolioConstituents`** takes **`signal_2_simple_quantiles_constituents`** and **`global_universe`**.
- Joins constituents to **`Industry`**, **`loc`**, **`MacroRegion`** at formation dates (point-in-time last observation in universe).
- **`run_all_plots`**: time series of counts and **donut** charts for the **last** formation month; options documented in the markdown cell (`analyse_all_portfolios_at_once`, `all_sub_portfolios`).
- **`total_stocks_over_time`**: diagnostic for non-NaN breadth across quantiles.

---

## How to run

1. Ensure **data paths** in the notebook (`golden_location`, `./data/...`, MSCI path) exist on your machine.
2. Set the core switches (`region_analysis`, `esg_choice`, `add_accounting_data`, `no_simple_quantiles`) and confirm the implied `currency_filter` / `fama_factor_region` are what you intend.
3. Run cells **top to bottom**. If you enable live downloads, verify `get_data.py` is configured for your environment.

---

## Design choices worth remembering

- **Signals are shares** of categorized activities, then **standardized within (fiscal year, currency, mapped industry)** — a relative “style” measure, not raw counts.
- **Portfolio sorts use next-month returns**, so summary statistics are aligned with **predictive** portfolio tests rather than contemporaneous correlation.
- **`mktcap_covered` and LC trimming** materially change which firms enter the cross-section; tune them when interpreting breadth and performance.

---

## Typo in the notebook headings

Section **2.2** is titled “Fama-Frenmch” in the notebook; the code uses the standard **Fama–French** datasets and `functions/portfolio_metrics/fama_french.py`.
