"""Audit the market-cap filter that shrinks the tradable universe.

Node `mktcap_filter_audit`: a pure diagnostic on the filter inside
functions/data_functions/process_data.py::process_global_universe, which has two selectable
methods (``cfg.market_cap_filter``) and is the pipeline's single largest sample cut:

* ``percent_total_mcap`` — per MONTH, pooled across every currency area in the universe.
  Sort listings ascending by month-end cap, cumulate from the smallest, keep those whose
  running total exceeds ``(1 - mktcap_covered_if_filter_by_cum_market_cap)`` of the month's
  total.
* ``percent_stocks`` — per YEAR, pooled, on the previous year's last cap. Drop a listing
  iff it is both among the smallest x% BY COUNT and below an absolute floor.

Either way the filter is invisible from the outside: it prints nothing, and the number of
listings it removed cannot be recovered from its own output.

Why the filter has to be replayed here rather than read off an upstream output:
``merge_esg_provider``'s ``global_universe`` retains ``last_mktcap`` / ``cumulative_mktcap``
/ ``total_mktcap``, so the KEPT caps, the (pooled) month total and the threshold are all
exactly recoverable — but the PRE-filter listing count is not, because the dropped rows are
gone. So the process replays the filter from the same node's per-region universes, on the
five columns the filter actually reads, and then cross-checks itself against the real
post-filter frame (kept-listing count and pooled ``total_mktcap`` per month, plus a
per-currency-area kept-count check) so that a drift in the replay is loud rather than silent.
The per-currency-area breakdown (``mktcap_filter_by_currency``) is exported alongside the
pooled cell purely as description: it shows where the one screen floor lands within each
currency area, not a second screen.

Nothing downstream reads this node. Its frames are exported as parquet by
``run.py::_export`` (alongside the other diagnostic nodes) but they are not compared by
``parity.compare``, which diffs only the artifacts the frozen notebook also produces.

Window note: this audit covers the RAW universe window, which starts BEFORE
``cfg.start_year``. ``get_usa_universe`` / ``get_row_universe`` / ``get_japan_universe``
apply only ``year <= end_year`` on their load-from-file branch, so the universe — and
therefore this audit — reaches back to the first year present in the on-disk CSVs (2013),
earlier than the analysis panel, which is additionally bounded by the LC sample and the
point-in-time accounting lag.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process

from New_Pipeline._common import cfg_schema, open_schema, store
from New_Pipeline.dashboard_viz import (
    BundleDualAxisViz,
    BundleMultiSeriesViz,
    BundleTableViz,
)


# ---- Dashboard extractors (bundle -> widget payloads; no computation happens here) --- #

def _totals(bundle):
    """One row per (year, month) — the screen's own pooled cell, exactly as
    `process_global_universe` computed it. There is nothing left to sum across currency
    areas here: the screen pools them itself, before this node ever sees the frame."""
    return bundle.get("mktcap_filter_by_month")


def _summary(bundle):
    """One row of headline stats: the configured coverage, the window, the range of
    percentage-dropped, and the cross-check verdict."""
    return bundle.get("mktcap_filter_summary")


def _binding_constraint(bundle):
    """Three lines showing which of the two `percent_stocks` conditions actually bit.

    Reads the screen's pooled cell (`mktcap_filter_by_month`), so this is genuinely one
    point per month — a true step function under the yearly rule. (Before the screen was
    pooled, this read a per-currency-month frame and would have drawn several points per
    x-value under a multi-currency run; that ambiguity cannot occur any more.)

    Empty under `percent_total_mcap`, which has no such conditions.
    """
    import pandas as pd

    df = bundle.get("mktcap_filter_by_month")
    if df is None or len(df) == 0 or "n_below_floor" not in df.columns:
        return []
    df = df.sort_values("ym")
    if df["n_below_floor"].isna().all():      # percent_total_mcap ran
        return []
    x = [str(v) for v in df["ym"]]
    out = []
    for col, name in (("n_below_floor", "below the floor"),
                      ("n_in_bottom_pct", "in the bottom x% by count"),
                      ("n_dropped", "actually dropped")):
        out.append({
            "name": name, "x": x,
            "y": [None if pd.isna(v) else float(v) for v in df[col]],
        })
    return out


def _series_by_currency(col: str, scale: float = 1.0, frame: str = "mktcap_filter_by_currency"):
    """One line per currency area for ``col``, over year-months.

    This is a DESCRIPTIVE slice of the screen's pooled cell (``mktcap_filter_by_currency``
    by default) — it shows how one Europe-wide (or otherwise pooled) threshold lands
    differently within each currency area, purely from that area's own concentration. It is
    NOT the screen's own cell any more: the screen does not group by currency area at all.

    ``scale`` divides the values for readability — market caps here are absolute currency
    units, not millions (``mktcap = prccd * cshoc``). Values are cast to plain ``float``
    because ``Manifest.save`` calls ``json.dumps`` with no ``default=`` handler, so a numpy
    scalar reaching this payload aborts the run *after* the pipeline has already succeeded.
    """
    def extract(bundle):
        import pandas as pd

        df = bundle.get(frame)
        if df is None or len(df) == 0 or col not in df.columns:
            return []
        if df[col].isna().all():
            # The column exists but belongs to the other method, or is all-absent for
            # this frame. Return nothing rather than one all-None series, which would
            # render as a legend entry with no line -- reading as broken, not as N/A.
            return []
        series = []
        for currency, part in df.groupby("curcdd", sort=True):
            part = part.sort_values("ym")
            series.append({
                "name": str(currency),
                "x": [str(v) for v in part["ym"]],
                "y": [None if pd.isna(v) else float(v) / scale for v in part[col]],
            })
        return series
    return extract


def _size_floor_series(bundle):
    """The screen's single pooled floor, plus (for context) where the smallest surviving
    listing sits within each currency area.

    The first line is the number `process_global_universe` actually applies — ONE floor
    for the whole universe that month. The remaining lines are `mktcap_filter_by_currency`,
    a descriptive slice of that same pooled cell: a currency area's own line sits at or
    above the screen floor purely because of which listings exist near the boundary in
    that area (concentration), not because that area was screened separately.
    """
    import pandas as pd

    out = []
    cell = bundle.get("mktcap_filter_by_month")
    if (cell is not None and len(cell) and "size_floor" in cell.columns
            and not cell["size_floor"].isna().all()):
        c = cell.sort_values("ym")
        out.append({
            "name": "screen floor (pooled, all currency areas)",
            "x": [str(v) for v in c["ym"]],
            "y": [None if pd.isna(v) else float(v) / 1e9 for v in c["size_floor"]],
        })
    out += _series_by_currency("size_floor_ccy", scale=1e9)(bundle)
    return out


def _discard_budget_series(bundle):
    """The screen's single cumulative discard budget, pooled across every currency area.

    ``percent_total_mcap`` only — the other rule has no cumulative budget. There is no
    per-currency-area version of this line: the budget is a property of the pooled cell,
    never promised per area (see ``max_pct_mktcap_dropped_ccy`` in the summary for how far
    a single area can exceed it).
    """
    import pandas as pd

    df = bundle.get("mktcap_filter_by_month")
    if df is None or len(df) == 0 or "cum_threshold" not in df.columns:
        return []
    if df["cum_threshold"].isna().all():
        return []
    df = df.sort_values("ym")
    return [{
        "name": "discard budget (pooled)",
        "x": [str(v) for v in df["ym"]],
        "y": [None if pd.isna(v) else float(v) / 1e9 for v in df["cum_threshold"]],
    }]


_UNITS_NOTE = (
    "**Units: billions, not millions.** `mktcap` is `prccd x cshoc` — whole currency units "
    "(a $184m firm is stored as `183919500.0`), *not* Compustat millions — so the raw value is "
    "divided by 1e9 here. Worked example from `base_none`: Jan-2013's raw `cum_threshold` is "
    "749,510,901,389, plotted as **749.5bn**, i.e. 5% of a 15.0tn total across 1,733 listings. "
    "Reading those as millions would imply a 15m-trillion US market.\n\n"
    "**Which currency** depends on `cfg.convert_to_USD` (reported in the summary table). When "
    "True, every cap was converted via `mktcap_lcu / rate`, so the values are USD bn even "
    "though a per-currency-area line is named after the LISTING currency — that name is this "
    "node's own *reporting* key, not a grouping key of the screen (the screen pools every "
    "currency area into one cell; see the size-floor chart's description). When False the "
    "values are in that listing currency. Every currently registered config is "
    "`region_analysis=\"United_States\"` (`convert_to_USD=False`, USD listings only, one "
    "currency area), so these are USD bn — but a `region_analysis=\"Japan\"` run keeps "
    "`convert_to_USD=False` with JPY listings and would plot JPY bn."
)


CONTRACT = Contract(
    name="mktcap_filter_audit",
    intent="""Make the market-cap universe filter visible, whichever of its two methods ran.
