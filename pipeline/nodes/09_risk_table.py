"""Risk metrics table (Sharpe, VaR 1%, Max Drawdown, Alpha, p-value).

Node `risk_table`: reproduces the risk-table portion of Main.ipynb cell 51, reusing
StrategyPerformance.performance_risk_metrics_table unchanged. Takes ff3_parts_df
(tidy) to attach Alpha/p-value(alpha). Emits the tidy formatted table.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process
from leonardo_nodes.viz import RowCountViz

from pipeline._common import cfg_schema, open_schema, store

CONTRACT = Contract(
    name="risk_table",
    intent="""Compute Sharpe (annualised, on excess returns), VaR 1% and Max Drawdown per portfolio,
and attach Alpha + p-value(alpha) from ff3_parts_df for matching columns — reproducing the risk table
exactly.

Mandatory measures (enforced by schema / audits):
- one row per portfolio with Sharpe/VaR/MaxDD and (where available) Alpha/p-value(alpha)

Surfaces: portfolio row count (``RowCountViz``).""",
    input_schema={"port": open_schema(), "ff3_parts_df": open_schema(), "cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[RowCountViz(title="Risk table rows")],
)


@process(tag="risk_table@v1", contract="risk_table", author="refactor")
def risk_table_v1(port, ff3_parts_df, cfg):
    from pathlib import Path

    from functions.portfolio_metrics.Strategy_Perfomance import StrategyPerformance
    from pipeline.boundary import pd_to_pl, pl_to_pd, unpack_obj

    P = unpack_obj(port)
    table_returns = P["table_returns"]
    table_excess = P["table_excess"]

    # Restore ff3_parts_df (metric-indexed) from the tidy upstream frame.
    ff3 = pl_to_pd(ff3_parts_df, index="metric")

    sp = StrategyPerformance(table_returns, ff3_parts_df=ff3, excess_returns=table_excess)
    out_dir = Path("./runs/tables")
    risk_table = sp.performance_risk_metrics_table(
        csv_path=out_dir / "strategy_performance_metrics.csv"
    )
    return pd_to_pl(risk_table, index_name="portfolio")


NODE = Node(
    name="risk_table",
    contract=CONTRACT,
    store=store,
    inputs=("port", "ff3_parts_df", "cfg"),
    outputs=("out",),
)
