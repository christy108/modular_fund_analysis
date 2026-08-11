"""Load and regionally-process the tradable universe — pure data ingestion.

Node `load_universes`: reproduces the ingestion portion of Main.ipynb cell 26
verbatim, reusing functions/data_functions/{get_data,process_data}.py unchanged.
First of two nodes that used to be one (``build_global_universe``); the paired
downstream node (``merge_esg_provider``) handles the ESG merge + assembly. The
split makes ingestion identical across every ESG configuration — the ESG choice
becomes a genuinely interchangeable Process, not an ``if/elif`` inside one process.

Output is a lossless (pickle) bundle carrying the three regionally-processed
universes plus fx_rates. No ESG column is attached yet.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process

from New_Pipeline._common import cfg_schema, open_schema, store

CONTRACT = Contract(
    name="load_universes",
    intent="""Load the three regional Compustat universes (USA / RoW / Japan) and FX rates for the
configured window, then regionally-process each (currency conversion when configured, Japan
fiscal-year alignment). No ESG columns are attached here — that belongs to the paired
``merge_esg_provider`` node so the ESG choice is picked as an interchangeable Process rather
than branched inside this Process. The window and FX-conversion knobs are read from cfg.

Mandatory measures (enforced by schema / audits):
- three per-region universes with return and market-cap columns, no ESG column
- fx_rates present for the configured end year

Surfaces: (none — output is a lossless pickle bundle, not a tidy frame; a plain
``RowCountViz`` would always report 1 and add no information).""",
    input_schema={"cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[],
)


@process(tag="load_universes@v1", contract="load_universes", author="refactor")
def load_universes_v1(cfg):
    import json

    from functions.data_functions.get_data import (
        get_japan_universe,
        get_processed_fx_rates,
        get_row_universe,
        get_usa_universe,
    )
    from functions.data_functions.process_data import (
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

    return pack_obj({
        "fx_rates": fx_rates,
        "usa_universe": usa_universe,
        "row_universe": row_universe,
        "japan_universe": japan_universe,
    })


NODE = Node(
    name="load_universes",
    contract=CONTRACT,
    store=store,
    inputs=("cfg",),
    outputs=("out",),
)