That filter lives inside ``process_global_universe`` and is the pipeline's largest single
sample cut, yet it reports nothing and its own output cannot reveal how many listings it
removed. This node replays it from the same per-region universes and reports, per MONTH
(POOLED across every currency area the universe spans): how many listings entered, how many
were removed, what share that is, and the effective per-listing size floor (the smallest
market cap that survived) — which is what a reader usually means by "the cutoff". A
per-currency-area BREAKDOWN of that same pooled cell is reported alongside
(``mktcap_filter_by_currency``), purely descriptive: it shows where the one screen floor
lands within each currency area, which can differ sharply by area concentration, but it is
not itself a screen and obeys none of this node's invariants.

Which method ran is read from ``cfg.market_cap_filter`` and the replay branches to match:

- ``percent_total_mcap`` — per MONTH, pooled; keeps listings whose cumulative cap exceeds
  ``(1 - mktcap_covered_if_filter_by_cum_market_cap) x total_mktcap``, where both the
  cumulation and the total are over the WHOLE universe that month, not one currency area.
  Also reported: that literal threshold, a CUMULATIVE budget over the whole discarded tail
  and NOT a per-listing size (it is ~300x the size floor; conflating the two is the standard
  misreading).
- ``percent_stocks`` — per YEAR, pooled, decided on each listing's last cap in Y-1: dropped
  iff both among the smallest ``percentage_stocks_removed_if_percent_stocks_true`` of listings
  BY COUNT (across the whole universe, not one currency area) and below
  ``floor_if_percent_stocks_true``. Also reported: which of the two conditions bound each
  year, and how many listings were dropped purely for having no Y-1 observation. The two
  methods' percentages are NOT comparable — one is a share of aggregate value, the other a
  share of the listing count.

Both methods used to group by ``curcdd`` (listing currency) too, making each currency area
its own cell. That was removed from the screen itself (``process_data.py``) and this node's
replay follows it: a currency area is not a market boundary a size screen should respect once
the universe is one comparable numéraire, and the per-currency version fragmented the
effective size floor across currency areas by ~2x on a real multi-currency extract — an
artefact of each area's own concentration, not of the firms. ``process_global_universe`` now
raises if asked to pool a universe that spans multiple currency areas without
``convert_to_USD`` — reported here as ``screen_currency_safe`` rather than gating anything in
this audit, since the screen already enforces it.

