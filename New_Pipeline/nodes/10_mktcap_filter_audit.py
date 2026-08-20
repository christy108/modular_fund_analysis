"""Audit the market-cap coverage filter that shrinks the tradable universe.

Node `mktcap_filter_audit`: a pure diagnostic on the filter applied inside
functions/data_functions/process_data.py::process_global_universe (lines 149-187),
which sorts each currency-month's listings ascending by market cap, cumulates from the
smallest upward, and keeps only those whose running total exceeds ``(1 - mktcap_covered)``
of that currency-month's total. It is the pipeline's single largest sample cut and is
currently invisible: it prints nothing, and the number of listings it removed cannot be
recovered from its own output.

Why the filter has to be replayed here rather than read off an upstream output:
``merge_esg_provider``'s ``global_universe`` retains ``last_mktcap`` / ``cumulative_mktcap``
/ ``total_mktcap``, so the KEPT caps, the currency-month total and the threshold are all
exactly recoverable — but the PRE-filter listing count is not, because the dropped rows are
gone. So the process replays the filter from the same node's per-region universes, on the
five columns the filter actually reads, and then cross-checks itself against the real
post-filter frame (kept-listing count and ``total_mktcap`` per currency-month) so that a
drift in the replay is loud rather than silent.

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
    """One row per year-month, counts summed across currency areas (a listing count carries
    no currency, so summing is always safe; the cap columns are populated only when summing
    them is currency-safe)."""
    return bundle.get("mktcap_filter_totals")


def _summary(bundle):
    """One row of headline stats: the configured coverage, the window, the range of
    percentage-dropped, and the cross-check verdict."""
    return bundle.get("mktcap_filter_summary")


def _series_by_currency(col: str, scale: float = 1.0):
    """One line per currency area for ``col`` over year-months.

    ``scale`` divides the values for readability — market caps here are absolute currency
    units, not millions (``mktcap = prccd * cshoc``). Values are cast to plain ``float``
    because ``Manifest.save`` calls ``json.dumps`` with no ``default=`` handler, so a numpy
    scalar reaching this payload aborts the run *after* the pipeline has already succeeded.
    """
    def extract(bundle):
        import pandas as pd

        df = bundle.get("mktcap_filter_by_month")
        if df is None or len(df) == 0 or col not in df.columns:
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


_UNITS_NOTE = (
    "**Units: billions, not millions.** `mktcap` is `prccd x cshoc` — whole currency units "
    "(a $184m firm is stored as `183919500.0`), *not* Compustat millions — so the raw value is "
    "divided by 1e9 here. Worked example from `base_none`: Jan-2013's raw `cum_threshold` is "
    "749,510,901,389, plotted as **749.5bn**, i.e. 5% of a 15.0tn total across 1,733 listings. "
    "Reading those as millions would imply a 15m-trillion US market.\n\n"
    "**Which currency** depends on `cfg.convert_to_USD` (reported in the summary table). When "
    "True, every cap was converted via `mktcap_lcu / rate`, so the values are USD bn *even "
    "though each line is named after the listing currency* — the line name is the `curcdd` "
    "grouping key, not the unit. When False the values are in that listing currency. Every "
    "currently registered config is `region_analysis=\"United_States\"` (`convert_to_USD=False`, "
    "USD listings only), so these are USD bn — but a `region_analysis=\"Japan\"` run keeps "
    "`convert_to_USD=False` with JPY listings and would plot JPY bn."
)


CONTRACT = Contract(
    name="mktcap_filter_audit",
    intent="""Make the market-cap coverage filter visible. That filter runs inside
``process_global_universe`` and is the pipeline's largest single sample cut, yet it reports
nothing and its own output cannot reveal how many listings it removed. This node replays it
from the same per-region universes and reports, per currency-month: how many listings entered,
how many were removed, what share that is, and the exact numerical cutoff — both the literal
threshold in the code (``(1 - mktcap_covered) x total_mktcap``, a CUMULATIVE cap over the
discarded tail) and the effective per-listing size floor (the smallest market cap that
survived), which is what a reader usually means by "the cutoff".

