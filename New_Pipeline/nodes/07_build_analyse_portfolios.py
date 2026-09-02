"""Sort into quantile portfolios and produce every downstream portfolio-level analytic.

Node `build_analyse_portfolios`: **fully-merged reporting node** — folds the former
separate stages `build_portfolios` (05), `ff3_alphas` (06), `performance_tables` (07),
and `build_constituents` (08) into a single stage. All portfolio-level analytics are
produced, recorded and audited together. Reproduces Main.ipynb cells 31, 34, 36-39, 42,
43, 48, 51 (table construction), 58, and 59 verbatim, reusing:
  * ``functions/portfolio_strategy_design/Univariate_Portfolio.py``
  * ``functions/functions.set_first_row_to_zero`` and ``functions.low_high``
  * ``functions/portfolio_metrics/fama_french.{ff3_regressions,rolling_ff_alphas}``
  * ``functions/portfolio_metrics/Strategy_Perfomance.StrategyPerformance``
  * ``functions/portfolio_metrics/Portfolio_Constituents.PortfolioConstituents``
No math changes — same functions, same call order, same inputs. Emits a lossless
(pickle) bundle carrying every downstream artifact + audit input for the dashboard.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process
from leonardo_nodes.viz import BarComparisonViz

from New_Pipeline._common import cfg_schema, open_schema, store
from New_Pipeline.boundary import unpack_obj
from New_Pipeline.dashboard_viz import (
    BundleMultiSeriesViz,
    BundleSeriesViz,
    BundleStackedAreaViz,
    BundleTableViz,
)
from New_Pipeline.initiative_brackets import SCHEME_SLUGS, scheme_title


# ---- Row-count stats (real, unpack the bundle) --------------------------------------- #

def _ff3_rows(df) -> int:
    """Statistic: FF3 statistic rows carried in the bundle."""
    return int(len(unpack_obj(df)["ff3_parts_df"]))


def _rolling_rows(df) -> int:
    """Statistic: rolling-alpha observations carried in the bundle."""
    return int(len(unpack_obj(df)["rolling_alphas"]))


# ---- Dashboard extractors (bundle -> widget payloads; no computation happens here) --- #

def _dropped(bundle) -> set:
    """Labels hidden by the thin-portfolio gate. Empty when the gate is off or nothing failed.

    Filtering happens HERE, in the extractors, not in the Process: the bundle keeps every
    portfolio, so run.py's exports are untouched and the gate can never move a parity
    artifact. It is a presentation rule, not an analysis one.
    """
    return set(bundle.get("dropped_portfolio_labels") or [])


def _portfolio_gate_summary(bundle):
    """One-row status line: the thresholds in force and which legs they hid."""
    return bundle.get("portfolio_gate_summary")


def _portfolio_coverage(bundle):
    """One row per High/Low leg: how often it clears the minimum stock count."""
    return bundle.get("portfolio_coverage")


def _cumulative_wealth_series(bundle, *, spreads: bool) -> list[dict]:
    """Cumulative wealth (1+r).cumprod() per column of table_returns, matching
    Main.ipynb cell 51's plot split: spread columns (the High-Low legs) go on
    their own chart; every other column (Market, High/Low X, ...) on the other.
    Same series the notebook's ``plot_cumulative_returns`` draws — no new analysis.
    """
    table_returns = bundle["table_returns"]
    spread_cols = [c for c in bundle["spread_cum"] if c in table_returns.columns]
    cols = spread_cols if spreads else [c for c in table_returns.columns if c not in spread_cols]
    cols = [c for c in cols if c not in _dropped(bundle)]
    if not cols:
        return []
    wealth = (1.0 + table_returns[cols].sort_index()).cumprod()
    dates = [str(d)[:10] for d in wealth.index]
    return [
        {"name": col, "x": dates, "y": [None if v != v else float(v) for v in wealth[col]]}
        for col in cols
    ]


def _long_cumulative_series(bundle) -> list[dict]:
    return _cumulative_wealth_series(bundle, spreads=False)


def _spread_cumulative_series(bundle) -> list[dict]:
    return _cumulative_wealth_series(bundle, spreads=True)


def _drop_rows(df, bundle, col="portfolio"):
    """Hide gated portfolios from a table whose rows are labelled by `col` or by the index.

    In the BUNDLE, cumulative_table / risk_table carry the portfolio as the DataFrame
    INDEX -- run.py only names it "portfolio" when it exports
    (``pd_to_pl(frame, index_name="portfolio")``). Filtering on the column alone was a
    silent no-op for exactly the two tables this gate most needs to filter.
    """
    d = _dropped(bundle)
    if df is None or not d:
        return df
    if col in df.columns:
        return df[~df[col].isin(d)].reset_index(drop=True)
    return df[~df.index.isin(d)]


def _cumulative_table(bundle):
    """Formatted cumulative-returns table (rows = portfolios, cols = 1m..Since launch)."""
    return _drop_rows(bundle["cumulative_table"], bundle)


def _risk_table(bundle):
    """Formatted risk-metrics table (rows = portfolios, cols = Sharpe/VaR/MaxDD/Alpha/p)."""
    return _drop_rows(bundle["risk_table"], bundle)


def _ff3_table(bundle):
    """FF3 regression table (metric x portfolio)."""
    df = bundle["ff3_parts_df"]
    d = _dropped(bundle)
    return df.drop(columns=[c for c in df.columns if c in d]) if d else df


def _rolling_plot(window: int):
    """Build a multi-line rolling-alpha PLOT extractor: one line per portfolio label."""

    def extract(bundle) -> list[dict]:
        import pandas as pd

        df = bundle["rolling_alphas"]
        sub = df[(df["window"] == window) & (~df["label"].isin(_dropped(bundle)))]
        series: list[dict] = []
        for label, group in sub.groupby("label", sort=False):
            group = group.sort_values("date")
            series.append(
                {
                    "name": str(label),
                    "x": [str(d) for d in pd.to_datetime(group["date"]).dt.date],
                    "y": [float(v) for v in group["alpha"]],
                }
            )
        return series

    return extract


def _stocks_over_time(bundle):
    """Number of stocks in the inspected (high) portfolio each formation month."""
    h = bundle.get("holdings_over_time")
    if h is None or len(h) == 0:
        return []
    counts = h.groupby("date").size().sort_index()
    return [{"x": str(d)[:10], "y": int(n)} for d, n in counts.items()]


def _bucket_industry(bundle, bucket_label: str):
    """Look up the per-bucket Industry-counts frame; None if this cfg didn't produce it."""
    return (bundle.get("per_bucket_industry") or {}).get(bucket_label)


def _bucket_count_series(bucket_label: str):
    """Extractor: total stocks per month in a specific bucket (row sum of Industry counts)."""

    def extract(bundle) -> list[dict]:
        wide = _bucket_industry(bundle, bucket_label)
        if wide is None or wide.empty:
            return []
        totals = wide.sum(axis=1).sort_index()
        return [{"x": str(d)[:10], "y": int(v)} for d, v in totals.items()]

    return extract


def _bucket_sector_share_series(bucket_label: str):
    """Extractor: monthly sector share (% of portfolio in each sector) as one line per sector."""

    def extract(bundle) -> list[dict]:
        import pandas as pd

        wide = _bucket_industry(bundle, bucket_label)
        if wide is None or wide.empty:
            return []
        row_totals = wide.sum(axis=1).replace(0, pd.NA)
        share = (wide.divide(row_totals, axis=0) * 100.0).sort_index()
        dates = [str(d)[:10] for d in share.index]
        series: list[dict] = []
        # Order sectors most-to-least populated (average share) so the legend is legible.
        for sector in share.mean(axis=0).sort_values(ascending=False).index:
            col = share[sector]
            series.append(
                {
                    "name": str(sector),
                    "x": dates,
                    "y": [None if pd.isna(v) else float(v) for v in col],
                }
            )
        return series

    return extract


