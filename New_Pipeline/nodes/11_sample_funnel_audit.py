"""Stitch the per-node filter-stage rows into one sample funnel table.

Node `sample_funnel_audit`: a pure diagnostic answering "where did the sample go". The
pipeline drops firms at ~25 separate points across four nodes and three frozen
``functions/`` modules, and until now nothing reported the cumulative effect — only two
*endpoint* snapshots (``process_lc``'s and ``prepare_panel``'s ``sample_descriptives``),
with everything between them either silent or a bare ``print(lc.shape)`` swallowed into
``runs/<ts>/debug_prints.log``.

Why the rows are CONTRIBUTED rather than replayed here: the alternative — one node
replaying all 25 stages from the raw GOLDEN parquet — would re-read the raw dataset,
duplicate four nodes' filter logic, and drift silently the moment any of it changed. So
each node measures its own stages where they actually run and bundles them under
``funnel``; this node only concatenates, renumbers and formats. Almost every count is
either free (read off a frame the node already computed) or a single mask; the one genuine
replay, of the five filters buried inside ``functions/data_functions/process_lc.py``,
lives in node 01 next to the call it mirrors and carries its own cross-check.

Contrast ``mktcap_filter_audit``, which must replay: it needs *pre*-filter listing counts
per currency-month, and those rows no longer exist in the filter's output. A single
overall firm count per stage needs no such work.

Nothing downstream reads this node. Its frames are exported as parquet by
``run.py::_export`` alongside the other diagnostic nodes, and appear in
``parity.compare`` only as an informational ``(only in new: ...)`` line.

Its section is rendered LAST on the dashboard page, via
``dashboard_viz._DEFERRED_SECTIONS`` — the DAG cannot express that (it depends on
``prepare_panel``, so Kahn's algorithm makes it ready alongside the analysis nodes).
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process

from New_Pipeline._common import cfg_schema, open_schema, store
from New_Pipeline.dashboard_viz import BundleTableViz


# ---- Dashboard extractors (bundle -> widget payloads; no computation happens here) --- #

def _funnel(bundle):
    """The funnel itself: one row per filter stage, in execution order."""
    return bundle.get("sample_funnel")


def _summary(bundle):
    """One row: the window from first to last stage, total firms lost, and the two
    self-check verdicts."""
    return bundle.get("sample_funnel_summary")


_FUNNEL_NOTE = (
    "One row per filter, **in the order the code actually runs them** — which is not the "
    "order they are usually described in. `loc == \"USA\"` reads like an early regional "
    "screen but runs at `01_process_lc.py:179`, *after* the fiscal-year window, the "
    "three-filter block and the industry drops. Ordering the rows by execution is what "
    "makes **Firms after** a real funnel: each number is a subset of the one above it "
    "within the same `Acts on` group.\n\n"
    "- **Firms after** — distinct firms (gvkeys) still standing once that filter has run. "
    "Counted on the numeric gvkey, because the same firm is spelled `1004.0`, `1004` and "
    "`001004` at different points in the pipeline.\n"
    "- **—** means *this filter did not run under this config* (a gated flag that is off, "
    "or a stage that does not exist on this path). It never means zero, and it never means "
    "the filter ran and removed nothing.\n"
    "- **Acts on** — which panel the filter cuts. The `LC` and `Compustat universe` groups "
    "are two independent funnels that only meet at the `MERGE` row, so a `Compustat "
    "universe` count is *not* expected to be smaller than the `LC` count above it.\n\n"
    "Two steps are deliberately absent because they are not firm filters: "
    "`to_monthly_last_trading_date` (a `groupby().last()` collapse, which changes the row "
    "count but cannot drop a firm) and `compute_monthly_returns_long`'s 36-day gap mask "
    "(which nulls a value rather than dropping a row — it feeds the cross-signal mask "
    "instead). Row counts are not shown at all: a filter can remove many firm-years "
    "without removing a single firm, so mixing the two units in one table invites "
    "subtracting one from the other."
)


CONTRACT = Contract(
    name="sample_funnel_audit",
    intent="""Report the sample filter funnel: for every stage that can drop a firm, how many
