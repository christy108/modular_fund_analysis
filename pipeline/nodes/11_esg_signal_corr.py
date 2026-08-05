"""ESG vs behavioural-signal regression / correlation tables (diagnostic, gated).

Node `esg_signal_corr`: reproduces Main.ipynb cell 52 when enabled; returns a
sentinel frame when the gate is off (keeps the pipeline structure fixed). Full
implementation lands in task #6 (ESG variants); base_none is always gated off.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process
from leonardo_nodes.viz import RowCountViz

from pipeline._common import cfg_schema, open_schema, store

CONTRACT = Contract(
    name="esg_signal_corr",
    intent="""Diagnostic (LC path, a real ESG provider, not full-universe): regress the ESG score on
each behavioural signal and build the correlation matrix, at standardised and non-standardised
scales. Gated by cfg.show_esg_corr_matricies; returns a sentinel frame when off.

Mandatory measures (enforced by schema / audits):
- when enabled, output carries coefficient/SE/p per behavioural signal at each scale

Surfaces: (diagnostic) row count (``RowCountViz``).""",
    input_schema={"prep": open_schema(), "cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[RowCountViz(title="ESG corr diagnostic rows")],
)


@process(tag="esg_signal_corr@v1", contract="esg_signal_corr", author="refactor")
def esg_signal_corr_v1(prep, cfg):
    import json
    from pathlib import Path

    from functions.portfolio_metrics.signal_correlation import (
        esg_signal_relationship_outputs,
        masked_raw_value_df,
    )
    from pipeline.boundary import empty_sentinel, pack_obj, unpack_obj

    C = json.loads(cfg["json"][0])
    enabled = C["show_esg_corr_matricies"] and C["esg_choice"] != "none" and not C["esg_full_universe"]
    if not enabled:
        return empty_sentinel()

    P = unpack_obj(prep)
    signal_df = P["signal_df"]
    signal_names = P["signal_names"]
    global_universe = P["global_universe"]
    method = C["esg_corr_method"]

    out = Path("./runs/esg_corr")  # tables also written to CSV/PNG here (side outputs)
    reg_s, corr_s = esg_signal_relationship_outputs(
        signal_df, signal_names, out, out, method=method, scale_tag="standardised", show=False
    )
    non_norm = masked_raw_value_df(global_universe, signal_df, signal_names)
    reg_ns, corr_ns = esg_signal_relationship_outputs(
        non_norm, signal_names, out, out, method=method, scale_tag="non_standardised", show=False
    )
    return pack_obj({
        "esg_reg_standardised": reg_s,
        "esg_corr_standardised": corr_s,
        "esg_reg_non_standardised": reg_ns,
        "esg_corr_non_standardised": corr_ns,
    })


NODE = Node(
    name="esg_signal_corr",
    contract=CONTRACT,
    store=store,
    inputs=("prep", "cfg"),
    outputs=("out",),
)
