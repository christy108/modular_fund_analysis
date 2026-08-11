"""Assemble the global tradable universe (prices, mktcap, FX, ESG merge).

Node `build_global_universe`: reproduces the universe portion of Main.ipynb cell 26
verbatim, reusing functions/data_functions/{get_data,process_data}.py unchanged.
Output is a lossless (pickle) bundle carrying the global universe plus the raw
per-region universes + fx_rates (needed by the ESG-coverage diagnostic later).
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process

from New_Pipeline._common import cfg_schema, open_schema, store

CONTRACT = Contract(
    name="build_global_universe",
    intent="""Build the monthly global universe of tradable names with total returns, market cap and
currency, converting FX as configured and merging the ESG provider chosen by cfg.esg_choice (or a
neutral constant when esg_choice='none'). Region/currency filters and the provider are read from cfg.

Mandatory measures (enforced by schema / audits):
- one row per gvkey-month over the configured window, with a return and market-cap column
- the ESG column reflects exactly the provider named in cfg (or the neutral constant)

Surfaces: (none — output is a lossless pickle bundle, not a tidy frame; a plain
``RowCountViz`` would always report 1 and add no information).""",
    input_schema={"cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[],
)


@process(tag="build_global_universe@v1", contract="build_global_universe", author="refactor")
def build_global_universe_v1(cfg):
    import json

    from functions.data_functions.get_data import (
        get_japan_universe,
        get_msci_esg_merge_to_universe,
        get_processed_fx_rates,
        get_refinitive_snp_merge_to_universe,
        get_row_universe,
        get_snp_esg_merge_to_universe,
        get_usa_universe,
    )
    from functions.data_functions.process_data import (
        process_global_universe,
        process_japan_universe,
        process_row_universe,
        process_usa_universe,
    )
    from New_Pipeline.boundary import pack_obj

    C = json.loads(cfg["json"][0])
    start_year, end_year = C["start_year"], C["end_year"]

    fx_rates = get_processed_fx_rates(end_year)

    usa_universe = get_usa_universe(start_year, end_year, download_wrds_data=False)
    usa_universe = process_usa_universe(usa_universe)

    row_universe = get_row_universe(start_year, end_year, download_wrds_data=False)
    row_universe = process_row_universe(row_universe, fx_rates, C["convert_to_USD"])

    japan_universe = get_japan_universe(start_year, end_year, download_wrds_data=False)
    japan_universe = process_japan_universe(
        japan_universe, fx_rates, C["convert_to_USD"],
        C["japan_year_adjustment_split_month_for_two_or_one"],
    )

    esg_choice = C["esg_choice"]
    if esg_choice == "none":
        usa_universe["esg"] = 100
        row_universe["esg"] = 100
        japan_universe["esg"] = 100
    elif esg_choice == "refinitiv":
        usa_universe, row_universe, japan_universe = get_refinitive_snp_merge_to_universe(
            usa_universe, row_universe, japan_universe)
    elif esg_choice == "s&p":
        usa_universe, row_universe, japan_universe = get_snp_esg_merge_to_universe(
            usa_universe, row_universe, japan_universe)
    elif esg_choice == "msci":
        usa_universe, row_universe, japan_universe = get_msci_esg_merge_to_universe(
            usa_universe, row_universe, japan_universe, score_column=C["msci_score_column"])

    print("usa_universe unique gvkeys:", usa_universe["gvkey"].nunique())
    print("row_universe unique gvkeys:", row_universe["gvkey"].nunique())
    print("japan_universe unique gvkeys:", japan_universe["gvkey"].nunique())

    global_universe = process_global_universe(
        usa_universe, row_universe, japan_universe,
        C["currency_filter"], C["mktcap_covered"], esg_choice,
    )
    print("columns with year")
    print([c for c in global_universe.columns if c == "year" or c.startswith("year_")])

    global_universe["gvkey"] = global_universe["gvkey"].astype(str).str.zfill(6)
    print("global_universe unique gvkeys:", global_universe["gvkey"].nunique())

    return pack_obj({
        "global_universe": global_universe,
        "usa_universe": usa_universe,
        "row_universe": row_universe,
        "japan_universe": japan_universe,
        "fx_rates": fx_rates,
    })


NODE = Node(
    name="build_global_universe",
    contract=CONTRACT,
    store=store,
    inputs=("cfg",),
    outputs=("out",),
)
