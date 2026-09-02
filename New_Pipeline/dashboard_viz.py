"""Custom VizSpecs — and section ordering — for the audit dashboard.

Several nodes emit a lossless pickle *bundle* (one `__pickle__` cell) rather than a
tidy frame, so the built-in `SampleTableViz`/`LineChartViz` — which read columns off a
tidy `pl.DataFrame` — can't see inside them. These subclasses override only `compute`
to unpack the bundle and pull out an already-computed table/series; `render` is reused
unchanged, so the Taipy payload is exactly what the framework expects.

No node output changes and no new analysis: each `extract` just returns a frame the
Process already put in the bundle (or a trivial count of it), so parity is untouched.

`OrderedDashboard` (bottom of the imports block) is the one non-VizSpec here: it moves
audit-only node sections to the end of the page, which is presentation, not topology.
"""

from __future__ import annotations

from typing import Any, Callable

from leonardo_nodes import Dashboard
from leonardo_nodes.viz import (
    ColoredTableViz,
    DashboardComponent,
    DualAxisViz,
    HeatmapViz,
    LineChartViz,
    SampleTableViz,
)

# Nodes whose dashboard section is pushed to the BOTTOM of the page, after the sections
# that carry the actual results. These are pure diagnostics of an upstream step, so their
# DAG position (which is what the framework orders sections by) puts them far earlier than
# where a reader wants them — ahead of cumulative returns, alphas and risk tables.
# Order within this tuple is the order they render in (see _ordered_nodes below).
_DEFERRED_SECTIONS = ("mktcap_filter_audit", "sample_funnel_audit", "sort_cutpoint_audit")

# Palette for stacked-area bands. Not the framework's _CHART_COLORS: that one is tuned for
# thin lines on white and its adjacent entries (blue/amber/emerald/red) vibrate badly as
# large filled blocks. These are ordered so neighbouring bands stay distinguishable when
# one of them is a sliver.
#
# 18 entries because the widest scheme (Climate & Natural Capital vs each SDG) has 15 bands
# and any scheme may gain an Unclassified residual. Beyond ~8 bands an area chart is at the
# limit of what colour alone can separate -- read those against the coarser schemes rather
# than trying to identify a 2%-tall band by hue.
_AREA_COLORS = (
    "#2563eb", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444",
    "#06b6d4", "#84cc16", "#ec4899", "#64748b", "#a16207",
    "#1e3a8a", "#047857", "#b45309", "#5b21b6", "#991b1b",
    "#0e7490", "#4d7c0f", "#9d174d",
)