# Buckets we generate widgets for. Deliberately over-broad — an unused bucket just
# renders an empty (collapsible) chart, because the extractors .get() their bundle key.
# Order = descending signal index, High before Low.
#
# _MAX_SIGNAL_WIDGETS must cover the widest action_characterization in
# experiments.build_cfg, currently 30 signals (signal_0..signal_29: the
# Materiality_Climate_Natural_Capital_vs_All_SDGS characterization — material/immaterial x
# (Climate & Natural Capital + each remaining SDG individually)). The per-bucket data is computed for EVERY signal present (see the
# `for _sig in signal_quantile_constituents` loop below), so a value too low here doesn't
# crash — it silently omits that signal's widgets. Bump it when a characterization with
# more signals is added.
_MAX_SIGNAL_WIDGETS = 4
_BUCKET_KEYS = [
    *[(_b, f"signal_{_i}")
      for _i in reversed(range(_MAX_SIGNAL_WIDGETS))
      for _b in ("high", "low")],
    ("high", "esg_refinitive"), ("low", "esg_refinitive"),
    ("high", "esg_msci"), ("low", "esg_msci"),
    ("high", "esg_sp"), ("low", "esg_sp"),
]
_BUCKET_PREFIX = {"high": "High", "low": "Low"}


def _bucket_audits() -> list:
    """Two collapsible widgets per bucket: total stock count, and sector share %.
    Generated up front so the Contract is static; unused buckets render empty."""
    audits: list = []
    for _bkt, _sig in _BUCKET_KEYS:
        label = f"{_BUCKET_PREFIX[_bkt]} {_sig}"          # bundle key
        title_stem = f"{_BUCKET_PREFIX[_bkt]} {_sig}"     # widget title uses raw sig name
        audits.append(
            BundleSeriesViz(
                _bucket_count_series(label),
                title=f"Stocks — {title_stem}",
                key=f"lines:count:{label}",
                collapsible=True,
                expanded=False,
            )
        )
        audits.append(
            BundleMultiSeriesViz(
                _bucket_sector_share_series(label),
                title=f"Sector share (%) — {title_stem}",
                key=f"lines:sector_share:{label}",
                collapsible=True,
                expanded=False,
            )
        )
    return audits


# ---- Material-initiative decomposition: extractors + widget grid --------------------- #
# Every payload below is read straight out of the bundle the Process already built; nothing
# is computed here. Empty when the run is not a Material_Immaterial_only + add_materiality
# one, in which case each widget renders blank rather than erroring.

_DECOMP_BUCKETS = ("High", "Low")
_DECOMP_WEIGHTINGS = (
    ("pooled", "pooled"),
    ("equal_weight", "equal-weight"),
)


def _decomp(bundle) -> dict:
    return bundle.get("initiative_decomposition") or {}


def _decomp_area_series(weighting: str, slug: str, bucket: str):
    """Extractor: one stacked band per bracket, as % of the leg's material initiatives."""

    def extract(bundle) -> list[dict]:
        import pandas as pd

        frame = (_decomp(bundle).get(weighting) or {}).get(slug, {}).get(bucket)
        if frame is None or len(frame) == 0:
            return []
        dates = [str(d)[:10] for d in frame.index]
        # frame.columns is the scheme's DECLARATION order (residual last). Never re-sort:
        # bands that swap places between months make an area chart unreadable.
        return [
            {
                "name": str(band),
                "x": dates,
                "y": [None if pd.isna(v) else float(v) for v in frame[band]],
            }
            for band in frame.columns
        ]

    return extract


def _decomp_levels_series(bucket: str):
    """Extractor: the LEVELS behind the shares - total material vs total initiatives."""

    def extract(bundle) -> list[dict]:
        frame = (_decomp(bundle).get("levels") or {}).get(bucket)
        if frame is None or len(frame) == 0:
            return []
        dates = [str(d)[:10] for d in frame.index]
        return [
            {"name": label, "x": dates, "y": [float(v) for v in frame[col]]}
            for col, label in (
                ("total_initiatives", "All initiatives (SASB workbook)"),
                ("total_material_initiatives", "Material initiatives"),
                # Same holdings, lc's own count. It disagrees with the workbook because the
                # two were built from different Golden vintages; plotting both makes the
                # size of that gap visible instead of leaving it inside a ratio.
                ("total_initiatives_lc", "All initiatives (LC)"),
            )
            if col in frame.columns
        ]

    return extract


def _decomp_coverage(bundle):
    return _decomp(bundle).get("coverage_summary")


# One per weighting: the two charts look similar and mean different things, so the
# difference has to be stated on each rather than once somewhere else on the page.
_WEIGHTING_DESCRIPTION = {
    "pooled": (
        "**Pooled sum** — add up every holding's initiatives, then take shares. This is "
        "literally *the initiatives that make up this portfolio*, so it answers \"what did "
        "this leg's reporting consist of\". Because firms report anywhere from 1 to 100+ "
        "initiatives, a handful of heavy reporters can set the whole mix; a shift in this "
        "chart can mean one large firm entered the leg rather than that its firms changed "
        "behaviour."
    ),
    "equal_weight": (
        "**Equal-weight across firms** — compute each holding's own mix first, then average "
        "across holdings. Every firm counts once regardless of how much it reports, which "
        "matches how the portfolio is actually weighted in returns, so this is the mix to "
        "read when attributing the leg's alpha. Holdings with no material initiatives are "
        "undefined and excluded (see `pct_holdings_zero_material`).\n\n"
        "Where this and the pooled chart disagree, the pooled mix is being driven by the "
        "biggest reporters rather than by the typical holding."
    ),
}

_DECOMP_DESCRIPTION = (
    "Composition of the **material** initiatives held by this leg, by formation month, as "
    "a share of `material__total`. Read it with the coverage table above: the denominator "
    "counts only material initiatives, so a holding with none contributes nothing to this "
    "chart."
)


