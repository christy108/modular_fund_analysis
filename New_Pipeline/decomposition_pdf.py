"""Render build_analyse_portfolios' material-initiative area plots to a PDF.

Gated by ``cfg.area_initatives_plots_per_portfolio_to_PDF`` and called from
``New_Pipeline/run.py`` once a run has finished, writing
``runs/<ts>_<config>/initiative_decomposition.pdf`` next to ``dashboard.md``.

Two deliberate choices:

* **Rendered here, not in the node.** An archived Process is replayed in a fresh namespace
  and knows nothing about the run directory it is being replayed for; a Process that wrote
  files into one would produce different side effects on every replay. ``run.py`` owns the
  run directory, so the file-writing lives there.
* **Nothing is recomputed.** Every panel is read out of the finished run's manifest
  (``manifest.record_for(node).audit_stats[key]``) -- the exact payloads the Taipy dashboard
  renders -- so the PDF and the dashboard cannot disagree. Same approach as
  ``sweep_report.py``. If a VizSpec's ``key=`` changes, the matching panel goes blank; grep
  ``_AREA_KEY`` and ``_LEVELS_KEY`` when renaming one.

Six pages: a cover carrying the initiative levels and the coverage table, a sector page
reusing the dashboard's own "Sector share (%)" / "Stocks" payloads, then one page per
(leg x weighting) holding every bracket scheme. One chart per page would be two dozen pages
of mostly whitespace and impossible to compare across schemes.
"""

from __future__ import annotations

import os
from pathlib import Path

from New_Pipeline.dashboard_viz import _AREA_COLORS
from New_Pipeline.initiative_brackets import SCHEME_SLUGS, scheme_title

_NODE = "build_analyse_portfolios"
_BUCKETS = ("High", "Low")
_WEIGHTINGS = (("pooled", "pooled sum"), ("equal_weight", "equal-weight across firms"))

# The two weightings produce charts that look alike and mean different things, so the
# distinction goes on every page rather than once on the cover.
_WEIGHTING_BLURB = {
    "pooled": (
        "POOLED SUM\n"
        "Add up every holding's initiatives,\n"
        "then take shares. Literally the\n"
        "initiatives that make up this leg.\n"
        "Firms report 1 to 100+ each, so a\n"
        "few heavy reporters can set the mix:\n"
        "a shift here can mean one large firm\n"
        "entered, not that behaviour changed."
    ),
    "equal_weight": (
        "EQUAL-WEIGHT ACROSS FIRMS\n"
        "Each holding's own mix first, then\n"
        "average across holdings. Every firm\n"
        "counts once however much it reports,\n"
        "matching how the portfolio is weighted\n"
        "in returns -- so this is the mix to\n"
        "read when attributing alpha. Holdings\n"
        "with no material initiatives drop out."
    ),
}

_COVERAGE_KEY = "table:decomposition_coverage"

# The sector widgets predate this module and are keyed on the raw signal name, not on a
# scheme. signal_0 is the material share -- the same leg the decomposition charts describe
# (signal_1 is its exact mirror, so High signal_0 / Low signal_0 are the two real legs).
_SECTOR_SIGNAL = "signal_0"


def _SECTOR_KEY(bucket: str) -> str:
    return f"lines:sector_share:{bucket} {_SECTOR_SIGNAL}"


def _COUNT_KEY(bucket: str) -> str:
    return f"lines:count:{bucket} {_SECTOR_SIGNAL}"


def _AREA_KEY(weighting: str, slug: str, bucket: str) -> str:
    return f"area:decomp:{weighting}:{slug}:{bucket}"


def _LEVELS_KEY(bucket: str) -> str:
    return f"lines:decomp_levels:{bucket}"


_PAGE_W, _PAGE_H = 16.5, 10.5


def _payload(manifest, key):
    record = manifest.record_for(_NODE)
    return record.audit_stats.get(key) if record else None