distinct firms are still standing after it. The stages span four nodes and three frozen
``functions/`` modules, three of which are opaque from the outside — ``process_lc`` runs five
filters inside one function and returns only its final frame, ``process_global_universe`` runs
three more with no output at all, and ``prepare_univariate_sorting_inputs`` runs the last four
inside one composed call — so before this node the only visible numbers were the two endpoint
``sample_descriptives`` rows, with everything in between silent.

This node owns no measurement. Each stage is counted by the node where that filter actually
runs and bundled under ``funnel``; this node concatenates those contributions in pipeline
order, renumbers them, and formats the counts. That is the whole design: the count lives next
to the filter, so a filter that changes cannot leave a stale row behind in a central replay.

Rows are in TRUE EXECUTION ORDER, not the order the filters are conventionally listed, so the
firm count is a genuine funnel rather than a set of unrelated snapshots.

Scope boundary: audit-only. No downstream node reads its output and ``parity.compare`` does
not diff its artifacts.

Mandatory measures (enforced by schema / audits):
- ``Firms after`` counts DISTINCT FIRMS, on the numeric gvkey, so it is comparable across
  stages that spell a gvkey differently (``1004.0`` / ``1004`` / ``001004``)
- an em dash means the stage did not run under this config, or does not exist on this path;
  it never means zero, which is why the underlying column is nullable rather than int
- ``Firms after`` is non-increasing WITHIN each ``Acts on`` group. The LC and Compustat
  universe groups are two independent funnels that meet only at the MERGE row, so a step
  UP across that boundary is correct, not a defect
- the counts are firm-level throughout. Row / firm-year counts are deliberately absent: a
  filter can remove many firm-years while removing no firm at all, and putting both units in
  one table invites subtracting one from the other
- two self-checks are reported rather than raised (regression canaries, like
  ``mktcap_filter_audit``'s ``cross_check_all_match``, not reconciliations the run depends
  on): node 01's replay of the filters inside ``process_lc`` must agree with the frame that
  function actually returned (``process_lc_replay_ok``), and the last LC-side stage must
  agree with ``process_lc``'s own ``sample_descriptives`` (``lc_endpoint_ok``)