Scope boundary: this node owns no numerics that anything else consumes. It re-derives a filter
that already ran upstream, purely so the filter can be inspected. No downstream node reads its
output, and ``parity.compare`` does not diff its artifacts.

Mandatory measures (enforced by schema / audits), all at the screen's own POOLED cell:
- the replayed kept-listing count and pooled ``total_mktcap`` equal the real post-filter
  ``global_universe``'s, per month (``matches_actual`` in ``mktcap_filter_by_month``; rolled
  into ``cross_check_all_match`` in the summary together with a per-currency-area KEPT-COUNT
  check, ``matches_actual_n`` in ``mktcap_filter_by_currency`` — there is no per-currency
  total on the real side to compare, since the screen no longer computes one). Expected to be
  vacuously true against a frozen ``process_global_universe`` and a pinned pandas — it is a
  regression canary for a pandas upgrade changing groupby/sort semantics, not a numerical
  reconciliation. ``screen_pooled_confirmed`` is a second, independent canary: it checks that
  the real frame's ``total_mktcap`` column is genuinely constant within each cell (as a pooled
  screen implies), so a REVERT of the screen back to per-currency grouping is caught even if
  it happened to preserve kept-counts and totals by coincidence.
- ``percent_total_mcap`` only: market cap actually dropped never exceeds the configured budget
  (because the strict ``>`` keeps the listing straddling the threshold),
  ``pct_mktcap_dropped <= 100 x (1 - mktcap_covered_if_filter_by_cum_market_cap)``; and
  ``largest_dropped <= size_floor`` always, since the sort is ascending by cap (equality means
  the boundary fell inside a tie). Both are POOLED-cell statements and both are reported as
  ``None`` under ``percent_stocks``, where they are meaningless, rather than as a vacuous pass
  — the second because the ranking uses the Y-1 cap while these two are measured on the
  current month's caps, so a dropped listing can legitimately out-grow a kept one during
  year Y. A SINGLE currency area, by contrast, CAN legitimately lose more than the pooled
  budget (the budget was never promised per-area) — reported descriptively as
  ``max_pct_mktcap_dropped_ccy`` / ``n_ccy_months_over_budget``, deliberately outside this
  invariant.
- ``percent_stocks`` only: ``n_dropped == min(n_below_floor, n_in_bottom_pct) + n_no_ref``
  (``prefix_invariant_ok``). Both selection sets are prefixes of the ascending-cap order, so
  their intersection is a prefix and the smaller set is the binding one.
- counts are LISTING-level, keyed on (gvkey, iid) exactly as the screen groups; company-level
  (distinct gvkey) counts are reported alongside and are NOT the same number
- ``process_global_universe`` itself refuses to pool caps across currency areas unless every
  cap is already in one numéraire (``convert_to_USD``, or a single-currency
  ``currency_filter``) — the same guard ``functions/extra_functions/plot_coverage.py``
  enforces. This node reports that precondition as ``screen_currency_safe`` rather than
  re-checking it (an audit must not crash a run on its own account).
- every cap column in the bundled/exported frames is in WHOLE currency units, not millions
  (``mktcap = prccd x cshoc``); only the ``*_bn`` summary fields and the two charts are scaled,
  by 1e9. The currency is USD whenever ``convert_to_USD`` is set or the listings are USD, and
  the listing currency otherwise (e.g. JPY for a ``region_analysis="Japan"`` run, which leaves
  ``convert_to_USD`` False)

