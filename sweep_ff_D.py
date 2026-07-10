"""
Parameter sweep harness for fund_analysis (FF3 / FF5 alpha exploration).

Approach B (papermill): for every parameter combination we execute
``Sweep_Main.ipynb`` end-to-end with the parameters injected into the tagged
``parameters`` cell. The notebook's last sweep cell pickles the two regression
tables (``ff3_parts_df`` / ``ff5_parts_df``) keyed by ``sweep_run_id``. This
driver then flattens those tables and writes ONE Excel workbook with an FF3 and
an FF5 sheet. Each row = one parameter combo; columns = each swept parameter,
a ``full_params`` column holding the whole parameter dict, plus one column per
(portfolio, statistic) regression coefficient.

Usage
-----
    python3 sweep_ff.py                 # run the full grid
    python3 sweep_ff.py --limit 1       # smoke test: only the first valid combo
    python3 sweep_ff.py --dry-run       # list combos, run nothing

Notes
-----
* ``region_analysis`` is intentionally NOT swept. In ``Sweep_Main.ipynb`` the
  region-dependent variables (currency_filter, fama_factor_region, ...) are
  derived *inside* the parameters cell, i.e. BEFORE papermill's injected cell
  runs. Injecting a different region would not re-run that derivation. Keep it
  pinned to "Japan"; ``convert_to_USD`` is safe to sweep because nothing
  recomputes it after injection.
* ``ff_factors_number`` is pinned to 5 so the FF5 factor set (rmw, cma) is
  always downloaded and both FF3 and FF5 regressions are valid.
"""

from __future__ import annotations

import argparse
import itertools
import pickle
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import papermill as pm

# --------------------------------------------------------------------------- #
# Paths / constants
# --------------------------------------------------------------------------- #
# Unique per-script tag so two sweeps can run concurrently without clobbering
# each other's outputs (separate OUT_DIR + prefixed run_id). Keep distinct across
# copies of this script (e.g. "A" here, "B" in sweep_ff copy.py).
SWEEP_TAG = "NA_CAN_MSCI_Quick_Test"
REPO = Path(__file__).resolve().parent
NB_IN = REPO / "Main.ipynb"
OUT_DIR = REPO / "output" / "Sweeps" / f"SWEEP_{SWEEP_TAG}"
RUN_NB_DIR = OUT_DIR / "executed_notebooks"
PKL_DIR = OUT_DIR / "ff_pickles"
KERNEL_NAME = "python3"

# --------------------------------------------------------------------------- #
# BASE parameters -- mirror the pinned values in Sweep_Main.ipynb cell 2.
# Anything in SWEEP_GRID overrides the matching key here for a given run.
# These are injected explicitly so the recorded params == what actually ran.
# --------------------------------------------------------------------------- #
BASE = {
    "golden_data": "v_2C",
    "region_analysis": "North_America_and_Canada",   # this sweep's region (injected; derived in Main.ipynb post-injection cell)
    "fama_factors_currency": "JPY",   # pinned: Japanese-investor numeraire (USD factors -> JPY)
    "action_characterization": "original_matteo",
    "esg_choice": "msci", 
    "start_year": 2012,
    "end_year": 2024,
    "no_simple_quantiles": 6,
    "ff_factors_number": 5,              # pinned: FF5 needs rmw/cma
    
    "alpha_bound": 0.1,
    "mktcap_covered": 0.95,
    "add_accounting_data": False,
    "industry_level": 0,
    "execute_3_filters": True,
    "min_available_fyears": 3,
    "min_initatives_annual_reports": 5,
    "drop_suspicious_gvkeys": True,
    "drop_real_estate": True,
    # Japan fundamentals lag: months <= this -> use (year-2) report, else (year-1).
    "japan_year_adjustment_split_month_for_two_or_one": 3,
   
    "drop_utilities": True, 
    "drop_health_care": False,

    "drop_fin": False,


   "signal_denominator": "Sum_All_Signals", 
    "anlayse_fashion_only": False,
    "use_alpha_bound": True,

}