class OrderedDashboard(Dashboard):
    """Dashboard that renders ``_DEFERRED_SECTIONS`` last, whatever the DAG says.

    ``Dashboard`` orders both the Taipy page and ``to_markdown()`` by
    ``Pipeline.topological_order()``, and there is no edge arrangement that moves an
    audit-only node to the end: it depends on one early node, so Kahn's algorithm makes it
    ready long before the analysis nodes finish. Reordering here — rather than adding a
    fake edge — keeps the DAG (and the pipeline graph the dashboard draws) honest about
    what actually depends on what.
    """

    def _ordered_nodes(self) -> list:
        nodes = super()._ordered_nodes()
        # Sorted by position in _DEFERRED_SECTIONS, not left in topological order among
        # themselves: with more than one deferred section, their relative order would
        # otherwise be whatever Kahn's algorithm happened to produce from their upstream
        # dependencies -- which has nothing to do with how a reader wants them stacked.
        deferred = sorted((n for n in nodes if n.name in _DEFERRED_SECTIONS),
                          key=lambda n: _DEFERRED_SECTIONS.index(n.name))
        if not deferred:
            return nodes
        return [n for n in nodes if n.name not in _DEFERRED_SECTIONS] + deferred

    def _lines_figure(self, c):
        """Draw STACKED AREA when ``options["stack"]`` is set; otherwise the normal lines.

        The framework has no area chart: ``Dashboard._lines_figure`` hardcodes
        ``mode="lines"``, and a ``DashboardComponent`` with an unrecognised ``kind`` falls
        through to a table. It is called as ``self._lines_figure(c)`` though, so overriding
        it here adds the one chart type this repo needs without touching ``leonardo-nodes``
        -- and any node in any pipeline built on that framework keeps the old behaviour.

        Layout deliberately mirrors the base implementation exactly (one subplot per
        experiment, shared y, one legend entry per series NAME with a stable colour across
        subplots) so a stacked chart sits beside the line charts without looking foreign.
        The y-axis is pinned to 0-100 because these payloads are percentages that sum to
        100 by construction -- letting Plotly autoscale would make a band look like it grew
        when only the axis moved.
        """
        if not (c.options or {}).get("stack"):
            return super()._lines_figure(c)
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
        except ImportError:
            return None

        gathered = c.data if isinstance(c.data, dict) else {}
        experiments = [
            exp for exp, payload in gathered.items()
            if isinstance(payload, dict) and payload.get("series")
        ]
        if not experiments:
            return go.Figure()

        fig = make_subplots(
            rows=1, cols=len(experiments), subplot_titles=experiments, shared_yaxes=True
        )
        names: list[str] = []
        for exp in experiments:
            for s in gathered[exp]["series"]:
                name = str(s.get("name"))
                if name not in names:
                    names.append(name)
        color_of = {n: _AREA_COLORS[i % len(_AREA_COLORS)] for i, n in enumerate(names)}

        for col, exp in enumerate(experiments, start=1):
            # stackgroup is per-subplot: sharing one across subplots would stack every
            # experiment's bands on top of each other into a single 100*N-tall pile.
            group = f"stack{col}"
            for s in gathered[exp]["series"]:
                name = str(s.get("name"))
                fig.add_trace(
                    go.Scatter(
                        x=s.get("x") or [],
                        y=s.get("y") or [],
                        mode="lines",
                        name=name,
                        legendgroup=name,
                        showlegend=(col == 1),
                        stackgroup=group,
                        fillcolor=color_of.get(name),
                        line={"color": color_of.get(name), "width": 0.5},
                        hovertemplate="%{y:.1f}%<extra>%{fullData.name}</extra>",
                    ),
                    row=1,
                    col=col,
                )
            fig.update_yaxes(range=[0, 100], row=1, col=col)
        fig.update_layout(
            title=c.title,
            height=420,
            margin={"t": 60, "b": 40},
            hoverlabel={"namelength": -1},
        )
        return fig


class BundleTableViz(SampleTableViz):
    """Render a pandas table pulled from a node's pickle-bundle output as a table widget.

    ``extract(bundle_dict) -> pandas.DataFrame``. Columns are discovered from the data
    (they vary by config, e.g. the FF3 table gains ESG portfolio columns), so nothing
    is hard-coded.
    """

    def __init__(self, extract: Callable[[dict], Any], *, title: str, n: int = 200,
                 key: str | None = None, description: str = ""):
        super().__init__(columns=[], n=n, title=title, key=key)
        self._extract = extract
        # SampleTableViz does not take `description`; set it directly on the VizSpec so
        # Dashboard.build() picks it up and renders it under the widget title.
        self.description = description

    def compute(self, output: Any) -> Any:
        import pandas as pd

        from New_Pipeline.boundary import unpack_obj

        df = self._extract(unpack_obj(output))
        if not isinstance(df, pd.DataFrame):
            df = pd.DataFrame(df)
        df = df.copy()
        if not isinstance(df.index, pd.RangeIndex):
            df = df.reset_index()
        df.columns = [str(c) for c in df.columns]
        for col in df.columns:  # JSON-safe cells (datetimes -> str)
            if str(df[col].dtype).startswith("datetime"):
                df[col] = df[col].astype(str)
        return {"rows": df.head(self.n).to_dict("records")}

    def render(self, gathered: dict) -> DashboardComponent:
        # Columns = union of keys seen across configs, first-seen order.
        cols: list[str] = []
        for payload in gathered.values():
            for row in (payload or {}).get("rows", []):
                for k in row:
                    if k not in cols:
                        cols.append(k)
        return DashboardComponent(
            kind="table", title=self.title, data=gathered, options={"columns": cols}
        )


