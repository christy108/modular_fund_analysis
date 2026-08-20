"""Audit the market-cap filter that shrinks the tradable universe.

Node `mktcap_filter_audit`: a pure diagnostic on the filter inside
functions/data_functions/process_data.py::process_global_universe, which has two selectable
methods (``cfg.market_cap_filter``) and is the pipeline's single largest sample cut:

* ``percent_total_mcap`` — per currency-MONTH. Sort listings ascending by month-end cap,
  cumulate from the smallest, keep those whose running total exceeds
  ``(1 - mktcap_covered_if_filter_by_cum_market_cap)`` of the cell total.
* ``percent_stocks`` — per currency-YEAR, on the previous year's last cap. Drop a listing
  iff it is both among the smallest x% BY COUNT and below an absolute floor.

Either way the filter is invisible from the outside: it prints nothing, and the number of
listings it removed cannot be recovered from its own output.

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


def _binding_constraint(bundle):
    """Three lines showing which of the two `percent_stocks` conditions actually bit.

    Empty under `percent_total_mcap`, which has no such conditions. A step function under
    the yearly rule — one level per year — which is the correct depiction of an annual
    rebalance, not a rendering artefact.
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
        if df[col].isna().all():
            # The column exists but belongs to the other method (e.g. cum_threshold under
            # percent_stocks). Return nothing rather than one all-None series, which would
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
    intent="""Make the market-cap universe filter visible, whichever of its two methods ran.
That filter lives inside ``process_global_universe`` and is the pipeline's largest single
sample cut, yet it reports nothing and its own output cannot reveal how many listings it
removed. This node replays it from the same per-region universes and reports, per
currency-month: how many listings entered, how many were removed, what share that is, and the
effective per-listing size floor (the smallest market cap that survived) — which is what a
reader usually means by "the cutoff".

Which method ran is read from ``cfg.market_cap_filter`` and the replay branches to match:

- ``percent_total_mcap`` — per currency-MONTH; keeps listings whose cumulative cap exceeds
  ``(1 - mktcap_covered_if_filter_by_cum_market_cap) x total_mktcap``. Also reported: that
  literal threshold, a CUMULATIVE budget over the whole discarded tail and NOT a per-listing
  size (it is ~300x the size floor; conflating the two is the standard misreading).
- ``percent_stocks`` — per currency-YEAR, decided on each listing's last cap in Y-1: dropped
  iff both among the smallest ``percentage_stocks_removed_if_percent_stocks_true`` of listings
  BY COUNT and below ``floor_if_percent_stocks_true``. Also reported: which of the two
  conditions bound each year, and how many listings were dropped purely for having no Y-1
  observation. The two methods' percentages are NOT comparable — one is a share of aggregate
  value, the other a share of the listing count.

Scope boundary: this node owns no numerics that anything else consumes. It re-derives a filter
that already ran upstream, purely so the filter can be inspected. No downstream node reads its
output, and ``parity.compare`` does not diff its artifacts.

Mandatory measures (enforced by schema / audits):
- the replayed kept-listing count and currency-month ``total_mktcap`` equal the real
  post-filter ``global_universe``'s, per currency-month (``matches_actual`` in the by-month
  table; ``cross_check_all_match`` in the summary). Expected to be vacuously true against a
  frozen ``process_global_universe`` and a pinned pandas — it is a regression canary for a
  pandas upgrade changing groupby/sort semantics, not a numerical reconciliation.
- ``percent_total_mcap`` only: market cap actually dropped never exceeds the configured budget
  (because the strict ``>`` keeps the listing straddling the threshold),
  ``pct_mktcap_dropped <= 100 x (1 - mktcap_covered_if_filter_by_cum_market_cap)``; and
  ``largest_dropped <= size_floor`` always, since the sort is ascending by cap (equality means
  the boundary fell inside a tie). Both are reported as ``None`` under ``percent_stocks``, where
  they are meaningless, rather than as a vacuous pass — the second because the ranking uses the
  Y-1 cap while those two are measured on the current month's caps, so a dropped listing can
  legitimately out-grow a kept one during year Y.
- ``percent_stocks`` only: ``n_dropped == min(n_below_floor, n_in_bottom_pct) + n_no_ref``
  (``prefix_invariant_ok``). Both selection sets are prefixes of the ascending-cap order, so
  their intersection is a prefix and the smaller set is the binding one.
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
differ by orders of magnitude (``BundleDualAxisViz``); the effective per-listing size floor over
time, in billions (``BundleMultiSeriesViz``); and the headline summary including the cross-check
verdict (``BundleTableViz``) — all three under either method. Plus one method-specific chart
each, blank when its method is not the active one, since ``Contract.audits`` is static at import
time and cannot branch on cfg: the cumulative discard budget for ``percent_total_mcap``, and the
binding-constraint comparison for ``percent_stocks`` (``BundleMultiSeriesViz``). The full
per-currency-month numbers are deliberately NOT a widget — 144+ rows read badly on a dashboard —
but they are still bundled and exported as ``mktcap_filter_by_month.parquet`` for anyone who
wants the exact figures.""",
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
                "Populated under **both** methods — the cutoff in the sense you probably "
                "mean it: a single listing had to be worth at least this much to survive "
                "that month.\n\n"
                "Under `percent_total_mcap`, contrast the discard-budget chart, which is a "
                "SUM over 1,077-1,713 firms and therefore 283-388x larger — not a comparable "
                "magnitude. Under `percent_stocks` this can sit *below* the configured floor: "
                "that happens exactly when the bottom-x% cap binds before the floor does, so "
                "listings under the floor survive because they are not among the very "
                "smallest.\n\n" + _UNITS_NOTE
            ),
        ),
        BundleMultiSeriesViz(
            _series_by_currency("cum_threshold", scale=1e9),
            title=("DISCARD BUDGET, summed over all dropped listings: (1 - coverage) x total "
                   "market cap (billions) — percent_total_mcap only"),
            key="lines:mktcap_filter_cum_threshold",
            description=(
                "**Blank unless `market_cap_filter=\"percent_total_mcap\"`** — the other rule "
                "has no cumulative budget.\n\n"
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
    pre_sorted = pre.sort_values(by=["date"])
    del pre
    sec = (
        pre_sorted.groupby(["month", "year", "curcdd", "gvkey", "iid"])
        .agg(last_mktcap=("mktcap", "last"))
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
            pre_sorted.groupby(["year", "curcdd", "gvkey", "iid"])
            .agg(ref_mktcap=("mktcap", "last"))
            .reset_index()
        )
    del pre_sorted

    sec = sec.sort_values(by=["month", "year", "curcdd", "last_mktcap"])
    grouped = sec.groupby(["month", "year", "curcdd"])["last_mktcap"]
    # Computed under both methods: informative either way, and percent_total_mcap's test
    # needs them.
    sec["cumulative_mktcap"] = grouped.cumsum()
    sec["total_mktcap"] = grouped.transform("sum")

    if method == "percent_total_mcap":
        sec["kept"] = sec["cumulative_mktcap"] > (1 - cov) * sec["total_mktcap"]
        sec["no_ref"] = False
    else:
        # Rank by COUNT within each reference year+currency, decide, then shift the
        # reference year forward so Y-1's decision governs year Y.
        ref = ref.sort_values(by=["year", "curcdd", "ref_mktcap"])
        _c = ["year", "curcdd"]
        ref["ref_pct_rank"] = (ref.groupby(_c).cumcount() + 1) / ref.groupby(_c)[
            "ref_mktcap"
        ].transform("size")
        ref["in_bottom_pct"] = ref["ref_pct_rank"] <= pct
        ref["below_floor"] = ref["ref_mktcap"] < floor
        ref["drop_ref"] = ref["in_bottom_pct"] & ref["below_floor"]
        ref["year"] = ref["year"] + 1
        sec = sec.merge(
            ref[["year", "curcdd", "gvkey", "iid", "ref_mktcap", "ref_pct_rank",
                 "in_bottom_pct", "below_floor", "drop_ref"]],
            on=["year", "curcdd", "gvkey", "iid"], how="left",
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
    by["pct_mktcap_dropped"] = (
        100.0 * (by["total_mktcap"] - by["kept_mktcap"]) / by["total_mktcap"]
    )

    # ---- method-specific columns ----------------------------------------------------- #
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
        # Merged on `keys`, not assigned via .values: `by` has a RangeIndex by this point,
        # so a positional assignment would rely on this groupby emitting rows in exactly
        # the order `all_g` did — true today, and a silent mis-alignment the day it isn't.
        _counts = (
            sec.groupby(keys)[["below_floor", "in_bottom_pct", "no_ref"]].sum()
            .rename(columns={"below_floor": "n_below_floor",
                             "in_bottom_pct": "n_in_bottom_pct",
                             "no_ref": "n_no_ref"})
            .reset_index()
        )
        by = by.merge(_counts, on=keys, how="left")
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
    # A currency-month with ZERO survivors produces no group in `actual`, so the outer
    # merge leaves NaN rather than 0 -- and total_mktcap_actual is genuinely unreadable
    # there, since there are no surviving rows to read it off. Treat "absent from the real
    # frame" as zero kept, and only compare the total where the real frame has rows.
    # Without this, a legitimately empty cell reports as a cross-check FAILURE: under
    # percent_stocks every month of the earliest year is empty (no listing has a Y-1
    # reference), which is the rule working, not a replay mismatch.
    _cell_present = by["n_kept_actual"].notna()
    by["n_kept_actual"] = by["n_kept_actual"].fillna(0)
    by["matches_actual"] = (by["n_kept"] == by["n_kept_actual"]) & (
        ~_cell_present
        | np.isclose(by["total_mktcap"], by["total_mktcap_actual"],
                     rtol=0.0, atol=0.0, equal_nan=True)
    )
    by = by.sort_values(["ym", "curcdd"]).reset_index(drop=True)
    by = by[[
        "ym", "year", "month", "curcdd", "filter_period",
        "n_pre", "n_kept", "n_dropped", "pct_dropped",
        "n_pre_gvkeys", "n_kept_gvkeys", "n_dropped_gvkeys",
        "size_floor", "largest_dropped", "boundary_tied",
        "cum_threshold", "total_mktcap", "kept_mktcap", "pct_mktcap_dropped",
        # percent_stocks only; NaN/"" under percent_total_mcap
        "n_below_floor", "n_in_bottom_pct", "n_no_ref", "binding_constraint",
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
    # NB: local name is `floor_rows`, not `floor` -- `floor` is the config value read at
    # the top of this Process and shadowing it here would silently corrupt the summary.
    floor_rows = by.dropna(subset=["size_floor"]).sort_values("ym")
    first_floor = float(floor_rows["size_floor"].iloc[0]) if len(floor_rows) else float("nan")
    last_floor = float(floor_rows["size_floor"].iloc[-1]) if len(floor_rows) else float("nan")

    row = {
        "market_cap_filter": method,
        "filter_period": "month" if method == "percent_total_mcap" else "year",
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

    row["cross_check_all_match"] = bool(by["matches_actual"].all())
    row["cross_check_n_mismatched"] = int((~by["matches_actual"]).sum())
    summary = pd.DataFrame([row])

    print(f"[mktcap_filter_audit] {len(totals)} months, "
          f"pct_dropped mean={row['mean_pct_dropped']:.1f}% "
          f"range=[{row['min_pct_dropped']:.1f}%, {row['max_pct_dropped']:.1f}%], "
          f"size_floor {first_floor / 1e9:.2f}bn -> {last_floor / 1e9:.2f}bn, "
          f"cross-check all_match={row['cross_check_all_match']}")

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
