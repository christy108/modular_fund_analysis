"""Audit: measure the tie mass sitting exactly ON each quantile cutpoint.

Why this node exists
--------------------
``univariate_portfolio_sorting`` (functions/functions.py:6) builds half-open buckets
``(q_{i-1}, q_i]``: the low bucket ``s <= q_1`` KEEPS a tie block sitting on its cutpoint,
while the high bucket ``s > q_{K-1}`` DROPS one. That asymmetry is invisible for a
continuous signal (no observation ever lands exactly on a cutpoint) but not for a signal
built from small integer counts, whose distribution is atomic.

It becomes measurable whenever two signals are affine complements. If ``z_b = -z_a`` then
``q^b_1 = -q^a_{K-1}``, so::

    High_a = {z_a >  q^a_{K-1}}
    Low_b  = {z_a >= q^a_{K-1}}

and the two sets differ by EXACTLY ``{z_a == q^a_{K-1}}`` -- the tie mass on the cutpoint.
``base_materiality``'s Material / Immaterial pair is exactly this case (they sum to 1,
correlation -1.00), and its High Material portfolio is empirically short of its Low
Immaterial mirror by up to 24% of the bucket.

The two sparsity tables narrowed this by elimination but cannot close it: node 02 measures
the raw signal's atoms at 0 and at max, node 06 measures the largest tie block ANYWHERE in
the standardised cross-section. Neither measures the block ON a cutpoint, which is the only
one that does damage -- so on real data they give an upper bound that is tight in some years
and vacuous in others. This node measures the thing itself and tests the prediction
``gap == expected_gap``, which either confirms the mechanism quantitatively or proves a
second mechanism is at work.

The tie block always lands in the bucket that uses ``<=``, so which side gains it FLIPS with
the end being compared -- ``expected_gap`` is ``+tie`` for High_a-vs-Low_b and ``-tie`` for
Low_a-vs-High_b. Getting that sign wrong makes a fully-explained end look unexplained.

Audit-only: nothing downstream reads it, and it computes no new numerics -- it replays a
sort that already happened.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process

from New_Pipeline._common import cfg_schema, open_schema, store
from New_Pipeline.dashboard_viz import (
    BundleColoredTableViz,
    BundleMultiSeriesViz,
    BundleTableViz,
)


# ---- Dashboard extractors (bundle -> widget payloads; no computation happens here) --- #

def _mirror_pair_summary(bundle):
    """One row per (complementary pair, end): does the observed bucket gap equal the tie
    mass on the cutpoint? Empty when the config has no complementary pair."""
    return bundle.get("mirror_pair_summary")


def _sort_cutpoint_summary(bundle):
    """One row per signal: how often a cutpoint lands on a tie block, and whether the
    replay reproduced the real sort."""
    return bundle.get("sort_cutpoint_summary")


def _mirror_gap_series(bundle):
    """One line per (pair, end): the monthly bucket-size gap. Answers *which* months."""
    by_month = bundle.get("mirror_pairs_by_month")
    if by_month is None or by_month.empty:
        return []
    out = []
    for label, grp in by_month.groupby("pair_end", sort=True):
        g = grp.sort_values("date")
        out.append({
            "name": str(label),
            "x": [str(d)[:10] for d in g["date"]],
            "y": [int(v) for v in g["gap"]],
        })
    return out


CONTRACT = Contract(
    name="sort_cutpoint_audit",
    intent="""Measure the tie mass sitting exactly ON each quantile cutpoint, and test whether it
explains the observed mirror-portfolio discrepancy.

``univariate_portfolio_sorting`` cuts half-open buckets ``(q_{i-1}, q_i]``, so a tie block
landing on a cutpoint is KEPT by the bucket below it and DROPPED by the bucket above. For two
signals that are affine complements (``z_b = -z_a``, e.g. Material / Immaterial, which sum to 1)
the cutpoints mirror exactly -- ``q^b_1 = -q^a_{K-1}`` -- but the interval convention does not:
``High_a = {z_a > q}`` while ``Low_b = {z_a >= q}``. The two portfolios should be identical and
instead differ by exactly the tie mass at ``q``.

