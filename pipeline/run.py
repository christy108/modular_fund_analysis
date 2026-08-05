"""Driver: run one Experiment and export its parity artifacts.

Usage:
    python -m pipeline.run base_none
    python -m pipeline.run base_none --out parity/artifacts/new/base_none
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

from leonardo_nodes import run_experiment
from pipeline._common import store
from pipeline.experiments import EXPERIMENTS
from pipeline.registry import register_processes

# Maps the six parity artifacts to how they are pulled from run_experiment outputs.
# Tidy tables come straight off their node; the constituent frames are unpacked
# from the build_constituents bundle.
_TIDY = {
    "ff3_parts_df": "ff3_parts",
    "cumulative_table": "cumulative_table",
    "risk_table": "risk_table",
}
_BUNDLE_NODE = "build_constituents"
_BUNDLE_KEYS = ["constituents_Industry", "constituents_loc", "holdings_over_time"]


def run(name: str, out_dir: str | None = None):
    if name not in EXPERIMENTS:
        raise SystemExit(f"unknown experiment {name!r}; choose from {sorted(EXPERIMENTS)}")
    out = Path(out_dir or f"parity/artifacts/new/{name}")
    out.mkdir(parents=True, exist_ok=True)

    register_processes()
    exp = EXPERIMENTS[name]()

    # External bindings are prebuilt pl.DataFrames (the cfg frames) — pass through.
    manifest, outputs = run_experiment(
        exp, resolve_input=lambda b: b, store=store, verify=False
    )

    # Tidy tables -> parquet
    for fname, node in _TIDY.items():
        df = outputs[node]
        if isinstance(df, pl.DataFrame):
            df.write_parquet(out / f"{fname}.parquet")
            print(f"[run_new] wrote {fname} shape={df.shape}")

    # Constituents bundle -> parquet per frame
    from pipeline.boundary import PICKLE_COL, SENTINEL_COL, unpack_obj

    bundle = unpack_obj(outputs[_BUNDLE_NODE])
    for k in _BUNDLE_KEYS:
        if k in bundle and bundle[k] is not None:
            bundle[k].to_parquet(out / f"{k}.parquet")
            print(f"[run_new] wrote {k} shape={bundle[k].shape}")

    # Diagnostic bundles (esg_signal_corr, esg_coverage): each frame -> its own parquet,
    # skipped when the node returned the sentinel (gate off).
    for node in ("esg_signal_corr", "esg_coverage"):
        df = outputs.get(node)
        if df is None or SENTINEL_COL in df.columns or PICKLE_COL not in df.columns:
            continue
        for k, frame in unpack_obj(df).items():
            if frame is not None:
                # Mirror the notebook capture hook: meaningful index -> explicit column.
                f = frame.reset_index()
                f.columns = [str(c) for c in f.columns]
                f.to_parquet(out / f"{k}.parquet")
                print(f"[run_new] wrote {k} shape={f.shape}")

    print(f"[run_new] done -> {out}")
    return manifest, outputs


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    name = args[0] if args else "base_none"
    out_dir = None
    if "--out" in sys.argv:
        out_dir = sys.argv[sys.argv.index("--out") + 1]
    run(name, out_dir)
