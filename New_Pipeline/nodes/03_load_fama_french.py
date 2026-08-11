"""Load Fama-French factors for the configured region / numeraire.

Node `load_fama_french`: reproduces the factor portion of Main.ipynb cell 26,
reusing functions/data_functions/get_data.get_famafrench_factors unchanged.
Carried losslessly (pickle) since prepare consumes the raw pandas factor frame.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process

from New_Pipeline._common import cfg_schema, open_schema, store

CONTRACT = Contract(
    name="load_fama_french",
    intent="""Load the Fama-French factor series (mktrf, smb, hml, rf) for the region and factor count
in cfg, applying the JPY-numeraire conversion when configured (Japan + JPY). FF5 is out of scope.

Mandatory measures (enforced by schema / audits):
- monthly factor rows with mktrf, smb, hml, rf present for the configured region

Surfaces: (none — output is a lossless pickle bundle, not a tidy frame; a plain
``RowCountViz`` would always report 1 and add no information).""",
    input_schema={"cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[],
)


@process(tag="load_fama_french@v1", contract="load_fama_french", author="refactor")
def load_fama_french_v1(cfg):
    import json

    from functions.data_functions.get_data import get_famafrench_factors
    from functions.data_functions.process_data import convert_factors_to_jpy
    from New_Pipeline.boundary import pack_obj

    C = json.loads(cfg["json"][0])

    fama_french = get_famafrench_factors(
        C["start_year"], C["end_year"], C["fama_factor_region"],
        C["ff_factors_number"], download_developed_ff_data=False,
    )

    # JPY numeraire (Japanese-investor case) needs fx_rates; only reached for
    # region_analysis == "Japan" with fama_factors_currency == "JPY".
    if C["region_analysis"] == "Japan" and C["fama_factors_currency"] == "JPY":
        from functions.data_functions.get_data import get_processed_fx_rates

        fx_rates = get_processed_fx_rates(C["end_year"])
        fama_french = convert_factors_to_jpy(fama_french, fx_rates, C["RF_JAPAN_PATH"])

    return pack_obj({"fama_french": fama_french})


NODE = Node(
    name="load_fama_french",
    contract=CONTRACT,
    store=store,
    inputs=("cfg",),
    outputs=("out",),
)