def _decomposition_audits() -> list:
    """Coverage table, the two level charts, then the 20 area charts.

    Generated unconditionally: the Contract is built at import time, so the keys must be
    static. A run that does not produce the decomposition just renders them empty.
    """
    audits: list = [
        BundleTableViz(
            _decomp_coverage,
            title="Material-initiative decomposition — coverage",
            key="table:decomposition_coverage",
            description=(
                "The denominator behind every area chart below, and the reason to distrust "
                "one of them.\n\n"
                "Those charts decompose each leg's **material** initiatives, so a holding "
                "with `material__total == 0` contributes nothing at all — it is in the "
                "portfolio and absent from the chart. That is not rare on the Low leg, "
                "which is by construction the firms whose material share is lowest.\n\n"
                "- **pct_holdings_matched** — share of holdings that found a "
                "`(gvkey, rfyear)` row in the materiality workbook. Should be near 100; a "
                "shortfall means firm-years the universe kept but the LC trim dropped.\n"
                "- **pct_holdings_zero_material** — **the one to read.** Share of holdings "
                "with no material initiatives. The area charts describe the *complement* "
                "of this, so at 30% the chart is speaking for 70% of the leg.\n"
                "- **median_holdings_with_material** — the typical month's effective "
                "sample size for the equal-weight charts.\n"
                "- **pct_initiatives_material** — material as a share of "
                "`total_initiatives`. The sort's own target, aggregated to the leg; High "
                "should sit far above Low or the sort is not separating anything.\n"
                "- **total_initiatives** vs **total_initiatives_lc** — the SAME holdings "
                "counted two ways: material+immaterial+unmapped from the SASB workbook, "
                "and `n_predicted_initiatives` from LC. Not a vintage difference — the "
                "workbook is built from exactly this LC file. It is the **gvkey "
                "zero-padding alias**: LC stores some firm-years twice, under `1075` and "
                "`001075`. Both sides pad to one key, then Matchings *sums* the pair while "
                "this pipeline `drop_duplicates(keep=\"first\")` — the "
                "`WARNING: lc had N duplicate (gvkey, rfyear) rows` lines in "
                "`debug_prints.log`. So the workbook figure counts both reports and the LC "
                "one counts a single report.\n"
                "- **lc_vs_workbook_pct** — how much LC is missing. 3.3% of firm-years are "
                "affected and 4.7% of initiatives overall, but nearer 15% here, because "
                "the firms with duplicate identifier history are the large ones a "
                "market-cap-filtered universe holds. Only the workbook figure is a valid "
                "denominator against a workbook numerator; the LC one puts the High leg's "
                "material share above 100%.\n\n"
                "Audit-only. Nothing downstream reads it and it is not exported."
            ),
        ),
    ]
    for _bkt in _DECOMP_BUCKETS:
        audits.append(
            BundleMultiSeriesViz(
                _decomp_levels_series(_bkt),
                title=f"Initiatives in portfolio over time — {_bkt} Material",
                key=f"lines:decomp_levels:{_bkt}",
                collapsible=True,
                expanded=False,
                description=(
                    "Counts, not shares — the levels the area charts below normalise away. "
                    "A composition shift means something different when the underlying "
                    "count is also moving."
                ),
            )
        )
    # Bucket-major, then weighting, then scheme: keeps a leg's ten charts contiguous.
    for _bkt in _DECOMP_BUCKETS:
        for _w_key, _w_label in _DECOMP_WEIGHTINGS:
            for _slug in SCHEME_SLUGS:
                audits.append(
                    BundleStackedAreaViz(
                        _decomp_area_series(_w_key, _slug, _bkt),
                        title=(f"Material initiative mix (%) — {scheme_title(_slug)} — "
                               f"{_bkt} Material [{_w_label}]"),
                        key=f"area:decomp:{_w_key}:{_slug}:{_bkt}",
                        collapsible=True,
                        expanded=False,
                        description=(_DECOMP_DESCRIPTION + "\n\n"
                                     + _WEIGHTING_DESCRIPTION[_w_key]),
                    )
                )
    return audits


