"""Run many parameter combinations and accumulate the results on disk.

    python -m New_Pipeline.sweep                      # run everything in sweep_parameters.py
    python -m New_Pipeline.sweep --jobs 4             # 4 experiments at a time
    python -m New_Pipeline.sweep --jobs 1             # force serial
    python -m New_Pipeline.sweep --pdf-every 2        # rebuild PDF/CSV more often
    python -m New_Pipeline.sweep --only base_none     # a single named EXPERIMENTS entry
    python -m New_Pipeline.sweep --dry-run            # list what would run, run nothing
    python -m New_Pipeline.sweep --rebuild            # rebuild PDF/CSV from the ledger only

Where `New_Pipeline.dashboard` renders one live page for a handful of named configs and
forgets everything when the process exits, this walks a sweep list and appends each
result to an append-only ledger, so a hundred-experiment sweep survives being quit,
crashing, or being resumed tomorrow.

**Nothing here changes the pipeline.** Each experiment goes through the ordinary
``New_Pipeline.run.run()``, and every number on the page is a dashboard widget payload
this module reads back out of the run's manifest. See ``New_Pipeline/sweep_report.py``
for the ledger/render/CSV layer and ``New_Pipeline/sweep_parameters.py`` for the inputs.

Output tree (all of it gitignored):

    sweep_output/
      results.jsonl        append-only ledger -- the source of truth
      results.pdf          one dense page per experiment, rebuilt from the ledger
      results.csv          one row per experiment, rebuilt from the ledger
      artifacts/<name>/    that run's parquets
      failures/<name>.log  traceback, for experiments that raised
"""

from __future__ import annotations

import itertools
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from New_Pipeline import sweep_parameters as SP
from New_Pipeline.sweep_report import (
    SECTIONS,
    append_ledger,
    build_csv,
    build_pdf,
    build_xlsx,
    experiment_name,
    ledger_names,
    page_title,
    param_diff,
)


def _paths(output_dir: str) -> dict:
    base = Path(output_dir)
    return {
        "base": base,
        "ledger": base / "results.jsonl",
        "pdf": base / "results.pdf",
        "csv": base / "results.csv",
        "xlsx": base / "results.xlsx",
        "artifacts": base / "artifacts",
        "failures": base / "failures",
    }


def resolve_output_dir(parent: str, sweep_name: str, new_run: bool = False) -> Path:
    """Pick the folder this sweep writes to: ``<parent>/<UTC stamp>_<sweep_name>/``.

    Each sweep gets its own folder so one can never overwrite another's results.pdf.
    But a bare timestamp per invocation would break --resume, which is the whole point of
    the ledger -- re-running the same command must CONTINUE the sweep, not start an empty
    one beside it. So an existing folder for this name is reused, and a new stamp is
    minted only when there is nothing to resume (or --new-run says so explicitly).

    Net effect: editing SWEEP_NAME starts a new sweep; re-running resumes the current one.
    """
    p = Path(parent)
    if not new_run:
        # Ordered by mtime, NOT by name: the collision suffix below makes
        # "<stamp>-2_name" sort BEFORE "<stamp>_name" ('-' < '_'), so a lexicographic
        # max would resume the older folder. mtime is also the better question anyway --
        # "the one being written to" is what a resume should continue.
        existing = sorted((d for d in p.glob(f"*_{sweep_name}") if d.is_dir()),
                          key=lambda d: d.stat().st_mtime)
        if existing:
            return existing[-1]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = p / f"{stamp}_{sweep_name}"
    # The stamp resolves to the second, so --new-run within a second of the previous
    # folder's creation would hand back that same folder and silently append to a sweep
    # it was asked to start fresh. Suffix until the name is genuinely unused.
    n = 2
    while out.exists():
        out = p / f"{stamp}-{n}_{sweep_name}"
        n += 1
    return out


# --------------------------------------------------------------------------- #
# Building the work list
# --------------------------------------------------------------------------- #
def expand_grid(grid: dict) -> list[dict]:
    """Cartesian product of ``{param: [values]}``. Empty grid -> no combinations."""
    if not grid:
        return []
    keys = list(grid)
    return [dict(zip(keys, combo)) for combo in itertools.product(*(grid[k] for k in keys))]


def build_worklist() -> list[dict]:
    """Every override dict this sweep should run: GRID product, then EXPLICIT, both
    merged over FIXED. Duplicates (the same effective overrides reached twice) are
    dropped, keeping the first occurrence."""
    combos = expand_grid(SP.GRID) + [dict(e) for e in SP.EXPLICIT]
    if not combos:
        combos = [{}]           # nothing configured -> just run the baseline
    out, seen = [], set()
    for c in combos:
        merged = {**SP.FIXED, **c}
        fingerprint = tuple(sorted((k, repr(v)) for k, v in merged.items()))
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        out.append(merged)
    return out


