"""Assembly point: gather Contracts, register Processes, build & validate the Pipeline.

Nodes never reference their neighbours — all topology lives here (leonardo_nodes
principle: Pipeline owns the edges). Import this module to get:
    CONTRACTS      : {name -> Contract}
    NODE_MODULES   : the 9 node modules (each exposes CONTRACT + NODE + @process fns)
    build_pipeline(): a validated Pipeline
    register_processes(): ingest every @process into the shared store
"""

from __future__ import annotations

import importlib
from pathlib import Path

from leonardo_nodes import Pipeline

from New_Pipeline._common import store

# Node modules are numbered by reading order (nodes/NN_<name>.py). Filenames starting
# with a digit are not valid import identifiers, so they are loaded by string.
# run_experiment computes the true execution order from the DAG (topological_order);
# these numbers are just a readable reading order.
#
# Discovered from disk rather than hand-listed, so renaming or renumbering a node file
# can never desync this list from the directory (which it silently did once).
_NODES_DIR = Path(__file__).resolve().parent / "nodes"
_NODE_ORDER = sorted(p.stem for p in _NODES_DIR.glob("[0-9][0-9]_*.py"))
if not _NODE_ORDER:
    raise RuntimeError(f"no node modules found in {_NODES_DIR}")
NODE_MODULES = [importlib.import_module(f"New_Pipeline.nodes.{n}") for n in _NODE_ORDER]

CONTRACTS = {m.CONTRACT.name: m.CONTRACT for m in NODE_MODULES}

# Edges: "src_node.out" -> "dst_node.dst_port". `cfg` ports are intentionally left
# unconnected — they are external inputs bound per Experiment. prepare_panel already
# returns aligned factors, so there is no separate align node.
#
# process_lc (01) + derive_signals (02) are the former load_signal_lc split into two:
# process_lc handles cells 4/14/15 (load + filter + industry map), derive_signals cells
# 16/18/21 (category aggregation + winsor + signal_i ratio). esg_coverage still reads
# from process_lc because it needs lc_raw_for_coverage, which is snapshotted during
# process_lc BEFORE the sample filters — not the signal-bearing frame.
#
# load_universes (03) + merge_esg_provider (04) are the former build_global_universe
# split into two: load_universes does the raw ingestion (identical across every ESG
# config), and merge_esg_provider carries FOUR interchangeable Processes (esg_none /
# refinitiv / msci / snp) picked by Experiment.process_selection — one per ESG choice,
# rather than an if/elif inside a single process.
#
# build_analyse_portfolios (07) folds the former build_portfolios, ff3_alphas,
# performance_tables, and build_constituents into one node — all portfolio-level
# analytics live there. Only the diagnostic nodes (esg_signal_corr, esg_coverage) remain
# as separate stages downstream of prepare_panel.
EDGES = [
    ("process_lc.out", "derive_signals.lc"),
    ("derive_signals.out", "prepare_panel.lc"),
    ("load_universes.out", "merge_esg_provider.universes"),
    ("merge_esg_provider.out", "prepare_panel.global_universe"),
    ("load_fama_french.out", "prepare_panel.fama_french_raw"),
    ("prepare_panel.out", "build_analyse_portfolios.prep"),
    ("prepare_panel.out", "esg_signal_corr.prep"),
    ("prepare_panel.out", "esg_coverage.prep"),
    ("merge_esg_provider.out", "esg_coverage.universe"),
    ("process_lc.out", "esg_coverage.lc"),
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