class BundleColoredTableViz(ColoredTableViz):
    """Render a pandas table pulled from a node's pickle-bundle output, rows tinted by
    the value of ``color_col`` — for tables whose rows fall into a handful of groups
    (e.g. raw signal-input columns grouped by which signal they feed) where the grouping
    should be visible at a glance rather than only readable off a text column.

    ``extract(bundle_dict) -> pandas.DataFrame`` containing ``color_col``. ``compute``
    mirrors ``BundleTableViz`` exactly (unpack -> coerce to DataFrame -> reset a
    non-trivial index -> stringify columns/datetimes -> records); ``render`` adds the
    same union-of-columns discovery on top of the framework's ``ColoredTableViz.render``.
    """

    def __init__(
        self,
        extract: Callable[[dict], Any],
        *,
        title: str,
        color_col: str,
        n: int = 200,
        palette: list[str] | None = None,
        key: str | None = None,
        description: str = "",
    ):
        super().__init__(title=title, color_col=color_col, palette=palette, key=key)
        # ColoredTableViz does not take `description`; set it on the VizSpec directly so
        # Dashboard.build() picks it up and renders it under the widget title.
        self.description = description
        self._extract = extract
        self.n = n

    def compute(self, output: Any) -> Any:
        import pandas as pd

        from New_Pipeline.boundary import unpack_obj

        df = self._extract(unpack_obj(output))
        if not isinstance(df, pd.DataFrame):
            df = pd.DataFrame(df)
        df = df.copy()
        if not isinstance(df.index, pd.RangeIndex):
            df = df.reset_index()
        df.columns = [str(c) for c in df.columns]
        for col in df.columns:  # JSON-safe cells (datetimes -> str)
            if str(df[col].dtype).startswith("datetime"):
                df[col] = df[col].astype(str)
        return {"rows": df.head(self.n).to_dict("records")}

    def render(self, gathered: dict) -> DashboardComponent:
        # Columns = union of keys seen across configs, first-seen order (same discovery
        # BundleTableViz uses, since columns vary by config/action_characterization).
        cols: list[str] = []
        for payload in gathered.values():
            for row in (payload or {}).get("rows", []):
                for k in row:
                    if k not in cols:
                        cols.append(k)
        self.columns = cols
        return super().render(gathered)


class BundleDualAxisViz(DualAxisViz):
    """Two series on separate y-axes, pulled from a node's pickle-bundle output — for pairs
    whose scales differ by orders of magnitude (e.g. unique firms vs total initiatives).

    ``extract(bundle_dict) -> pandas.DataFrame`` carrying ``x_col``, ``left_col`` and
    ``right_col``. Returns an empty payload when the frame is missing or empty (e.g. the
    ESG-universe path, which produces no LC-derived table), so the widget renders blank
    rather than erroring.
    """

    def __init__(
        self,
        extract: Callable[[dict], Any],
        *,
        title: str,
        x_col: str,
        left_col: str,
        right_col: str,
        left_label: str | None = None,
        right_label: str | None = None,
        x_label: str | None = None,
        key: str | None = None,
        description: str = "",
    ):
        super().__init__(
            title=title,
            left_label=left_label or left_col,
            right_label=right_label or right_col,
            x_label=x_label or x_col,
            key=key,
        )
        self._extract = extract
        # DualAxisViz does not take `description`; set it directly on the VizSpec so
        # Dashboard.build() picks it up -- same pattern as the table wrappers above.
        self.description = description
        self._x_col = x_col
        self._left_col = left_col
        self._right_col = right_col

    def compute(self, output: Any) -> Any:
        import pandas as pd

        from New_Pipeline.boundary import unpack_obj

        df = self._extract(unpack_obj(output))
        if not isinstance(df, pd.DataFrame) or df.empty:
            return {"points": []}

        missing = [c for c in (self._x_col, self._left_col, self._right_col) if c not in df.columns]
        if missing:
            return {"points": [], "error": f"missing columns: {missing}"}

        df = df.sort_values(self._x_col)
        return {
            "points": [
                {
                    "x": str(row[self._x_col]),
                    "left": None if pd.isna(row[self._left_col]) else float(row[self._left_col]),
                    "right": None if pd.isna(row[self._right_col]) else float(row[self._right_col]),
                }
                for _, row in df.iterrows()
            ]
        }


