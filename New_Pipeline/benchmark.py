"""Freeze a sweep's inputs, outputs and timings — then prove a later sweep matches it.

    python -m New_Pipeline.benchmark capture <sweep_dir> <fixture_dir>
    python -m New_Pipeline.benchmark compare <baseline_dir> <candidate_dir>
    python -m New_Pipeline.benchmark verify-determinism <fixture_dir> [experiment]

This exists for the caching work: nodes 01/03/05 re-run from scratch on every sweep
cell even though every cell feeds them identical inputs. Before changing them we need
an oracle that answers two questions at once -- "is every number still bit-identical?"
and "did it actually get faster?" -- because an optimisation that silently moves a
number is worse than no optimisation.

WHAT MAKES THIS WORK. Every run already writes runs/<ts>_<name>/manifest.json, and
every record in it carries `output_hash` (leonardo_nodes/hashing.py: sha256 over the
polars frame's schema + row hashes, so genuinely content-addressed, no object identity
involved) and `duration_s`. Nothing in the repo reads either. `capture` distils them,
the ledger's numeric payloads, and the exported parquets into one small committed
directory; `compare` diffs two such directories.

Never compare `manifest_id` -- it is a sha256 over records INCLUDING run_ids and
timestamps, so it differs on every run by construction. Per-node `output_hash` is the
oracle; `manifest_id` is noise.

A parity verdict is only meaningful if the inputs and the environment held still, so
the fixture also pins the sha256 of every source data file and the versions of polars /
pandas / numpy. `compare` reports drift in those FIRST, before any verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The four frames New_Pipeline/run.py:44 exports per run. Everything else a run writes
# (dashboard.md, manifest.md, the decomposition PDF) is a report, not a result.
ARTIFACTS = ("ff3_parts_df", "ff5_parts_df", "table_returns", "table_excess")

# Source data this benchmark's runs read. Deliberately a slight OVER-estimate: hashing a
# file the sweep never opened only risks an unnecessary drift warning, whereas omitting
# one risks a silent "parity passed" against changed inputs -- the failure mode where a
# re-downloaded Compustat extract quietly invalidates every frozen number.
_SOURCES: dict[str, Path] = {
    "golden_lc": Path.home() / "Documents/GitHub/data/Golden_Data/LC_dataset_v2A1_20260813.parquet",
    "suspicious_gvkeys": Path.home() / "Documents/GitHub/data/Golden_Data/lc_gvkey_suspicious.csv",
    "universe_usa": REPO / "data/usa_universe_all_secstat.parquet",
    "universe_row": REPO / "data/row_universe_all_secstat_new.parquet",
    "universe_japan": REPO / "data/japan_universe_all_secstat.parquet",
    "sales": REPO / "data/sales_all_regions.parquet",
    "fama_us_3": REPO / "data/FAMA/United_States_3_Factors.parquet",
    "fama_us_5": REPO / "data/FAMA/United_States_5_Factors.parquet",
    "fama_us_mom": REPO / "data/FAMA/United_States_Momentum_Factor.parquet",
    "sasb_materiality": Path.home() / "Documents/GitHub/Data/Materiality/"
                        "Matched_SASB_GOLDEN_long_matchings_v_2A1_FirmYear_17SDGs_matching_v2.csv",
}


# --------------------------------------------------------------------------- #
# Reading what a finished sweep already wrote
# --------------------------------------------------------------------------- #
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _source_inventory() -> dict:
    """Identity of every source data file, so input drift is detectable later."""
    out = {}
    for label, path in _SOURCES.items():
        if not path.exists():
            out[label] = {"path": str(path), "exists": False}
            continue
        stat = path.stat()
        print(f"[benchmark]   hashing {label} ({stat.st_size / 1e6:.0f} MB)")
        out[label] = {
            "path": str(path),
            "exists": True,
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "sha256": _sha256(path),
        }
    return out


def _env() -> dict:
    import numpy
    import pandas
    import polars

    return {
        "python": sys.version.split()[0],
        "polars": polars.__version__,
        "pandas": pandas.__version__,
        "numpy": numpy.__version__,
    }


def _parse_ts(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def _manifest_for(run_dir: Path) -> dict:
    """Per-node parity + timing vector out of one run's manifest.json.

    Keeps a LIST per node name rather than the first match: Manifest.append is
    unconditional, so a node that failed and was retried has two records, and
    record_for() would hand back only the shadowed first one.
    """
    path = run_dir / "manifest.json"
    if not path.exists():
        return {"missing": str(path), "nodes": {}}

    manifest = json.loads(path.read_text())
    nodes: dict[str, list] = {}
    for record in manifest.get("records", []):
        nodes.setdefault(record["node_name"], []).append({
            "process_id": record.get("process_id"),
            "contract_version": record.get("contract_version"),
            "status": record.get("status"),
            "output_hash": record.get("output_hash"),
            "input_hashes": record.get("input_hashes") or {},
            "duration_s": record.get("duration_s"),
        })

    created, finalised = _parse_ts(manifest.get("created_at")), _parse_ts(manifest.get("finalised_at"))
    return {
        "created_at": manifest.get("created_at"),
        "finalised_at": manifest.get("finalised_at"),
        # Node execution only -- excludes run.py's export / dashboard.md / decomposition
        # PDF. The ledger's own duration_s is the end-to-end figure.
        "node_span_s": (finalised - created).total_seconds() if created and finalised else None,
        "nodes": nodes,
    }


def _read_ledger(sweep_dir: Path) -> list[dict]:
    ledger = sweep_dir / "results.jsonl"
    if not ledger.exists():
        raise SystemExit(f"no ledger at {ledger}")
    return [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]


# --------------------------------------------------------------------------- #
# capture
# --------------------------------------------------------------------------- #
def capture(sweep_dir: Path, fixture_dir: Path) -> int:
    records = _read_ledger(sweep_dir)
    print(f"[benchmark] {len(records)} ledger record(s) in {sweep_dir}")

    payload_dir, artifact_dir = fixture_dir / "payloads", fixture_dir / "artifacts"
    for directory in (fixture_dir, payload_dir, artifact_dir):
        directory.mkdir(parents=True, exist_ok=True)

    runs: dict[str, dict] = {}
    starts: list[datetime] = []
    ends: list[datetime] = []
    for record in records:
        name = record["experiment"]
        manifest = _manifest_for(Path(record.get("run_dir") or ""))
        start, end = _parse_ts(manifest.get("created_at")), _parse_ts(manifest.get("finalised_at"))
        if start:
            starts.append(start)
        if end:
            ends.append(end)

        runs[name] = {
            "title": record.get("title", ""),
            "status": record.get("status"),
            "timestamp": record.get("timestamp"),
            # End-to-end wall clock for the cell (sweep.run_one). None for ledgers
            # written before that was instrumented.
            "duration_s": record.get("duration_s"),
            "node_span_s": manifest.get("node_span_s"),
            "cfg": record.get("cfg") or {},
            "nodes": manifest["nodes"],
            "run_dir": record.get("run_dir", ""),
        }
        if record.get("error"):
            runs[name]["error"] = record["error"]
        if manifest.get("missing"):
            print(f"[benchmark]   WARNING no manifest for {name}: {manifest['missing']}")

        (payload_dir / f"{name}.json").write_text(
            json.dumps(record.get("payloads") or {}, indent=1, sort_keys=True, default=str))

        source = sweep_dir / "artifacts" / name
        target = artifact_dir / name
        target.mkdir(parents=True, exist_ok=True)
        for art in ARTIFACTS:
            parquet = source / f"{art}.parquet"
            if parquet.exists():
                shutil.copy2(parquet, target / f"{art}.parquet")
            else:
                print(f"[benchmark]   WARNING missing artifact {art} for {name}")

    index = {
        "captured_at": datetime.now().astimezone().isoformat(),
        "sweep_dir": str(sweep_dir),
        "n_runs": len(runs),
        "n_ok": sum(1 for r in runs.values() if r["status"] == "ok"),
        # Earliest manifest start to latest manifest finish: under --jobs N this is the
        # real elapsed time of the sweep, which the sum of per-cell durations is not.
        "sweep_wall_s": (max(ends) - min(starts)).total_seconds() if starts and ends else None,
        "total_cell_s": sum(r["duration_s"] or 0.0 for r in runs.values()) or None,
        "env": _env(),
        # Sorted by name so the file does not churn on the ledger's completion order,
        # which under --jobs N is not deterministic.
        "runs": dict(sorted(runs.items())),
    }

    print("[benchmark] hashing source data")
    (fixture_dir / "data_identity.json").write_text(
        json.dumps(_source_inventory(), indent=2, sort_keys=True))
    # NOT sort_keys: experiments.cfg_frame packs the config with a bare json.dumps(cfg),
    # so the key ORDER of the cfg dict feeds its content hash and therefore the
    # input_hashes of every node (and the output_hash of the two that carry the config
    # into their bundle). Re-ordering the cfg here would make a cfg replayed out of this
    # fixture hash differently from the one that produced it, and verify-determinism
    # would report a reproducibility failure that is purely an artefact of this file.
    (fixture_dir / "index.json").write_text(json.dumps(index, indent=1, default=str))

    print(f"[benchmark] fixture -> {fixture_dir}  "
          f"({index['n_ok']}/{index['n_runs']} ok, "
          f"{_fmt(index['sweep_wall_s'])} wall clock)")
    return 0 if index["n_ok"] == index["n_runs"] else 1


# --------------------------------------------------------------------------- #
# compare
# --------------------------------------------------------------------------- #
def _fmt(seconds: float | None) -> str:
    # Both branches are 9 characters wide, so the columns line up when a run predates
    # the ledger's duration_s field (or its manifest is gone) and the cell is blank.
    return f"{'-':>9}" if seconds is None else f"{seconds:8.1f}s"


def _load(fixture_dir: Path) -> tuple[dict, dict]:
    index = json.loads((fixture_dir / "index.json").read_text())
    identity_path = fixture_dir / "data_identity.json"
    identity = json.loads(identity_path.read_text()) if identity_path.exists() else {}
    return index, identity


def compare(baseline_dir: Path, candidate_dir: Path) -> int:
    import pandas as pd

    from parity.compare import _compare_frame

    base, base_id = _load(baseline_dir)
    cand, cand_id = _load(candidate_dir)
    failures: list[str] = []

    print("\n=== 1. INPUTS AND ENVIRONMENT ===")
    for label in sorted(set(base_id) | set(cand_id)):
        before, after = base_id.get(label, {}), cand_id.get(label, {})
        if before.get("sha256") != after.get("sha256"):
            print(f"  !! {label} CHANGED  {before.get('sha256', '?')[:12]} -> "
                  f"{after.get('sha256', '?')[:12]}")
            failures.append(f"source data changed: {label}")
    if base.get("env") != cand.get("env"):
        print(f"  !! environment differs:\n     baseline={base.get('env')}\n     "
              f"candidate={cand.get('env')}")
        failures.append("environment differs")
    if not failures:
        print(f"  all {len(base_id)} source files and the environment are unchanged")

    base_runs, cand_runs = base["runs"], cand["runs"]
    only_base, only_cand = sorted(set(base_runs) - set(cand_runs)), sorted(set(cand_runs) - set(base_runs))
    shared = sorted(set(base_runs) & set(cand_runs))
    if only_base or only_cand:
        print(f"  !! run sets differ: {len(only_base)} only in baseline, "
              f"{len(only_cand)} only in candidate")
        failures.append("run sets differ")

    print(f"\n=== 2. BIT PARITY (per-node output_hash, {len(shared)} runs) ===")
    changed_processes: set[str] = set()
    for name in shared:
        before, after = base_runs[name]["nodes"], cand_runs[name]["nodes"]
        for node in sorted(set(before) | set(after)):
            b_recs, c_recs = before.get(node, []), after.get(node, [])
            if len(b_recs) != len(c_recs):
                print(f"  !! {_short(name)} / {node}: {len(b_recs)} -> {len(c_recs)} executions")
                failures.append(f"{name}/{node}: execution count")
                continue
            for b, c in zip(b_recs, c_recs):
                if b.get("process_id") != c.get("process_id"):
                    changed_processes.add(node)
                if b.get("output_hash") != c.get("output_hash"):
                    # Inputs identical but output moved => this node's own code changed
                    # behaviour. Inputs also moved => the real cause is upstream.
                    cause = ("inputs identical -- THIS node changed"
                             if b.get("input_hashes") == c.get("input_hashes")
                             else "inputs also differ -- cause is upstream")
                    print(f"  !! {_short(name)} / {node}: output_hash differs ({cause})")
                    failures.append(f"{name}/{node}: output_hash")
    if changed_processes:
        print(f"  (process_id changed for: {sorted(changed_processes)} -- expected only "
              f"for nodes you edited)")
    if not any(f.endswith("output_hash") for f in failures):
        print(f"  every node of every run is bit-identical")

    print(f"\n=== 3. NUMBERS (parquets rtol=1e-9, ledger payloads exact) ===")
    for name in shared:
        for art in ARTIFACTS:
            b_path = baseline_dir / "artifacts" / name / f"{art}.parquet"
            c_path = candidate_dir / "artifacts" / name / f"{art}.parquet"
            if not b_path.exists() or not c_path.exists():
                continue
            ok, msg = _compare_frame(pd.read_parquet(b_path), pd.read_parquet(c_path))
            if not ok:
                print(f"  !! {_short(name)} / {art}: {msg}")
                failures.append(f"{name}/{art}")
        b_pay = baseline_dir / "payloads" / f"{name}.json"
        c_pay = candidate_dir / "payloads" / f"{name}.json"
        if b_pay.exists() and c_pay.exists() and b_pay.read_text() != c_pay.read_text():
            b_obj, c_obj = json.loads(b_pay.read_text()), json.loads(c_pay.read_text())
            differing = [k for k in sorted(set(b_obj) | set(c_obj)) if b_obj.get(k) != c_obj.get(k)]
            print(f"  !! {_short(name)}: payload sections differ: {differing}")
            failures.append(f"{name}/payloads")
    if not any("/payloads" in f or any(f.endswith(a) for a in ARTIFACTS) for f in failures):
        print("  every exported frame and every dashboard payload matches")

    print("\n=== 4. TIMING ===")
    print(f"  {'run':<54}{'baseline':>10}{'candidate':>11}{'delta':>10}{'speedup':>9}")
    for name in shared:
        b_t, c_t = base_runs[name].get("duration_s"), cand_runs[name].get("duration_s")
        print(f"  {_short(name, 52):<54}{_fmt(b_t)}{_fmt(c_t)}{_fmt(_delta(b_t, c_t))}"
              f"{_speedup(b_t, c_t):>9}")
    b_tot, c_tot = base.get("total_cell_s"), cand.get("total_cell_s")
    b_wall, c_wall = base.get("sweep_wall_s"), cand.get("sweep_wall_s")
    print(f"  {'-' * 82}")
    print(f"  {'TOTAL (sum of cells)':<54}{_fmt(b_tot)}{_fmt(c_tot)}{_fmt(_delta(b_tot, c_tot))}"
          f"{_speedup(b_tot, c_tot):>9}")
    print(f"  {'SWEEP WALL CLOCK':<54}{_fmt(b_wall)}{_fmt(c_wall)}{_fmt(_delta(b_wall, c_wall))}"
          f"{_speedup(b_wall, c_wall):>9}")

    print(f"\n  per-node, summed across all {len(shared)} runs:")
    print(f"  {'node':<54}{'baseline':>10}{'candidate':>11}{'delta':>10}{'speedup':>9}")
    for node in sorted({n for name in shared for n in base_runs[name]["nodes"]}):
        b_sum = _node_total(base_runs, shared, node)
        c_sum = _node_total(cand_runs, shared, node)
        print(f"  {node:<54}{_fmt(b_sum)}{_fmt(c_sum)}{_fmt(_delta(b_sum, c_sum))}"
              f"{_speedup(b_sum, c_sum):>9}")

    print("\n=== VERDICT ===")
    if failures:
        print(f"  FAIL -- {len(failures)} problem(s):")
        for failure in failures[:20]:
            print(f"    - {failure}")
        if len(failures) > 20:
            print(f"    ... and {len(failures) - 20} more")
        return 1
    print("  PASS -- outputs are identical to the baseline")
    return 0


def _node_total(runs: dict, names: list[str], node: str) -> float | None:
    total = [r.get("duration_s") or 0.0 for name in names for r in runs[name]["nodes"].get(node, [])]
    return sum(total) if total else None


def _delta(before: float | None, after: float | None) -> float | None:
    return None if before is None or after is None else after - before


def _speedup(before: float | None, after: float | None) -> str:
    if not before or not after:
        return "     -"
    return f"{before / after:7.2f}x"


def _short(name: str, width: int = 60) -> str:
    """Experiment names run to 150 chars; the tail (the varying knobs) is the readable
    part, so keep that rather than the shared prefix."""
    return name if len(name) <= width else "..." + name[-(width - 3):]


# --------------------------------------------------------------------------- #
# verify-determinism
# --------------------------------------------------------------------------- #
def verify_determinism(fixture_dir: Path, experiment: str | None) -> int:
    """Re-run ONE captured cfg and check it reproduces the fixture exactly.

    This is the gate before trusting the fixture as an oracle: if the pipeline is not
    reproducible run-to-run with unchanged code, no parity verdict about CHANGED code
    means anything. Uses the same registration path sweep.run_one does.
    """
    import pandas as pd

    from parity.compare import _compare_frame
    from New_Pipeline import run as run_mod
    from New_Pipeline.experiments import EXPERIMENTS, make_experiment

    index, _ = _load(fixture_dir)
    if experiment is None:
        ok = [n for n, r in index["runs"].items() if r["status"] == "ok"]
        if not ok:
            raise SystemExit("no successful run in the fixture to re-run")
        experiment = sorted(ok)[0]
    if experiment not in index["runs"]:
        raise SystemExit(f"{experiment!r} is not in {fixture_dir}/index.json")

    cfg = index["runs"][experiment]["cfg"]
    print(f"[benchmark] re-running {_short(experiment)}")
    EXPERIMENTS.setdefault(experiment, lambda n=experiment, c=cfg: make_experiment(n, c))

    out_dir = REPO / "sweep_output" / "_determinism_check" / experiment
    run_mod.run(experiment, out_dir=str(out_dir))

    run_dirs = sorted((REPO / "runs").glob(f"*_{experiment}"))
    fresh = _manifest_for(run_dirs[-1])
    frozen = index["runs"][experiment]["nodes"]

    failures = []
    for node in sorted(set(frozen) | set(fresh["nodes"])):
        before = [r.get("output_hash") for r in frozen.get(node, [])]
        after = [r.get("output_hash") for r in fresh["nodes"].get(node, [])]
        if before != after:
            print(f"  !! {node}: output_hash differs")
            failures.append(node)
    for art in ARTIFACTS:
        frozen_art = fixture_dir / "artifacts" / experiment / f"{art}.parquet"
        fresh_art = out_dir / f"{art}.parquet"
        if not frozen_art.exists() or not fresh_art.exists():
            continue
        ok, msg = _compare_frame(pd.read_parquet(frozen_art), pd.read_parquet(fresh_art))
        if not ok:
            print(f"  !! {art}: {msg}")
            failures.append(art)

    if failures:
        print(f"\n  FAIL -- the pipeline is NOT reproducible: {failures}")
        print("  The fixture cannot be used as a parity oracle until this is understood.")
        return 1
    print(f"\n  PASS -- {len(frozen)} nodes and {len(ARTIFACTS)} artifacts reproduced exactly")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="New_Pipeline.benchmark", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_capture = sub.add_parser("capture", help="freeze a finished sweep into a fixture")
    p_capture.add_argument("sweep_dir")
    p_capture.add_argument("fixture_dir")

    p_compare = sub.add_parser("compare", help="diff two fixtures: parity + timing")
    p_compare.add_argument("baseline_dir")
    p_compare.add_argument("candidate_dir")

    p_verify = sub.add_parser("verify-determinism", help="re-run one cell, expect no diff")
    p_verify.add_argument("fixture_dir")
    p_verify.add_argument("experiment", nargs="?", default=None)

    args = parser.parse_args(argv)
    if args.command == "capture":
        return capture(Path(args.sweep_dir), Path(args.fixture_dir))
    if args.command == "compare":
        return compare(Path(args.baseline_dir), Path(args.candidate_dir))
    return verify_determinism(Path(args.fixture_dir), args.experiment)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
