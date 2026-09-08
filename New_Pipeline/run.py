"""Driver: run one Experiment, saving every run to its own timestamped folder.

Usage:
    python -m New_Pipeline.run base_none
    python -m New_Pipeline.run base_none --out some/dir     # also mirror to a custom dir

Each run writes to TWO places:
  * runs/<UTC-timestamp>_<config>/   -- a NEW folder per run, never overwritten:
        the output tables (parquet) + manifest.json/.md (immutable provenance:
        which process ran each node, input/output content-hashes, audit stats).
  * parity/artifacts/new/<config>/   -- the "latest" snapshot, overwritten each run,
        which parity.compare / parity.show read.

So you always keep a full, auditable history of every run, and the compare/show
tools always see the most recent one.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from leonardo_nodes import run_experiment
from New_Pipeline._common import store
from New_Pipeline.experiments import EXPERIMENTS
from New_Pipeline.registry import register_processes

# The merged build_analyse_portfolios node is the SINGLE source of every exported artifact.
# We split them out of its pickle bundle to preserve the on-disk artifact layout used by
# parity.compare / parity.show — no numbers change, only where they come from.
#
# Deliberately kept small: this used to also export cumulative_table / risk_table /
# constituents_* / holdings_over_time / the thin-portfolio-gate and weight-diagnostic
# frames, but nobody read those off disk -- dashboard.md and manifest.json already carry
# everything they summarise, straight from the nodes that produce them, independent of
# what gets exported here. Trimming this list only stops writing loose parquet files; it
# does not stop any node from running.
_MERGED_NODE = "build_analyse_portfolios"
# {bundle key: index-column name for pd_to_pl, or None for a plain .to_parquet()}
_MERGED_EXPORTS = {
    "ff3_parts_df": "metric",
    "ff5_parts_df": "metric",
    # Raw monthly returns behind cumulative_table (this frame IS what
    # StrategyPerformance.cumulative_performance_table compounds, via (1+r).cumprod()), and
    # its rf-adjusted twin -- the exact input to the FF3 alpha regressions for every
    # High/Low/High-Low/Market/Sample column (see functions/portfolio_metrics/fama_french.py
    # and 07_build_analyse_portfolios.py's rf-subtraction into `signal_quantiles`). The two
    # agree exactly on every "High - Low <signal>" column, since rf cancels in the spread;
    # they differ by the risk-free rate on the individual "High <signal>"/"Low <signal>"
    # legs. Both date-indexed, not portfolio-indexed like ff3_parts_df above -- pd_to_pl's
    # index_name is documented to handle a DatetimeIndex the same way (boundary.py), so
    # "date" is correct here.
    "table_returns": "date",
    "table_excess": "date",
}


def _export(outputs: dict, target: Path) -> list[str]:
    """Write every output artifact under ``target``; return the artifact names.

    Only the ``_MERGED_EXPORTS`` frames are written -- the per-audit-node dumps
    (esg_signal_corr / esg_coverage / mktcap_filter_audit / sample_funnel_audit /
    sort_cutpoint_audit / geography_audit) used to each spill every key of their own
    bundle as a loose parquet file here. Those nodes still run as part of the pipeline
    and still feed dashboard.md / manifest.json's audit_stats directly -- this only
    stopped writing their bundles to disk a second time as files nobody was opening.
    """
    from New_Pipeline.boundary import pd_to_pl, unpack_obj

    target.mkdir(parents=True, exist_ok=True)
    # This function only ever ADDS files for keys it currently produces -- it never removes
    # a stale one left behind by an EARLIER _MERGED_EXPORTS (or an earlier version of this
    # code, before a key was dropped). Harmless for runs/<ts>_<name>/, a fresh directory
    # every call, but `target` is also the "latest" snapshot dir (parity/artifacts/new/<name>/,
    # any sweep's artifacts/<name>/) that gets REUSED across repeated runs of the same named
    # config -- the module docstring already promises that one is "overwritten each run", so
    # make that literal: wipe old parquet output before writing this run's. parity/compare.py
    # and parity/show.py both glob *.parquet fresh on every call rather than trusting a fixed
    # list, so this cannot orphan anything either of them reads.
    for stale in target.glob("*.parquet"):
        stale.unlink()
    written: list[str] = []

    merged = outputs.get(_MERGED_NODE)
    if merged is not None:
        bundle = unpack_obj(merged)
        for fname, index_name in _MERGED_EXPORTS.items():
            frame = bundle.get(fname)
            if frame is None:
                continue
            if index_name is None:
                frame.to_parquet(target / f"{fname}.parquet")
            else:
                pd_to_pl(frame, index_name=index_name).write_parquet(target / f"{fname}.parquet")
            written.append(fname)

    return written


def run(name: str, out_dir: str | None = None):
    if name not in EXPERIMENTS:
        raise SystemExit(f"unknown experiment {name!r}; choose from {sorted(EXPERIMENTS)}")

    register_processes()
    exp = EXPERIMENTS[name]()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path("runs") / f"{ts}_{name}"

    # Node processes (and the functions/ code they call) print a lot of intermediate
    # diagnostics — shape-before/after on every filter, value_counts/describe dumps, and
    # an uncapped FF/returns date-alignment table (~100 lines by itself). None of that is
    # useful on every run and it floods anything capturing this command's output.
    # Capture it instead of streaming it, and persist it next to the run's other archived
    # artifacts — written even on failure, so a crash's last prints aren't lost.
    # External bindings are prebuilt pl.DataFrames (the cfg frames) — pass through.
    debug_buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(debug_buf):
            manifest, outputs = run_experiment(exp, resolve_input=lambda b: b, store=store, verify=False)
    finally:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "debug_prints.log").write_text(debug_buf.getvalue())

    # 1. Per-run archive (never overwritten): tables + immutable manifest.
    written = _export(outputs, run_dir)
    manifest.save(str(run_dir / "manifest"))  # manifest.json + manifest.md


    # (run_dir / "cfg.json").write_text(json.dumps(json.loads(exp.inputs[...]["json"][0]), indent=2))



    # Static snapshot of the audit dashboard for this one run — the same
    # intent-text + widget tables + mermaid DAG that `New_Pipeline.dashboard --markdown`
    # prints, just captured to a file instead of stdout so it's reopenable later without
    # re-running anything (not interactive/live — a frozen text snapshot of this run).
    from New_Pipeline.dashboard_viz import OrderedDashboard
    from New_Pipeline.registry import build_pipeline

    # Same ordering as the served dashboard: audit-only sections last.
    dash = OrderedDashboard(manifests={name: manifest}, pipeline=build_pipeline()).build()
    dashboard_md = dash.to_markdown() + "\n\n```mermaid\n" + dash.pipeline_graph_mermaid() + "\n```\n"
    (run_dir / "dashboard.md").write_text(dashboard_md)

    # Optional PDF of the material-initiative area plots, in the run's own archive next to
    # dashboard.md. Read back out of the manifest's audit payloads -- the same values the
    # dashboard renders -- so nothing is recomputed and the two can never disagree.
    # Deliberately NOT written to `latest` below: it is a report, like dashboard.md, and a
    # sweep passing --out should not scatter PDFs through the parity area.
    _cfg = json.loads(next(iter(exp.inputs.values()))["json"][0])
    if _cfg.get("area_material_initatives_plots_per_signal_to_PDF"):
        from New_Pipeline.decomposition_pdf import build_decomposition_pdf

        _pdf = run_dir / "initiative_decomposition.pdf"
        # 0 pages = this config produced no decomposition (not Material_Immaterial_only, or
        # add_materiality off). Skip silently rather than leaving an empty PDF behind.
        _n_pages = build_decomposition_pdf(manifest, name, _pdf)
        if _n_pages:
            print(f"[run] decomposition PDF    -> {_pdf}  ({_n_pages} pages)")

        # The same numbers as a tidy CSV, so the charts can be redrawn without the
        # pipeline. Read from the manifest payloads the PDF plots from, so the two cannot
        # disagree; `scheme_coverage` is the one panel that comes from the bundle, since it
        # is context for the charts rather than a chart itself.
        from New_Pipeline.boundary import unpack_obj
        from New_Pipeline.decomposition_csv import build_decomposition_csv

        _csv = run_dir / "initiative_decomposition.csv"
        _merged = outputs.get(_MERGED_NODE)
        _decomp = (unpack_obj(_merged).get("initiative_decomposition")
                   if _merged is not None else None)
        _n_rows = build_decomposition_csv(manifest, name, _csv, bundle=_decomp)
        if _n_rows:
            print(f"[run] decomposition CSV    -> {_csv}  ({_n_rows} rows)")

    # 2. "Latest" snapshot for parity.compare / parity.show (overwritten each run).
    latest = Path(out_dir) if out_dir else Path("parity/artifacts/new") / name
    _export(outputs, latest)

    print(f"[run] {name}: {len(written)} artifacts")
    print(f"[run] archived (kept)     -> {run_dir}/   (+ manifest.json/.md, dashboard.md)")
    print(f"[run] latest (overwrites) -> {latest}/")
    print(f"[run] debug prints        -> {run_dir}/debug_prints.log")
    print(f"[run] view it:  python -m parity.show {name}")
    return manifest, outputs


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    name = args[0] if args else "base_none"
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    run(name, out)
