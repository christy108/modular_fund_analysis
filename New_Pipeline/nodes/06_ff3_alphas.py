"""Fama-French alphas: the static FF3 regression table and the rolling alphas together.

Node `ff3_alphas`: reproduces Main.ipynb cells 48 (ff3_parts_df) and 43 (rolling alphas),
reusing functions/portfolio_metrics/fama_french.{ff3_regressions,rolling_ff_alphas} and
functions.low_high unchanged. Merges the former `ff3_parts` (06) and `rolling_alphas` (07)
nodes so the level alpha and its rolling history are produced, recorded and exported as one
unit — they are read together.

The two results have no common key (a 9-row metric x portfolio table vs a ~1000-row long
date/label/window frame), so they travel as a lossless pickle bundle rather than one frame.
That would normally make ``RowCountViz`` report 1, so this Contract declares two *custom*
statistics instead, keeping both row counts visible on the dashboard and in every manifest.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process
from leonardo_nodes.viz import BarComparisonViz

from New_Pipeline._common import cfg_schema, open_schema, store
from New_Pipeline.boundary import unpack_obj


def _ff3_rows(df) -> int:
    """Statistic: FF3 statistic rows carried in the bundle."""
    return int(len(unpack_obj(df)["ff3_parts_df"]))


def _rolling_rows(df) -> int:
    """Statistic: rolling-alpha observations carried in the bundle."""
    return int(len(unpack_obj(df)["rolling_alphas"]))


CONTRACT = Contract(
    name="ff3_alphas",
    intent="""Report the FF3 factor attribution of the analysed portfolios at both horizons: the level
statistics (alpha, betas on mktrf/smb/hml, p-values, Adj. R^2) for the Low and High quantile of each
signal plus the High-Low spreads, and the rolling alphas of those same portfolios at each configured
window. Which portfolios are analysed and how many factors are used come from cfg; the estimator is
left to the Process.

Mandatory measures (enforced by schema / audits):
- the level statistics carry one column per portfolio label, in signal-insertion order then spreads
- one rolling alpha per (date, label, window) for each analysed portfolio
- both results are present in the output bundle (row counts surfaced separately)

Surfaces: FF3 statistic rows (``BarComparisonViz``); rolling-alpha rows (``BarComparisonViz``).""",
    input_schema={"port": open_schema(), "cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[
        BarComparisonViz(statistic="ff3_rows", title="FF3 statistic rows",
                         custom={"ff3_rows": _ff3_rows}),
        BarComparisonViz(statistic="rolling_rows", title="Rolling-alpha rows",
                         custom={"rolling_rows": _rolling_rows}),
    ],
)


@process(tag="ff3_alphas@v1", contract="ff3_alphas", author="refactor")
def ff3_alphas_v1(port, cfg):
    import json

    import pandas as pd

    from functions.functions import low_high
    from functions.portfolio_metrics.fama_french import ff3_regressions, rolling_ff_alphas
    from New_Pipeline.boundary import pack_obj, unpack_obj

    C = json.loads(cfg["json"][0])
    P = unpack_obj(port)
    signal_quantiles = P["signal_quantiles"]
    fama_french = P["fama_french"]
    signal_names = P["signal_names"]
    spread_signals = P["spread_signals"]
    Excess_returns_sample = P["Excess_returns_sample"]
    base_analysis_selection = P["base_analysis_selection"]
    _bucket_to_col = P["bucket_to_col"]
    _bucket_to_prefix = P["bucket_to_prefix"]

    # ---- cell 48: level FF3 statistics (ff3_parts_df) --------------------- #
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

    # ---- cell 43: rolling alphas (windows 40 and 24) --------------------- #
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

    return pack_obj({"ff3_parts_df": ff3_parts_df, "rolling_alphas": long})


NODE = Node(
    name="ff3_alphas",
    contract=CONTRACT,
    store=store,
    inputs=("port", "cfg"),
    outputs=("out",),
)
