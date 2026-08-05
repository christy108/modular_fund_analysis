"""Cumulative returns table (1m..Since launch).

Node `cumulative_table`: reproduces the cumulative-table portion of Main.ipynb
cell 51, reusing StrategyPerformance.cumulative_performance_table unchanged. The
include-all table inputs are prebuilt in build_portfolios. Emits the tidy formatted
table (rows under a `portfolio` column).
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process
from leonardo_nodes.viz import RowCountViz

from pipeline._common import cfg_schema, open_schema, store

CONTRACT = Contract(
    name="cumulative_table",
    intent="""Compute the horizon compound returns (1m, 3m, YTD, 1yr, 3yr, 5yr, 10yr, Since launch)
per portfolio as formatted percentages — reproducing the cumulative table exactly.

Mandatory measures (enforced by schema / audits):
- one row per portfolio; the fixed horizon columns; cells are the notebook's formatted % strings

Surfaces: portfolio row count (``RowCountViz``).""",
    input_schema={"port": open_schema(), "cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[RowCountViz(title="Cumulative table rows")],
)


@process(tag="cumulative_table@v1", contract="cumulative_table", author="refactor")
def cumulative_table_v1(port, cfg):
    from pathlib import Path

    from functions.portfolio_metrics.Strategy_Perfomance import StrategyPerformance
    from pipeline.boundary import pd_to_pl, unpack_obj

    P = unpack_obj(port)
    table_returns = P["table_returns"]
    table_excess = P["table_excess"]

    sp = StrategyPerformance(table_returns, ff3_parts_df=None, excess_returns=table_excess)
    out_dir = Path("./runs/tables")
    cumulative_table = sp.cumulative_performance_table(
        csv_path=out_dir / "strategy_cumulative_performance.csv"
    )
    return pd_to_pl(cumulative_table, index_name="portfolio")


NODE = Node(
    name="cumulative_table",
    contract=CONTRACT,
    store=store,
    inputs=("port", "cfg"),
    outputs=("out",),
)