CONTRACT = Contract(
    name="build_analyse_portfolios",
    intent="""Build quantile portfolios from the prepared panel and, in the SAME stage, produce every
portfolio-level analytic: FF3 regression table (level + rolling), the cumulative-return / risk
tables, and constituent counts / holdings. The former separate stages ``build_portfolios``,
``ff3_alphas``, ``performance_tables``, and ``build_constituents`` are folded into this node so all
portfolio-level analytics are computed, recorded and audited together.

Sort each signal into quantile portfolios (p_1..p_K), subtract rf to get excess returns, add the
market row, form the per-signal High-Low spread (p_K - p_1). Run the level FF3 OLS (HC1) of each
portfolio's excess return on mktrf/smb/hml (Low/High per signal in insertion order, then spreads;
rounded to 2dp) and the rolling FF3 alphas at both configured windows (40 and 24). Build the horizon
compound returns (1m, 3m, YTD, 1yr, 3yr, 5yr, 10yr, Since launch) and the risk metrics (Sharpe on
excess returns, VaR 1%, Max Drawdown), attaching Alpha + p-value(alpha) from the level FF3 table for
matching columns. Derive, for the pinned sort key (the last signal in cfg.lc_signals insertion
order, or the ESG column under esg_full_universe), the constituent counts by category over time
plus the high-bucket holdings.

Which signals/legs are analysed (and any ESG leg) comes from cfg; how the tables are built is left
to the Process. cumulative_table and risk_table are formatted exactly as the notebook's tables.

Mandatory measures (enforced by schema / audits):
- output bundles every downstream artifact: ff3_parts_df, rolling_alphas, cumulative_table,
  risk_table, constituents_Industry (and constituents_loc outside esg_full_universe),
  holdings_over_time
- cumulative_table and risk_table share the same portfolio row keys (the Process raises otherwise)
- Alpha/p-value(alpha) appear only for portfolios present in ff3_parts_df
- constituent counts are non-negative integers per (date, portfolio, category_value)

Surfaces: FF3 statistic rows and rolling-alpha row counts (``BarComparisonViz``); the
Fama-French 3-factor table (``BundleTableViz``); rolling-alpha plots per window
(``BundleMultiSeriesViz``); cumulative-return plots for long portfolios and High-Low spreads
(``BundleMultiSeriesViz``); the cumulative-returns and risk-metrics tables (``BundleTableViz``);
number of stocks in the portfolio over time (``BundleSeriesViz``).

Also applies a thin-portfolio gate, reported just above that stock-count chart: for each High
(``p_K``) and Low (``p_1``) leg, the share of formation months in which it holds at least
``cfg.min_stocks_per_portfolio`` names. Below ``cfg.min_portfolio_coverage`` the leg is hidden
from the dashboard, and its High-Low spread with it (a spread needs both legs). A leg that is
EMPTY in any month is hidden unconditionally, whatever its coverage and even when the coverage
rule is switched off: ``compute_returns`` emits NaN for an empty bucket and ``(1+r).cumprod()``
skips NaN, so that month is silently recorded as a 0% return that never happened. Only the extreme
buckets are gated; the middle splits are neither gated nor presented. ``portfolio_coverage`` gives
the per-leg numbers and ``portfolio_gate_summary`` the one-line verdict.

The gate is PRESENTATION ONLY: filtering happens in the dashboard extractors, never in the
bundle, so every exported parquet still carries every portfolio and the gate cannot move a parity
artifact. A hidden leg's numbers remain in ``risk_table.parquet``.

Finally, on ``Material_Immaterial_only`` runs carrying the SASB counts, decomposes each leg's
MATERIAL initiatives into behavioural and SDG brackets over time (``BundleStackedAreaViz``, five
schemes x High/Low x pooled/equal-weight), with the underlying counts (``BundleMultiSeriesViz``)
and a coverage table (``BundleTableViz``). ``material__total`` is an opaque count, so the High-Low
alpha cannot otherwise be attributed to a behaviour or an SDG; this says what the leg's material
initiatives actually ARE and whether that mix drifts. Every scheme is normalised by
``material__total`` — including the old 3-way split, which covers only ~91% of it and therefore
carries an explicit ``Unclassified`` band rather than being rescaled to its own smaller total.
Each holding's fiscal year is read back off ``global_universe``'s ``rfyear``, the same point-in-time
key the signal merge used, so the initiatives shown for a formation month are the ones that month's
sort actually saw. Only ``signal_0`` is decomposed: under this characterization ``signal_1`` is its
exact mirror, so ``High signal_1`` and ``Low signal_0`` are the same portfolio. Audit-only —
nothing downstream reads it, no parquet is written, and it is empty for every other config.""",
    input_schema={"prep": open_schema(), "cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[
        BarComparisonViz(statistic="ff3_rows", title="FF3 statistic rows",
                         custom={"ff3_rows": _ff3_rows}),
        BarComparisonViz(statistic="rolling_rows", title="Rolling-alpha rows",
                         custom={"rolling_rows": _rolling_rows}),
        # Explicit keys: BundleTableViz's default key collapses to the literal "table:"
        # for every instance (it always passes columns=[] to SampleTableViz), so
        # multiple unkeyed BundleTableViz on one Contract silently collide in the
        # dashboard's per-node audit_stats dict — only the last one computed survives
        # and gets shown under every colliding widget.
        BundleTableViz(_ff3_table, title="Fama-French 3-factor table", n=50, key="table:ff3_parts_df"),
        BundleMultiSeriesViz(_rolling_plot(40), title="Rolling alpha — 40-month window",
                             key="lines:rolling_alpha_40"),
        BundleMultiSeriesViz(_rolling_plot(24), title="Rolling alpha — 24-month window",
                             key="lines:rolling_alpha_24"),
        BundleMultiSeriesViz(_long_cumulative_series, title="Cumulative returns — long portfolios",
                             key="lines:cumulative_long"),
        BundleMultiSeriesViz(_spread_cumulative_series, title="Cumulative returns — High-Low spreads",
                             key="lines:cumulative_spreads"),
        BundleTableViz(_cumulative_table, title="Cumulative returns (%)", key="table:cumulative_table"),
        BundleTableViz(_risk_table, title="Risk metrics", key="table:risk_table"),
        BundleTableViz(
            _portfolio_gate_summary,
            title="Thin-portfolio gate — which legs were hidden",
            key="table:portfolio_gate_summary",
            description=(
                "A quantile bucket holding a handful of names is not a portfolio — its "
                "return is idiosyncratic noise, and showing it beside well-populated ones "
                "invites reading signal into sampling error. This gate hides the ones that "
                "are too small too often.\n\n"
                "- **min_stocks_required** — `cfg.min_stocks_per_portfolio`. A leg must hold "
                "at least this many names. Set it to 0 to disable the gate.\n"
                "- **min_coverage_pct** — `cfg.min_portfolio_coverage`. It must clear that "
                "count in at least this share of formation months.\n"
                "- **n_legs** / **n_kept** / **n_dropped** — High and Low legs only; the "
                "middle splits are neither gated nor presented.\n"
                "- **n_dropped_empty** — how many of those were dropped for being EMPTY in "
                "at least one month rather than merely thin. That rule is unconditional: an "
                "empty bucket makes `compute_returns` emit NaN, and `(1+r).cumprod()` skips "
                "NaN, so the month is silently booked as a 0% return. Such a leg has "
                "fabricated flat months in its series and is not a portfolio at all.\n"
                "- **dropped** — the hidden labels, or `none`. A High−Low spread is listed "
                "whenever *either* of its legs failed, since a spread cannot outlive one "
                "unreliable side.\n\n"
                "**Presentation only.** Hidden legs are removed from the charts and the "
                "cumulative/risk/FF3 widgets above, but the exported parquets still contain "
                "every portfolio — so nothing is lost and this can never move a parity "
                "artifact. Read `risk_table.parquet` for a hidden leg's numbers."
            ),
        ),
        BundleTableViz(
            _portfolio_coverage,
            title="Portfolio size coverage — % of months at or above the minimum",
            key="table:portfolio_coverage",
            description=(
                "One row per High/Low leg, worst first. The evidence behind the gate "
                "above.\n\n"
                "- **label** / **signal** / **bucket** — the portfolio, as named in the "
                "charts and tables.\n"
                "- **n_months** — formation months. One fewer than the panel's months: no "
                "portfolio is formed on the last date.\n"
                "- **min_stocks** / **median_stocks** — the thinnest and typical month.\n"
                "- **n_months_empty** — months where the bucket held NOTHING. Any value "
                "above 0 hides the leg regardless of its coverage: those months are "
                "recorded as a 0% return that never happened, so the return series is "
                "partly fictional. Checked even when `min_stocks_per_portfolio=0`.\n"
                "- **pct_months_at_least_x** — **the measure.** Share of months holding at "
                "least `min_stocks_required` names. High is healthy; below "
                "`min_coverage_pct` the leg is hidden. Note this is the share of *months*, "
                "not of stocks — a leg can look fine on median size and still fail here if "
                "it collapses in a minority of months.\n"
                "- **kept** / **drop_reason** — whether it survived, and why not. The two "
                "reasons are independent and both are listed when both apply."
            ),
        ),
        BundleSeriesViz(_stocks_over_time, title="Stocks in portfolio over time"),
        # Per-bucket constituent widgets — all collapsed by default so the page
        # stays scannable; expand the ones you care about.
        *_bucket_audits(),
        # Material-initiative decomposition, directly beneath the sector-share charts it
        # is the sibling of. Empty outside Material_Immaterial_only + add_materiality.
        *_decomposition_audits(),
    ],
)