Surfaces: listings dropped against percentage dropped over time, on separate y-axes since they
differ by orders of magnitude (``BundleDualAxisViz``, off the pooled ``mktcap_filter_by_month``);
the effective per-listing size floor over time — the screen's own pooled floor plus, for
context, where it lands within each currency area — in billions (``BundleMultiSeriesViz``); and
the headline summary including the cross-check verdict (``BundleTableViz``) — all three under
either method. Plus one method-specific chart each, blank when its method is not the active
one, since ``Contract.audits`` is static at import time and cannot branch on cfg: the pooled
cumulative discard budget for ``percent_total_mcap``, and the binding-constraint comparison for
``percent_stocks`` (``BundleMultiSeriesViz``). The full per-month numbers are deliberately NOT
a widget — 144+ rows read badly on a dashboard — but they are still bundled and exported as
``mktcap_filter_by_month.parquet`` (pooled) and ``mktcap_filter_by_currency.parquet`` (per
currency area, descriptive) for anyone who wants the exact figures.""",
    input_schema={"universe": open_schema(), "cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[
        # Explicit keys throughout: an unkeyed BundleTableViz collapses to the literal
        # "table:" and collides with every other unkeyed one on the same Contract.
        BundleDualAxisViz(
            _totals,
            title="Listings removed by the market-cap coverage filter",
            x_col="ym", left_col="n_dropped", right_col="pct_dropped",
            left_label="Listings dropped", right_label="% of universe dropped",
            x_label="Month",
            key="dual_axis:mktcap_filter_dropped",
        ),
        BundleMultiSeriesViz(
            _size_floor_series,
            title="PER-FIRM cutoff: the screen's pooled floor, and the smallest listing "
                  "kept in each currency area (billions)",
            key="lines:mktcap_filter_size_floor",
            description=(
                "Populated under **both** methods — the cutoff in the sense you probably "
                "mean it: a single listing had to be worth at least this much to survive "
                "that month.\n\n"
                "The **screen floor** line is the pooled cutoff `process_global_universe` "
                "actually applies — ONE floor for the whole universe. The per-currency-area "
                "lines are a descriptive slice of that same pooled cell, not six different "
                "screens: a currency area's line sits at or above the screen floor purely "
                "because of which listings exist near the boundary in that area, which is "
                "concentration, not policy.\n\n"
                "Under `percent_total_mcap`, contrast the discard-budget chart, which is a "
                "SUM over 1,077-1,713 firms and therefore 283-388x larger — not a comparable "
                "magnitude. Under `percent_stocks` the pooled floor can sit *below* the "
                "configured floor: that happens exactly when the bottom-x% cap binds before "
                "the floor does, so listings under the floor survive because they are not "
                "among the very smallest.\n\n" + _UNITS_NOTE
            ),
        ),
        BundleMultiSeriesViz(
            _discard_budget_series,
            title=("DISCARD BUDGET, summed over all dropped listings, pooled across every "
                   "currency area: (1 - coverage) x total market cap (billions) — "
                   "percent_total_mcap only"),
            key="lines:mktcap_filter_cum_threshold",
            description=(
                "**Blank unless `market_cap_filter=\"percent_total_mcap\"`** — the other rule "
                "has no cumulative budget.\n\n"
                "**This is not a per-firm size.** It is the total market cap the filter is "
                "allowed to discard collectively FROM THE WHOLE UNIVERSE that month, pooled "
                "across every currency area, and it is never compared against one firm's cap: "
                "the test is `cumulative_mktcap > threshold`, where `cumulative_mktcap` means "
                "'my cap plus everything smaller than me, anywhere in the universe that "
                "month'.\n\n"
                "Worked example (base_none, Jan-2013 — single-currency, so pooling changes "
                "nothing here): the budget is 749.5bn = 5% of a 14,990bn market. The 1,081 "
                "listings actually dropped sum to 748.2bn — a mean of 692m each. The largest "
                "of them is 2.64bn and the smallest survivor is 2.65bn, so the PER-FIRM "
                "boundary is ~2.65bn (see the chart above), roughly 283x smaller than this "
                "budget. Both numbers are correct; they measure different things.\n\n"
                + _UNITS_NOTE
            ),
        ),
        BundleMultiSeriesViz(
            _binding_constraint,
            title="Which constraint bit: listings below the floor vs in the bottom x% "
                  "vs actually dropped — percent_stocks only",
            key="lines:mktcap_filter_binding",
            description=(
                "**Blank unless `market_cap_filter=\"percent_stocks\"`.**\n\n"
                "That rule drops a listing only if it satisfies BOTH conditions, so the "
                "dropped count is the smaller of the two lines (plus any listing with no "
                "previous-year cap at all, which is dropped outright). Whichever line sits "
                "lower is the constraint doing the work:\n\n"
                "- **below the floor** lower → the *floor* binds; raising `x%` would change "
                "nothing.\n"
                "- **in the bottom x% by count** lower → the *x% cap* binds; the floor wants "
                "to remove more listings than x% allows, so lowering the floor changes "
                "nothing.\n\n"
                "Expect a **step function**: the decision is taken once a year off the "
                "previous year's caps, so it is constant across each year's twelve months. "
                "That flatness is the annual rebalance, not a plotting artefact."
            ),
        ),
        BundleTableViz(
            _summary,
            title="Market-cap filter — summary",
            key="table:mktcap_filter_summary",
        ),
    ],
)


@process(tag="mktcap_filter_audit@v1", contract="mktcap_filter_audit", author="audit")
def mktcap_filter_audit_v1(universe, cfg):
    import json

    import numpy as np
    import pandas as pd

    from New_Pipeline.boundary import pack_obj, unpack_obj

    C = json.loads(cfg["json"][0])
    if not C.get("show_mktcap_filter_audit", True):
        # Empty bundle rather than empty frames or empty_sentinel(): unpack_obj still
        # succeeds so every extractor's `bundle.get(...) -> None` guard renders the widget
        # blank (no {"error": ...} in the manifest), and run.py's export loop writes nothing.
        return pack_obj({})

    U = unpack_obj(universe)
    currency_filter = C["currency_filter"]
    # Which screen actually ran upstream. .get() defaults mirror _common.mktcap_filter_kwargs
    # so this replay follows whatever process_global_universe was given.
    method = C.get("market_cap_filter", "percent_total_mcap")
    cov = C["mktcap_covered_if_filter_by_cum_market_cap"]
    pct = C.get("percentage_stocks_removed_if_percent_stocks_true", 0.01)
    floor = C.get("floor_if_percent_stocks_true", 100e6)
    if method not in ("percent_total_mcap", "percent_stocks"):
        raise ValueError(f"unknown market_cap_filter {method!r}")

    # ---- 1. Replay the PRE-filter security-month set -------------------------------- #
    # Mirrors the ESG rescale, mktcap-notna drop, and currency filter near the top of
    # process_global_universe (before the market-cap screen itself) on the five columns
    # the screen reads.
    #
    # `year` is deliberately NOT taken off the frames. The Refinitiv and MSCI ESG merges
    # left-join on `last_year` against a right frame that also carries `year`, and the S&P
    # merge_asof does the same, so those universes come back with `year_x`/`year_y` and NO
    # plain `year` — reading it would KeyError on three of the four ESG configs. The frozen
    # filter recomputes month/year from `date` (overwriting any inherited `year`); so do we.
    #
    # The currency filter and the mktcap-notna drop are applied per REGION FRAME before the
    # concat rather than after it. Both are purely row-wise predicates and concat preserves
    # within-frame and frame order, so filter-then-concat selects the same rows in the same
    # order as concat-then-filter. Doing it first is what keeps this audit off the ~17M
    # RoW/Japan daily rows that no single-currency config can keep (RoW is CHF/GBP/EUR only,
    # Japan is JPY).
    cols = ["date", "curcdd", "gvkey", "iid", "mktcap"]
    parts = []
    for frame in (U["usa_universe"], U["row_universe"], U["japan_universe"]):
        if frame is None:
            continue
        part = frame.reindex(columns=cols)
        part = part[part["mktcap"].notna()]
        if currency_filter is not None and len(currency_filter) > 0:
            part = part[part["curcdd"].isin(currency_filter)]
        parts.append(part)

    pre = pd.concat(parts, axis=0, ignore_index=True)
    del parts
    pre["month"] = pre["date"].dt.month
    pre["year"] = pre["date"].dt.year

    # groupby drops any group with NaN in a key (pandas default dropna=True). The frozen
    # code drops those rows too, one step later: they get a NaN cumulative_mktcap from the
    # left merge, and `NaN > x` is False. Same rows either way.
    pre_sorted = pre.sort_values(by=["date"])
    del pre
    sec = (
        pre_sorted.groupby(["month", "year", "gvkey", "iid"])
        .agg(last_mktcap=("mktcap", "last"),
             # curcdd is NOT a grouping key of the screen any more -- it pools every
             # currency area into one cell (process_data.py, `last_values`). Carried
             # here as the listing-month's LAST observed currency, off the same
             # date-sorted row `last_mktcap` is taken from -- purely for the
             # descriptive per-currency-area breakdown built in step 2 below.
             curcdd=("curcdd", "last"))
        .reset_index()
    )
    # The yearly reference cap for percent_stocks: each listing's LAST observation in the
    # year, taken off the same date-sorted daily frame the frozen function uses. Built
    # here, before pre_sorted is released, rather than re-derived from `sec` -- that
    # shortcut would only be equivalent via sec.last_mktcap being the month's last daily
    # observation, and this replay's whole value is not assuming things like that.
    ref = None
    if method == "percent_stocks":
        ref = (
            pre_sorted.groupby(["year", "gvkey", "iid"])
            .agg(ref_mktcap=("mktcap", "last"))
            .reset_index()
        )
    del pre_sorted

    sec = sec.sort_values(by=["month", "year", "last_mktcap"])
    grouped = sec.groupby(["month", "year"])["last_mktcap"]
    # Computed under both methods: informative either way, and percent_total_mcap's test
    # needs them. POOLED across currency areas -- matches process_global_universe.
    sec["cumulative_mktcap"] = grouped.cumsum()
    sec["total_mktcap"] = grouped.transform("sum")

    if method == "percent_total_mcap":
        sec["kept"] = sec["cumulative_mktcap"] > (1 - cov) * sec["total_mktcap"]
        sec["no_ref"] = False
    else:
        # Rank by COUNT within each reference year (pooled), decide, then shift the
        # reference year forward so Y-1's decision governs year Y.
        ref = ref.sort_values(by=["year", "ref_mktcap"])
        _c = ["year"]
        ref["ref_pct_rank"] = (ref.groupby(_c).cumcount() + 1) / ref.groupby(_c)[
            "ref_mktcap"
        ].transform("size")
        ref["in_bottom_pct"] = ref["ref_pct_rank"] <= pct
        ref["below_floor"] = ref["ref_mktcap"] < floor
        ref["drop_ref"] = ref["in_bottom_pct"] & ref["below_floor"]
        ref["year"] = ref["year"] + 1
        sec = sec.merge(
            ref[["year", "gvkey", "iid", "ref_mktcap", "ref_pct_rank",
                 "in_bottom_pct", "below_floor", "drop_ref"]],
            on=["year", "gvkey", "iid"], how="left",
        )
        # ORDER MATTERS: derive `kept` from the raw merged column first. .eq(False) drops
        # both drop_ref=True and drop_ref=NaN, NaN meaning "no Y-1 observation" (a new
        # listing, or every listing in the earliest year present). Only afterwards may the
        # diagnostic booleans be filled, because fillna(False) on drop_ref would flip
        # those no-reference rows from dropped to kept.
        sec["no_ref"] = sec["drop_ref"].isna()
        sec["kept"] = sec["drop_ref"].eq(False)
        for _b in ("in_bottom_pct", "below_floor"):
            sec[_b] = sec[_b].fillna(False).astype(bool)

    print(f"[mktcap_filter_audit] method={method}: replayed {len(sec)} listing-months, "
          f"{int(sec['kept'].sum())} kept "
          f"({'coverage=%s' % cov if method == 'percent_total_mcap' else 'pct=%s floor=%s' % (pct, floor)})")

    # ---- 2. Aggregate to the screen's own cell, and to a per-currency-area slice ----- #
    cell_keys = ["year", "month"]           # the screen's actual cell -- POOLED
    ccy_keys = ["year", "month", "curcdd"]  # reporting only; decides nothing
    cell_g = sec.groupby(cell_keys)
    kept, dropped = sec[sec["kept"]], sec[~sec["kept"]]

    by = pd.DataFrame({
        "n_pre": cell_g.size(),
        "n_kept": cell_g["kept"].sum(),
        "n_pre_gvkeys": cell_g["gvkey"].nunique(),
        "n_currencies": cell_g["curcdd"].nunique(),
        "total_mktcap": cell_g["total_mktcap"].first(),
    })
    by["n_kept_gvkeys"] = kept.groupby(cell_keys)["gvkey"].nunique()
    by["size_floor"] = kept.groupby(cell_keys)["last_mktcap"].min()
    by["largest_dropped"] = dropped.groupby(cell_keys)["last_mktcap"].max()
    by["kept_mktcap"] = kept.groupby(cell_keys)["last_mktcap"].sum()
    by = by.reset_index()

    by["n_dropped"] = by["n_pre"] - by["n_kept"]
    by["pct_dropped"] = 100.0 * by["n_dropped"] / by["n_pre"]
    by["n_dropped_gvkeys"] = by["n_pre_gvkeys"] - by["n_kept_gvkeys"]
    by["pct_mktcap_dropped"] = (
        100.0 * (by["total_mktcap"] - by["kept_mktcap"]) / by["total_mktcap"]
    )

    # ---- method-specific columns (pooled cell) --------------------------------------- #
    by["filter_period"] = "month" if method == "percent_total_mcap" else "year"
    if method == "percent_total_mcap":
        by["cum_threshold"] = (1.0 - cov) * by["total_mktcap"]
        # Ascending-by-cap sort means every dropped listing precedes every kept one, so
        # largest_dropped <= size_floor holds by construction; equality means the threshold
        # fell inside a tie and the boundary does not strictly separate.
        by["boundary_tied"] = by["largest_dropped"] == by["size_floor"]
        for _c in ("n_below_floor", "n_in_bottom_pct", "n_no_ref"):
            by[_c] = np.nan
        by["binding_constraint"] = ""
    else:
        # No cumulative budget exists under this rule.
        by["cum_threshold"] = np.nan
        # largest_dropped <= size_floor is NOT expected month-by-month here: the ranking
        # uses the Y-1 cap while these two are measured on the current month's caps, so a
        # dropped listing can out-grow a kept one during year Y. Checked on the reference
        # frame instead (see cross_check / summary).
        by["boundary_tied"] = False
        # Merged on `cell_keys`, not assigned via .values: `by` has a RangeIndex by this
        # point, so a positional assignment would rely on this groupby emitting rows in
        # exactly the order `cell_g` did — true today, and a silent mis-alignment the day
        # it isn't.
        _counts = (
            sec.groupby(cell_keys)[["below_floor", "in_bottom_pct", "no_ref"]].sum()
            .rename(columns={"below_floor": "n_below_floor",
                             "in_bottom_pct": "n_in_bottom_pct",
                             "no_ref": "n_no_ref"})
            .reset_index()
        )
        by = by.merge(_counts, on=cell_keys, how="left")
        # Both sets are prefixes of the ascending-cap order, so their intersection is a
        # prefix and n_dropped == min(...) whenever every listing has a reference. Reporting
        # which side is smaller says which constraint actually bit.
        by["binding_constraint"] = np.where(
            by["n_below_floor"] < by["n_in_bottom_pct"], "floor",
            np.where(by["n_below_floor"] > by["n_in_bottom_pct"], "pct_stocks", "tie"),
        )
    by["ym"] = (
        by["year"].astype(int).astype(str) + "-"
        + by["month"].astype(int).astype(str).str.zfill(2)
    )

    # ---- per-currency-area descriptive slice of the SAME pooled cell ----------------- #
    # Decides nothing and obeys none of the invariants below -- it exists only to show
    # where the one pooled floor/budget lands within each currency area. Built by
    # RE-SUMMING `last_mktcap` on the slice, never by reading the `total_mktcap` column:
    # that column is now the POOLED total and would repeat the whole-universe figure on
    # every currency-area row.
    ccy_g = sec.groupby(ccy_keys)
    by_ccy = pd.DataFrame({
        "n_pre": ccy_g.size(),
        "n_kept": ccy_g["kept"].sum(),
        "n_pre_gvkeys": ccy_g["gvkey"].nunique(),
        "pre_mktcap_ccy": ccy_g["last_mktcap"].sum(),
    })
    by_ccy["n_kept_gvkeys"] = kept.groupby(ccy_keys)["gvkey"].nunique()
    by_ccy["size_floor_ccy"] = kept.groupby(ccy_keys)["last_mktcap"].min()
    by_ccy["largest_dropped_ccy"] = dropped.groupby(ccy_keys)["last_mktcap"].max()
    by_ccy["kept_mktcap_ccy"] = kept.groupby(ccy_keys)["last_mktcap"].sum()
    by_ccy = by_ccy.reset_index()

    by_ccy["n_dropped"] = by_ccy["n_pre"] - by_ccy["n_kept"]
    by_ccy["pct_dropped"] = 100.0 * by_ccy["n_dropped"] / by_ccy["n_pre"]
    by_ccy["n_dropped_gvkeys"] = by_ccy["n_pre_gvkeys"] - by_ccy["n_kept_gvkeys"]
    # A currency area can now be wiped out entirely by the pooled floor (e.g. every DKK
    # listing falls below a Europe-wide cutoff) -- impossible under the old per-currency
    # screen, where the largest listing in a cell always survived. fillna(0.0), not left
    # NaN, so pct_mktcap_dropped_ccy reads 100.0 rather than NaN for that row.
    by_ccy["kept_mktcap_ccy"] = by_ccy["kept_mktcap_ccy"].fillna(0.0)
    by_ccy["pct_mktcap_dropped_ccy"] = 100.0 * (
        1.0 - by_ccy["kept_mktcap_ccy"] / by_ccy["pre_mktcap_ccy"]
    )
    by_ccy["ym"] = (
        by_ccy["year"].astype(int).astype(str) + "-"
        + by_ccy["month"].astype(int).astype(str).str.zfill(2)
    )
    # Carry the screen's own pooled floor and total alongside each currency area's own
    # slice -- this pairing is the point of this frame: one pooled floor, landing at a
    # different level in each currency area purely from that area's concentration.
    by_ccy = by_ccy.merge(
        by[["year", "month", "total_mktcap", "size_floor"]].rename(
            columns={"total_mktcap": "cell_total_mktcap", "size_floor": "cell_size_floor"}
        ),
        on=["year", "month"], how="left",
    )
    by_ccy["share_of_cell_mktcap"] = (
        100.0 * by_ccy["pre_mktcap_ccy"] / by_ccy["cell_total_mktcap"]
    )

    # ---- 3. Cross-check against the REAL post-filter frame --------------------------- #
    # Counts and totals only, never a join on gvkey: the frozen function reformats it
    # (astype(float).astype(int).astype(str)) and the node then zfills it, so the real
    # frame's "001004" is not comparable to this replay's "1004.0". The real frame is DAILY
    # rows (last_values is merged back onto every trading day), hence the drop_duplicates
    # to recover kept listing-months.
    #
    # `curcdd` is deliberately NOT in the dedup subset: the screen's grain is now
    # (month, year, gvkey, iid), pooled across currency areas, so including curcdd would
    # split a listing that redenominates mid-month into two rows and inflate
    # n_kept_actual. It is retained as a plain column (whichever row drop_duplicates
    # happens to keep) purely for the per-currency-area count check below.
    guniv = U["global_universe"]
    kept_actual = guniv.drop_duplicates(subset=["year", "month", "gvkey", "iid"])

    actual = (
        kept_actual.groupby(cell_keys)
        .agg(n_kept_actual=("gvkey", "size"),
             total_mktcap_actual=("total_mktcap", "first"),
             # If the screen really is pooled, `transform("sum")` wrote ONE float to
             # every row of the cell, so nunique is 1. A revert to per-currency
             # grouping in process_data.py shows up here as >1 -- an independent
             # canary from the count/total cross-check below.
             n_total_mktcap_distinct=("total_mktcap", "nunique"))
        .reset_index()
    )
    by = by.merge(actual, on=cell_keys, how="outer")
    # A cell with ZERO survivors produces no group in `actual`, so the outer merge leaves
    # NaN rather than 0 -- and total_mktcap_actual is genuinely unreadable there, since
    # there are no surviving rows to read it off. Treat "absent from the real frame" as
    # zero kept, and only compare the total where the real frame has rows. Without this, a
    # legitimately empty cell reports as a cross-check FAILURE: under percent_stocks every
    # month of the earliest year is empty (no listing has a Y-1 reference), which is the
    # rule working, not a replay mismatch.
    _cell_present = by["n_kept_actual"].notna()
    by["n_kept_actual"] = by["n_kept_actual"].fillna(0)
    by["matches_actual"] = (by["n_kept"] == by["n_kept_actual"]) & (
        ~_cell_present
        | np.isclose(by["total_mktcap"], by["total_mktcap_actual"],
                     rtol=0.0, atol=0.0, equal_nan=True)
    )
    by["screen_pooled"] = (~_cell_present) | (by["n_total_mktcap_distinct"] <= 1)
    by = by.sort_values("ym").reset_index(drop=True)

    # Per-currency-area count check: not a total (the real frame carries only the POOLED
    # total_mktcap, so there is no per-currency-area total on the other side to compare),
    # but the count is a real equality once the pooled screen has chosen its survivor set
    # -- both sides must still agree on how that set splits by currency area. Strictly
    # stronger than the pooled count alone: it catches a replay that keeps the right
    # NUMBER of listings, but in the wrong currency areas.
    actual_ccy = (
        kept_actual.groupby(ccy_keys)
        .agg(n_kept_actual=("gvkey", "size"))
        .reset_index()
    )
    by_ccy = by_ccy.merge(actual_ccy, on=ccy_keys, how="outer")
    by_ccy["n_kept_actual"] = by_ccy["n_kept_actual"].fillna(0)
    by_ccy["matches_actual_n"] = by_ccy["n_kept"] == by_ccy["n_kept_actual"]
    by_ccy = by_ccy.sort_values(["ym", "curcdd"]).reset_index(drop=True)

    by = by[[
        "ym", "year", "month", "filter_period", "n_currencies",
        "n_pre", "n_kept", "n_dropped", "pct_dropped",
        "n_pre_gvkeys", "n_kept_gvkeys", "n_dropped_gvkeys",
        "size_floor", "largest_dropped", "boundary_tied",
        "cum_threshold", "total_mktcap", "kept_mktcap", "pct_mktcap_dropped",
        # percent_stocks only; NaN/"" under percent_total_mcap
        "n_below_floor", "n_in_bottom_pct", "n_no_ref", "binding_constraint",
        "n_kept_actual", "total_mktcap_actual", "matches_actual",
        "n_total_mktcap_distinct", "screen_pooled",
    ]]
    by_ccy = by_ccy[[
        "ym", "year", "month", "curcdd",
        "n_pre", "n_kept", "n_dropped", "pct_dropped",
        "n_pre_gvkeys", "n_kept_gvkeys", "n_dropped_gvkeys",
        "size_floor_ccy", "largest_dropped_ccy", "cell_size_floor",
        "pre_mktcap_ccy", "kept_mktcap_ccy", "pct_mktcap_dropped_ccy",
        "cell_total_mktcap", "share_of_cell_mktcap",
        "n_kept_actual", "matches_actual_n",
    ]]

    # ---- 4. Headline summary --------------------------------------------------------- #
    # NB: local name is `floor_rows`, not `floor` -- `floor` is the config value read at
    # the top of this Process and shadowing it here would silently corrupt the summary.
    floor_rows = by.dropna(subset=["size_floor"]).sort_values("ym")
    first_floor = float(floor_rows["size_floor"].iloc[0]) if len(floor_rows) else float("nan")
    last_floor = float(floor_rows["size_floor"].iloc[-1]) if len(floor_rows) else float("nan")

    n_ccy = int(by_ccy["curcdd"].nunique())
    # The screen itself now pools caps across currency areas, so the question is no longer
    # "may this node sum them" (there is nothing left for this node to sum) but "was the
    # screen entitled to". process_global_universe enforces exactly this and raises, so a
    # False here should be unreachable on a healthy run -- an audit must not crash a run,
    # so it is reported rather than re-raised. Mirrors the screen's own condition (see
    # _common.mktcap_filter_kwargs).
    screen_currency_safe = bool(C["convert_to_USD"]) or n_ccy <= 1

    row = {
        "market_cap_filter": method,
        "filter_period": "month" if method == "percent_total_mcap" else "year",
        "screen_cell": ("year-month, pooled across currency areas"
                        if method == "percent_total_mcap"
                        else "year, pooled across currency areas"),
        "currency_filter": ", ".join(currency_filter) if currency_filter else "(all)",
        "convert_to_USD": bool(C["convert_to_USD"]),
        "currency_areas": n_ccy,
        "screen_currency_safe": bool(screen_currency_safe),
        "months": int(by["ym"].nunique()),
        "first_month": str(by["ym"].min()),
        "last_month": str(by["ym"].max()),
        "mean_n_pre": float(by["n_pre"].mean()),
        "mean_n_dropped": float(by["n_dropped"].mean()),
        "mean_pct_dropped": float(by["pct_dropped"].mean()),
        "min_pct_dropped": float(by["pct_dropped"].min()),
        "max_pct_dropped": float(by["pct_dropped"].max()),
        "size_floor_first_bn": first_floor / 1e9,
        "size_floor_last_bn": last_floor / 1e9,
        "max_pct_mktcap_dropped": float(by["pct_mktcap_dropped"].max()),
    }

    if method == "percent_total_mcap":
        # Only this rule has a value budget, and only here does the ordering invariant hold
        # month by month. Reported as None under the other method so a vacuous True can
        # never be mistaken for a real check.
        row["mktcap_covered_if_filter_by_cum_market_cap"] = float(cov)
        row["percentage_stocks_removed"] = None
        row["floor_bn"] = None
        row["mktcap_budget_respected"] = bool(
            (by["pct_mktcap_dropped"] <= 100.0 * (1.0 - cov) + 1e-9).all()
        )
        row["boundary_ordering_ok"] = bool(
            (by["largest_dropped"] <= by["size_floor"])
            .where(by["largest_dropped"].notna(), True).all()
        )
        row["n_months_floor_binding"] = None
        row["n_months_pct_binding"] = None
        row["prefix_invariant_ok"] = None
        # Descriptive only -- NOT an invariant. The budget above is a property of the
        # POOLED cell; a single currency area can legitimately lose more than it, because
        # the budget was never promised per-area. Reported here rather than corrupting
        # mktcap_budget_respected with a check the screen never made.
        _budget_pct = 100.0 * (1.0 - cov)
        row["max_pct_mktcap_dropped_ccy"] = float(by_ccy["pct_mktcap_dropped_ccy"].max())
        row["n_ccy_months_over_budget"] = int(
            (by_ccy["pct_mktcap_dropped_ccy"] > _budget_pct + 1e-9).sum()
        )
    else:
        row["mktcap_covered_if_filter_by_cum_market_cap"] = None
        row["percentage_stocks_removed"] = float(pct)
        row["floor_bn"] = float(floor) / 1e9
        row["mktcap_budget_respected"] = None
        row["boundary_ordering_ok"] = None
        row["n_months_floor_binding"] = int((by["binding_constraint"] == "floor").sum())
        row["n_months_pct_binding"] = int((by["binding_constraint"] == "pct_stocks").sum())
        # Both selection sets are prefixes of the ascending-cap order, so their
        # intersection is a prefix and the dropped count is the smaller of the two --
        # except where listings lack a Y-1 reference and are dropped on top of that.
        _expect = by[["n_below_floor", "n_in_bottom_pct"]].min(axis=1) + by["n_no_ref"]
        row["prefix_invariant_ok"] = bool((by["n_dropped"] == _expect).all())
        # No cumulative value budget exists under this rule -- see cum_threshold above.
        row["max_pct_mktcap_dropped_ccy"] = None
        row["n_ccy_months_over_budget"] = None

    row["cross_check_all_match"] = bool(
        by["matches_actual"].all() and by_ccy["matches_actual_n"].all()
    )
    row["cross_check_n_mismatched"] = int((~by["matches_actual"]).sum())
    row["cross_check_n_mismatched_ccy"] = int((~by_ccy["matches_actual_n"]).sum())
    row["screen_pooled_confirmed"] = bool(by["screen_pooled"].all())
    summary = pd.DataFrame([row])

    print(f"[mktcap_filter_audit] {len(by)} months, "
          f"pct_dropped mean={row['mean_pct_dropped']:.1f}% "
          f"range=[{row['min_pct_dropped']:.1f}%, {row['max_pct_dropped']:.1f}%], "
          f"size_floor {first_floor / 1e9:.2f}bn -> {last_floor / 1e9:.2f}bn, "
          f"currency_areas={n_ccy}, "
          f"cross-check all_match={row['cross_check_all_match']} "
          f"(pooled n_mismatched={row['cross_check_n_mismatched']}, "
          f"per-currency-area n_mismatched={row['cross_check_n_mismatched_ccy']}, "
          f"screen_pooled_confirmed={row['screen_pooled_confirmed']})")

    return pack_obj({
        "mktcap_filter_by_month": by,
        "mktcap_filter_by_currency": by_ccy,
        "mktcap_filter_summary": summary,
    })


NODE = Node(
    name="mktcap_filter_audit",
    contract=CONTRACT,
    store=store,
    inputs=("universe", "cfg"),
    outputs=("out",),
)