Surfaces: the funnel table itself, one row per stage with #/Filter/Acts on/Where/Firms after
(``BundleTableViz``); and a one-row summary carrying the first and last firm counts, the total
share of firms lost, and both self-check verdicts (``BundleTableViz``).""",
    input_schema={
        "lc_stages": open_schema(),
        "universe_stages": open_schema(),
        "panel_stages": open_schema(),
        "cfg": cfg_schema(),
    },
    output_schema=open_schema(),
    audits=[
        # Explicit keys throughout: an unkeyed BundleTableViz collapses to the literal
        # "table:" (it always passes columns=[] to SampleTableViz) and collides with every
        # other unkeyed one on the same Contract, showing one table under both titles.
        BundleTableViz(
            _funnel,
            title="Sample filter funnel — firms surviving each stage",
            key="table:sample_funnel",
            n=100,
            description=_FUNNEL_NOTE,
        ),
        BundleTableViz(
            _summary,
            title="Sample filter funnel — summary and self-checks",
            key="table:sample_funnel_summary",
            description=(
                "`process_lc_replay_ok` — node 01 replays the five filters buried inside "
                "`functions/data_functions/process_lc.py` (which returns only its final "
                "frame) and compares its own last replayed count against that frame. "
                "`lc_endpoint_ok` — the last LC-side funnel row against `process_lc`'s "
                "independently-computed `sample_descriptives`.\n\n"
                "Both are expected to be vacuously true against frozen `functions/` code "
                "and a pinned pandas. They are canaries for a pandas upgrade changing "
                "`dropna` / comparison / groupby semantics, not numbers the run depends on "
                "— a False here means the funnel has drifted from what the pipeline did, "
                "and the funnel is wrong, not the pipeline."
            ),
        ),
    ],
)


@process(tag="sample_funnel_audit@v1", contract="sample_funnel_audit", author="audit")
def sample_funnel_audit_v1(lc_stages, universe_stages, panel_stages, cfg):
    import json

    import pandas as pd

    from New_Pipeline.boundary import pack_obj, unpack_obj

    C = json.loads(cfg["json"][0])
    if not C.get("show_sample_funnel_audit", True):
        # Empty bundle rather than empty frames or empty_sentinel(): unpack_obj still
        # succeeds, so each extractor's `bundle.get(...) -> None` renders the widget blank
        # (no {"error": ...} in the manifest) and run.py's export loop writes nothing.
        return pack_obj({})

    # panel_stages already carries the LC and universe rows: node 02 forwards node 01's
    # rows and node 06 concatenates node 02's and node 04's ahead of its own, so the whole
    # funnel arrives on one input in pipeline order. The other two inputs are read only as
    # fallbacks (if prepare_panel ever stops forwarding) and for the endpoint cross-check,
    # which needs process_lc's own sample_descriptives.
    P = unpack_obj(panel_stages)
    LC = unpack_obj(lc_stages)
    UNIV = unpack_obj(universe_stages)

    funnel = P.get("funnel")
    if funnel is None:
        parts = [f for f in (LC.get("funnel"), UNIV.get("funnel")) if f is not None]
        funnel = (pd.concat(parts, axis=0, ignore_index=True) if parts
                  else pd.DataFrame(columns=["filter", "acts_on", "where", "n_firms_after"]))
    funnel = funnel.reset_index(drop=True)

    # ---- self-checks ---------------------------------------------------------------- #
    # Both are decided in node 01, where the numbers being compared actually exist, and
    # forwarded untouched. Reported, never raised -- see the Contract's mandatory measures.
    _checks = P.get("funnel_checks") or LC.get("funnel_checks") or {}
    replay_ok = _checks.get("process_lc_replay_ok")
    lc_endpoint_ok = _checks.get("lc_endpoint_ok")

    # ---- display frame: renumber, format, rename ------------------------------------ #
    # n_firms_after is nullable Int64, so `pd.isna` is the only safe emptiness test; the
    # em dash is the requested rendering of "this stage did not run".
    display = pd.DataFrame({
        "#": range(1, len(funnel) + 1),
        "Filter": funnel["filter"].astype(str),
        "Acts on": funnel["acts_on"].astype(str),
        "Where (node / func)": funnel["where"].astype(str),
        "Firms after": ["—" if pd.isna(v) else f"{int(v):,}" for v in funnel["n_firms_after"]],
    })

    _known = funnel["n_firms_after"].dropna()
    _first = int(_known.iloc[0]) if len(_known) else None
    _last = int(_known.iloc[-1]) if len(_known) else None
    summary = pd.DataFrame([{
        "n_stages": int(len(funnel)),
        "n_stages_not_run": int(funnel["n_firms_after"].isna().sum()),
        "firms_at_first_stage": _first,
        "firms_at_last_stage": _last,
        "pct_firms_lost": (None if not _first
                           else round(100.0 * (_first - _last) / _first, 2)),
        "process_lc_replay_ok": replay_ok,
        "lc_endpoint_ok": lc_endpoint_ok,
    }])

    print(f"[sample_funnel_audit] {len(funnel)} stages "
          f"({int(funnel['n_firms_after'].isna().sum())} not run under this config); "
          f"firms {_first} -> {_last}; "
          f"process_lc_replay_ok={replay_ok} lc_endpoint_ok={lc_endpoint_ok}")

    return pack_obj({
        "sample_funnel": display,
        "sample_funnel_summary": summary,
    })


NODE = Node(
    name="sample_funnel_audit",
    contract=CONTRACT,
    store=store,
    inputs=("lc_stages", "universe_stages", "panel_stages", "cfg"),
    outputs=("out",),
)
