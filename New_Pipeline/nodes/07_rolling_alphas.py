"""Rolling Fama-French alphas (windows 40 and 24).

Node `rolling_alphas`: reproduces Main.ipynb cell 43 verbatim, reusing
functions/portfolio_metrics/fama_french.rolling_ff_alphas. Emits a tidy long frame
(date, label, window, alpha).
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process
from leonardo_nodes.viz import RowCountViz

from New_Pipeline._common import cfg_schema, open_schema, store

CONTRACT = Contract(
    name="rolling_alphas",
    intent="""Compute rolling FF3 alphas for the analysed portfolios at both window sizes (40 and 24
months), stacked with a window discriminator — the series behind the rolling-alpha plots.

Mandatory measures (enforced by schema / audits):
- one alpha per (date, label, window) for each analysed portfolio

Surfaces: rolling-alpha row count (``RowCountViz``).""",
    input_schema={"port": open_schema(), "cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[RowCountViz(title="Rolling-alpha rows")],
)


@process(tag="rolling_alphas@v1", contract="rolling_alphas", author="refactor")
def rolling_alphas_v1(port, cfg):
    import json

    import pandas as pd

    from functions.portfolio_metrics.fama_french import rolling_ff_alphas
    from New_Pipeline.boundary import pd_to_pl, unpack_obj

    C = json.loads(cfg["json"][0])
    P = unpack_obj(port)
    signal_quantiles = P["signal_quantiles"]
    signal_names = P["signal_names"]
    spread_signals = P["spread_signals"]
    Excess_returns_sample = P["Excess_returns_sample"]
    base_analysis_selection = P["base_analysis_selection"]
    _bucket_to_col = P["bucket_to_col"]
    _bucket_to_prefix = P["bucket_to_prefix"]
    fama_french = P["fama_french"]

    rolling_alpha_selection = base_analysis_selection
    _valid_buckets = {"high", "low"}
    _invalid = sorted({b for _, b in rolling_alpha_selection} - _valid_buckets)
    if _invalid:
        raise ValueError(f"Invalid bucket(s) in analysis_selection: {_invalid}. Use 'high' or 'low'.")
    _missing = sorted({c for c, _ in rolling_alpha_selection} - set(signal_quantiles))
    if _missing:
        raise KeyError(f"Signal key(s) in analysis_selection not found in signal_quantiles: {_missing}")

    rolling_signals_arg = [
        {
            "label": f"{_bucket_to_prefix[bucket]} {signal_names[col]}",
            "returns": signal_quantiles[col],
            "alpha_column": _bucket_to_col[bucket],
        }
        for col, bucket in rolling_alpha_selection
    ]
    if C["show_sample_portfolio"]:
        rolling_signals_arg.append({"label": "Sample", "returns": Excess_returns_sample, "alpha_column": "Sample"})
    for _label, _df in spread_signals.items():
        rolling_signals_arg.append({"label": _label, "returns": _df, "alpha_column": _label})

    n_factors = C["ff_factors_number"]
    w40 = None
    try:
        w40 = rolling_ff_alphas(signals=rolling_signals_arg, fama_french=fama_french, window_size=40, n_factors=n_factors)
    except Exception as e:  # matches notebook's guarded call
        print(f"Error in rolling_ff_alphas: {e}")
    w24 = rolling_ff_alphas(signals=rolling_signals_arg, fama_french=fama_french, window_size=24, n_factors=n_factors)

    frames = []
    for window, dic in [(40, w40), (24, w24)]:
        if dic is None:
            continue
        for label, s in dic.items():
            d = s.reset_index()
            d.columns = ["date", "alpha"]
            d["label"] = label
            d["window"] = window
            frames.append(d)
    long = pd.concat(frames, axis=0, ignore_index=True) if frames else pd.DataFrame(
        columns=["date", "alpha", "label", "window"]
    )
    return pd_to_pl(long)


NODE = Node(
    name="rolling_alphas",
    contract=CONTRACT,
    store=store,
    inputs=("port", "cfg"),
    outputs=("out",),
)