class BundleHeatmapViz(HeatmapViz):
    """Colour-coded (diverging blue/white/red) heatmap pulled from a node's pickle-bundle
    output — e.g. a correlation matrix.

    ``extract(bundle_dict) -> pandas.DataFrame``, a SQUARE frame: one non-numeric column
    holding the row/column labels (e.g. from ``.reset_index(names=...)``, auto-detected
    unless ``row_label_col`` is given) plus one numeric column per label, in the same order.
    """

    def __init__(
        self,
        extract: Callable[[dict], Any],
        *,
        title: str,
        row_label_col: str | None = None,
        zmin: float = -1.0,
        zmax: float = 1.0,
        zmid: float = 0.0,
        key: str | None = None,
    ):
        super().__init__(title=title, zmin=zmin, zmax=zmax, zmid=zmid, key=key)
        self._extract = extract
        self._row_label_col = row_label_col

    def compute(self, output: Any) -> Any:
        import pandas as pd

        from New_Pipeline.boundary import unpack_obj

        df = self._extract(unpack_obj(output))
        if not isinstance(df, pd.DataFrame) or df.empty:
            return {"labels": [], "z": []}

        row_col = self._row_label_col
        if row_col is None:
            non_numeric = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
            row_col = non_numeric[0] if non_numeric else df.columns[0]

        labels = [str(v) for v in df[row_col]]
        value_cols = [c for c in df.columns if c != row_col]
        z = [[None if pd.isna(v) else float(v) for v in row] for row in df[value_cols].to_numpy()]
        return {"labels": labels, "z": z}


class BundleMultiSeriesViz(LineChartViz):
    """Render a MULTI-LINE plot pulled from a node's pickle-bundle output.

    ``extract(bundle_dict) -> [{"name": str, "x": [...], "y": [...]}, ...]`` — one entry
    per line (e.g. one per portfolio label). Sets ``options["multi_series"]``, which makes
    the dashboard draw one subplot per config with all lines overlaid and a consistent
    colour per line name across subplots (see ``Dashboard._lines_figure``).

    This is the plot itself — no table, no extra artifact on disk.

    Note ``_lines_figure`` sets no axis titles (the ``x``/``y`` names below are only used as
    payload keys), so units belong in ``title`` and ``description`` — there is no axis label
    to put them on.
    """

    def __init__(
        self,
        extract: Callable[[dict], list],
        *,
        title: str,
        key: str | None = None,
        collapsible: bool = False,
        expanded: bool = True,
        description: str = "",
    ):
        super().__init__(x="date", y="alpha", agg="mean", title=title, key=key or f"lines:{title}")
        self._extract = extract
        self._collapsible = collapsible
        self._expanded = expanded
        # LineChartViz does not take `description`; set it directly on the VizSpec so
        # Dashboard.build() picks it up and renders it under the widget title.
        self.description = description

    def compute(self, output: Any) -> Any:
        from New_Pipeline.boundary import unpack_obj

        return {"series": self._extract(unpack_obj(output))}

    def render(self, gathered: dict) -> DashboardComponent:
        opts: dict = {
            "multi_series": True,
            "show_legend": True,
            "x": self.x,
            "y": self.y,
        }
        if self._collapsible:
            opts["collapsible"] = True
            opts["expanded"] = self._expanded
        return DashboardComponent(kind="lines", title=self.title, data=gathered, options=opts)


