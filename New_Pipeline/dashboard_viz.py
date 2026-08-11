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

from leonardo_nodes.viz import DashboardComponent, LineChartViz, SampleTableViz


class BundleTableViz(SampleTableViz):
    """Render a pandas table pulled from a node's pickle-bundle output as a table widget.

    ``extract(bundle_dict) -> pandas.DataFrame``. Columns are discovered from the data
    (they vary by config, e.g. the FF3 table gains ESG portfolio columns), so nothing
    is hard-coded.
    """

    def __init__(self, extract: Callable[[dict], Any], *, title: str, n: int = 200, key: str | None = None):
        super().__init__(columns=[], n=n, title=title, key=key)
        self._extract = extract

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