@process(tag="build_analyse_portfolios@v1", contract="build_analyse_portfolios", author="refactor")
def build_analyse_portfolios_v1(prep, cfg):
    import json
    from pathlib import Path

    import numpy as np
    import pandas as pd

    from functions.functions import low_high, set_first_row_to_zero
    from functions.portfolio_metrics.fama_french import ff3_regressions, rolling_ff_alphas
    from functions.portfolio_metrics.Portfolio_Constituents import PortfolioConstituents
    from functions.portfolio_metrics.Strategy_Perfomance import StrategyPerformance
    from functions.portfolio_strategy_design.Univariate_Portfolio import (
        UnivariateQuantilePortfolio,
    )
    from New_Pipeline.boundary import pack_obj, unpack_obj

    C = json.loads(cfg["json"][0])
    P = unpack_obj(prep)
    global_universe = P["global_universe"]
    global_returns = P["global_returns"]
    signals = P["signals"]
    signal_names = P["signal_names"]
    fama_french = P["fama_french"]

    K = C["no_simple_quantiles"]

    # ---- cell 31: drop columns (gvkeys) with inf values ------------------ #
    bad_columns = set()
    for df in signals.values():
        num = df.select_dtypes(include=[np.number])
        if num.empty:
            continue
        bad_columns.update(num.columns[np.isinf(num).any(axis=0)].tolist())
    bad_columns = list(bad_columns)
    print("gvekys dropped due to inf values:")
    print(bad_columns)
    signals = {name: df.drop(columns=bad_columns, errors="ignore") for name, df in signals.items()}

    # ---- cell 34: manual settings ---------------------------------------- #
    first_conditioning_set = 0
    no_simple_extremes_quantiles = 1
    take_extremes = False
    # How a firm sitting exactly ON a cutpoint is bucketed. .get() with a default so an
    # archived Process replayed against an older cfg (no such key) still runs -- same
    # backwards-compat pattern as signal_type in 02_derive_signals.py.
    quantile_interval_bounds = C.get("quantile_interval_bounds", "half_open")

    # ---- cell 36: quantile portfolios + constituents --------------------- #
    signal_quantiles: dict = {}
    signal_quantile_constituents: dict = {}
    for col, pivot in signals.items():
        U = UnivariateQuantilePortfolio(
            signal=pivot,
            returns=global_returns,
            n_quantiles=K,
            first_conditioning_set=first_conditioning_set,
            take_extremes=take_extremes,
            n_extremes_quantiles=no_simple_extremes_quantiles,
            quantile_interval_bounds=quantile_interval_bounds,
        )
        signal_quantiles[col] = U.compute_returns()
        signal_quantile_constituents[col] = U.get_constituents_over_time()

    # ---- thin-portfolio gate (PRESENTATION ONLY) -------------------------- #
    # A bucket of a handful of names is not a portfolio -- its return is idiosyncratic
    # noise. For each High (p_K) and Low (p_1) leg, measure the share of formation months
    # in which it holds at least `min_stocks_per_portfolio` names; below
    # `min_portfolio_coverage` the leg is hidden from the DASHBOARD (and its High-Low
    # spread with it, since a spread needs both legs). Only p_1 and p_K are gated -- the
    # middle splits are neither gated nor presented.
    #
    # Nothing is removed from the bundle: run.py exports the unfiltered frames, so this can
    # never move a parity artifact. The extractors do the hiding -- see _dropped().
    _min_stocks = int(C.get("min_stocks_per_portfolio", 0))
    _min_cov = float(C.get("min_portfolio_coverage", 0.0)) * 100.0
    _cov_rows, _dropped_labels, _bad_signals = [], [], set()
    _n_empty_dropped = [0]   # list so the inner loop can bump it without a nonlocal
    for _sig, _sel_list in signal_quantile_constituents.items():
        _nm = signal_names.get(_sig, _sig)
        for _bkt, _pcol in (("High", f"p_{K}"), ("Low", "p_1")):
            _sizes = [len(pd.Index(_s[_pcol])) for _s in _sel_list if _pcol in _s.index]
            if not _sizes:
                continue
            _sizes = pd.Series(_sizes, dtype=float)
            _pct = round(float((_sizes >= _min_stocks).mean()) * 100, 1)
            _n_empty = int((_sizes == 0).sum())
            _label = f"{_bkt} {_nm}"
            # Two independent reasons to hide a leg:
            #  * EMPTY in any month -- unconditional, and a correctness issue rather than a
            #    size preference. compute_returns sets val=NaN for an empty bucket, and
            #    (1+r).cumprod() skips NaN, so that month is silently booked as a 0% return.
            #    A leg that is ever empty therefore has FABRICATED flat months in its series.
            #    This fires even when min_stocks_per_portfolio=0 turns the coverage rule off.
            #  * too small too often -- the coverage rule.
            _reasons = []
            if _n_empty:
                _reasons.append(f"empty in {_n_empty} month(s)")
            if _pct < _min_cov:
                _reasons.append(f"coverage {_pct}% < {_min_cov:.0f}%")
            _kept = not _reasons
            if not _kept:
                _dropped_labels.append(_label)
                _bad_signals.add(_sig)
                if _n_empty:
                    _n_empty_dropped[0] += 1
            _cov_rows.append({
                "label": _label, "signal": _nm, "bucket": _bkt,
                "n_months": int(len(_sizes)),
                "min_stocks": int(_sizes.min()), "median_stocks": int(_sizes.median()),
                "n_months_empty": _n_empty,
                "pct_months_at_least_x": _pct,
                "min_stocks_required": _min_stocks,
                "kept": bool(_kept),
                "drop_reason": "; ".join(_reasons),
            })
    # A spread needs both legs, so one failing leg takes the spread with it.
    for _sig in _bad_signals:
        _dropped_labels.append(f"High - Low {signal_names.get(_sig, _sig)}")
    portfolio_coverage = pd.DataFrame(_cov_rows)
    if not portfolio_coverage.empty:
        portfolio_coverage = portfolio_coverage.sort_values(
            "pct_months_at_least_x").reset_index(drop=True)
    portfolio_gate_summary = pd.DataFrame([{
        "min_stocks_required": _min_stocks,
        "min_coverage_pct": round(_min_cov, 1),
        "n_legs": len(_cov_rows),
        "n_kept": sum(1 for r in _cov_rows if r["kept"]),
        "n_dropped": len(_dropped_labels),
        "n_dropped_empty": _n_empty_dropped[0],
        "dropped": ", ".join(_dropped_labels) if _dropped_labels else "none",
    }])
    print(f"[portfolio gate] >={_min_stocks} stocks in >={_min_cov:.0f}% of months -> "
          f"dropped: {portfolio_gate_summary.at[0, 'dropped']}")

    # ---- cell 37/38: market factor + excess returns ---------------------- #
    market_factor = fama_french["mktrf"]
    for col in signal_quantiles:
        signal_quantiles[col] = signal_quantiles[col].sub(fama_french["rf"].values, axis=0)
    Excess_returns_sample = (
        global_returns.mean(axis=1).sub(fama_french["rf"].values, axis=0).to_frame("Sample")
    )

    # ---- cell 39: zeroed-first-row copies for compounding ---------------- #
    global_returns_cum = set_first_row_to_zero(global_returns)
    signal_quantiles_cum = {c: set_first_row_to_zero(df) for c, df in signal_quantiles.items()}
    market_factor_cum = market_factor.copy()
    market_factor_cum.iloc[0] = 0

    # ---- cell 42: per-signal High-Low spreads ---------------------------- #
    hml_directions = C["hml_directions"]
    _hml_hi, _hml_lo = f"p_{K}", "p_1"
    spread_signals: dict = {}
    spread_cum: dict = {}
    for _sig, _dir in hml_directions.items():
        if _sig not in signal_quantiles:
            raise KeyError(f"{_sig!r} in hml_directions not found in signal_quantiles (available: {list(signal_quantiles)})")
        if _dir != "high_minus_low":
            raise ValueError(f"Unknown direction {_dir!r} for {_sig}; only 'high_minus_low' is supported")
        _label = f"High - Low {signal_names[_sig]}"
        spread_signals[_label] = (signal_quantiles[_sig][_hml_hi] - signal_quantiles[_sig][_hml_lo]).to_frame(_label)
        spread_cum[_label] = signal_quantiles_cum[_sig][_hml_hi] - signal_quantiles_cum[_sig][_hml_lo]

    # ---- cell 43: analysis selection ------------------------------------- #
    lc_signals = C["lc_signals"]
    esg_full_universe = C["esg_full_universe"]
    esg_choice = C["esg_choice"]
    base_analysis_selection = [(s, "high") for s in reversed(list(lc_signals))]
    if not esg_full_universe:
        base_analysis_selection.append(("signal_0", "low"))
    if esg_choice == "refinitiv":
        base_analysis_selection.append(("esg_refinitive", "high"))
    elif esg_choice == "s&p":
        base_analysis_selection.append(("esg_sp", "high"))
    elif esg_choice == "msci":
        base_analysis_selection.append(("esg_msci", "high"))

    _bucket_to_col = {"high": f"p_{K}", "low": "p_1"}
    _bucket_to_prefix = {"high": "High", "low": "Low"}

    # ---- cell 48: level FF3 statistics (ff3_parts_df) -------------------- #
    ff3_parts = [
        low_high(
            ff3_regressions(signal_quantiles[col], fama_french.reset_index(drop=True)),
            signal_names[col],
        )
        for col in signal_quantiles
    ]
    take_high_minus_low = True
    if take_high_minus_low:
        for _label, _df in spread_signals.items():
            ff3_parts.append(ff3_regressions(_df, fama_french.reset_index(drop=True)))
    if C["show_sample_portfolio"]:
        ff3_parts.append(ff3_regressions(Excess_returns_sample, fama_french.reset_index(drop=True)))
    ff3_parts_df = pd.concat(ff3_parts, axis=1).round(2)
    print(ff3_parts_df.head())

    # ---- cell 43: rolling alphas (windows 40 and 24) --------------------- #
    rolling_alpha_selection = base_analysis_selection
    _valid_buckets = {"high", "low"}
    _invalid = sorted({b for _, b in rolling_alpha_selection} - _valid_buckets)
    if _invalid:
        raise ValueError(f"Invalid bucket(s) in analysis_selection: {_invalid}. Use 'high' or 'low'.")
    _missing = sorted({c for c, _ in rolling_alpha_selection} - set(signal_quantiles))
    if _missing:
        raise KeyError(f"Signal key(s) in analysis_selection not found in signal_quantiles: {_missing}")
    rolling_signals_arg = [
        {
            "label": f"{_bucket_to_prefix[bucket]} {signal_names[col]}",
            "returns": signal_quantiles[col],
            "alpha_column": _bucket_to_col[bucket],
        }
        for col, bucket in rolling_alpha_selection
    ]
    if C["show_sample_portfolio"]:
        rolling_signals_arg.append({"label": "Sample", "returns": Excess_returns_sample, "alpha_column": "Sample"})
    for _label, _df in spread_signals.items():
        rolling_signals_arg.append({"label": _label, "returns": _df, "alpha_column": _label})
    n_factors = C["ff_factors_number"]
    w40 = None
    try:
        w40 = rolling_ff_alphas(signals=rolling_signals_arg, fama_french=fama_french, window_size=40, n_factors=n_factors)
    except Exception as e:  # matches notebook's guarded call
        print(f"Error in rolling_ff_alphas: {e}")
    w24 = rolling_ff_alphas(signals=rolling_signals_arg, fama_french=fama_french, window_size=24, n_factors=n_factors)
    _rolling_frames = []
    for _window, _dic in [(40, w40), (24, w24)]:
        if _dic is None:
            continue
        for _label, _s in _dic.items():
            _d = _s.reset_index()
            _d.columns = ["date", "alpha"]
            _d["label"] = _label
            _d["window"] = _window
            _rolling_frames.append(_d)
    rolling_alphas_long = pd.concat(_rolling_frames, axis=0, ignore_index=True) if _rolling_frames else pd.DataFrame(
        columns=["date", "alpha", "label", "window"]
    )

    # ---- cell 51: include-all cumulative/risk table inputs --------------- #
    show_sample_portfolio = C["show_sample_portfolio"]
    _all_gross = pd.DataFrame(index=global_returns_cum.index)
    if show_sample_portfolio:
        _all_gross["Sample"] = 1 + global_returns_cum.mean(axis=1).sub(fama_french["rf"].values, axis=0)
    _all_gross["Market"] = 1 + market_factor_cum
    _lc_keys = [k for k in signal_quantiles if k.startswith("signal_")]
    _esg_keys = [k for k in signal_quantiles if not k.startswith("signal_")]
    for _sig in list(reversed(_lc_keys)) + _esg_keys:
        _nm = signal_names.get(_sig, _sig)
        for _bkt in ("high", "low"):
            _all_gross[f"{_bucket_to_prefix[_bkt]} {_nm}"] = 1 + signal_quantiles_cum[_sig][_bucket_to_col[_bkt]]
    _table_returns = _all_gross.add(fama_french["rf"].values, axis=0) - 1
    _table_excess = _all_gross - 1
    for _label, _series in spread_cum.items():
        _table_returns[_label] = _series
        _table_excess[_label] = _series

    # ---- cell 51 tables: cumulative + risk ------------------------------- #
    # ff3_parts_df is the level FF3 table computed just above (cell 48).
    sp = StrategyPerformance(_table_returns, ff3_parts_df=ff3_parts_df, excess_returns=_table_excess)
    out_dir = Path("./runs/tables")
    cumulative = sp.cumulative_performance_table(csv_path=out_dir / "strategy_cumulative_performance.csv")
    risk = sp.performance_risk_metrics_table(csv_path=out_dir / "strategy_performance_metrics.csv")
    if list(cumulative.index) != list(risk.index):
        raise ValueError(
            f"portfolio rows differ between tables: "
            f"cumulative={list(cumulative.index)} risk={list(risk.index)}"
        )
    print(cumulative.head())

    # ---- cells 58 & 59: constituents + holdings-over-time --------------- #
    # Pinned sort key: the ESG column under esg_full_universe, else the LAST lc signal
    # in cfg.lc_signals insertion order (signal_2 for the 3-signal original_matteo
    # characterization it was originally written for — but not every characterization
    # has 3+ signals, e.g. Material_Immaterial_only has only signal_0/signal_1, so this
    # must be derived rather than hardcoded). Matches base_analysis_selection's own
    # "reversed(lc_signals)" convention just above, whose first element is this same key.
    key = next(iter(C["universe_signals"])) if esg_full_universe else list(lc_signals)[-1]
    pc2 = PortfolioConstituents(
        signal_quantile_constituents[key], global_universe, portfolio_type="univariate_split"
    )
    cats = ["Industry"] if esg_full_universe else ["Industry", "loc"]
    constituents_out: dict = {}
    for cat in cats:
        _d, _wide = pc2._counts_by_category_over_time(
            cat, portfolio_key=None, analyse_all_portfolios_at_once=False
        )
        w = _wide.reset_index()
        w.columns = [str(c) for c in w.columns]
        constituents_out[f"constituents_{cat}"] = w

    inspect = K - 1
    rows = []
    for _ms in pc2.constituents:
        _names = _ms.iloc[inspect]
        for _gi in list(_names):
            rows.append({"date": pd.to_datetime(_ms.name), "gvkey_iid": str(_gi), "gvkey": str(_gi).split("_")[0]})
    holdings = pd.DataFrame(rows).sort_values(["date", "gvkey_iid"]).reset_index(drop=True)
    holdings_out = holdings.reset_index()
    holdings_out.columns = [str(c) for c in holdings_out.columns]

    # ---- per-bucket sector counts (High + Low of every signal) ---------- #
    # For each configured signal, run PortfolioConstituents with the right slice
    # index and compute Industry counts over time. High = last quantile (K-1),
    # Low = first (0). Yields one Industry-counts frame per bucket, plus a
    # matching stocks-per-month total (row sums). Purely additive: existing
    # constituents_Industry / holdings_over_time artifacts are unchanged.
    # Key by (bucket, signal_key) so the dashboard extractors can look up buckets
    # without depending on cfg-specific display names. e.g. "High signal_2" or
    # "Low esg_msci". Display titles for the widgets are derived separately.
    _per_bucket: dict = {}
    for _sig in signal_quantile_constituents:
        _pc = PortfolioConstituents(
            signal_quantile_constituents[_sig], global_universe, portfolio_type="univariate_split"
        )
        for _bkt, _idx in (("high", K - 1), ("low", 0)):
            _, _wide = _pc._counts_by_category_over_time(
                "Industry", portfolio_key=_idx, analyse_all_portfolios_at_once=False
            )
            _label = f"{_bucket_to_prefix[_bkt]} {_sig}"  # raw signal key, cfg-independent
            _per_bucket[_label] = _wide  # sectors x date (cols = sectors, index = date)

    # ---- material-initiative decomposition (AUDIT-ONLY) ------------------ #
    # What ARE the material initiatives each leg holds? `material__total` is an opaque
    # count, so the High-Low alpha cannot be attributed to a behaviour or an SDG. This
    # cuts that total five ways (see New_Pipeline/initiative_brackets.py) per leg per
    # formation month. Nothing downstream reads it and it is not exported, so it cannot
    # move a parity artifact.
    #
    # NO LOOKAHEAD, and no date arithmetic: `global_universe` already carries, per
    # (gvkey_iid, date), the exact `rfyear` whose LC row produced that month's signal --
    # it is a merge key in merge_lc_into_global_universe (left_on ["gvkey","last_year"],
    # right_on ["gvkey","rfyear"]) and survives in _LC_MERGE_FIXED. Reading it back is
    # therefore point-in-time correct BY CONSTRUCTION, and automatically right for Japan,
    # whose split month differs. Re-deriving the Jan-Jun/Jul-Dec rule here would be a
    # second copy of it, free to drift.
    initiative_decomposition = None
    _mat_counts = P.get("materiality_counts")
    _DECOMP_SIGNAL = "signal_0"
    if (_mat_counts is not None
            and C.get("action_characterization") == "Material_Immaterial_only"
            and _DECOMP_SIGNAL in signal_quantile_constituents):
        from New_Pipeline.initiative_brackets import (
            RESIDUAL_BAND,
            SCHEME_SLUGS,
            TOTAL_COLUMN,
            bands_for,
            required_columns,
        )

        # signal_0 ONLY. Under Material_Immaterial_only, sum_activities is
        # material__total + immaterial__total, so signal_1 == 1 - signal_0 exactly;
        # standardize_pivot's (x-mean)/std preserves the mirror, so "High signal_1" and
        # "Low signal_0" are the SAME portfolio. Doing both would duplicate every chart.
        # (The mirror itself is reported by the sort_cutpoint_audit node.)
        _rows = []
        for _bkt, _idx in (("High", K - 1), ("Low", 0)):
            for _ms in signal_quantile_constituents[_DECOMP_SIGNAL]:
                _dt = pd.to_datetime(_ms.name)
                for _gi in pd.Index(_ms.iloc[_idx]):
                    _rows.append({"bucket": _bkt, "date": _dt, "gvkey_iid": str(_gi)})
        _h = pd.DataFrame(_rows, columns=["bucket", "date", "gvkey_iid"])

        # 1. holdings -> point-in-time (gvkey, rfyear)
        _gu_key = global_universe[["gvkey_iid", "date", "gvkey", "rfyear"]].copy()
        _gu_key["date"] = pd.to_datetime(_gu_key["date"])
        _gu_key["gvkey_iid"] = _gu_key["gvkey_iid"].astype(str)
        _gu_key = _gu_key.drop_duplicates(subset=["gvkey_iid", "date"])
        _h = _h.merge(_gu_key, on=["gvkey_iid", "date"], how="left")
        if _h["rfyear"].isna().any():
            # Every holding came from a signal pivot built off these same rows, so a miss
            # is a key-format bug, not a data gap.
            raise ValueError(
                f"{int(_h['rfyear'].isna().sum())} of {len(_h)} holdings found no "
                "(gvkey_iid, date) row in global_universe - cannot date their initiatives"
            )
        # rfyear reaches the panel through a LEFT merge so it is float64; lc's is integer.
        # Without this cast the join below matches nothing and every share reads 0.
        _h["rfyear"] = _h["rfyear"].astype("int64")

        # NO-LOOKAHEAD CANARY. Deliberately a BOUND, not a restatement of the Jan-Jun/Jul-Dec
        # rule: asserting "rfyear is Y-2 or Y-1" holds for every region including Japan
        # (whose split month is configurable), while asserting the rule itself would be a
        # second copy of it, free to drift from the one in process_data.py. What matters for
        # this widget is only that no initiative shown for month M was reported after M --
        # guaranteed by rfyear being at least a full year behind.
        _lag = _h["date"].dt.year - _h["rfyear"]
        if not _lag.isin((1, 2)).all():
            _bad = _h.loc[~_lag.isin((1, 2)), ["date", "gvkey", "rfyear"]].head()
            raise ValueError(
                f"LOOKAHEAD: {int((~_lag.isin((1, 2))).sum())} holdings have rfyear outside "
                f"[year-2, year-1] of their formation month:\n{_bad}"
            )
        _h1 = _h["date"].dt.month <= 6
        print(f"[decomposition] point-in-time lag OK — Jan-Jun: "
              f"{sorted(_lag[_h1].unique().tolist())}, "
              f"Jul-Dec: {sorted(_lag[~_h1].unique().tolist())} "
              f"(years behind formation month)")

        # 2. (gvkey, rfyear) -> the raw materiality counts
        _need = [c for c in required_columns() if c in _mat_counts.columns]
        _missing = [c for c in required_columns() if c not in _mat_counts.columns]
        if _missing:
            raise KeyError(
                f"materiality_counts is missing bracket columns {_missing} - the workbook "
                "vintage does not carry the per-SDG breakdown these schemes need"
            )
        # The other two materiality groups are not band sources -- they are what makes an
        # internally consistent "all initiatives" denominator possible (see _wb_total below).
        _totals = [c for c in ("immaterial__total", "unmapped__total")
                   if c in _mat_counts.columns and c not in _need]
        _mc = _mat_counts[["gvkey", "rfyear", "n_predicted_initiatives"] + _need + _totals].copy()
        _mc["rfyear"] = _mc["rfyear"].astype("int64")
        _h = _h.merge(_mc, on=["gvkey", "rfyear"], how="left")

        # An unmatched holding is a real coverage fact (its firm-year was trimmed out of lc
        # after the universe merge), reported below rather than silently dropped. Zero
        # matches, though, is a broken key -- fail loudly.
        _matched = _h[_h[TOTAL_COLUMN].notna()].copy()
        if _matched.empty:
            raise ValueError(
                "no holding matched materiality_counts on (gvkey, rfyear) - check gvkey "
                "zero-padding / rfyear dtype"
            )

        _pooled: dict = {}
        _equal: dict = {}
        _max_dev = 0.0
        for _slug in SCHEME_SLUGS:
            _bands = bands_for(_slug)
            # Row-level band counts, in declaration order. An area chart whose bands
            # reorder between months is unreadable, so this order is preserved throughout.
            _bf = pd.DataFrame(
                {_label: _matched[_cols].sum(axis=1) for _label, _cols in _bands.items()},
                index=_matched.index,
            )
            # Explicit residual instead of rescaling to the scheme's own smaller total: the
            # old 3-way split covers only ~91% of material initiatives, and rescaling would
            # hide that AND make its bands incomparable with the other four schemes. Every
            # scheme therefore sums to material__total exactly.
            _resid = _matched[TOTAL_COLUMN] - _bf.sum(axis=1)
            if float(_resid.abs().max()) > 0:
                if float(_resid.min()) < 0:
                    raise ValueError(
                        f"scheme {_slug!r} DOUBLE-COUNTS: its bands exceed {TOTAL_COLUMN} "
                        f"on {int((_resid < 0).sum())} holdings"
                    )
                _bf[RESIDUAL_BAND] = _resid
            _dev = float((_bf.sum(axis=1) - _matched[TOTAL_COLUMN]).abs().max())
            if _dev > 0:
                raise ValueError(f"scheme {_slug!r} bands do not sum to {TOTAL_COLUMN} (max dev {_dev})")

            _keyed = pd.concat([_matched[["bucket", "date", TOTAL_COLUMN]], _bf], axis=1)

            # POOLED: sum every holding's initiatives, then share. Literally "the
            # initiatives that make up this portfolio" -- but set by the heaviest reporters.
            _g = _keyed.groupby(["bucket", "date"], sort=True)
            _num = _g[list(_bf.columns)].sum()
            _den = _g[TOTAL_COLUMN].sum()
            _pool_pct = _num.div(_den.where(_den > 0), axis=0) * 100.0

            # EQUAL-WEIGHT: each firm's own mix, then average across holdings. Matches how
            # the portfolio is weighted in returns. Undefined for a holding with no material
            # initiatives at all, which is why _keyed is filtered here and not above.
            _nz = _keyed[_keyed[TOTAL_COLUMN] > 0]
            _ew_pct = (
                _nz[list(_bf.columns)].div(_nz[TOTAL_COLUMN], axis=0)
                .groupby([_nz["bucket"], _nz["date"]], sort=True).mean() * 100.0
            )
            _ew_pct.index.names = ["bucket", "date"]

            _pooled[_slug] = {}
            _equal[_slug] = {}
            for _bkt in ("High", "Low"):
                for _store, _frame in ((_pooled, _pool_pct), (_equal, _ew_pct)):
                    _sub = (_frame.xs(_bkt, level="bucket").sort_index()
                            if _bkt in _frame.index.get_level_values("bucket")
                            else pd.DataFrame(columns=list(_bf.columns)))
                    _store[_slug][_bkt] = _sub
                    if len(_sub):
                        _max_dev = max(_max_dev, float((_sub.sum(axis=1) - 100.0).abs().max()))

        # Levels + coverage. With a material-only denominator a holding with zero material
        # initiatives contributes NOTHING, so how many of those a leg holds decides whether
        # its chart describes the leg or a minority of it. Belongs next to the charts.
        _h["_matched"] = _h[TOTAL_COLUMN].notna()
        _h["_has_material"] = _h[TOTAL_COLUMN].fillna(0) > 0
        # "All initiatives" must come from the SASB workbook, NOT from lc's
        # n_predicted_initiatives, and the reason is NOT a vintage mismatch -- the workbook
        # is built from exactly the LC file this pipeline loads. It is the gvkey
        # zero-padding alias: LC stores some firm-years TWICE, under "1075" and "001075".
        # Both sides zfill to one key, then the Matchings pipeline SUMS the pair while
        # process_lc/prepare_panel drop_duplicates(keep="first") -- see the
        # "WARNING: lc had N duplicate (gvkey, rfyear) rows" lines in debug_prints.log.
        # So material__total covers both reports and n_predicted_initiatives covers one.
        # Verified: wb_total == the summed LC rows for all 72,412 firm-years, exactly.
        #
        # 2,423 firm-years (3.3%) are affected, 4.7% of all initiatives -- but nearer 15%
        # inside a portfolio, because the firms with duplicate identifier history are the
        # large ones a market-cap-filtered universe holds. Against an alias-summed
        # numerator, lc's count puts the High leg's material share ABOVE 100%.
        # material/immaterial/unmapped partition the workbook's own total exactly, so
        # summing them is the only internally consistent denominator here. lc's count stays
        # beside it as `total_initiatives_lc` so the size of the loss is visible.
        #
        # The SIGNAL is unaffected: under Material_Immaterial_only sum_activities is
        # material__total + immaterial__total, both alias-summed. But
        # signal_denominator="Sum_All_Initiatives" would divide an alias-summed numerator by
        # this first-alias-only count and produce shares above 1 -- no registered config
        # uses it, and this is the reason not to.
        _h["_wb_total"] = _h[TOTAL_COLUMN].fillna(0)
        for _c in ("immaterial__total", "unmapped__total"):
            if _c in _h.columns:
                _h["_wb_total"] = _h["_wb_total"] + _h[_c].fillna(0)
        _levels: dict = {}
        _cov_rows = []
        for _bkt in ("High", "Low"):
            _b = _h[_h["bucket"] == _bkt]
            if _b.empty:
                continue
            _lv = _b.groupby("date", sort=True).agg(
                n_holdings=("gvkey_iid", "size"),
                n_matched=("_matched", "sum"),
                n_with_material=("_has_material", "sum"),
                total_material_initiatives=(TOTAL_COLUMN, "sum"),
                total_initiatives=("_wb_total", "sum"),
                total_initiatives_lc=("n_predicted_initiatives", "sum"),
            )
            _levels[_bkt] = _lv
            _wb = float(_b["_wb_total"].sum())
            _lc_tot = float(_b["n_predicted_initiatives"].fillna(0).sum())
            _cov_rows.append({
                "bucket": _bkt,
                "n_months": int(len(_lv)),
                "median_holdings": int(_lv["n_holdings"].median()),
                "pct_holdings_matched": round(float(_b["_matched"].mean()) * 100, 1),
                "median_holdings_with_material": int(_lv["n_with_material"].median()),
                "pct_holdings_zero_material": round(
                    float((~_b["_has_material"]).mean()) * 100, 1),
                "total_material_initiatives": int(_b[TOTAL_COLUMN].fillna(0).sum()),
                "total_initiatives": int(_wb),
                "pct_initiatives_material": round(
                    float(_b[TOTAL_COLUMN].fillna(0).sum()) / max(_wb, 1.0) * 100, 1),
                "total_initiatives_lc": int(_lc_tot),
                "lc_vs_workbook_pct": round(_lc_tot / max(_wb, 1.0) * 100, 1),
            })

        initiative_decomposition = {
            "pooled": _pooled,
            "equal_weight": _equal,
            "levels": _levels,
            "coverage_summary": pd.DataFrame(_cov_rows),
        }
        print(f"[decomposition] {len(SCHEME_SLUGS)} schemes x 2 buckets x 2 weightings; "
              f"max |band sum - 100| = {_max_dev:.10f}")
        print(initiative_decomposition["coverage_summary"].to_string(index=False))

    return pack_obj({
        # portfolio-construction outputs (unchanged from the old build_portfolios bundle)
        "signal_quantiles": signal_quantiles,
        "signal_quantiles_cum": signal_quantiles_cum,
        "signal_quantile_constituents": signal_quantile_constituents,
        "spread_signals": spread_signals,
        "spread_cum": spread_cum,
        "signal_names": signal_names,
        "fama_french": fama_french,
        "market_factor_cum": market_factor_cum,
        "global_returns_cum": global_returns_cum,
        "Excess_returns_sample": Excess_returns_sample,
        "base_analysis_selection": base_analysis_selection,
        "bucket_to_col": _bucket_to_col,
        "bucket_to_prefix": _bucket_to_prefix,
        "table_returns": _table_returns,
        "table_excess": _table_excess,
        "global_universe": global_universe,
        # FF3 outputs (formerly ff3_alphas node output)
        "ff3_parts_df": ff3_parts_df,
        "rolling_alphas": rolling_alphas_long,
        # reporting tables (formerly performance_tables node output)
        "cumulative_table": cumulative,
        "risk_table": risk,
        # constituents (formerly build_constituents node output)
        **constituents_out,
        "holdings_over_time": holdings_out,
        # per-bucket Industry counts: label -> DataFrame(date x sector). Drives the
        # per-bucket count and sector-share dashboard widgets. Not written to parquet.
        "per_bucket_industry": _per_bucket,
        # Material-initiative decomposition (audit-only, not written to parquet). None
        # unless add_materiality and action_characterization == "Material_Immaterial_only".
        "initiative_decomposition": initiative_decomposition,
        # Thin-portfolio gate. The frames are audit output; dropped_portfolio_labels is the
        # drop set the dashboard extractors filter on. Every other bundle key stays COMPLETE
        # so the exported parquets are unaffected.
        "portfolio_coverage": portfolio_coverage,
        "portfolio_gate_summary": portfolio_gate_summary,
        "dropped_portfolio_labels": _dropped_labels,
    })


NODE = Node(
    name="build_analyse_portfolios",
    contract=CONTRACT,
    store=store,
    inputs=("prep", "cfg"),
    outputs=("out",),
)