def _series(manifest, key, *, name: str = "value") -> list:
    """Normalise either widget payload shape to [{"name","x","y"}, ...].

    ``BundleMultiSeriesViz`` / ``BundleStackedAreaViz`` emit ``{"series": [...]}`` with a
    name per line; ``BundleSeriesViz`` emits ``{"points": [{"x":..,"y":..}, ...]}`` -- one
    unnamed series. The stock-count widget is the second kind, so reading only "series"
    silently returns nothing and the panel renders "no data".
    """
    payload = _payload(manifest, key) or {}
    if payload.get("series"):
        return payload["series"]
    points = payload.get("points") or []
    if not points:
        return []
    return [{"name": name,
             "x": [pt["x"] for pt in points],
             "y": [pt["y"] for pt in points]}]


def _has_data(manifest) -> bool:
    """True when this run actually produced the decomposition (any area panel non-empty)."""
    return any(
        _series(manifest, _AREA_KEY(w, slug, bkt))
        for w, _ in _WEIGHTINGS
        for slug in SCHEME_SLUGS
        for bkt in _BUCKETS
    )


def _dates(series):
    import pandas as pd

    return pd.to_datetime(series[0]["x"])


def _stack_panel(ax, series, title, color_of=None, ylabel="% of material initiatives"):
    """One scheme's bands as a stacked area, 0-100%.

    ``color_of`` maps a band NAME to a colour. Pass it when two panels show the same
    concept under different band orderings (the sector widgets sort by mean share, so the
    High and Low legs list their sectors differently and positional colours would give one
    sector two colours). Leave it None for the bracket schemes, where band names collide
    across schemes with different meanings ("Advocacy" is not the same cut in the 3-way and
    4-way splits) and a name-based map would imply a link that is not there.
    """
    if not series:
        ax.text(0.5, 0.5, "no data", ha="center", va="center", fontsize=9, color="#888")
        ax.set_axis_off()
        return
    x = _dates(series)
    # 0.0 for a missing month rather than dropping it: stackplot needs rectangular input,
    # and a gap month genuinely held no material initiatives in that band.
    ys = [[0.0 if v is None else float(v) for v in s["y"]] for s in series]
    if color_of is None:
        colors = [_AREA_COLORS[i % len(_AREA_COLORS)] for i in range(len(series))]
    else:
        colors = [color_of[str(s["name"])] for s in series]
    ax.stackplot(
        x, *ys,
        labels=[str(s["name"]) for s in series],
        colors=colors,
        linewidth=0.4, edgecolor="white",
    )
    ax.set_ylim(0, 100)
    ax.set_xlim(x.min(), x.max())
    ax.set_title(title, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=8)
    ax.tick_params(labelsize=7)
    # Band names differ per scheme, so each panel carries its own legend. Columns scale
    # with the band count -- the widest scheme has 15 bands and at ncol=2 its legend is
    # taller than the chart.
    n = len(series)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13),
              ncol=2 if n <= 6 else 4, fontsize=6.5 if n <= 6 else 5.5, frameon=False)


def _levels_panel(ax, series, title):
    if not series:
        ax.text(0.5, 0.5, "no data", ha="center", va="center", fontsize=9, color="#888")
        ax.set_axis_off()
        return
    x = _dates(series)
    for i, s in enumerate(series):
        ax.plot(x, [None if v is None else float(v) for v in s["y"]],
                label=str(s["name"]), color=_AREA_COLORS[i % len(_AREA_COLORS)], linewidth=1.2)
    ax.set_title(title, fontsize=10)
    ax.set_ylabel("Initiatives", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize=7, frameon=False)


