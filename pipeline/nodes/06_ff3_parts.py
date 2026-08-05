"""Fama-French 3-factor regression table (ff3_parts_df).

Node `ff3_parts`: reproduces Main.ipynb cell 48 verbatim, reusing
functions/portfolio_metrics/fama_french.ff3_regressions and functions.low_high.
Emits the tidy table (rows = FF3 statistics under a `metric` column).
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process
from leonardo_nodes.viz import RowCountViz

from pipeline._common import cfg_schema, open_schema, store

CONTRACT = Contract(
    name="ff3_parts",
    intent="""Run the FF3 OLS (HC1) of each portfolio's excess return on mktrf/smb/hml, keep the Low
and High quantile columns per signal (in signal-insertion order), append the High-Low spread
regressions, and round to 2dp — reproducing ff3_parts_df exactly.

Mandatory measures (enforced by schema / audits):
- rows are the FF3 statistics (alpha, betas, p-values, Adj. R^2); one column per portfolio label
- column order follows signal-insertion order then the spreads

Surfaces: statistic row count (``RowCountViz``).""",
    input_schema={"port": open_schema(), "cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[RowCountViz(title="FF3 statistic rows")],
)


@process(tag="ff3_parts@v1", contract="ff3_parts", author="refactor")
def ff3_parts_v1(port, cfg):
    import json

    import pandas as pd

    from functions.functions import low_high
    from functions.portfolio_metrics.fama_french import ff3_regressions
    from pipeline.boundary import pack_obj, pd_to_pl, unpack_obj  # noqa: F401

    C = json.loads(cfg["json"][0])
    P = unpack_obj(port)
    signal_quantiles = P["signal_quantiles"]
    fama_french = P["fama_french"]
    signal_names = P["signal_names"]
    spread_signals = P["spread_signals"]
    Excess_returns_sample = P["Excess_returns_sample"]

    ff3_parts = [
        low_high(
            ff3_regressions(signal_quantiles[col], fama_french.reset_index(drop=True)),
            signal_names[col],
        )
        for col in signal_quantiles
    ]

    take_high_minus_low = True
    if take_high_minus_low:
        for _label, _df in spread_signals.items():
            ff3_parts.append(ff3_regressions(_df, fama_french.reset_index(drop=True)))

    if C["show_sample_portfolio"]:
        ff3_parts.append(ff3_regressions(Excess_returns_sample, fama_french.reset_index(drop=True)))

    ff3_parts_df = pd.concat(ff3_parts, axis=1).round(2)
    print(ff3_parts_df.head())
    return pd_to_pl(ff3_parts_df, index_name="metric")


NODE = Node(
    name="ff3_parts",
    contract=CONTRACT,
    store=store,
    inputs=("port", "cfg"),
    outputs=("out",),
)
