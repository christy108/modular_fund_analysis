"""Custom VizSpecs that surface EXISTING node outputs on the dashboard.

Several nodes emit a lossless pickle *bundle* (one `__pickle__` cell) rather than a
tidy frame, so the built-in `SampleTableViz`/`LineChartViz` — which read columns off a
tidy `pl.DataFrame` — can't see inside them. These subclasses override only `compute`
to unpack the bundle and pull out an already-computed table/series; `render` is reused
unchanged, so the Taipy payload is exactly what the framework expects.

No node output changes and no new analysis: each `extract` just returns a frame the
Process already put in the bundle (or a trivial count of it), so parity is untouched.
"""

from __future__ import annotations

from typing import Any, Callable

from leonardo_nodes.viz import (
    ColoredTableViz,
    DashboardComponent,
    DualAxisViz,
    HeatmapViz,
    LineChartViz,
    SampleTableViz,
)


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
    ):
        super().__init__(
            title=title,
            left_label=left_label or left_col,
            right_label=right_label or right_col,
            x_label=x_label or x_col,
            key=key,
        )
        self._extract = extract
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
        super().__init__(x="date", y="alpha", agg="mean", title=title, key=key or f"lines:{title}")
        self._extract = extract
        self._collapsible = collapsible
        self._expanded = expanded

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
