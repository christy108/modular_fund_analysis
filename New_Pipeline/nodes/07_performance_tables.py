"""Per-portfolio performance tables: cumulative returns + risk metrics.

Node `performance_tables`: reproduces the table portion of Main.ipynb cell 51,
reusing StrategyPerformance.{cumulative_performance_table,performance_risk_metrics_table}
unchanged. Merges the former `cumulative_table` (08) and `risk_table` (09) nodes —
they consumed the same two frames off the portfolio bundle and each built its own
StrategyPerformance from them; one instance now serves both.

Both tables are indexed by portfolio with identical row keys, so they travel in ONE
tidy frame whose columns are prefixed ``<table>::<column>``. run.py splits them back
into cumulative_table.parquet / risk_table.parquet with row and column order intact,
so the parity artifacts are unchanged. Keeping the frame tidy (one row per portfolio)
rather than a pickle bundle is what keeps ``RowCountViz`` meaningful here.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process
from leonardo_nodes.viz import RowCountViz

from New_Pipeline._common import cfg_schema, open_schema, store

CONTRACT = Contract(
    name="performance_tables",
    intent="""Report each portfolio's realised performance: the horizon compound returns (1m, 3m, YTD,
1yr, 3yr, 5yr, 10yr, Since launch) and the risk metrics (Sharpe on excess returns, VaR 1%, Max
Drawdown), with Alpha + p-value(alpha) attached from ff3_parts_df for matching columns. Both are
formatted exactly as the notebook's tables. How the two are carried in one frame is left to the
Process.

Mandatory measures (enforced by schema / audits):
- one row per portfolio, shared by both tables (the Process raises if their row keys diverge)
- the fixed horizon columns and the Sharpe/VaR/MaxDD columns are present; cells are the notebook's
  formatted strings
- Alpha/p-value(alpha) appear only for portfolios present in ff3_parts_df

Surfaces: portfolio row count (``RowCountViz``).""",
    input_schema={"port": open_schema(), "ff3_parts_df": open_schema(), "cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[RowCountViz(title="Performance table rows")],
)

@process(tag="performance_tables@v1", contract="performance_tables", author="refactor")
def performance_tables_v1(port, ff3_parts_df, cfg):
    from pathlib import Path

    import pandas as pd

    from functions.portfolio_metrics.Strategy_Perfomance import StrategyPerformance
    from New_Pipeline.boundary import pd_to_pl, unpack_obj

    P = unpack_obj(port)
    table_returns = P["table_returns"]
    table_excess = P["table_excess"]

    # ff3_alphas carries both the level table and the rolling alphas; take the level one.
    ff3 = unpack_obj(ff3_parts_df)["ff3_parts_df"]

    # ONE StrategyPerformance for both tables. cumulative_performance_table never reads
    # self.ff3_parts_df (only performance_risk_metrics_table does), so passing ff3 here
    # is inert for the cumulative table — the previous two-object form is preserved.
    sp = StrategyPerformance(table_returns, ff3_parts_df=ff3, excess_returns=table_excess)
    out_dir = Path("./runs/tables")
    cumulative = sp.cumulative_performance_table(csv_path=out_dir / "strategy_cumulative_performance.csv")
    risk = sp.performance_risk_metrics_table(csv_path=out_dir / "strategy_performance_metrics.csv")

    # Guard rather than let pd.concat silently align/pad if the two ever diverge.
    if list(cumulative.index) != list(risk.index):
        raise ValueError(
            f"portfolio rows differ between tables: "
            f"cumulative={list(cumulative.index)} risk={list(risk.index)}"
        )

    # Literal, not a module constant: an archived Process is re-executed in a fresh
    # namespace, so it must not reference module-level names. run.py's _SPLIT_SEP is
    # the matching half — keep the two in sync.
    sep = "::"
    combined = pd.concat(
        [cumulative.add_prefix(f"cumulative_table{sep}"), risk.add_prefix(f"risk_table{sep}")],
        axis=1,
    )
    print(combined.head())
    return pd_to_pl(combined, index_name="portfolio")


NODE = Node(
    name="performance_tables",
    contract=CONTRACT,
    store=store,
    inputs=("port", "ff3_parts_df", "cfg"),
    outputs=("out",),
)