No existing table can measure this. Node 02's ``pct_zero`` / ``pct_at_max`` locate the raw
signal's atoms at 0 and at its maximum; node 06's ``largest_tie_pct`` finds the biggest tie block
anywhere in the standardised cross-section. A tie block only causes damage if it lands on a
cutpoint, and none of those columns know where the cutpoints are -- which is why they behave as an
upper bound on real data, tight in some years and vacuous in others.

This node replays the sort from the standardised pivots (recomputing
``s.quantile(np.linspace(1/K, 1, K))`` exactly as the sort does), records the tie mass on every
cutpoint, and then CROSS-CHECKS itself against the real buckets from
``build_analyse_portfolios``. The cross-check is why it depends on the portfolio node rather than
on ``prepare_panel`` alone: without it a replay bug would be indistinguishable from a finding.
``matches_actual`` / ``cross_check_all_match`` are expected vacuously true and exist as a
regression canary -- they break if node 07's pre-sort ``bad_columns`` drop, its
``first_conditioning_set``, or pandas' quantile interpolation ever changes.

Complementary pairs are DETECTED (pooled Pearson correlation <= -0.99), not hardcoded, so the
audit also covers the SDG and ``_counts`` designs. Configs with no such pair produce an empty
mirror table rather than an error.

Mandatory measures:
- ``sort_cutpoints_by_month`` -- (signal, date, q_index): the cutpoint value, and the count and
  share of the cross-section sitting exactly on it. Long format, so any K fits.
- ``sort_buckets_by_month`` -- (signal, date): cross-section size, replayed vs ACTUAL low/high
  bucket sizes, and ``matches_actual`` / ``all_buckets_match``.
- ``mirror_pairs_by_month`` -- the decisive table. Per (pair, end, date): both bucket sizes, the
  ``gap``, the set differences either way, ``tie_at_cutpoint``, ``expected_gap`` (``+tie`` at the
  High_a-vs-Low_b end, ``-tie`` at the other -- the tie block always joins the bucket that uses
  ``<=``, so which side gains it flips), and ``gap_explained = (gap == expected_gap)``.
  ``cutpoint_sum`` (``q^a_{K-1} + q^b_1``, expected 0) is the float-rounding escape hatch: pandas'
  linear-interpolation quantile does not round identically on x and -x, so in a handful of months
  the two cutpoints are not bit-exact mirrors and one asset falls the other side of the cut.
- ``mirror_pair_summary`` / ``sort_cutpoint_summary`` -- per-pair and per-signal rollups.

Surfaces: the pair-level verdict (``pct_gap_explained``), the per-signal cross-check status, and
the monthly gap as a time series. Read ``months_unexplained`` for the verdict: it counts months
that miss the tie prediction AND have bit-exact mirrored cutpoints, so anything above 0 is a
second mechanism. ``months_float_rounding`` absorbs the quantile-rounding months separately.

