"""Compute portfolio constituent counts by category over time (numeric plot data).

Node `build_constituents`: reproduces the numeric parts of Main.ipynb cells 58 & 59,
reusing PortfolioConstituents unchanged. Emits a lossless (pickle) bundle of the
counts-by-category frames plus the holdings-over-time membership table — the numeric
data behind the constituent plots (verified numerically, per the plan).
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process
from leonardo_nodes.viz import RowCountViz

from New_Pipeline._common import cfg_schema, open_schema, store

CONTRACT = Contract(
    name="build_constituents",
    intent="""For the pinned sort key (signal_2, or the ESG column under esg_full_universe), reproduce
the quantile membership each formation month and count constituents by category (Industry, and loc
outside the ESG-universe mode) over time, plus the high-bucket holdings — the numeric data behind the
constituent plots.

Mandatory measures (enforced by schema / audits):
- counts are non-negative integers per (date, portfolio, category_value)

Surfaces: constituent-count bundle (``RowCountViz``).""",
    input_schema={"port": open_schema(), "cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[RowCountViz(title="Constituents bundle")],
)


@process(tag="build_constituents@v1", contract="build_constituents", author="refactor")
def build_constituents_v1(port, cfg):
    import json

    import pandas as pd

    from functions.portfolio_metrics.Portfolio_Constituents import PortfolioConstituents
    from New_Pipeline.boundary import pack_obj, unpack_obj

    C = json.loads(cfg["json"][0])
    P = unpack_obj(port)
    signal_quantile_constituents = P["signal_quantile_constituents"]
    global_universe = P["global_universe"]

    esg_full = C["esg_full_universe"]
    universe_signals = C["universe_signals"]
    key = next(iter(universe_signals)) if esg_full else "signal_2"
    constituents = signal_quantile_constituents[key]

    pc2 = PortfolioConstituents(constituents, global_universe, portfolio_type="univariate_split")

    cats = ["Industry"] if esg_full else ["Industry", "loc"]
    out: dict = {}
    for cat in cats:
        _d, _wide = pc2._counts_by_category_over_time(
            cat, portfolio_key=None, analyse_all_portfolios_at_once=False
        )
        w = _wide.reset_index()
        w.columns = [str(c) for c in w.columns]
        out[f"constituents_{cat}"] = w

    # cell 59: high-bucket holdings over time
    K = C["no_simple_quantiles"]
    inspect = K - 1
    rows = []
    for _ms in pc2.constituents:
        _names = _ms.iloc[inspect]
        for _gi in list(_names):
            rows.append({"date": pd.to_datetime(_ms.name), "gvkey_iid": str(_gi), "gvkey": str(_gi).split("_")[0]})
    holdings = pd.DataFrame(rows).sort_values(["date", "gvkey_iid"]).reset_index(drop=True)
    out["holdings_over_time"] = holdings.reset_index()
    out["holdings_over_time"].columns = [str(c) for c in out["holdings_over_time"].columns]

    return pack_obj(out)


NODE = Node(
    name="build_constituents",
    contract=CONTRACT,
    store=store,
    inputs=("port", "cfg"),
    outputs=("out",),
)