class BundleStackedAreaViz(BundleMultiSeriesViz):
    """A STACKED AREA chart -- same payload as ``BundleMultiSeriesViz``, drawn filled.

    ``extract(bundle_dict) -> [{"name": str, "x": [...], "y": [...]}, ...]``, one entry per
    band, where the y-values at each x are PERCENTAGES summing to 100. Setting
    ``options["stack"]`` is what ``OrderedDashboard._lines_figure`` keys off; against the
    stock framework ``Dashboard`` the flag is simply ignored and the same data renders as
    ordinary overlaid lines, which is a degraded view rather than a broken one.

    Normalise in the EXTRACTOR, not with Plotly's ``groupnorm``: the percentages are an
    analytical result that belongs in the bundle where it can be asserted, not a rendering
    side effect. Band ORDER is the extractor's order and is never re-sorted -- an area chart
    whose bands swap places between months is unreadable.
    """

    def render(self, gathered: dict) -> DashboardComponent:
        component = super().render(gathered)
        component.options["stack"] = True
        return component


class BundleSeriesViz(LineChartViz):
    """Render a single (x, y) time series pulled from a node's pickle-bundle output.

    ``extract(bundle_dict) -> list[{"x": ..., "y": ...}]`` (x stringified). Reuses
    LineChartViz.render, which draws one trace per config (colour = config). Set
    ``collapsible=True`` to wrap the chart in a click-to-expand Taipy expandable.
    """

    def __init__(
        self,
        extract: Callable[[dict], list],
        *,
        title: str,
        key: str | None = None,
        collapsible: bool = False,
        expanded: bool = True,
    ):
        super().__init__(x="x", y="y", agg="sum", title=title, key=key or f"lines:{title}")
        self._extract = extract
        self._collapsible = collapsible
        self._expanded = expanded

    def compute(self, output: Any) -> Any:
        from New_Pipeline.boundary import unpack_obj

        return {"points": self._extract(unpack_obj(output))}

    def render(self, gathered: dict) -> DashboardComponent:
        component = super().render(gathered)
        if self._collapsible:
            component.options = {**component.options, "collapsible": True, "expanded": self._expanded}
        return component