Gated by ``cfg.show_sort_cutpoint_audit`` (default True). The per-month tables are exported as
parquet but deliberately NOT dashboard widgets: at 100+ formation months x signals they are far
too long to read there (the ``mktcap_filter_by_month`` precedent). Read the parquet for exact
figures.""",
    input_schema={"prep": open_schema(), "portfolios": open_schema(), "cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[
        # Explicit keys throughout: an unkeyed BundleTableViz collapses to the literal
        # "table:" and collides with every other unkeyed one on the same Contract.
        BundleColoredTableViz(
            _mirror_pair_summary,
            title="Mirror-portfolio verdict — does the cutpoint tie mass explain the gap?",
            color_col="pair", n=1000,
            key="colored_table:mirror_pair_summary",
            description=(
                "The point of this node. Each row is one complementary signal pair at one end "
                "of the sort. Because the two signals are affine complements, the two "
                "portfolios named in `pair_end` are the *same portfolio* and should hold "
                "identical names; any gap is an artefact of the sort's interval "
                "convention.\n\n"
                "- **pair** / **pair_end** — the two signals, and which ends are being "
                "compared (`High A vs Low B`). Both ends of every pair get a row.\n"
                "- **corr** — pooled Pearson correlation of the two standardised panels. "
                "Pairs are detected at <= -0.99 rather than hardcoded.\n"
                "- **max_abs_sum** — largest `|z_a + z_b|` over every cell. Exactly 0 means "
                "the two are *exact* complements, so the mirror should be exact and any gap "
                "is entirely down to tie handling.\n"
                "- **n_months** — formation months compared.\n"
                "- **months_gap_nonzero** / **pct_months_gap_nonzero** — how often the two "
                "portfolios that should be identical actually differ in size.\n"
                "- **median_gap** — signed size difference in names. The sign flips "
                "between the two ends of a pair (the tie block always joins whichever "
                "bucket uses `<=`), so magnitude is reported separately as "
                "**max_abs_gap**; **max_gap_pct** expresses the worst month as a share of "
                "the larger bucket.\n"
                "- **months_gap_explained** / **pct_gap_explained** — the share of months "
                "where `gap` equals `expected_gap` (`+tie_at_cutpoint` at the High-vs-Low "
                "end, `-tie_at_cutpoint` at the other) exactly.\n"
                "- **months_float_rounding** — months that miss that prediction but whose "
                "two cutpoints are *not* bit-exact mirrors (`cutpoint_sum != 0`, at ~1e-16). "
                "pandas' linear-interpolation quantile does not round identically on `x` and "
                "`-x`, so one asset falls the other side of the cut. Float noise, not a "
                "mechanism.\n"
                "- **months_unexplained** — **the verdict.** Months that miss the prediction "
                "*and* have bit-exact mirrored cutpoints. **0 means the tie mechanism fully "
                "accounts for the discrepancy**; anything above 0 is a second mechanism that "
                "still needs finding.\n"
                "- **max_abs_cutpoint_sum** — largest `|q^a_(K-1) + q^b_1|`. The cutpoints "
                "are algebraic mirrors, so this should be 0 or at rounding scale."
            ),
        ),
        BundleTableViz(
            _sort_cutpoint_summary,
            title="Cutpoint ties by signal (with replay cross-check)",
            key="table:sort_cutpoint_summary",
            description=(
                "One row per signal, describing how often the sort's cutpoints land on a "
                "block of exactly-equal values — the only ties that change a portfolio's "
                "membership.\n\n"
                "- **n_months** — formation months sorted. One fewer than the panel's "
                "months: `compute_returns` never forms a portfolio on the last date.\n"
                "- **median_assets** — sortable (non-NaN) assets in a typical month.\n"
                "- **months_tie_on_low_cut** / **months_tie_on_high_cut** — months where a "
                "tie block sits exactly on `q_1` / `q_K-1`. The low cutpoint's block is "
                "absorbed into the Low bucket (`<=`); the high cutpoint's block is excluded "
                "from the High bucket (`>`). That difference is the whole bug.\n"
                "- **median_tie_on_high_cut** / **max_tie_on_high_cut** — names excluded "
                "from the High bucket by that convention, in a typical and the worst "
                "month.\n"
                "- **months_any_cutpoint_tie** — months where *any* of the K-1 cutpoints "
                "lands on a tie block, so interior buckets are affected too.\n"
                "- **cross_check_all_match** / **cross_check_n_mismatched** — whether this "
                "node's replay reproduced the REAL bucket sizes from "
                "`build_analyse_portfolios`, month by month. Expected vacuously true; it is "
                "a regression canary. False invalidates every other number here and points "
                "at the replay (node 07's `bad_columns` inf-drop, `first_conditioning_set`, "
                "or pandas' quantile interpolation), not at the sort."
            ),
        ),
        BundleMultiSeriesViz(
            _mirror_gap_series,
            title="Mirror-portfolio gap over time (names, not %)",
            key="lines:mirror_gap",
            description=(
                "The monthly size gap between two portfolios that should be identical, in "
                "number of names. Flat at 0 means the mirror holds that month; a step up "
                "means a tie block landed on a cutpoint. Steps are typically flat for "
                "several months because the signal is annual — the cross-section only "
                "changes when a new fiscal year becomes tradeable, so a tie block that "
                "straddles a cutpoint keeps doing so until then. Read alongside the per-year "
                "sparsity tables: a tie block existing is necessary but not sufficient, and "
                "this chart shows the months where it actually bit."
            ),
        ),
    ],
)


@process(tag="sort_cutpoint_audit@v1", contract="sort_cutpoint_audit", author="audit")
def sort_cutpoint_audit_v1(prep, portfolios, cfg):
    import json
    from itertools import combinations

    import numpy as np
    import pandas as pd

    from New_Pipeline.boundary import pack_obj, unpack_obj

    C = json.loads(cfg["json"][0])
    if not C.get("show_sort_cutpoint_audit", True):
        # Empty bundle rather than empty frames or empty_sentinel(): unpack_obj still
        # succeeds so every extractor's `bundle.get(...) -> None` guard renders the widget
        # blank, and run.py's export loop writes nothing.
        return pack_obj({})

    P = unpack_obj(prep)
    B = unpack_obj(portfolios)
    signals = P.get("signals") or {}
    signal_names = dict(P.get("signal_names") or {})
    actual = B.get("signal_quantile_constituents") or {}
    K = int(C["no_simple_quantiles"])
    # The replay must use whatever convention the real sort used, or matches_actual below
    # reports a replay mismatch instead of a finding. See univariate_portfolio_sorting.
    closed = C.get("quantile_interval_bounds", "half_open") == "closed"

    if not signals or K < 2:
        return pack_obj({})

    # ---- replicate node 07's pre-sort column drop ----------------------------------- #
    # 07_build_analyse_portfolios.py:306-314 drops every gvkey_iid column holding an inf in
    # ANY signal, before sorting. prep's bundled pivots are PRE-drop, so replaying without
    # this would sort a different cross-section than the real run did. Replicated rather
    # than read back off the actual constituents on purpose: an independent replay is what
    # gives matches_actual below any diagnostic value.
    bad_columns = set()
    for df in signals.values():
        num = df.select_dtypes(include=[np.number])
        if num.empty:
            continue
        bad_columns.update(num.columns[np.isinf(num).any(axis=0)].tolist())
    signals = {k: v.drop(columns=list(bad_columns), errors="ignore") for k, v in signals.items()}

    # Formation dates: compute_returns loops range(first_conditioning_set, T-1), with
    # first_conditioning_set hardcoded to 0 in node 07 -- so the LAST date never forms a
    # portfolio. Off-by-one here shifts every row against the actual constituents.
    first_conditioning_set = 0

    # ---- per-month replay: cutpoints, cutpoint ties, bucket membership -------------- #
    cut_rows = []      # (signal, date, q_index)
    bucket_rows = []   # (signal, date)
    # {(signal_col, date): {"low": Index, "high": Index, "q_low": float, "q_high": float}}
    replay = {}

    for col, wide in signals.items():
        name = signal_names.get(col, col)
        dates = list(wide.index)
        actual_list = actual.get(col) or []
        # Actual constituents are a list of Series keyed by formation date in .name; index
        # by date rather than by position so a length mismatch cannot silently misalign.
        actual_by_date = {}
        for s in actual_list:
            try:
                actual_by_date[pd.Timestamp(s.name)] = s
            except Exception:
                continue

        for i in range(first_conditioning_set, len(dates) - 1):
            dt = dates[i]
            row = wide.iloc[i, :]
            s = row.dropna()
            n = len(s)
            if n == 0:
                continue

            # Exactly as univariate_portfolio_sorting does it.
            q = s.quantile(np.linspace(1 / K, 1, num=K))
            counts = s.value_counts()

            for j in range(K - 1):          # K-1 interior cutpoints; q_K is the max
                qv = float(q.iloc[j])
                n_at = int(counts.get(qv, 0))
                cut_rows.append({
                    "signal": name, "date": pd.Timestamp(dt),
                    "q_index": j + 1, "q_value": qv,
                    "n_at_cutpoint": n_at,
                    "pct_at_cutpoint": round(100.0 * n_at / n, 2),
                })

            q_low, q_high = float(q.iloc[0]), float(q.iloc[K - 2])
            low = s.index[(s <= q_low).values]
            high = s.index[((s >= q_high) if closed else (s > q_high)).values]

            act = actual_by_date.get(pd.Timestamp(dt))
            n_low_actual = n_high_actual = -1
            if act is not None:
                if "p_1" in act.index:
                    n_low_actual = int(len(pd.Index(act["p_1"])))
                if f"p_{K}" in act.index:
                    n_high_actual = int(len(pd.Index(act[f"p_{K}"])))

            bucket_rows.append({
                "signal": name, "date": pd.Timestamp(dt), "n_assets": n,
                "n_low_replay": int(len(low)), "n_high_replay": int(len(high)),
                "n_low_actual": n_low_actual, "n_high_actual": n_high_actual,
                "matches_actual": bool(
                    n_low_actual == len(low) and n_high_actual == len(high)
                ),
                "n_at_low_cut": int(counts.get(q_low, 0)),
                "n_at_high_cut": int(counts.get(q_high, 0)),
            })
            replay[(col, pd.Timestamp(dt))] = {
                "low": low, "high": high, "q_low": q_low, "q_high": q_high,
            }

    sort_cutpoints_by_month = pd.DataFrame(cut_rows)
    sort_buckets_by_month = pd.DataFrame(bucket_rows)

    # ---- per-signal rollup ---------------------------------------------------------- #
    summary_rows = []
    if not sort_buckets_by_month.empty:
        any_tie = (
            sort_cutpoints_by_month.assign(hit=sort_cutpoints_by_month["n_at_cutpoint"] > 0)
            .groupby(["signal", "date"])["hit"].any()
            .groupby("signal").sum()
        )
        for name, g in sort_buckets_by_month.groupby("signal", sort=True):
            summary_rows.append({
                "signal": name,
                "n_months": int(len(g)),
                "median_assets": int(g["n_assets"].median()),
                "months_tie_on_low_cut": int((g["n_at_low_cut"] > 0).sum()),
                "months_tie_on_high_cut": int((g["n_at_high_cut"] > 0).sum()),
                "median_tie_on_high_cut": int(g["n_at_high_cut"].median()),
                "max_tie_on_high_cut": int(g["n_at_high_cut"].max()),
                "months_any_cutpoint_tie": int(any_tie.get(name, 0)),
                "cross_check_all_match": bool(g["matches_actual"].all()),
                "cross_check_n_mismatched": int((~g["matches_actual"]).sum()),
            })
    sort_cutpoint_summary = pd.DataFrame(summary_rows)

    # ---- detect complementary pairs -------------------------------------------------- #
    # z_b = -z_a is the case that makes the interval convention observable. Detected on the
    # pooled standardised panels so this generalises past Material/Immaterial; max_abs_sum
    # then reports how exact the complement actually is.
    flat = {}
    for col, wide in signals.items():
        flat[col] = wide.to_numpy(dtype=float).ravel()
    pairs = []
    for a, b in combinations(sorted(signals), 2):
        va, vb = flat[a], flat[b]
        ok = np.isfinite(va) & np.isfinite(vb)
        if ok.sum() < 2:
            continue
        xa, xb = va[ok], vb[ok]
        if xa.std() == 0 or xb.std() == 0:
            continue
        corr = float(np.corrcoef(xa, xb)[0, 1])
        if corr <= -0.99:
            pairs.append((a, b, corr, float(np.abs(xa + xb).max())))

    # ---- mirror test: High_a vs Low_b, and Low_a vs High_b -------------------------- #
    mirror_rows = []
    for a, b, corr, max_abs_sum in pairs:
        na, nb = signal_names.get(a, a), signal_names.get(b, b)
        # (label, bucket taken from a, bucket taken from b, which cutpoint of `a` the tie
        # block sits on). The tie block on a's HIGH cutpoint is dropped from High_a but
        # kept by Low_b, and vice versa at the other end.
        ends = [
            (f"High {na} vs Low {nb}", "high", "low", "q_high"),
            (f"Low {na} vs High {nb}", "low", "high", "q_low"),
        ]
        for label, bkt_a, bkt_b, qkey in ends:
            for (col, dt) in [k for k in replay if k[0] == a]:
                ra = replay.get((a, dt))
                rb = replay.get((b, dt))
                if ra is None or rb is None:
                    continue
                ia, ib = pd.Index(ra[bkt_a]), pd.Index(rb[bkt_b])
                # Tie mass on a's relevant cutpoint, recovered from the by-month table.
                qv = ra[qkey]
                sa = signals[a].loc[dt].dropna()
                tie = int((sa == qv).sum())
                gap = int(len(ib) - len(ia))
                # Under "half_open" the tie block lands in whichever bucket uses `<=`, so
                # which side gains it flips with the end being compared:
                #   High_a vs Low_b : Low_b  keeps it -> b is LARGER -> expected gap = +tie
                #   Low_a  vs High_b: Low_a  keeps it -> a is LARGER -> expected gap = -tie
                # Under "closed" BOTH buckets include their boundary, so the two mirror
                # portfolios coincide and the gap must be 0 regardless of the tie mass --
                # which is exactly the check that the closed convention did its job.
                expected_gap = 0 if closed else (tie if bkt_a == "high" else -tie)
                mirror_rows.append({
                    "pair": f"{na} / {nb}",
                    "pair_end": label,
                    "date": pd.Timestamp(dt),
                    "n_a": int(len(ia)),
                    "n_b": int(len(ib)),
                    "gap": gap,
                    "n_only_in_a": int(len(ia.difference(ib))),
                    "n_only_in_b": int(len(ib.difference(ia))),
                    "tie_at_cutpoint": tie,
                    "expected_gap": int(expected_gap),
                    "gap_explained": bool(gap == expected_gap),
                    # Cutpoints are algebraic mirrors (q^b_1 = -q^a_{K-1}); a non-zero value
                    # at 1e-16 scale is quantile-interpolation rounding, not a new effect.
                    "cutpoint_sum": float(ra["q_high"] + rb["q_low"]) if bkt_a == "high"
                    else float(ra["q_low"] + rb["q_high"]),
                    "corr": round(corr, 6),
                    "max_abs_sum": max_abs_sum,
                })
    mirror_pairs_by_month = pd.DataFrame(mirror_rows)

    # ---- pair-level verdict --------------------------------------------------------- #
    pair_rows = []
    if not mirror_pairs_by_month.empty:
        for (pair, end), g in mirror_pairs_by_month.groupby(["pair", "pair_end"], sort=True):
            nz = g[g["gap"] != 0]
            denom = g[["n_a", "n_b"]].max(axis=1).replace(0, np.nan)
            # Months that miss the tie prediction but whose two cutpoints are not bit-exact
            # mirrors: pandas' linear-interpolation quantile rounds differently on x and -x,
            # so an asset can fall the other side of the cut. Reported separately because it
            # is float noise (~1e-16), not a second mechanism.
            miss = g[~g["gap_explained"]]
            float_rounding = int((miss["cutpoint_sum"].abs() > 0).sum())
            pair_rows.append({
                "pair": pair,
                "pair_end": end,
                "corr": round(float(g["corr"].iloc[0]), 6),
                "max_abs_sum": float(g["max_abs_sum"].iloc[0]),
                "n_months": int(len(g)),
                "months_gap_nonzero": int(len(nz)),
                "pct_months_gap_nonzero": round(100.0 * len(nz) / len(g), 1),
                # Signed, because which bucket is the larger one flips between the two
                # ends; magnitude separately, or an end whose gaps are all negative
                # summarises as max_gap=0 and reads as "no discrepancy".
                "median_gap": int(g["gap"].median()),
                "max_abs_gap": int(g["gap"].abs().max()),
                "max_gap_pct": round(float((g["gap"].abs() / denom).max() * 100), 1),
                "months_gap_explained": int(g["gap_explained"].sum()),
                "pct_gap_explained": round(100.0 * g["gap_explained"].mean(), 1),
                "months_float_rounding": float_rounding,
                "months_unexplained": int(len(miss) - float_rounding),
                "max_abs_cutpoint_sum": float(g["cutpoint_sum"].abs().max()),
            })
    mirror_pair_summary = pd.DataFrame(pair_rows)

    if not mirror_pair_summary.empty:
        for _, r in mirror_pair_summary.iterrows():
            print(f"[sort_cutpoint_audit] {r['pair_end']}: gap nonzero in "
                  f"{r['months_gap_nonzero']}/{r['n_months']} months, max {r['max_abs_gap']} "
                  f"names ({r['max_gap_pct']}%), explained {r['pct_gap_explained']}% "
                  f"(+{r['months_float_rounding']} float-rounding, "
                  f"{r['months_unexplained']} unexplained)")
    if not sort_cutpoint_summary.empty:
        print(f"[sort_cutpoint_audit] replay cross-check all_match="
              f"{bool(sort_cutpoint_summary['cross_check_all_match'].all())}")

    return pack_obj({
        "sort_cutpoints_by_month": sort_cutpoints_by_month,
        "sort_buckets_by_month": sort_buckets_by_month,
        "mirror_pairs_by_month": mirror_pairs_by_month,
        "mirror_pair_summary": mirror_pair_summary,
        "sort_cutpoint_summary": sort_cutpoint_summary,
    })


NODE = Node(
    name="sort_cutpoint_audit",
    contract=CONTRACT,
    store=store,
    inputs=("prep", "portfolios", "cfg"),
    outputs=("out",),
)