def _plan(worklist: list[dict]) -> list[tuple[str, str, dict]]:
    """Validate every combination up front and derive its name/title.

    Validation happens here, before the first pipeline run, so a typo'd key raises in the
    first second rather than after an hour of successful runs -- build_cfg already rejects
    unknown keys (experiments.py:133).
    """
    from New_Pipeline.experiments import build_cfg

    base = build_cfg()
    planned = []
    for overrides in worklist:
        cfg = build_cfg(**overrides)        # raises on an unknown key or a bad value
        diff = param_diff(cfg, base)
        planned.append((experiment_name(diff), page_title(diff), cfg))
    return planned


def _named_plan(names: list[str]) -> list[tuple[str, str, dict]]:
    """Plan entries for existing EXPERIMENTS names, so --only works on hand-written
    configs too. The cfg is read back off the built Experiment's own cfg frame, which
    keeps the diff honest for configs whose overrides live in a function body."""
    import json

    from New_Pipeline.experiments import EXPERIMENTS, build_cfg

    base = build_cfg()
    planned = []
    for name in names:
        if name not in EXPERIMENTS:
            raise SystemExit(f"unknown experiment {name!r}; choose from {sorted(EXPERIMENTS)}")
        exp = EXPERIMENTS[name]()
        frame = next(iter(exp.inputs.values()))
        cfg = json.loads(frame["json"][0])
        planned.append((name, page_title(param_diff(cfg, base)), cfg))
    return planned


# --------------------------------------------------------------------------- #
# Running one experiment
# --------------------------------------------------------------------------- #
def _register(name: str, cfg: dict) -> None:
    """Make ``name`` resolvable by ``New_Pipeline.run.run``.

    run() looks names up in the EXPERIMENTS dict, so a sweep-generated config has to be
    declared there. EXPERIMENTS is a plain dict of zero-arg thunks and adding an entry is
    exactly how every named config is declared -- doing it at runtime is the same
    declaration, just not written out by hand a hundred times.
    """
    from New_Pipeline.experiments import EXPERIMENTS, make_experiment

    EXPERIMENTS.setdefault(name, lambda n=name, c=cfg: make_experiment(n, c))


def _collect_payloads(manifest) -> dict:
    """Pull the seven widget payloads out of a finished run's manifest.

    audit_stats holds what Dashboard.build() would render (leonardo_nodes/dashboard.py:138),
    so this is a read of already-computed values -- no analysis happens here.
    """
    payloads = {}
    for slug, node, key, _title in SECTIONS:
        record = manifest.record_for(node)
        payloads[slug] = (record.audit_stats.get(key) if record else None)
    return payloads


def _latest_run_dir(name: str) -> str:
    """The runs/<ts>_<name>/ directory run() just wrote. run() does not return it, and
    the timestamp is generated inside, so recover it by picking the newest match."""
    matches = sorted(Path("runs").glob(f"*_{name}"))
    return str(matches[-1]) if matches else ""


def run_one(name: str, title: str, cfg: dict, paths: dict) -> dict:
    """Run one experiment and return its ledger record (never raises)."""
    from New_Pipeline import run as run_mod

    _register(name, cfg)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        # --out keeps 100 sweep configs out of parity/artifacts/new/, which
        # parity.compare reads. The runs/<ts>_<name>/ archive still happens as normal.
        manifest, _outputs = run_mod.run(name, out_dir=str(paths["artifacts"] / name))
    except Exception as exc:                                  # noqa: BLE001
        paths["failures"].mkdir(parents=True, exist_ok=True)
        (paths["failures"] / f"{name}.log").write_text(traceback.format_exc())
        print(f"[sweep] FAILED {name}: {type(exc).__name__}: {exc}")
        print(f"[sweep]   traceback -> {paths['failures'] / f'{name}.log'}")
        return {
            "experiment": name, "title": title, "timestamp": stamp,
            "status": "failed", "error": f"{type(exc).__name__}: {exc}",
            "cfg": cfg, "payloads": {}, "run_dir": _latest_run_dir(name),
        }

    return {
        "experiment": name, "title": title, "timestamp": stamp,
        "status": "ok", "cfg": cfg,
        "payloads": _collect_payloads(manifest),
        "run_dir": _latest_run_dir(name),
    }


def _rebuild(paths: dict) -> None:
    pages = build_pdf(paths["ledger"], paths["pdf"])
    rows = build_csv(paths["ledger"], paths["csv"])
    build_xlsx(paths["ledger"], paths["xlsx"])
    print(f"[sweep] rebuilt {paths['base']}/results.{{pdf,csv,xlsx}} "
          f"({pages} pages, {rows} rows)")


def _run_serial(todo, paths, pdf_every) -> int:
    completed = 0
    for i, (name, title, cfg) in enumerate(todo, 1):
        print(f"\n[sweep] ({i}/{len(todo)}) {name}\n[sweep]     {title}")
        record = run_one(name, title, cfg, paths)
        append_ledger(paths["ledger"], record)      # committed before anything else
        completed += 1
        if completed % pdf_every == 0:
            _rebuild(paths)
    return completed