# --------------------------------------------------------------------------- #
# Run configuration table
# --------------------------------------------------------------------------- #
# One short line per cfg key, for the "Run configuration" widget below. Kept here
# rather than in experiments.py because it is documentation for a *reader of a run*,
# not an input to the run -- and because a Process body must be self-contained, so a
# module-level dict like this one can never live inside a node.
#
# Ordering is irrelevant here (the table follows the cfg dict's own order, which mirrors
# the notebook's cell-2/8/11 sequence); any key missing from this map still renders, with
# an empty description, so adding a knob to build_cfg cannot break the widget.
#
# "Provenance only" marks keys that no node reads: they travel in the cfg frame (so they
# are hashed, and they name output files via functions/output_paths.py) but change nothing
# in this pipeline. Verified by grepping every C[...] / .get(...) read across New_Pipeline.
_PARAM_DOCS: dict[str, str] = {
    # ---- cell 2: data vintage, window, region -------------------------------
    "golden_data": "Which Golden LC extract vintage to load from $GOLDEN_LOCATION (e.g. v_2C, v_2A1).",
    "region_analysis": "Region preset. Drives currency_filter / region_filter / convert_to_USD / fama_factor_region below.",
    "fama_factors_currency": "Currency of the FF factor set. Consulted only when region_analysis='Japan' (05_load_fama_french).",
    "RF_JAPAN_PATH": "Workbook holding the Japanese monthly risk-free rate; read only on the Japan JPY path.",
    "action_characterization": "Which signal design to build -- selects the categories_dict + signal-name pair from signal_definitions(_materiality).py. Consumed by build_cfg only; nodes see the derived dicts.",
    "start_year": "First calendar year of the return / universe window.",
    "end_year": "Last calendar year. Overridden by esg_choice (refinitiv or msci -> 2024, s&p -> 2022).",
    "security_status": "'active_only' keeps Compustat secstat=='A' (the frozen behaviour); 'all_firms_even_delisted' keeps inactive securities, so a delisted name retains its full price history.",
    "no_simple_quantiles": "Number of buckets in the univariate quantile sort (7 = septiles).",
    "ff_factors_number": "Factors in the alpha regression (3 = Mkt-RF, SMB, HML).",
    # ---- cell 2: ESG provider ----------------------------------------------
    "esg_choice": "ESG provider merged into the universe: none / refinitiv / msci / s&p. Also picks which Process runs at merge_esg_provider.",
    "esg_full_universe": "Sort the whole ESG universe on the provider score alone, with no LC signals. Requires a provider.",
    "show_esg_corr_matricies": "Gate for the esg_signal_corr node's correlation output.",
    "esg_corr_method": "Correlation method used there (pearson / spearman / kendall).",
    "esg_min_group_size": "Minimum issues per sort cell before prepare_panel collapses it into one composite stage.",
    "drop_real_estate_Full_ESG": "In the esg_full_universe run only: exclude real estate.",
    "drop_utilities_Full_ESG": "In the esg_full_universe run only: exclude utilities.",
    "download_gics_data": "Re-download GICS sector codes instead of using the cached file.",
    # ---- cell 2: signal construction ---------------------------------------
    "signal_denominator": "Denominator for signal_i: 'Sum_All_Signals' or 'Sum_All_Initiatives' (02_derive_signals).",
    "signal_type": "'weights' = signal_i is the group's share of sum_activities; 'counts' = the raw initiative total, and signal names gain a _counts suffix.",
    "alpha_bound": "Trim fraction applied to the signal tails when use_alpha_bound is on.",
    "winsorise_signal_pct": "Per-tail fraction of each signal CLIPPED (not dropped) within its rfyear. 0 = off. Rank-preserving, so it moves results only via the standardisation, not the sort.",
    # ---- cell 2: market-cap screen -----------------------------------------
    "market_cap_filter": "Which universe size screen runs: 'percent_total_mcap' (per currency-MONTH, share of aggregate cap VALUE) or 'percent_stocks' (per currency-YEAR, share of listing COUNT plus an absolute floor).",
    "mktcap_covered_if_filter_by_cum_market_cap": "percent_total_mcap only: fraction of each currency-month's total cap to retain. 0.95 is a share of value, so it discards roughly 65% of listings.",
    "percentage_stocks_removed_if_percent_stocks_true": "percent_stocks only: fraction of listings BY COUNT eligible for dropping (0.01 = 1%). Must be in [0,1]; a listing is dropped only if it is also below the floor.",
    "floor_if_percent_stocks_true": "percent_stocks only: absolute cap floor in the mktcap currency. Being absolute, it makes that screen single-currency only.",
    # ---- cell 2: optional merges -------------------------------------------
    "add_accounting_data": "Merge Compustat accounting items. Provenance only -- not read by any node.",
    "add_materiality": "Inner-join the SASB materiality workbook on (gvkey, rfyear). CHANGES THE SAMPLE -- the workbook stops at rfyear 2022.",
    "materiality_version": "SASB workbook vintage (1 or 2). Only v2 carries the per-SDG breakdown columns.",
    # ---- cell 2: sorting / calendar ----------------------------------------
    "industry_level": "Industry granularity the sort is taken within (0, 1 or 2).",
    "japan_year_adjustment_split_month_for_two_or_one": "Japan fiscal-year alignment: the month that splits fiscal year Y-2 from Y-1.",
    # ---- cell 2: sample filters --------------------------------------------
    "execute_3_filters": "Which sample filters run: 'all' (min fyears + suspicious gvkeys + min initiatives), 'suspicious_only' (filter 2 alone), or 'none'.",
    "min_available_rfyears_if_execute_3_filters_true": "Filter 1: minimum distinct fiscal years a firm must have to stay in the sample.",
    "min_initatives_annual_reports_if_execute_3_filters_true": "Filter 3: minimum initiatives an Annual Report row must carry. (Key spelling is as in the config.)",
    "drop_suspicious_gvkeys": "Filter 2: drop the hand-listed suspicious gvkeys.",
    "drop_real_estate": "Exclude real estate from the LC sample.",
    "drop_fin": "Exclude financials from the LC sample.",
    "drop_utilities": "Exclude utilities from the LC sample.",
    "drop_health_care": "Exclude health care from the LC sample.",
    "anlayse_fashion_only": "Restrict the sample to fashion firms. (Key spelling is as in the config.)",
    "msci_score_column": "Which MSCI score column to merge ('weighted' or 'industry').",
    "use_alpha_bound": "Whether the alpha_bound trim runs at all.",
    # ---- cell 2: diagnostics gates -----------------------------------------
    "show_sample_portfolio": "Emit the sample-portfolio diagnostic from build_analyse_portfolios.",
    "plot_coverage": "Coverage plots. Provenance only -- not read by any node (that plot is notebook-era, in functions/extra_functions/plot_coverage.py).",
    "show_esg_coverage": "Gate for the esg_coverage node, and for the pre-filter LC snapshot it needs from this node.",
    "show_mktcap_filter_audit": "Gate for the mktcap_filter_audit node, which replays the size screen per currency-month.",
    "show_sample_funnel_audit": "Gate for the sample_funnel_audit node, which reports rows in / out at each filter.",
    "include_all_signals_in_cum_risk_table": "Include every signal in the cumulative / risk tables. Provenance only -- not read by any node.",
    # ---- derived: region block (cell 2 if/elif) ----------------------------
    "fama_factor_region": "Derived from region_analysis: which FF factor file to load.",
    "currency_filter": "Derived from region_analysis: currencies kept in the universe.",
    "convert_to_USD": "Derived from region_analysis: whether returns and caps are converted to USD.",
    "region_filter": "Derived from region_analysis: Compustat region names kept.",
    "execute_region_filters": "Derived from region_analysis: whether that region filter is applied at all.",
    # ---- derived: signal design (cell 8) -----------------------------------
    "categories_dict": "Derived from action_characterization: LC category column -> signal index.",
    "lc_signals": "Derived from action_characterization: signal_i -> human-readable name (with the _counts suffix when signal_type='counts').",
    # ---- derived: analysis selection (cell 11) -----------------------------
    "analyse_high_low": "Derived: which tail the LC sorts report. Provenance only -- not read by any node.",
    "hml_directions": "Derived: per-signal direction of the long-short leg.",
    "universe_signals": "Derived: the provider ESG score treated as an extra sortable signal ({} when esg_choice='none').",
    "analysis_selection": "Derived: the (signal, bucket) pairs to analyse. Provenance only -- 07_build_analyse_portfolios rebuilds this list locally instead of reading it.",
}

