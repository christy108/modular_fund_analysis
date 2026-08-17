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
from New_Pipeline.dashboard_viz import BundleMultiSeriesViz, BundleSeriesViz, BundleTableViz


# ---- Row-count stats (real, unpack the bundle) --------------------------------------- #

def _ff3_rows(df) -> int:
    """Statistic: FF3 statistic rows carried in the bundle."""
    return int(len(unpack_obj(df)["ff3_parts_df"]))


def _rolling_rows(df) -> int:
    """Statistic: rolling-alpha observations carried in the bundle."""
    return int(len(unpack_obj(df)["rolling_alphas"]))


# ---- Dashboard extractors (bundle -> widget payloads; no computation happens here) --- #

def _cumulative_wealth_series(bundle, *, spreads: bool) -> list[dict]:
    """Cumulative wealth (1+r).cumprod() per column of table_returns, matching
    Main.ipynb cell 51's plot split: spread columns (the High-Low legs) go on
    their own chart; every other column (Market, High/Low X, ...) on the other.
    Same series the notebook's ``plot_cumulative_returns`` draws — no new analysis.
    """
    table_returns = bundle["table_returns"]
    spread_cols = [c for c in bundle["spread_cum"] if c in table_returns.columns]
    cols = spread_cols if spreads else [c for c in table_returns.columns if c not in spread_cols]
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


def _cumulative_table(bundle):
    """Formatted cumulative-returns table (rows = portfolios, cols = 1m..Since launch)."""
    return bundle["cumulative_table"]


def _risk_table(bundle):
    """Formatted risk-metrics table (rows = portfolios, cols = Sharpe/VaR/MaxDD/Alpha/p)."""
    return bundle["risk_table"]


def _ff3_table(bundle):
    """FF3 regression table (metric x portfolio)."""
    return bundle["ff3_parts_df"]


def _rolling_plot(window: int):
    """Build a multi-line rolling-alpha PLOT extractor: one line per portfolio label."""

    def extract(bundle) -> list[dict]:
        import pandas as pd

        df = bundle["rolling_alphas"]
        sub = df[df["window"] == window]
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
_MAX_SIGNAL_WIDGETS = 30
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
number of stocks in the portfolio over time (``BundleSeriesViz``).""",
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
        BundleSeriesViz(_stocks_over_time, title="Stocks in portfolio over time"),
        # Per-bucket constituent widgets — all collapsed by default so the page
        # stays scannable; expand the ones you care about.
        *_bucket_audits(),
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
        )
        signal_quantiles[col] = U.compute_returns()
        signal_quantile_constituents[col] = U.get_constituents_over_time()

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
    })


NODE = Node(
    name="build_analyse_portfolios",
    contract=CONTRACT,
    store=store,
    inputs=("prep", "cfg"),
    outputs=("out",),
)