def _run_parallel(todo, paths, pdf_every, jobs) -> int:
    """Run `jobs` experiments at a time, each in its own process.

    Processes, not threads: a pipeline run is CPU-bound pandas/numpy work that holds the
    GIL, so threads would serialise it. Each worker is a fresh interpreter that loads its
    own copy of the Golden panel and the Compustat universe -- which is why `jobs` is
    bounded by RAM as much as by cores.

    THE LEDGER STAYS SINGLE-WRITER: workers only compute and return their record; this
    parent process is the only thing that ever appends, so the fsync-per-record guarantee
    is exactly the same as in serial mode. Records land in COMPLETION order, which is why
    the PDF/CSV sort themselves (sweep_report.sorted_records) rather than trusting it.
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed

    # Populate the content-addressed process store ONCE, here, before any worker starts.
    # Every run() calls register_processes() itself; doing it up front means the workers
    # find the store already warm instead of N processes writing it simultaneously.
    from New_Pipeline.registry import register_processes
    register_processes()

    completed = 0
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        futures = {ex.submit(run_one, n, t, c, paths): n for n, t, c in todo}
        print(f"[sweep] submitted {len(futures)} experiment(s) to {jobs} worker process(es)")
        try:
            for fut in as_completed(futures):
                record = fut.result()      # run_one catches its own errors; never raises
                append_ledger(paths["ledger"], record)
                completed += 1
                print(f"[sweep] ({completed}/{len(todo)}) done: {record['experiment']} "
                      f"[{record.get('status')}]")
                if completed % pdf_every == 0:
                    _rebuild(paths)
        except KeyboardInterrupt:
            # Stop handing out new work; in-flight children die with the process group.
            ex.shutdown(wait=False, cancel_futures=True)
            raise
    return completed


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
_HELP = __doc__


def main(argv: list[str]) -> None:
    if "--help" in argv or "-h" in argv:
        print(_HELP)
        return

    def flag_value(flag, default):
        return argv[argv.index(flag) + 1] if flag in argv else default

    pdf_every = max(1, int(flag_value("--pdf-every", SP.PDF_EVERY)))
    jobs = max(1, int(flag_value("--jobs", getattr(SP, "JOBS", 1))))
    no_resume = "--no-resume" in argv
    dry_run = "--dry-run" in argv
    # --out names the folder outright; otherwise it is derived from SWEEP_NAME, reusing
    # an existing folder for that name so a re-run resumes rather than starting over.
    output_dir = (argv[argv.index("--out") + 1] if "--out" in argv else
                  str(resolve_output_dir(SP.OUTPUT_DIR,
                                         getattr(SP, "SWEEP_NAME", "sweep"),
                                         new_run="--new-run" in argv)))
    paths = _paths(output_dir)

    if "--rebuild" in argv:
        _rebuild(paths)
        return

    # --only takes every following bare argument: --only base_none base_materiality
    if "--only" in argv:
        rest = argv[argv.index("--only") + 1:]
        names = list(itertools.takewhile(lambda a: not a.startswith("--"), rest))
        if not names:
            raise SystemExit("--only needs at least one experiment name")
        planned = _named_plan(names)
    else:
        planned = _plan(build_worklist())

    done = set() if no_resume else ledger_names(paths["ledger"])
    todo = [p for p in planned if p[0] not in done]

    print(f"[sweep] {len(planned)} experiment(s) planned; "
          f"{len(planned) - len(todo)} already in ledger; {len(todo)} to run")
    print(f"[sweep] output -> {paths['base']}/  (rebuild PDF/CSV/XLSX every {pdf_every}, "
          f"{jobs} job(s))")
    if dry_run:
        for name, title, _cfg in planned:
            mark = "skip" if name in done else "RUN "
            print(f"  [{mark}] {name}\n           {title}")
        return

    if not todo:
        print("[sweep] nothing to do; rebuilding derived files from the ledger")
        _rebuild(paths)
        return

    # cfg.write_debug_csv sends ~128MB of CSV to FIXED paths under ./data/debug/, so
    # concurrent workers would overwrite each other's dumps. Serial runs are unaffected.
    if jobs > 1 and any(c.get("write_debug_csv") for _n, _t, c in todo):
        raise SystemExit(
            "write_debug_csv=True is incompatible with --jobs > 1: the dumps go to fixed "
            "paths under ./data/debug/ and parallel workers would clobber each other. "
            "Either set write_debug_csv=False (the default) or run with --jobs 1."
        )

    try:
        if jobs > 1:
            _run_parallel(todo, paths, pdf_every, jobs)
        else:
            _run_serial(todo, paths, pdf_every)
    except KeyboardInterrupt:
        print("\n[sweep] interrupted -- every completed experiment is already in the ledger")
    finally:
        # Always leave the PDF and CSV consistent with the ledger, however we got here.
        _rebuild(paths)
        print(f"[sweep] ledger -> {paths['ledger']}")


if __name__ == "__main__":
    main(sys.argv[1:])