# Cells wider than this are truncated with an ellipsis: categories_dict alone is ~50
# entries, and one runaway cell makes every other row in the Taipy table unreadable.
_VALUE_CHARS = 150


def config_table(bundle) -> Any:
    """``parameter | value | description`` for every key in the run's cfg.

    Reads the ``cfg_json`` string this node carries in its bundle, so the table shows the
    config *as the run actually received it* -- not as ``build_cfg`` would derive it today.
    Rows follow the cfg dict's own order (notebook cells 2, then 8, then 11), so the
    baseline knobs come first and the derived values last.
    """
    import json

    import pandas as pd

    raw = (bundle or {}).get("cfg_json")
    if not raw:
        return pd.DataFrame(columns=["parameter", "value", "description"])

    cfg = json.loads(raw)
    rows = []
    for key, value in cfg.items():
        # Scalars render as-is; dicts/lists as compact JSON, with the item count kept
        # visible when truncation hides the tail.
        if isinstance(value, (dict, list)):
            text = json.dumps(value, default=str)
            if len(text) > _VALUE_CHARS:
                text = f"{text[:_VALUE_CHARS]}... ({len(value)} items)"
        else:
            text = "None" if value is None else str(value)
        rows.append({"parameter": key, "value": text,
                     "description": _PARAM_DOCS.get(key, "")})
    return pd.DataFrame(rows)
