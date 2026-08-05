"""Sort into quantile portfolios and build excess returns + High-Low spreads.

Node `build_portfolios`: reproduces Main.ipynb cells 31, 34, 36, 37, 38, 39, 42, 43
(selection) and the cell-51 include-all table construction, reusing
functions/portfolio_strategy_design/Univariate_Portfolio.py and
functions/functions.set_first_row_to_zero unchanged. Emits a lossless (pickle)
bundle carrying everything the reporting nodes need.

MSCI benchmark (cell 37/38 MSCI_excess_returns) is intentionally omitted: it feeds
only a commented-out benchmark line and none of the six parity artifacts.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process
from leonardo_nodes.viz import RowCountViz

from pipeline._common import cfg_schema, open_schema, store

CONTRACT = Contract(
    name="build_portfolios",
    intent="""Reconstruct the return/signal pivots from the prepared panel, sort each signal into
quantile portfolios (p_1..p_K), subtract rf to get excess returns, add the market row, and form the
per-signal High-Low spread (p_K - p_1). Which signals/legs are analysed (and any ESG leg) comes from
cfg. Also builds the include-all cumulative/risk table inputs (cell 51).

Mandatory measures (enforced by schema / audits):
- output carries, in signal-insertion order, each signal's quantile excess-return series, its
  High-Low spread, the Market series and the constituents needed downstream

