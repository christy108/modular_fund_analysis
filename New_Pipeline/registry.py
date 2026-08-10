"""Assembly point: gather Contracts, register Processes, build & validate the Pipeline.

Nodes never reference their neighbours — all topology lives here (leonardo_nodes
principle: Pipeline owns the edges). Import this module to get:
    CONTRACTS      : {name -> Contract}
    NODE_MODULES   : the 13 node modules (each exposes CONTRACT + NODE + @process fns)
    build_pipeline(): a validated Pipeline
    register_processes(): ingest every @process into the shared store
"""

from __future__ import annotations

import importlib

from leonardo_nodes import Pipeline

from New_Pipeline._common import store

# Node modules are numbered by run order (nodes/NN_<name>.py). Filenames starting
# with a digit are not valid import identifiers, so they are loaded by string.
# run_experiment computes the true execution order from the DAG (topological_order);
# these numbers are just a readable reading order.
_NODE_ORDER = [
    "01_load_signal_lc",
    "02_build_global_universe",
    "03_load_fama_french",
    "04_prepare_panel",
    "05_build_portfolios",
    "06_ff3_parts",
    "07_rolling_alphas",
    "08_cumulative_table",
    "09_risk_table",
    "10_build_constituents",
    "11_esg_signal_corr",
    "12_esg_coverage",
]
NODE_MODULES = [importlib.import_module(f"New_Pipeline.nodes.{n}") for n in _NODE_ORDER]

CONTRACTS = {m.CONTRACT.name: m.CONTRACT for m in NODE_MODULES}

# Edges: "src_node.out" -> "dst_node.dst_port". `cfg` ports are intentionally left
# unconnected — they are external inputs bound per Experiment. prepare_panel already
# returns aligned factors, so there is no separate align node.
EDGES = [
    ("load_signal_lc.out", "prepare_panel.lc"),
    ("build_global_universe.out", "prepare_panel.global_universe"),
    ("load_fama_french.out", "prepare_panel.fama_french_raw"),
    ("prepare_panel.out", "build_portfolios.prep"),
    ("prepare_panel.out", "esg_signal_corr.prep"),
    ("prepare_panel.out", "esg_coverage.prep"),
    ("build_global_universe.out", "esg_coverage.universe"),
    ("load_signal_lc.out", "esg_coverage.lc"),
    ("build_portfolios.out", "build_constituents.port"),
    ("build_portfolios.out", "ff3_parts.port"),
    ("build_portfolios.out", "rolling_alphas.port"),
    ("build_portfolios.out", "cumulative_table.port"),
    ("build_portfolios.out", "risk_table.port"),
    ("ff3_parts.out", "risk_table.ff3_parts_df"),
]


def build_pipeline() -> Pipeline:
    """Construct the fund-analysis DAG (structure only)."""
    p = Pipeline(name="fund_analysis")
    for m in NODE_MODULES:
        p.add_node(m.NODE)
    for src, dst in EDGES:
        p.connect(src, dst)
    return p


def register_processes() -> dict:
    """Ingest every node module's @process functions into the shared store.

    Returns {tag -> process_id}. Skipped during pure structure validation, needed
    before running Experiments.
    """
    resolved: dict = {}
    for m in NODE_MODULES:
        resolved.update(store.register_all_processes(m, CONTRACTS))
    return resolved


if __name__ == "__main__":
    pipe = build_pipeline()
    report = pipe.validate()
    print("validate.ok    :", report.ok)
    print("validate.errors:", list(report.errors))
    print("validate.warns :", len(list(report.warnings)), "warning(s)")
    print("topo order     :", [n.name for n in pipe.topological_order()])
    print("external inputs:", pipe.external_inputs())