# --------------------------------------------------------------------------- #
# SWEEP grid -- edit these lists to explore the space.
# Keep it small first; the cartesian product grows fast.
# --------------------------------------------------------------------------- #

SWEEP_GRID = {
    "start_year": [2012, 2015, 2018],
     "no_simple_quantiles": [6, 7],
    "alpha_bound": [0.05, 0.1],
}



def is_valid_combo(params: dict) -> bool:
    """Reject parameter combinations that cannot produce a sensible run."""
    # Need at least `min_available_fyears` of sample span.
    if params["end_year"] - params["start_year"] < params["min_available_fyears"]:
        return False
    return True


def iter_combos():
    """Yield BASE-merged, validated parameter dicts from the grid."""
    keys = list(SWEEP_GRID.keys())
    for values in itertools.product(*(SWEEP_GRID[k] for k in keys)):
        combo = dict(zip(keys, values))
        params = {**BASE, **combo}
        if is_valid_combo(params):
            yield params


def flatten_ff_table(df: pd.DataFrame, prefix: str) -> dict:
    """
    Flatten a regression table (index=statistic, columns=portfolio) into a flat
    dict of ``{prefix}__{portfolio}__{statistic}`` -> value.
    """
    flat = {}
    for col in df.columns:
        for stat in df.index:
            key = f"{prefix}__{col}__{stat}"
            flat[key] = df.at[stat, col]
    return flat


def run_one(params: dict, run_id: str) -> dict | None:
    """Execute the notebook for one combo, return flattened FF3+FF5 coefficients."""
    out_nb = RUN_NB_DIR / f"run_{run_id}.ipynb"
    pkl = PKL_DIR / f"ff_{run_id}.pkl"
    # Remove any stale pickle from a previous sweep so a silently-missing save
    # is detected here instead of masked by old data under the same run_id.
    if pkl.exists():
        pkl.unlink()
    pm.execute_notebook(
        str(NB_IN),
        str(out_nb),
        parameters={
            **params,
            "sweep_mode": True,
            "sweep_run_id": run_id,
            "sweep_out_dir": str(PKL_DIR),
        },
        cwd=str(REPO),
        kernel_name=KERNEL_NAME,
        progress_bar=False,
    )
    if not pkl.exists():
        print(f"  !! no pickle produced for run {run_id}", file=sys.stderr)
        return None
    with open(pkl, "rb") as f:
        payload = pickle.load(f)
    flat = {}
    flat.update(flatten_ff_table(payload["ff3"], "ff3"))
    flat.update(flatten_ff_table(payload["ff5"], "ff5"))
    return flat


def _alpha_cols(flat: dict, prefix: str) -> dict:
    """Keep ONLY the alpha and p-value(alpha) entries for a given ff3__/ff5__ prefix."""
    return {
        k: v for k, v in flat.items()
        if k.startswith(prefix) and (k.endswith("__alpha") or k.endswith("__p-value(alpha)"))
    }


def _write_combined_xlsx(out_xlsx: Path, rows: list[dict]) -> bool:
    """Rebuild the combined (params + FF3/FF5 alpha & p-value) Excel file. Returns True on success.

    Never raises: if Excel is locked/open the sweep keeps going (the CSV
    checkpoint remains the durable record).
    """
    try:
        with pd.ExcelWriter(out_xlsx, engine="openpyxl") as xl:
            pd.DataFrame(rows).to_excel(xl, sheet_name="alpha_pvalue", index=False)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  !! could not write {out_xlsx.name} ({exc}); "
              f"results are safe in the CSV checkpoint.", file=sys.stderr)
        return False