Surfaces: number of signals sorted (``RowCountViz``).""",
    input_schema={"prep": open_schema(), "cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[RowCountViz(title="Portfolio bundle")],
)


@process(tag="build_portfolios@v1", contract="build_portfolios", author="refactor")
def build_portfolios_v1(prep, cfg):
    import json

    import numpy as np
    import pandas as pd

    from functions.functions import set_first_row_to_zero
    from functions.portfolio_strategy_design.Univariate_Portfolio import (
        UnivariateQuantilePortfolio,
    )
    from pipeline.boundary import pack_obj, unpack_obj

    C = json.loads(cfg["json"][0])
    P = unpack_obj(prep)
    global_universe = P["global_universe"]
    global_returns = P["global_returns"]
    signals = P["signals"]
    signal_names = P["signal_names"]
    fama_french = P["fama_french"]

    K = C["no_simple_quantiles"]

    # ---- cell 31: drop columns (gvkeys) with inf values ------------------ #
    bad_columns = set()
    for df in signals.values():
        num = df.select_dtypes(include=[np.number])
        if num.empty:
            continue
        bad_columns.update(num.columns[np.isinf(num).any(axis=0)].tolist())
    bad_columns = list(bad_columns)
    print("gvekys dropped due to inf values:")
    print(bad_columns)
    signals = {name: df.drop(columns=bad_columns, errors="ignore") for name, df in signals.items()}

    # ---- cell 34: manual settings ---------------------------------------- #
    first_conditioning_set = 0
    no_simple_extremes_quantiles = 1
    take_extremes = False

    # ---- cell 36: quantile portfolios + constituents --------------------- #
    signal_quantiles: dict = {}
    signal_quantile_constituents: dict = {}
    for col, pivot in signals.items():
        U = UnivariateQuantilePortfolio(
            signal=pivot,
            returns=global_returns,
            n_quantiles=K,
            first_conditioning_set=first_conditioning_set,
            take_extremes=take_extremes,
            n_extremes_quantiles=no_simple_extremes_quantiles,
        )
        signal_quantiles[col] = U.compute_returns()
        signal_quantile_constituents[col] = U.get_constituents_over_time()

    # ---- cell 37/38: market factor + excess returns ---------------------- #
    market_factor = fama_french["mktrf"]
    for col in signal_quantiles:
        signal_quantiles[col] = signal_quantiles[col].sub(fama_french["rf"].values, axis=0)
    Excess_returns_sample = (
        global_returns.mean(axis=1).sub(fama_french["rf"].values, axis=0).to_frame("Sample")
    )

    # ---- cell 39: zeroed-first-row copies for compounding ---------------- #
    global_returns_cum = set_first_row_to_zero(global_returns)
    signal_quantiles_cum = {c: set_first_row_to_zero(df) for c, df in signal_quantiles.items()}
    market_factor_cum = market_factor.copy()
    market_factor_cum.iloc[0] = 0

    # ---- cell 42: per-signal High-Low spreads ---------------------------- #
    hml_directions = C["hml_directions"]
    _hml_hi, _hml_lo = f"p_{K}", "p_1"
    spread_signals: dict = {}
    spread_cum: dict = {}
    for _sig, _dir in hml_directions.items():
        if _sig not in signal_quantiles:
            raise KeyError(f"{_sig!r} in hml_directions not found in signal_quantiles (available: {list(signal_quantiles)})")
        if _dir != "high_minus_low":
            raise ValueError(f"Unknown direction {_dir!r} for {_sig}; only 'high_minus_low' is supported")
        _label = f"High - Low {signal_names[_sig]}"
        spread_signals[_label] = (signal_quantiles[_sig][_hml_hi] - signal_quantiles[_sig][_hml_lo]).to_frame(_label)
        spread_cum[_label] = signal_quantiles_cum[_sig][_hml_hi] - signal_quantiles_cum[_sig][_hml_lo]

    # ---- cell 43: analysis selection ------------------------------------- #
    lc_signals = C["lc_signals"]
    esg_full_universe = C["esg_full_universe"]
    esg_choice = C["esg_choice"]
    base_analysis_selection = [(s, "high") for s in reversed(list(lc_signals))]
    if not esg_full_universe:
        base_analysis_selection.append(("signal_0", "low"))
    if esg_choice == "refinitiv":
        base_analysis_selection.append(("esg_refinitive", "high"))
    elif esg_choice == "s&p":
        base_analysis_selection.append(("esg_sp", "high"))
    elif esg_choice == "msci":
        base_analysis_selection.append(("esg_msci", "high"))

    _bucket_to_col = {"high": f"p_{K}", "low": "p_1"}
    _bucket_to_prefix = {"high": "High", "low": "Low"}

    # ---- cell 51: include-all cumulative/risk table inputs --------------- #
    show_sample_portfolio = C["show_sample_portfolio"]
    _all_gross = pd.DataFrame(index=global_returns_cum.index)
    if show_sample_portfolio:
        _all_gross["Sample"] = 1 + global_returns_cum.mean(axis=1).sub(fama_french["rf"].values, axis=0)
    _all_gross["Market"] = 1 + market_factor_cum
    _lc_keys = [k for k in signal_quantiles if k.startswith("signal_")]
    _esg_keys = [k for k in signal_quantiles if not k.startswith("signal_")]
    for _sig in list(reversed(_lc_keys)) + _esg_keys:
        _nm = signal_names.get(_sig, _sig)
        for _bkt in ("high", "low"):
            _all_gross[f"{_bucket_to_prefix[_bkt]} {_nm}"] = 1 + signal_quantiles_cum[_sig][_bucket_to_col[_bkt]]
    _table_returns = _all_gross.add(fama_french["rf"].values, axis=0) - 1
    _table_excess = _all_gross - 1
    for _label, _series in spread_cum.items():
        _table_returns[_label] = _series
        _table_excess[_label] = _series

    return pack_obj({
        "signal_quantiles": signal_quantiles,
        "signal_quantiles_cum": signal_quantiles_cum,
        "signal_quantile_constituents": signal_quantile_constituents,
        "spread_signals": spread_signals,
        "spread_cum": spread_cum,
        "signal_names": signal_names,
        "fama_french": fama_french,
        "market_factor_cum": market_factor_cum,
        "global_returns_cum": global_returns_cum,
        "Excess_returns_sample": Excess_returns_sample,
        "base_analysis_selection": base_analysis_selection,
        "bucket_to_col": _bucket_to_col,
        "bucket_to_prefix": _bucket_to_prefix,
        "table_returns": _table_returns,
        "table_excess": _table_excess,
        "global_universe": global_universe,
    })


NODE = Node(
    name="build_portfolios",
    contract=CONTRACT,
    store=store,
    inputs=("prep", "cfg"),
    outputs=("out",),
)