Scope boundary: this node owns no numerics that anything else consumes. It re-derives a filter
that already ran upstream, purely so the filter can be inspected. No downstream node reads its
output, and ``parity.compare`` does not diff its artifacts.

Mandatory measures (enforced by schema / audits):
- the replayed kept-listing count and currency-month ``total_mktcap`` equal the real
  post-filter ``global_universe``'s, per currency-month (``matches_actual`` in the by-month
  table; ``cross_check_all_match`` in the summary). Expected to be vacuously true against a
  frozen ``process_global_universe`` and a pinned pandas — it is a regression canary for a
  pandas upgrade changing groupby/sort semantics, not a numerical reconciliation.
- market cap actually dropped never exceeds the configured budget: because the strict ``>``
  keeps the listing straddling the threshold,
  ``pct_mktcap_dropped <= 100 x (1 - mktcap_covered)``
- ``largest_dropped <= size_floor`` always, since the sort is ascending by cap; equality means
  the boundary fell inside a tie
- counts are LISTING-level, keyed on (gvkey, iid) exactly as the filter groups; company-level
  (distinct gvkey) counts are reported alongside and are NOT the same number
- cap columns are never summed across currency areas unless every market cap is already in one
  currency (``convert_to_USD``, or a single-currency ``currency_filter``) — the same guard
  ``functions/extra_functions/plot_coverage.py`` enforces
- every cap column in the bundled/exported frames is in WHOLE currency units, not millions
  (``mktcap = prccd x cshoc``); only the ``*_bn`` summary fields and the two charts are scaled,
  by 1e9. The currency is USD whenever ``convert_to_USD`` is set or the listings are USD, and
  the listing currency otherwise (e.g. JPY for a ``region_analysis="Japan"`` run, which leaves
  ``convert_to_USD`` False)

