"""Compare frozen notebook artifacts (old) against pipeline artifacts (new).

For each config, every artifact present in both parity/artifacts/{old,new}/<config>/
is diffed cell-by-cell after aligning columns and sorting rows by a stable key:
  - string/object cells       -> exact equality (formatted %-tables, gvkeys, dates)
  - numeric cells             -> np.isclose(rtol=1e-9, atol=1e-12, equal_nan=True)

Prints a PASS/FAIL line per artifact and the first differing cell on failure.
Exit code is non-zero if anything fails.

Usage:
    python -m parity.compare                # all configs found under new/
    python -m parity.compare base_none
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent / "artifacts"


def _norm(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c) for c in df.columns]
    # First column is the row-key (metric/portfolio/date/RangeIndex); unify its name.
    df = df.rename(columns={df.columns[0]: "key"}).copy()
    df.loc[:, "key"] = df["key"].astype(str)
    return df.sort_values("key", kind="stable").reset_index(drop=True)


def _compare_frame(old: pd.DataFrame, new: pd.DataFrame) -> tuple[bool, str]:
    o, n = _norm(old), _norm(new)
    if list(o.columns) != list(n.columns):
        return False, f"columns differ:\n  old={list(o.columns)}\n  new={list(n.columns)}"
    if o.shape != n.shape:
        return False, f"shape differs: old={o.shape} new={n.shape}"
    if not (o["key"].values == n["key"].values).all():
        return False, "row keys differ after sort"
    for col in o.columns:
        ov, nv = o[col].values, n[col].values
        if pd.api.types.is_numeric_dtype(o[col]) and pd.api.types.is_numeric_dtype(n[col]):
            ok = np.isclose(ov.astype(float), nv.astype(float), rtol=1e-9, atol=1e-12, equal_nan=True)
        else:
            ov_s = pd.Series(ov).astype(object).where(pd.notna(pd.Series(ov)), None)
            nv_s = pd.Series(nv).astype(object).where(pd.notna(pd.Series(nv)), None)
            ok = (ov_s.values == nv_s.values)
        if not np.all(ok):
            i = int(np.argmax(~np.asarray(ok)))
            return False, f"first diff col={col!r} row={i} key={o['key'].iloc[i]!r}: old={ov[i]!r} new={nv[i]!r}"
    return True, "ok"


def compare_config(config: str) -> bool:
    old_dir, new_dir = ROOT / "old" / config, ROOT / "new" / config
    if not new_dir.exists():
        print(f"[{config}] NO new artifacts at {new_dir}")
        return False
    old_files = {p.stem for p in old_dir.glob("*.parquet")} if old_dir.exists() else set()
    new_files = {p.stem for p in new_dir.glob("*.parquet")}
    shared = sorted(old_files & new_files)
    only_old, only_new = sorted(old_files - new_files), sorted(new_files - old_files)

    all_ok = True
    print(f"\n=== config: {config} ===")
    if only_old:
        print(f"  (only in old, not produced by pipeline: {only_old})")
    if only_new:
        print(f"  (only in new: {only_new})")
    if not shared:
        print("  no shared artifacts to compare"); return False
    for art in shared:
        old = pd.read_parquet(old_dir / f"{art}.parquet")
        new = pd.read_parquet(new_dir / f"{art}.parquet")
        ok, msg = _compare_frame(old, new)
        print(f"  [{'PASS' if ok else 'FAIL'}] {art}" + ("" if ok else f"  -> {msg}"))
        all_ok = all_ok and ok
    return all_ok


def main(argv):
    configs = argv or sorted(p.name for p in (ROOT / "new").glob("*") if p.is_dir())
    results = {c: compare_config(c) for c in configs}
    print("\n=== SUMMARY ===")
    for c, ok in results.items():
        print(f"  {c}: {'ALL PASS' if ok else 'FAIL'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main([a for a in sys.argv[1:] if not a.startswith("--")]))
