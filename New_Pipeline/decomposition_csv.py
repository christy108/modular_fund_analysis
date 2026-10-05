"""Write the numbers behind ``initiative_decomposition.pdf`` as a tidy CSV.

Called from ``New_Pipeline/run.py`` alongside the PDF, writing
``runs/<ts>_<config>/initiative_decomposition.csv``. The point is that someone can redraw
these charts themselves -- in Excel, R, whatever -- without running the pipeline.

Same two design choices as ``decomposition_pdf.py``, for the same reasons:

* **Written by run.py, not by the node.** An archived Process is replayed in a fresh
  namespace and knows nothing about the run directory; a Process that wrote files into one
  would have different side effects on every replay.
* **Nothing is recomputed.** Every value is read from the finished run's manifest
  (``manifest.record_for(node).audit_stats[key]``) -- the exact payloads the dashboard and
  the PDF render. So the CSV cannot disagree with the picture it describes. If a VizSpec's
  ``key=`` changes, those rows vanish; grep the ``_*_KEY`` helpers in decomposition_pdf.py.

LONG format, one observation per row, because it is the only shape that holds four
different panels without a ragged header. Pivot to draw:

    df[(df.panel=="bracket_share") & (df.weighting=="pooled") & (df.bucket=="High")
       & (df.scheme_slug=="matteo3")].pivot(index="date", columns="series", values="value")

Columns
    panel         bracket_share | scheme_coverage | levels | sector_share | stocks
    scheme_slug   bracket scheme, e.g. matteo3 (blank for the non-bracket panels)
    scheme_title  its display name, as printed on the PDF page
    weighting     pooled | equal_weight (blank where the panel has no weighting)
    bucket        High | Low
    series        the band / line name -- what a stacked-area layer is labelled
    date          formation month, YYYY-MM-DD
    value         the plotted number
    unit          what `value` means; see _UNITS below

The ``bracket_share`` bands sum to 100 per (scheme, weighting, bucket, date): they are
shares of what the scheme could CLASSIFY, not of the leg's whole material count. The
``scheme_coverage`` panel carries that gap explicitly -- for ``matteo3``, which labels only
~91% of material initiatives, those rows are what tells you the other ~9% exists.
"""

from __future__ import annotations

from pathlib import Path

from New_Pipeline.decomposition_pdf import (
    _AREA_KEY,
    _BUCKETS,
    _COUNT_KEY,
    _LEVELS_KEY,
    _SECTOR_KEY,
    _WEIGHTINGS,
    _series,
)
from New_Pipeline.initiative_brackets import SCHEME_SLUGS, scheme_title

_COLUMNS = ["panel", "scheme_slug", "scheme_title", "weighting", "bucket",
            "series", "date", "value", "unit"]

_UNITS = {
    "bracket_share": "percent_of_classified_initiatives",
    "scheme_coverage": "percent_of_signal_numerator",
    "levels": "initiative_count",
    "sector_share": "percent_of_holdings",
    "stocks": "holding_count",
}


def _rows_from_series(series, *, panel, bucket, weighting="", slug="", title=""):
    out = []
    for s in series or []:
        name = str(s.get("name", ""))
        for x, y in zip(s.get("x") or [], s.get("y") or []):
            out.append({
                "panel": panel, "scheme_slug": slug, "scheme_title": title,
                "weighting": weighting, "bucket": bucket, "series": name,
                "date": str(x)[:10],
                # None (a gap in the line) is written as an EMPTY cell, not 0 -- a month a
                # chart deliberately skips must not read as a real zero downstream.
                "value": "" if y is None else float(y),
                "unit": _UNITS[panel],
            })
    return out


def build_decomposition_csv(manifest, name: str, csv_path, bundle=None) -> int:
    """Write the tidy CSV; return the row count (0 = this run drew no decomposition)."""
    import pandas as pd

    rows: list[dict] = []

    # The bracket area charts -- the plots this CSV mainly exists for.
    for slug in SCHEME_SLUGS:
        title = scheme_title(slug)
        for weighting, _ in _WEIGHTINGS:
            for bkt in _BUCKETS:
                rows += _rows_from_series(
                    _series(manifest, _AREA_KEY(weighting, slug, bkt)),
                    panel="bracket_share", bucket=bkt, weighting=weighting,
                    slug=slug, title=title,
                )

    if not rows:
        return 0        # no decomposition in this run; skip the file entirely

    # How much of each leg those bands actually describe. Read from the bundle rather than
    # a widget payload because it is context for the charts, not itself a chart.
    cov = None if bundle is None else bundle.get("scheme_coverage")
    if cov is not None and not cov.empty:
        for r in cov.to_dict("records"):
            rows.append({
                "panel": "scheme_coverage",
                "scheme_slug": r["scheme_slug"], "scheme_title": r["scheme_title"],
                "weighting": "", "bucket": r["bucket"],
                "series": "pct_of_numerator_classified",
                "date": str(r["date"])[:10],
                "value": r["pct_of_numerator_classified"],
                "unit": _UNITS["scheme_coverage"],
            })

    # The remaining PDF panels, so the file covers the whole report rather than one page.
    for bkt in _BUCKETS:
        rows += _rows_from_series(_series(manifest, _LEVELS_KEY(bkt)),
                                  panel="levels", bucket=bkt)
        rows += _rows_from_series(_series(manifest, _SECTOR_KEY(bkt)),
                                  panel="sector_share", bucket=bkt)
        rows += _rows_from_series(_series(manifest, _COUNT_KEY(bkt), name="stocks"),
                                  panel="stocks", bucket=bkt)

    df = pd.DataFrame(rows, columns=_COLUMNS).sort_values(
        ["panel", "scheme_slug", "weighting", "bucket", "date", "series"],
        kind="mergesort",
    )
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    return len(df)