Surfaces: listings dropped against percentage dropped over time, on separate y-axes since they
differ by orders of magnitude (``BundleDualAxisViz``); the effective size floor per currency
area over time, in billions (``BundleMultiSeriesViz``); the literal cumulative threshold per
currency area, in billions (``BundleMultiSeriesViz``); and the headline summary including the
cross-check verdict (``BundleTableViz``). The full per-currency-month numbers are deliberately
NOT a widget — 144+ rows read badly on a dashboard — but they are still bundled and exported as
``mktcap_filter_by_month.parquet`` for anyone who wants the exact figures.""",
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
            _series_by_currency("size_floor", scale=1e9),
            title="PER-FIRM cutoff: market cap of the smallest listing kept (billions)",
            key="lines:mktcap_filter_size_floor",
            description=(
                "The cutoff in the sense you probably mean it: a single listing had to be "
                "worth at least this much to survive that month. Contrast the discard-budget "
                "chart below, which is a SUM over 1,077-1,713 firms and is therefore 283-388x "
                "larger — the two are not comparable magnitudes.\n\n" + _UNITS_NOTE
            ),
        ),
        BundleMultiSeriesViz(
            _series_by_currency("cum_threshold", scale=1e9),
            title=("DISCARD BUDGET, summed over all dropped listings: "
                   "(1 - mktcap_covered) x total market cap (billions)"),
            key="lines:mktcap_filter_cum_threshold",
            description=(
                "**This is not a per-firm size.** It is the total market cap the filter is "
                "allowed to discard collectively, and it is never compared against one "
                "firm's cap: the test is `cumulative_mktcap > threshold`, where "
                "`cumulative_mktcap` means 'my cap plus everything smaller than me'.\n\n"
                "Worked example (base_none, Jan-2013): the budget is 749.5bn = 5% of a "
                "14,990bn market. The 1,081 listings actually dropped sum to 748.2bn — a mean "
                "of 692m each. The largest of them is 2.64bn and the smallest survivor is "
                "2.65bn, so the PER-FIRM boundary is ~2.65bn (see the chart above), roughly "
                "283x smaller than this budget. Both numbers are correct; they measure "
                "different things.\n\n" + _UNITS_NOTE
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
    cov = C["mktcap_covered"]
    currency_filter = C["currency_filter"]

    # ---- 1. Replay the PRE-filter security-month set -------------------------------- #
    # Mirrors process_global_universe lines 113-187 on the five columns the filter reads.
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
    sec = (
        pre.sort_values(by=["date"])
        .groupby(["month", "year", "curcdd", "gvkey", "iid"])
        .agg(last_mktcap=("mktcap", "last"))
        .reset_index()
    )
    del pre
    sec = sec.sort_values(by=["month", "year", "curcdd", "last_mktcap"])
    grouped = sec.groupby(["month", "year", "curcdd"])["last_mktcap"]
    sec["cumulative_mktcap"] = grouped.cumsum()
    sec["total_mktcap"] = grouped.transform("sum")
    sec["kept"] = sec["cumulative_mktcap"] > (1 - cov) * sec["total_mktcap"]
    print(f"[mktcap_filter_audit] replayed {len(sec)} listing-months, "
          f"{int(sec['kept'].sum())} kept at mktcap_covered={cov}")

    # ---- 2. Aggregate to one row per currency-month --------------------------------- #
    keys = ["year", "month", "curcdd"]
    all_g = sec.groupby(keys)
    kept, dropped = sec[sec["kept"]], sec[~sec["kept"]]

    by = pd.DataFrame({
        "n_pre": all_g.size(),
        "n_kept": all_g["kept"].sum(),
        "n_pre_gvkeys": all_g["gvkey"].nunique(),
        "total_mktcap": all_g["total_mktcap"].first(),
    })
    by["n_kept_gvkeys"] = kept.groupby(keys)["gvkey"].nunique()
    by["size_floor"] = kept.groupby(keys)["last_mktcap"].min()
    by["largest_dropped"] = dropped.groupby(keys)["last_mktcap"].max()
    by["kept_mktcap"] = kept.groupby(keys)["last_mktcap"].sum()
    by = by.reset_index()

    by["n_dropped"] = by["n_pre"] - by["n_kept"]
    by["pct_dropped"] = 100.0 * by["n_dropped"] / by["n_pre"]
    by["n_dropped_gvkeys"] = by["n_pre_gvkeys"] - by["n_kept_gvkeys"]
    by["cum_threshold"] = (1.0 - cov) * by["total_mktcap"]
    by["pct_mktcap_dropped"] = (
        100.0 * (by["total_mktcap"] - by["kept_mktcap"]) / by["total_mktcap"]
    )
    # Ascending-by-cap sort means every dropped listing precedes every kept one, so
    # largest_dropped <= size_floor holds by construction; equality means the threshold
    # fell inside a tie and the boundary does not strictly separate.
    by["boundary_tied"] = by["largest_dropped"] == by["size_floor"]
    by["ym"] = (
        by["year"].astype(int).astype(str) + "-"
        + by["month"].astype(int).astype(str).str.zfill(2)
    )

    # ---- 3. Cross-check against the REAL post-filter frame --------------------------- #
    # Counts and totals only, never a join on gvkey: the frozen function reformats it
    # (astype(float).astype(int).astype(str)) and the node then zfills it, so the real
    # frame's "001004" is not comparable to this replay's "1004.0". The real frame is DAILY
    # rows (last_values is merged back onto every trading day), hence the drop_duplicates
    # to recover kept listing-months.
    guniv = U["global_universe"]
    actual = (
        guniv.drop_duplicates(subset=["year", "month", "curcdd", "gvkey", "iid"])
        .groupby(keys)
        .agg(n_kept_actual=("gvkey", "size"),
             total_mktcap_actual=("total_mktcap", "first"))
        .reset_index()
    )
    by = by.merge(actual, on=keys, how="outer")
    by["matches_actual"] = (
        (by["n_kept"] == by["n_kept_actual"])
        & np.isclose(by["total_mktcap"], by["total_mktcap_actual"],
                     rtol=0.0, atol=0.0, equal_nan=True)
    )
    by = by.sort_values(["ym", "curcdd"]).reset_index(drop=True)
    by = by[[
        "ym", "year", "month", "curcdd",
        "n_pre", "n_kept", "n_dropped", "pct_dropped",
        "n_pre_gvkeys", "n_kept_gvkeys", "n_dropped_gvkeys",
        "size_floor", "largest_dropped", "boundary_tied",
        "cum_threshold", "total_mktcap", "kept_mktcap", "pct_mktcap_dropped",
        "n_kept_actual", "total_mktcap_actual", "matches_actual",
    ]]

    # ---- 4. Totals across currency areas -------------------------------------------- #
    # Listing counts carry no currency, so they always sum. Market caps do NOT unless every
    # row is already in one currency — the same guard
    # functions/extra_functions/plot_coverage.py::compute_coverage_over_time enforces (it
    # raises; an audit must not crash a run, so the cap columns are simply omitted).
    currency_safe = bool(C["convert_to_USD"]) or by["curcdd"].nunique() <= 1
    tg = by.groupby("ym", sort=True)
    totals = pd.DataFrame({"n_pre": tg["n_pre"].sum(), "n_kept": tg["n_kept"].sum()})
    totals["n_dropped"] = totals["n_pre"] - totals["n_kept"]
    # Recomputed, never averaged: the mean of per-currency percentages is not the
    # percentage of the pooled universe.
    totals["pct_dropped"] = 100.0 * totals["n_dropped"] / totals["n_pre"]
    if currency_safe:
        totals["size_floor"] = tg["size_floor"].min()
        totals["cum_threshold"] = tg["cum_threshold"].sum()
        totals["total_mktcap"] = tg["total_mktcap"].sum()
        totals["pct_mktcap_dropped"] = 100.0 * (
            1.0 - tg["kept_mktcap"].sum() / tg["total_mktcap"].sum()
        )
    totals = totals.reset_index()

    # ---- 5. Headline summary --------------------------------------------------------- #
    floor = by.dropna(subset=["size_floor"]).sort_values("ym")
    first_floor = float(floor["size_floor"].iloc[0]) if len(floor) else float("nan")
    last_floor = float(floor["size_floor"].iloc[-1]) if len(floor) else float("nan")
    boundary_ok = bool(
        (by["largest_dropped"] <= by["size_floor"])
        .where(by["largest_dropped"].notna(), True).all()
    )
    summary = pd.DataFrame([{
        "mktcap_covered": float(cov),
        "currency_filter": ", ".join(currency_filter) if currency_filter else "(all)",
        "convert_to_USD": bool(C["convert_to_USD"]),
        "currency_areas": int(by["curcdd"].nunique()),
        "currency_safe_totals": bool(currency_safe),
        "months": int(totals["ym"].nunique()),
        "first_month": str(totals["ym"].min()),
        "last_month": str(totals["ym"].max()),
        "mean_n_pre": float(totals["n_pre"].mean()),
        "mean_n_dropped": float(totals["n_dropped"].mean()),
        "mean_pct_dropped": float(totals["pct_dropped"].mean()),
        "min_pct_dropped": float(totals["pct_dropped"].min()),
        "max_pct_dropped": float(totals["pct_dropped"].max()),
        "size_floor_first_bn": first_floor / 1e9,
        "size_floor_last_bn": last_floor / 1e9,
        "max_pct_mktcap_dropped": float(by["pct_mktcap_dropped"].max()),
        "mktcap_budget_respected": bool(
            (by["pct_mktcap_dropped"] <= 100.0 * (1.0 - cov) + 1e-9).all()
        ),
        "boundary_ordering_ok": boundary_ok,
        "cross_check_all_match": bool(by["matches_actual"].all()),
        "cross_check_n_mismatched": int((~by["matches_actual"]).sum()),
    }])

    print(f"[mktcap_filter_audit] {len(totals)} months, "
          f"pct_dropped mean={summary['mean_pct_dropped'].iloc[0]:.1f}% "
          f"range=[{summary['min_pct_dropped'].iloc[0]:.1f}%, "
          f"{summary['max_pct_dropped'].iloc[0]:.1f}%], "
          f"size_floor {first_floor / 1e9:.2f}bn -> {last_floor / 1e9:.2f}bn, "
          f"cross-check all_match={summary['cross_check_all_match'].iloc[0]}")

    return pack_obj({
        "mktcap_filter_by_month": by,
        "mktcap_filter_totals": totals,
        "mktcap_filter_summary": summary,
    })


NODE = Node(
    name="mktcap_filter_audit",
    contract=CONTRACT,
    store=store,
    inputs=("universe", "cfg"),
    outputs=("out",),
)