def _table_panel(ax, rows, title):
    ax.set_axis_off()
    ax.set_title(title, fontsize=10, loc="left")
    if not rows:
        ax.text(0, 0.5, "no data", fontsize=9, color="#888")
        return
    cols = list(rows[0])
    # Wrap on underscores. These are snake_case column names up to 30 characters wide in a
    # 1/11th-of-a-page cell, so left flat they overlap their neighbours and become unreadable.
    labels = ["\n".join(c.split("_")) for c in cols]
    n = len(rows)
    # Height proportional to the row count rather than filling the axes: with two buckets a
    # bbox of 1.0 gives cells several centimetres tall holding one number each.
    height = min(0.9, 0.13 * (n + 2.2))
    table = ax.table(
        cellText=[[f"{r.get(c, '')}" for c in cols] for r in rows],
        colLabels=labels,
        loc="upper left",
        cellLoc="center",
        bbox=[0, 0.92 - height, 1, height],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(7)
    for (row, _), cell in table.get_celld().items():
        if row == 0:
            cell.set_fontsize(6.5)
            cell.set_facecolor("#f1f5f9")


def _cover_page(pdf, manifest, name):
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec

    fig = plt.figure(figsize=(_PAGE_W, _PAGE_H))
    # Line breaks are explicit rather than relying on matplotlib's wrap=True, which measures
    # against the FIGURE width and lets a long fig.text run off both edges of the page.
    fig.suptitle(f"Material-initiative decomposition — {name}", fontsize=15, y=0.975)
    fig.text(0.5, 0.945,
             "Composition of each portfolio leg's MATERIAL initiatives, by formation month.\n"
             "Each holding's fiscal year is the point-in-time rfyear its own signal was built "
             "from, so no chart shows an initiative the sort had not yet seen.",
             ha="center", va="top", fontsize=8.5, color="#444", linespacing=1.5)
    fig.text(0.5, 0.895,
             "Every leg is charted twice.\n"
             "POOLED SUM adds up all holdings' initiatives then takes shares — the leg's "
             "actual reporting, but set by the heaviest reporters.\n"
             "EQUAL-WEIGHT takes each firm's own mix then averages, so every firm counts "
             "once — the weighting the portfolio itself uses, and the one to read when "
             "attributing alpha.",
             ha="center", va="top", fontsize=8, color="#444", linespacing=1.5)
    gs = GridSpec(2, 2, figure=fig, top=0.80, bottom=0.07, hspace=0.3, wspace=0.18)
    for i, bkt in enumerate(_BUCKETS):
        _levels_panel(fig.add_subplot(gs[0, i]), _series(manifest, _LEVELS_KEY(bkt)),
                      f"Initiatives held over time — {bkt} Material")
    ax = fig.add_subplot(gs[1, :])
    _table_panel(ax, (_payload(manifest, _COVERAGE_KEY) or {}).get("rows") or [],
                 "Coverage — how much of each leg these charts actually describe")
    pdf.savefig(fig)
    plt.close(fig)


def _sector_page(pdf, manifest, name):
    """Sector mix of each leg over time, plus how many names it held.

    Exactly the payloads the dashboard's "Sector share (%)" and "Stocks" widgets render --
    read out of the manifest, not recomputed -- so this page and the dashboard cannot
    disagree. Drawn as a stacked area rather than the dashboard's overlaid lines because
    the shares sum to 100 by construction; the numbers are identical either way.

    Sector -> colour is shared across the two legs. The widget sorts its series by mean
    share, so High and Low list their sectors in different orders and positional colours
    would paint "Financial" two different colours on one page.
    """
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec

    fig = plt.figure(figsize=(_PAGE_W, _PAGE_H))
    fig.suptitle(f"Sector distribution of each leg   ({name})", fontsize=15, y=0.975)
    fig.text(0.5, 0.94,
             "Share of each leg's HOLDINGS by sector (counts of names, not of initiatives) "
             "and the leg's total size beneath it.\n"
             "The sector cut is `map_sectors(GICS_level_1)` at cfg.industry_level -- the same "
             "grouping standardize_pivot demeans the signal within, so a\nsurviving sector "
             "tilt here is variance the standardisation did not remove.",
             ha="center", va="top", fontsize=8.5, color="#444", linespacing=1.5)

    series_by_bucket = {b: _series(manifest, _SECTOR_KEY(b)) for b in _BUCKETS}
    # Union in first-seen order across both legs, so a sector present in only one still
    # gets a stable colour.
    names: list[str] = []
    for b in _BUCKETS:
        for s in series_by_bucket[b]:
            if str(s["name"]) not in names:
                names.append(str(s["name"]))
    color_of = {n: _AREA_COLORS[i % len(_AREA_COLORS)] for i, n in enumerate(names)}

    gs = GridSpec(2, 2, figure=fig, top=0.83, bottom=0.07, hspace=0.45, wspace=0.18,
                  height_ratios=[1.6, 1.0])
    for i, b in enumerate(_BUCKETS):
        _stack_panel(fig.add_subplot(gs[0, i]), series_by_bucket[b],
                     f"Sector share (%) — {b} Material",
                     color_of=color_of, ylabel="% of holdings")
        ax = fig.add_subplot(gs[1, i])
        _levels_panel(ax, _series(manifest, _COUNT_KEY(b), name="Stocks held"),
                      f"Stocks held — {b} Material")
        ax.set_ylabel("Number of stocks", fontsize=8)
    pdf.savefig(fig)
    plt.close(fig)


def _scheme_page(pdf, manifest, name, bucket, weighting, weighting_label):
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec

    fig = plt.figure(figsize=(_PAGE_W, _PAGE_H))
    fig.suptitle(f"{bucket} Material — {weighting_label}   ({name})", fontsize=14, y=0.97)
    # Grid sized from the scheme count + 1, so the note cell always follows the last chart
    # rather than being overwritten when a scheme is added.
    ncols = 3
    nrows = -(-(len(SCHEME_SLUGS) + 1) // ncols)
    # bottom/hspace are set for the LEGENDS, not the axes: each panel hangs its own legend
    # below itself (band names differ per scheme, so one shared legend is impossible), and
    # the bottom row's runs off the page at the default margins.
    gs = GridSpec(nrows, ncols, figure=fig, top=0.90, bottom=0.07,
                  hspace=0.75, wspace=0.20)
    for i, slug in enumerate(SCHEME_SLUGS):
        _stack_panel(fig.add_subplot(gs[i // ncols, i % ncols]),
                     _series(manifest, _AREA_KEY(weighting, slug, bucket)),
                     scheme_title(slug))
    # Cell after the last chart: what the weighting means, and the caveat that decides how
    # to read every panel on the page.
    _n = len(SCHEME_SLUGS)
    ax = fig.add_subplot(gs[_n // ncols, _n % ncols])
    ax.set_axis_off()
    rows = (_payload(manifest, _COVERAGE_KEY) or {}).get("rows") or []
    row = next((r for r in rows if str(r.get("bucket")) == bucket), None)
    lines = [f"Leg: {bucket} Material", "", _WEIGHTING_BLURB[weighting], ""]
    if row:
        lines += [
            f"months: {row.get('n_months')}",
            f"median holdings: {row.get('median_holdings')}",
            f"holdings matched: {row.get('pct_holdings_matched')}%",
            f"holdings with NO material: {row.get('pct_holdings_zero_material')}%",
            f"median holdings charted: {row.get('median_holdings_with_material')}",
            f"material share of initiatives: {row.get('pct_initiatives_material')}%",
            "",
            "Denominator is material__total, so",
            "holdings with none are absent from",
            "every panel on this page.",
        ]
    ax.text(0, 1, "\n".join(lines), va="top", ha="left", fontsize=7.2, family="monospace")
    pdf.savefig(fig)
    plt.close(fig)


def build_decomposition_pdf(manifest, name: str, pdf_path) -> int:
    """Write the PDF; return the page count (0 = nothing to draw, no file written)."""
    if not _has_data(manifest):
        return 0

    import matplotlib
    matplotlib.use("Agg")           # no display needed, and safe under nohup/cron
    from matplotlib.backends.backend_pdf import PdfPages

    pdf_path = Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = pdf_path.with_suffix(".pdf.tmp")

    pages = 0
    with PdfPages(tmp) as pdf:
        _cover_page(pdf, manifest, name)
        pages += 1
        _sector_page(pdf, manifest, name)
        pages += 1
        for bucket in _BUCKETS:
            for weighting, label in _WEIGHTINGS:
                _scheme_page(pdf, manifest, name, bucket, weighting, label)
                pages += 1

    os.replace(tmp, pdf_path)       # atomic: the old PDF stays valid until this instant
    return pages
