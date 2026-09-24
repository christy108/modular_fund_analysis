"""Regression harness: prove a code change leaves `base_none` numerically untouched.

Three frozen baselines live under ``parity/artifacts/robustness/<config>/`` -- the same
four parquet artifacts ``New_Pipeline.run`` exports (ff3_parts_df, ff5_parts_df,
table_returns, table_excess), for base_none run in three regions:

    base_none_US    United_States, Add_Momentum_Factor=True   (FF3+Mom / FF5+Mom)
    base_none_EU    Europe,        Add_Momentum_Factor=True   (FF3+Mom / FF5+Mom)
    base_none_JP    Japan,         Add_Momentum_Factor=False  (plain FF3 / FF5)

Workflow: make a change, run ``--check``; every artifact must say PASS. A FAIL names the
first differing cell, so "did my refactor move the numbers?" is answered by exit code.

Usage:
    python -m New_Pipeline.parity_robustness            # re-run all three, diff vs baseline
    python -m New_Pipeline.parity_robustness base_none_US
    python -m New_Pipeline.parity_robustness --write    # (re)freeze the baselines

Comparison is `parity.compare._compare_frame`'s -- the same tolerance the notebook parity
oracle uses (exact on strings, rtol=1e-9/atol=1e-12 on numbers), so a PASS here means the
same thing a PASS there does. checksums.json additionally records each baseline file's
SHA256, which catches a byte-level change the tolerance would forgive.

NOTE: --check re-runs the pipeline, so it costs ~5-6 minutes per config, and (like any
run) each one leaves an archive under runs/<UTC-timestamp>_<config>/. Only the temporary
compare directory is cleaned up; the archives are the driver's normal provenance trail.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

from parity.compare import _compare_frame

BASELINE_DIR = Path("parity/artifacts/robustness")

# Kept in this order everywhere the tool prints, so two runs' output diff cleanly.
CONFIGS = ["base_none_US", "base_none_EU", "base_none_JP"]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_into(config: str, target: Path) -> None:
    """Run one experiment, exporting its artifacts to ``target``."""
    from New_Pipeline.run import run

    target.mkdir(parents=True, exist_ok=True)
    run(config, str(target))


def _artifacts(d: Path) -> list[str]:
    return sorted(p.stem for p in d.glob("*.parquet"))


def write_baselines(configs: list[str]) -> int:
    """Run each config and freeze its artifacts as the new baseline."""
    checks: dict[str, dict[str, str]] = {}
    for config in configs:
        target = BASELINE_DIR / config
        print(f"\n=== freezing {config} -> {target} ===")
        _run_into(config, target)
        checks[config] = {p.name: _sha256(p) for p in sorted(target.glob("*.parquet"))}

    # Merge rather than replace: freezing one config must not drop the other two.
    path = BASELINE_DIR / "checksums.json"
    existing = json.loads(path.read_text()) if path.exists() else {}
    existing.update(checks)
    path.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n")
    print(f"\n[write] checksums -> {path}")
    _write_readable(configs)
    return 0


def _write_readable(configs: list[str]) -> None:
    """Dump the two headline stat frames as text, so the baseline is readable as a file.

    The parquet files remain the authority the comparison runs against -- this is for a
    human opening the folder, and for `git diff` to show what moved in review.
    """
    for config in configs:
        d = BASELINE_DIR / config
        lines = [f"# {config}", ""]
        for art in ("ff3_parts_df", "ff5_parts_df"):
            p = d / f"{art}.parquet"
            if not p.exists():
                continue
            lines += [f"## {art}", "", pd.read_parquet(p).to_string(index=False), ""]
        (d / "headline_tables.txt").write_text("\n".join(lines) + "\n")
        print(f"[write] readable  -> {d / 'headline_tables.txt'}")


def check(configs: list[str]) -> int:
    results: dict[str, bool] = {}
    stored = {}
    cpath = BASELINE_DIR / "checksums.json"
    if cpath.exists():
        stored = json.loads(cpath.read_text())

    for config in configs:
        base = BASELINE_DIR / config
        print(f"\n=== config: {config} ===")
        if not base.exists():
            print(f"  NO baseline at {base} -- run --write first")
            results[config] = False
            continue

        tmp = Path(tempfile.mkdtemp(prefix=f"parity_{config}_"))
        try:
            _run_into(config, tmp)
            base_arts, new_arts = _artifacts(base), _artifacts(tmp)
            if base_arts != new_arts:
                print(f"  artifact SET differs: baseline={base_arts} new={new_arts}")
            ok_all = base_arts == new_arts
            for art in sorted(set(base_arts) & set(new_arts)):
                old = pd.read_parquet(base / f"{art}.parquet")
                new = pd.read_parquet(tmp / f"{art}.parquet")
                ok, msg = _compare_frame(old, new)
                byte_ok = (stored.get(config, {}).get(f"{art}.parquet")
                           == _sha256(tmp / f"{art}.parquet"))
                note = "" if ok else f"  -> {msg}"
                if ok and not byte_ok:
                    note = "  (values equal within tolerance; bytes differ)"
                print(f"  [{'PASS' if ok else 'FAIL'}] {art}{note}")
                ok_all = ok_all and ok
            results[config] = ok_all
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    print("\n=== SUMMARY ===")
    for config, ok in results.items():
        print(f"  {config}: {'ALL PASS' if ok else 'FAIL'}")
    return 0 if results and all(results.values()) else 1


def main(argv: list[str]) -> int:
    write = "--write" in argv
    named = [a for a in argv if not a.startswith("--")]
    configs = named or CONFIGS
    unknown = [c for c in configs if c not in CONFIGS]
    if unknown:
        raise SystemExit(f"unknown config(s) {unknown}; choose from {CONFIGS}")
    return write_baselines(configs) if write else check(configs)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
