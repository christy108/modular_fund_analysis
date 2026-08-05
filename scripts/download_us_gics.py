"""One-off: download the US GICS classification cache from WRDS (INTERACTIVE).

Why: the `esg_full_universe` path needs ``data/GICS/gics_comp_<region>_<end_year>.csv``.
Only the Japan file ships with the repo; the US file must be pulled from WRDS, which
requires an interactive WRDS login. Run this yourself once:

    cd /Users/cbruce1/Documents/GitHub/modular_fund_analysis
    .venv/bin/python -m scripts.download_us_gics            # United_States, 2024
    .venv/bin/python -m scripts.download_us_gics Japan 2024 # other region/year

It builds the universe from the cached local extracts (no WRDS needed for that),
then makes the single WRDS GICS call and writes the CSV to ./data/GICS/. After it
finishes, the pipeline + notebook can run `esg_full_universe` with
`download_gics_data=False` and be parity-gated headlessly.
"""

from __future__ import annotations

import sys


def main(region_analysis: str = "United_States", end_year: int = 2024) -> None:
    from functions.data_functions.get_data import (
        get_gics_by_gvkey,
        get_japan_universe,
        get_processed_fx_rates,
        get_row_universe,
        get_usa_universe,
    )
    from functions.data_functions.process_data import (
        process_global_universe,
        process_japan_universe,
        process_row_universe,
        process_usa_universe,
    )

    start_year = 2015
    convert_to_USD = region_analysis not in ("United_States", "North_America_and_Canada")
    currency_map = {
        "United_States": ["USD"],
        "North_America_and_Canada": ["USD"],
        "Europe": ["EUR"],
        "Japan": ["JPY"],
    }
    currency_filter = currency_map.get(region_analysis, ["EUR", "USD", "JPY"])

    fx_rates = get_processed_fx_rates(end_year)
    usa = process_usa_universe(get_usa_universe(start_year, end_year, download_wrds_data=False))
    row = process_row_universe(get_row_universe(start_year, end_year, download_wrds_data=False), fx_rates, convert_to_USD)
    jpn = process_japan_universe(get_japan_universe(start_year, end_year, download_wrds_data=False), fx_rates, convert_to_USD, 3)
    for u in (usa, row, jpn):
        u["esg"] = 100
    global_universe = process_global_universe(usa, row, jpn, currency_filter, 0.95, "none")
    global_universe["gvkey"] = global_universe["gvkey"].astype(str).str.zfill(6)

    print(f"Universe built ({global_universe['gvkey'].nunique()} gvkeys). Calling WRDS for GICS ...")
    get_gics_by_gvkey(global_universe, region_analysis, end_year, download_gics_data=True)
    print(f"Done. Wrote ./data/GICS/gics_comp_{region_analysis}_{end_year}.csv")


if __name__ == "__main__":
    region = sys.argv[1] if len(sys.argv) > 1 else "United_States"
    year = int(sys.argv[2]) if len(sys.argv) > 2 else 2024
    main(region, year)