def _append_csv(csv_path: Path, row: dict) -> None:
    """Append a single row to a CSV, writing the header on first write."""
    pd.DataFrame([row]).to_csv(
        csv_path, mode="a", header=not csv_path.exists(), index=False
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None,
                    help="only run the first N valid combos (smoke test)")
    ap.add_argument("--dry-run", action="store_true",
                    help="list the combos and exit without running")
    ap.add_argument("--flush", type=int, default=10,
                    help="rebuild the .xlsx every N runs (default 10). The CSV "
                         "checkpoints are always written after every run.")
    ap.add_argument("--resume", action="store_true",
                    help="continue the latest run: skip combos already present in "
                         "the most recent CSV checkpoint and append to those same "
                         "files instead of starting a new timestamped set.")
    args = ap.parse_args(argv)

    combos = list(iter_combos())
    if args.limit is not None:
        combos = combos[: args.limit]

    print(f"{len(combos)} valid combo(s) to run.")
    if args.dry_run:
        swept = list(SWEEP_GRID.keys())
        for i, p in enumerate(combos):
            print(f"  [{i}] " + ", ".join(f"{k}={p[k]}" for k in swept))
        return 0

    for d in (OUT_DIR, RUN_NB_DIR, PKL_DIR):
        d.mkdir(parents=True, exist_ok=True)

    swept_keys = list(SWEEP_GRID.keys())
    rows: list = []
    done: set = set()
    stamp = None

    # --resume: reload the latest checkpoint, pre-fill rows, and reuse its stamp so
    # new results append to the SAME csv/xlsx. Completed combos are matched on the
    # swept-parameter values (string-compared) so any failed/missing run is retried.
    if args.resume:
        prev = sorted(OUT_DIR.glob("sweep_ff_*_alpha_pvalue_combined.csv"))
        if prev:
            comb_prev = prev[-1]
            stamp = comb_prev.name[len("sweep_ff_"):-len("_alpha_pvalue_combined.csv")]
            rows = pd.read_csv(comb_prev).to_dict("records")
            done = {tuple(str(r[k]) for k in swept_keys) for r in rows}
            print(f"resume: {len(done)} combo(s) already done in {comb_prev.name}; skipping them.")
        else:
            print("resume: no existing checkpoint found; starting a fresh run.")

    # Output paths share one timestamp. CSVs are appended after every run (the
    # crash-proof record); the xlsx is rebuilt every `--flush` runs and at the end.
    if stamp is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Single combined output: params + alpha & p-value(alpha) for FF3 and FF5 only.
    # (Full betas / SMB / HML / RMW / CMA remain in the per-run pickles under ff_pickles/.)
    combined_csv = OUT_DIR / f"sweep_ff_{stamp}_alpha_pvalue_combined.csv"
    combined_xlsx = OUT_DIR / f"sweep_ff_{stamp}_alpha_pvalue_combined.xlsx"

    for i, params in enumerate(combos):
        run_id = f"{SWEEP_TAG}_{i:04d}"
        if tuple(str(params[k]) for k in swept_keys) in done:
            continue
        label = ", ".join(f"{k}={params[k]}" for k in swept_keys)
        print(f"[{i + 1}/{len(combos)}] run {run_id}: {label}")
        try:
            flat = run_one(params, run_id)
        except Exception as exc:  # noqa: BLE001 - keep the sweep going
            print(f"  !! run {run_id} FAILED: {exc}", file=sys.stderr)
            continue
        if flat is None:
            continue

        # Common per-combo columns: every BASE/swept param + the full dict repr.
        meta = {**params, "run_id": run_id, "full_params": repr(params)}

        # Keep ONLY alpha + p-value(alpha) per portfolio (FF3 & FF5), combined into one row.
        row = {**meta, **_alpha_cols(flat, "ff3__"), **_alpha_cols(flat, "ff5__")}
        rows.append(row)

        # Durable checkpoint: append this combined row to the CSV right away.
        _append_csv(combined_csv, row)

        # Periodically refresh the Excel workbook.
        if args.flush > 0 and (len(rows) % args.flush == 0):
            if _write_combined_xlsx(combined_xlsx, rows):
                print(f"  .. checkpoint: {len(rows)} rows -> {combined_xlsx.name}")

    if not rows:
        print("No successful runs; nothing to write.", file=sys.stderr)
        return 1

    _write_combined_xlsx(combined_xlsx, rows)
    print(f"\nWrote {len(rows)} row(s) to {combined_xlsx}")
    print(f"CSV checkpoint: {combined_csv.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
