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
    intent="""Load BOTH Fama-French factor series for the configured region -- FF3 (mktrf, smb,
hml, rf) and FF5 (+ rmw, cma) -- applying the JPY-numeraire conversion to both when
configured (Japan + JPY).

Each specification is read from its OWN file: *_3_Factors.csv for FF3 and *_5_Factors.csv
for FF5. They are not interchangeable and neither is derived from the other -- Ken French
builds the FF5 SMB from the size x value, size x profitability and size x investment sorts,
so it is a different series from the FF3 SMB (US 2026-01: 2.12 vs 3.21). Mixing them would
silently misattribute the size premium.

Mandatory measures (enforced by schema / audits):
- monthly factor rows with mktrf, smb, hml, rf present for the configured region (FF3)
- the same months with mktrf, smb, hml, rmw, cma, rf present (FF5)

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

    # Both specifications, each from its own file. Loaded unconditionally: every run
    # reports FF3 and FF5 side by side, so there is no config knob that can leave a run
    # without one of them.
    fama_french = get_famafrench_factors(
        C["start_year"], C["end_year"], C["fama_factor_region"],
        3, download_developed_ff_data=False,
    )
    fama_french_5 = get_famafrench_factors(
        C["start_year"], C["end_year"], C["fama_factor_region"],
        5, download_developed_ff_data=False,
    )

    # JPY numeraire (Japanese-investor case) needs fx_rates; only reached for
    # region_analysis == "Japan" with fama_factors_currency_if_Japan == "JPY".
    # convert_factors_to_jpy auto-adapts to the factor count -- it scales rmw/cma too
    # when they are present (process_data.py, "if c in ff.columns" loop).
    if C["region_analysis"] == "Japan" and C["fama_factors_currency_if_Japan"] == "JPY":
        from functions.data_functions.get_data import get_processed_fx_rates

        fx_rates = get_processed_fx_rates(C["end_year"])
        fama_french = convert_factors_to_jpy(fama_french, fx_rates, C["RF_JAPAN_PATH"])
        fama_french_5 = convert_factors_to_jpy(fama_french_5, fx_rates, C["RF_JAPAN_PATH"])

    return pack_obj({"fama_french": fama_french, "fama_french_5": fama_french_5})


NODE = Node(
    name="load_fama_french",
    contract=CONTRACT,
    store=store,
    inputs=("cfg",),
    outputs=("out",),
)
