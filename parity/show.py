"""Human viewer: print a config's output tables and whether they match the notebook.

    python -m parity.show base_none              # headline tables + match flags
    python -m parity.show show_corr --all        # every artifact
    python -m parity.show base_none --old         # also print the notebook's table

This reads the parquet artifacts under parity/artifacts/{new,old}/<config>/. Generate
them first with `python -m pipeline.run <config>` (new) and the capture harness (old).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from parity.compare import _compare_frame

ROOT = Path(__file__).resolve().parent / "artifacts"
HEADLINE = ["risk_table", "cumulative_table", "ff3_parts_df"]

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)
pd.set_option("display.max_rows", 200)


def show(config: str, *, all_artifacts: bool = False, show_old: bool = False) -> None:
    new_dir, old_dir = ROOT / "new" / config, ROOT / "old" / config
    if not new_dir.exists():
        raise SystemExit(f"No pipeline output for {config!r}. Run: python -m pipeline.run {config}")

    present = sorted(p.stem for p in new_dir.glob("*.parquet"))
    names = present if all_artifacts else [n for n in HEADLINE if n in present]

    print(f"\n{'#' * 78}\n# CONFIG: {config}   (NOTEBOOK vs PIPELINE, printed for your own eyes)\n{'#' * 78}")
    for name in names:
        new = pd.read_parquet(new_dir / f"{name}.parquet")
        old_path = old_dir / f"{name}.parquet"

        print(f"\n{'=' * 78}\n===== {name} =====\n{'=' * 78}")
        if old_path.exists():
            old = pd.read_parquet(old_path)
            print("\n----- (1) NOTEBOOK  Main.ipynb -----")
            print(old.to_string(index=False))
            print("\n----- (2) PIPELINE  pipeline.run -----")
            print(new.to_string(index=False))
            ok, msg = _compare_frame(old, new)
            print(f"\n>>> automated check: {'IDENTICAL ✓ (every cell equal)' if ok else 'DIFFERS ✗ ' + msg}")
        else:
            print("\n----- PIPELINE  pipeline.run  (no notebook oracle captured) -----")
            print(new.to_string(index=False))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cfg = args[0] if args else "base_none"
    show(cfg, all_artifacts=("--all" in sys.argv), show_old=("--old" in sys.argv))
