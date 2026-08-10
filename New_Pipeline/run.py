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

import sys
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from leonardo_nodes import run_experiment
from New_Pipeline._common import store
from New_Pipeline.experiments import EXPERIMENTS
from New_Pipeline.registry import register_processes

# Output-table nodes whose tidy polars frame is written straight to parquet.
_TIDY = {"ff3_parts_df": "ff3_parts", "cumulative_table": "cumulative_table", "risk_table": "risk_table"}
_BUNDLE_NODE = "build_constituents"
_BUNDLE_KEYS = ["constituents_Industry", "constituents_loc", "holdings_over_time"]


def _export(outputs: dict, target: Path) -> list[str]:
    """Write every output artifact under ``target``; return the artifact names."""
    from New_Pipeline.boundary import PICKLE_COL, SENTINEL_COL, unpack_obj

    target.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    for fname, node in _TIDY.items():
        df = outputs.get(node)
        if isinstance(df, pl.DataFrame):
            df.write_parquet(target / f"{fname}.parquet")
            written.append(fname)

    bundle = unpack_obj(outputs[_BUNDLE_NODE])
    for k in _BUNDLE_KEYS:
        if bundle.get(k) is not None:
            bundle[k].to_parquet(target / f"{k}.parquet")
            written.append(k)

    for node in ("esg_signal_corr", "esg_coverage"):
        df = outputs.get(node)
        if df is None or SENTINEL_COL in df.columns or PICKLE_COL not in df.columns:
            continue
        for k, frame in unpack_obj(df).items():
            if frame is not None:
                f = frame.reset_index()
                f.columns = [str(c) for c in f.columns]
                f.to_parquet(target / f"{k}.parquet")
                written.append(k)
    return written


def run(name: str, out_dir: str | None = None):
    if name not in EXPERIMENTS:
        raise SystemExit(f"unknown experiment {name!r}; choose from {sorted(EXPERIMENTS)}")

    register_processes()
    exp = EXPERIMENTS[name]()

    # External bindings are prebuilt pl.DataFrames (the cfg frames) — pass through.
    manifest, outputs = run_experiment(exp, resolve_input=lambda b: b, store=store, verify=False)

    # 1. Per-run archive (never overwritten): tables + immutable manifest.
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path("runs") / f"{ts}_{name}"
    written = _export(outputs, run_dir)
    manifest.save(str(run_dir / "manifest"))  # manifest.json + manifest.md

    # 2. "Latest" snapshot for parity.compare / parity.show (overwritten each run).
    latest = Path(out_dir) if out_dir else Path("parity/artifacts/new") / name
    _export(outputs, latest)

    print(f"[run] {name}: {len(written)} artifacts")
    print(f"[run] archived (kept)     -> {run_dir}/   (+ manifest.json/.md)")
    print(f"[run] latest (overwrites) -> {latest}/")
    print(f"[run] view it:  python -m parity.show {name}")
    return manifest, outputs


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    name = args[0] if args else "base_none"
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    run(name, out)
