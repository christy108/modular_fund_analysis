"""Ledger + PDF page rendering + CSV export for `python -m New_Pipeline.sweep`.

Three ideas, in order of importance:

1. **The ledger is the database.** ``results.jsonl`` is append-only: one JSON object per
   experiment, flushed and fsync'd the moment that experiment finishes. Nothing else the
   sweep writes is authoritative. Quitting mid-sweep can lose at most the in-flight run.

2. **The PDF and the CSV are derived views**, rebuilt from the whole ledger rather than
   appended to. That is what makes a growing column set safe: portfolio labels differ per
   ``action_characterization``, so experiment #40 can introduce ``alpha__High Material``
   columns experiment #1 never had. A rebuild takes the union and back-fills; a plain
   append would misalign the file silently. Both are written to a ``.tmp`` sibling and
   ``os.replace``d into place, so a crash mid-write cannot corrupt the previous good copy.

3. **Nothing here recomputes any number.** Every panel on the page is an already-computed
   dashboard widget payload, pulled out of the run's manifest by key
   (``manifest.record_for(node).audit_stats[key]``) and drawn with matplotlib. This module
   is a renderer, not an analysis step — which is why the sweep cannot affect parity.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# The seven sections, in the order they appear on the page.
# (slug, node name, audit_stats key, panel title)
# Keys are the VizSpec `key=` values declared on each node's Contract -- see
# nodes/02_derive_signals.py, nodes/01_process_lc.py, nodes/07_build_analyse_portfolios.py.
# --------------------------------------------------------------------------- #
SECTIONS = [
    ("signal_breakdown", "derive_signals", "colored_table:category_column_stats",
     "1. Signal breakdown - category columns feeding each signal"),
    ("parameters", "process_lc", "table:config",
     "2. Parameters"),
    ("risk", "build_analyse_portfolios", "table:risk_table",
     "3. Risk metrics"),
    ("cumulative", "build_analyse_portfolios", "lines:cumulative_long",
     "4. Cumulative returns - long portfolios"),
    ("spreads", "build_analyse_portfolios", "lines:cumulative_spreads",
     "5. Cumulative returns - High-Low spreads"),
    ("rolling40", "build_analyse_portfolios", "lines:rolling_alpha_40",
     "6. Rolling alpha - 40-month window"),
    ("coverage", "build_analyse_portfolios", "table:portfolio_coverage",
     "7. Portfolio size coverage - % of months at or above the minimum"),
]

# Panels drawn as line charts rather than tables.
_LINE_SLUGS = {"cumulative", "spreads", "rolling40"}

# Risk-table rows whose FF3 alpha has p < this are shaded green on the page. 0.10 is the
# 10% significance level -- deliberately the loosest conventional threshold, because the
# point here is to make candidates jump out of a 222-page sweep, not to assert a result.
_ALPHA_SIGNIF_P = 0.10
_GREEN, _GREEN_ALT = "#cdeccd", "#c2e6c2"      # two shades so zebra striping survives


# --------------------------------------------------------------------------- #
# Config diffing
# --------------------------------------------------------------------------- #
def _is_scalar(v) -> bool:
    """True for JSON scalars only.

    Deliberately excludes the derived containers build_cfg fills in
    (categories_dict, lc_signals, analysis_selection, hml_directions, currency_filter,
    region_filter): they cascade from the scalar knobs, so reporting them as differences
    would swamp a title that is supposed to say "alpha_bound=0.05".
    """
    return v is None or isinstance(v, (str, int, float, bool))


def param_diff(cfg: dict, base: dict | None = None) -> dict:
    """Scalar cfg keys where ``cfg`` differs from the ``build_cfg()`` baseline.

    Works for sweep-generated configs and for hand-named EXPERIMENTS entries alike --
    it reads the resulting config, not the overrides that produced it.
    """
    if base is None:
        from New_Pipeline.experiments import build_cfg
        base = build_cfg()
    out = {}
    for k, v in cfg.items():
        if not _is_scalar(v):
            continue
        if k in base and base[k] == v:
            continue
        out[k] = v
    return out


def _fmt_value(v) -> str:
    if isinstance(v, float):
        # 0.05 not 0.05000000000000001; 100000000.0 -> 1e+08 stays readable.
        return f"{v:g}"
    return str(v)


def page_title(diff: dict) -> str:
    """The bold headline for a page: the parameters that differ from build_cfg defaults."""
    if not diff:
        return "base_parameters"
    return ", ".join(f"{k}={_fmt_value(v)}" for k, v in sorted(diff.items()))


def experiment_name(diff: dict) -> str:
    """Filesystem/registry-safe experiment name derived from the same diff.

    MUST be deterministic across processes: the name is the key `--resume` matches
    against the ledger, and it names `runs/<ts>_<name>/`. Python's builtin hash() is
    salted per interpreter (PYTHONHASHSEED), so using it here made long names differ on
    every invocation -- a resumed sweep would re-run those configs forever under fresh
    names. blake2b is stable across processes and machines.
    """
    if not diff:
        return "base_parameters"
    parts = []
    for k, v in sorted(diff.items()):
        val = _fmt_value(v).replace(".", "p").replace(" ", "").replace("/", "-")
        parts.append(f"{k}-{val}")
    name = "sweep__" + "__".join(parts)
    # Long action_characterization names can blow past filesystem limits once combined.
    if len(name) <= 150:
        return name
    import hashlib

    digest = hashlib.blake2b(name.encode("utf-8"), digest_size=4).hexdigest()
    return name[:140] + f"__h{digest}"


# --------------------------------------------------------------------------- #
# Ledger (append-only; the database)
# --------------------------------------------------------------------------- #
def append_ledger(path: str | Path, record: dict) -> None:
    """Append one record and force it to disk before returning.

    flush + fsync is the whole point: without it a Ctrl-C moments later can leave the
    line in a buffer that never reaches the file, which is exactly the loss this design
    exists to prevent.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def read_ledger(path: str | Path) -> list[dict]:
    """Every record in the ledger, oldest first. Missing file -> []."""
    path = Path(path)
    if not path.exists():
        return []
    records = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            # A half-written final line is the expected shape of a hard kill mid-append.
            # Skip it rather than refusing to rebuild everything that came before.
            print(f"[sweep] ledger line {line_no} is corrupt, skipping it")
    return records


def ledger_names(path: str | Path) -> set[str]:
    """Experiment names already recorded -- what ``--resume`` skips."""
    return {r.get("experiment") for r in read_ledger(path) if r.get("experiment")}


# --------------------------------------------------------------------------- #
# Presentation order
# --------------------------------------------------------------------------- #
def _sort_key(record: dict, sort_by: list, value_order: dict):
    """Sort key for one ledger record: cfg values in `sort_by` order.

    For each key, a value listed in `value_order[key]` sorts by its position there --
    which is how "group the PDF by action_characterization, in THIS order" is expressed.
    Values not listed sort after those, by their natural order. The (rank, value) pair
    keeps mixed types from ever being compared directly: an unlisted string and an
    unlisted int both land in rank 1, so they are coerced to str before comparing.
    """
    key = []
    for k in sort_by:
        v = (record.get("cfg") or {}).get(k)
        order = value_order.get(k) or []
        if v in order:
            key.append((0, order.index(v), ""))
        else:
            # Numbers keep numeric ordering among themselves; anything else compares as
            # text. Both are wrapped so the tuple shapes stay comparable.
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                key.append((1, float(v), ""))
            else:
                key.append((2, 0.0, str(v)))
    # Final tiebreak keeps the order deterministic (and stable under --jobs N, where
    # records land in completion order rather than submission order).
    key.append((0, 0.0, str(record.get("experiment", ""))))
    return key


def sorted_records(records: list, sort_by=None, value_order=None) -> list:
    """Ledger records in presentation order. Falls back to ledger order if unconfigured.

    build_pdf and build_csv BOTH call this, which is what keeps `row N <-> page N` true:
    the two derived views must enumerate the same records in the same sequence.
    """
    if sort_by is None or value_order is None:
        try:
            from New_Pipeline import sweep_parameters as SP
            sort_by = SP.SORT_BY if sort_by is None else sort_by
            value_order = getattr(SP, "VALUE_ORDER", None) if value_order is None else value_order
        except Exception:
            sort_by, value_order = [], {}
    if not sort_by:
        return list(records)
    if value_order is None:
        value_order = {}
    return sorted(records, key=lambda r: _sort_key(r, sort_by, value_order))


# --------------------------------------------------------------------------- #
# Page rendering
# --------------------------------------------------------------------------- #
# One page is 24x17in (~A2 landscape). Everything on it is vector, so the deliberately
# small fonts stay sharp at any zoom -- the page is meant to be zoomed into, not read at
# fit-to-window.
_PAGE_W, _PAGE_H = 24, 17
# Nothing is dropped for want of space: a table that does not fit shrinks its rows and
# its font until it does. 400 is a runaway guard, not a display choice -- the widest
# design in the repo (Materiality_Climate_Natural_Capital_vs_All_SDGS, 30 signals) needs
# 91 risk rows and 60 coverage rows, so a cap anywhere near those would silently hide
# most of a page. Truncation only ever kicks in for something pathological.
_MAX_TABLE_ROWS = 400
_TABLE_FONT = 6.0             # upper bound; small tables never exceed it
_TABLE_FONT_MIN = 1.1         # lower bound; vector output, so this stays sharp zoomed in
_TABLE_ROW_H_MAX = 0.050      # a 4-row table stays compact instead of filling a tall slot


def _num(v):
    """Coerce a pre-formatted table cell ('-0.36', '-11.15%', '') to float or None.

    risk_table / portfolio_coverage cells arrive as display strings from
    functions/portfolio_metrics/Strategy_Perfomance.py, so the CSV would otherwise carry
    text where Excel needs numbers.
    """
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v
    s = str(v).strip().replace("%", "").replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _panel_note(ax, text: str, title: str) -> None:
    """Draw an empty panel that says why it is empty, instead of raising."""
    ax.axis("off")
    ax.set_title(title, fontsize=10, fontweight="bold", loc="left")
    ax.text(0.5, 0.5, text, ha="center", va="center", fontsize=9,
            style="italic", color="#888888", transform=ax.transAxes)


def _significant_alpha(row: dict) -> bool:
    """True when this portfolio's FF3 alpha is significant at the 10% level.

    The risk-table payload carries `p-value(alpha)` as a PRE-FORMATTED string ("0.04",
    and "" for the Market row, which has no alpha), so it goes through _num rather than
    being compared directly. A missing / unparseable p-value is not significant.
    """
    p = _num(row.get("p-value(alpha)"))
    return p is not None and p < _ALPHA_SIGNIF_P


def _table_panel(ax, payload, title, *, max_rows=_MAX_TABLE_ROWS, drop_cols=(),
                 cell_chars=38, highlight=None) -> None:
    ax.axis("off")
    rows = (payload or {}).get("rows") or []
    if not rows:
        _panel_note(ax, "no data", title)
        return

    # Union of keys in first-seen order -- the same column discovery BundleTableViz.render
    # does, so the panel shows what the dashboard would show.
    cols: list[str] = []
    for r in rows:
        for k in r:
            if k not in cols and k not in drop_cols:
                cols.append(k)

    def _cell(v):
        if v is None:
            return ""
        # describe() stats arrive as full-precision floats (10.741016724623282); four
        # significant figures is all that is readable at this size and all that is meant.
        if isinstance(v, float) and not isinstance(v, bool):
            return f"{v:.4g}"
        return str(v)[:cell_chars]

    truncated = len(rows) > max_rows
    shown = rows[:max_rows]
    cells = [[_cell(r.get(c)) for c in cols] for r in shown]

    ax.set_title(title, fontsize=10, fontweight="bold", loc="left")

    # An explicit bbox is what keeps a long table INSIDE its panel: matplotlib's
    # loc="upper left" placement happily draws past the axes and over the neighbouring
    # panel. Row height is capped so a 4-row table stays compact at the top rather than
    # stretching to fill a tall slot, and shrinks below the cap once the rows stop fitting.
    n = len(shown) + 1                       # + header
    foot = 0.035 if truncated else 0.0
    row_h = min(_TABLE_ROW_H_MAX, (1.0 - foot) / n)
    h = n * row_h
    tbl = ax.table(cellText=cells, colLabels=cols, cellLoc="left",
                   bbox=[0.0, 1.0 - h, 1.0, h])
    tbl.auto_set_font_size(False)
    # Font follows row height, so a 91-row risk table (the 30-signal design) simply
    # renders smaller rather than losing rows. The floor is deliberately tiny: the page
    # is vector and meant to be zoomed, so unreadable-at-fit-to-window beats truncated.
    font = max(_TABLE_FONT_MIN, min(_TABLE_FONT, row_h * 145))
    tbl.set_fontsize(font)
    # Cell borders and padding have to come down with the font or they dominate the text
    # and the rows visually merge into a grey block.
    lw = 0.30 if font >= 4.0 else 0.12
    # Rows the caller wants flagged. Computed once here, then looked up per cell: the
    # celld loop visits every cell, and re-running the predicate for each column of a
    # 91-row table would be wasteful.
    flagged = {i for i, row in enumerate(shown) if highlight and highlight(row)}
    for (r, _c), cell in tbl.get_celld().items():
        cell.set_linewidth(lw)
        cell.PAD = 0.04 if font >= 4.0 else 0.015
        cell.set_edgecolor("#cccccc")
        if r == 0:
            cell.set_facecolor("#e8eaf0")
            cell.set_text_props(fontweight="bold")
        elif (r - 1) in flagged:                 # data row r maps to shown[r-1]
            # Two greens so the zebra striping still reads underneath the highlight.
            cell.set_facecolor(_GREEN_ALT if r % 2 == 0 else _GREEN)
        elif r % 2 == 0:
            cell.set_facecolor("#f7f7f9")

    if truncated:
        ax.text(0.0, 1.0 - h - 0.012, f"... {len(rows) - max_rows} more rows (see dashboard.md)",
                transform=ax.transAxes, fontsize=6.5, va="top",
                style="italic", color="#666666")


def _lines_panel(ax, payload, title) -> None:
    import matplotlib.dates as mdates
    import pandas as pd

    series = (payload or {}).get("series") or []
    series = [s for s in series if s.get("x") and s.get("y")]
    if not series:
        _panel_note(ax, "no series (window may not have been fitted for this config)", title)
        return

    # 30-signal designs put up to 90 lines here, far past the ~10 colours in the default
    # cycle, so the same colour recurs every 10 lines. Cycling linestyle underneath the
    # colour makes a line identifiable against its legend entry again.
    n = len(series)
    styles = ("-", "--", ":", "-.")
    lw = 1.1 if n <= 12 else (0.8 if n <= 40 else 0.6)
    for i, s in enumerate(series):
        x = pd.to_datetime(pd.Series(s["x"]), errors="coerce")
        ax.plot(x, s["y"], linewidth=lw, linestyle=styles[(i // 10) % len(styles)],
                label=str(s.get("name", "")))

    ax.set_title(title, fontsize=10, fontweight="bold", loc="left")
    ax.grid(True, linewidth=0.3, alpha=0.5)
    ax.axhline(0, color="#999999", linewidth=0.6)
    ax.tick_params(labelsize=7)
    # AutoDateLocator, not a fixed "%Y" formatter: the latter labels whatever ticks
    # matplotlib picked, which on a short window repeats the same year several times.
    loc = mdates.AutoDateLocator(minticks=4, maxticks=10)
    ax.xaxis.set_major_locator(loc)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))
    # A 90-entry legend at a readable size would cover the plot it labels, so it shrinks
    # and spreads into columns instead of being dropped -- same principle as the tables.
    if n <= 6:
        ncol, lfont = 1, 6.0
    elif n <= 12:
        ncol, lfont = 2, 5.0
    elif n <= 30:
        ncol, lfont = 3, 3.6
    else:
        ncol, lfont = 4, 2.6
    ax.legend(fontsize=lfont, ncol=ncol, loc="best", framealpha=0.85,
              handlelength=1.4, labelspacing=0.25, columnspacing=0.8,
              borderpad=0.3, handletextpad=0.4)


def _signal_map_text(record: dict) -> str:
    """'which buckets make each signal', straight from cfg -- no computation.

    categories_dict maps {category column -> signal index} and lc_signals maps
    {signal_i -> human name}; inverting the first and labelling with the second IS the
    answer to "what buckets are required to make each signal".
    """
    cfg = record.get("cfg") or {}
    cats = cfg.get("categories_dict") or {}
    names = cfg.get("lc_signals") or {}
    if not cats:
        return ""
    import textwrap

    grouped: dict[int, list[str]] = {}
    for col, idx in cats.items():
        grouped.setdefault(int(idx), []).append(str(col))
    lines = []
    for idx in sorted(grouped):
        label = names.get(f"signal_{idx}", f"signal_{idx}")
        head = f"signal_{idx} ({label}):"
        body = ", ".join(sorted(grouped[idx]))
        # Hard-wrapped rather than relying on matplotlib's wrap=True, which measures
        # against the figure edge and so ignores the panel it was placed in.
        lines.extend(textwrap.wrap(f"{head} {body}", width=118,
                                   subsequent_indent="      "))
    return "\n".join(lines)


def _draw_page_number(fig, page_num: int | None, total: int | None) -> None:
    """Bottom-right page stamp. This number is the join key to the CSV's 'page' column
    (row N <-> page N) -- see build_csv/build_pdf, which both enumerate the same ledger
    in the same order, so the two always agree."""
    if page_num is None:
        return
    label = f"Page {page_num}" + (f" / {total}" if total else "")
    fig.text(0.985, 0.008, label, ha="right", va="bottom", fontsize=9,
             fontweight="bold", color="#444444")


def render_page(record: dict, pdf, page_num: int | None = None, total: int | None = None) -> None:
    """Draw one experiment as a single page and save it into an open PdfPages."""
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec

    fig = plt.figure(figsize=(_PAGE_W, _PAGE_H))
    title = record.get("title") or record.get("experiment") or "(unnamed)"
    fig.suptitle(title, fontsize=19, fontweight="bold", y=0.985)
    subtitle = f"{record.get('experiment', '')}   ·   {record.get('timestamp', '')}"
    if record.get("run_dir"):
        subtitle += f"   ·   {record['run_dir']}"
    fig.text(0.5, 0.962, subtitle, ha="center", fontsize=9, color="#555555")
    _draw_page_number(fig, page_num, total)

    if record.get("status") == "failed":
        fig.text(0.5, 0.5, "RUN FAILED\n\n" + str(record.get("error", ""))[:2000],
                 ha="center", va="center", fontsize=11, color="#b00020", family="monospace")
        pdf.savefig(fig)
        plt.close(fig)
        return

    gs = GridSpec(4, 2, figure=fig, hspace=0.30, wspace=0.10,
                  left=0.025, right=0.985, top=0.935, bottom=0.025,
                  height_ratios=[1.15, 1.0, 1.0, 0.75])
    slots = {
        "signal_breakdown": gs[0, 0], "parameters": gs[0, 1],
        "risk": gs[1, 0], "cumulative": gs[1, 1],
        "spreads": gs[2, 0], "rolling40": gs[2, 1],
        "coverage": gs[3, :],
    }

    payloads = record.get("payloads") or {}
    for slug, _node, _key, panel_title in SECTIONS:
        payload = payloads.get(slug)

        if slug == "signal_breakdown":
            # Two things belong here: the literal signal -> category-column map (which IS
            # "what buckets make each signal") and the describe() stats for those columns.
            # They get their own sub-slots so a long map can never run over the table.
            sub = slots[slug].subgridspec(2, 1, height_ratios=[1.0, 1.35], hspace=0.12)
            ax_map = fig.add_subplot(sub[0])
            ax_map.axis("off")
            ax_map.set_title(panel_title, fontsize=10, fontweight="bold", loc="left")
            mapping = _signal_map_text(record) or "(no categories_dict in cfg)"
            # Same rule as the tables: shrink rather than spill. A 30-signal design needs
            # ~45 wrapped lines here, which at a fixed 6.2pt runs straight over the
            # statistics table below. ~11 lines fit comfortably at 6.2pt in this sub-slot.
            _lines_n = mapping.count("\n") + 1
            ax_map.text(0.0, 1.0, mapping, transform=ax_map.transAxes, va="top",
                        fontsize=max(1.1, min(6.2, 6.2 * 11 / max(_lines_n, 1))),
                        family="monospace", color="#222222", linespacing=1.4)
            _table_panel(fig.add_subplot(sub[1]), payload,
                         "     column statistics")
            continue

        if slug == "parameters":
            # ~60 cfg rows in one half-panel would be unreadably small, so split them
            # across two side-by-side tables -- same rows, roughly double the font.
            # The 'description' column is prose and eats the panel; the value is the point.
            rows = (payload or {}).get("rows") or []
            half = (len(rows) + 1) // 2
            sub = slots[slug].subgridspec(1, 2, wspace=0.06)
            for i, chunk in enumerate((rows[:half], rows[half:])):
                _table_panel(fig.add_subplot(sub[i]), {"rows": chunk},
                             panel_title if i == 0 else "",
                             drop_cols=("description",), cell_chars=44)
            continue

        ax = fig.add_subplot(slots[slug])
        if slug in _LINE_SLUGS:
            _lines_panel(ax, payload, panel_title)
        elif slug == "risk":
            # Green rows = alpha significant at the 10% level, so a page worth a second
            # look is identifiable while flicking through the sweep.
            _table_panel(ax, payload, f"{panel_title}   (green: p-value(alpha) < "
                                      f"{_ALPHA_SIGNIF_P:g})",
                         highlight=_significant_alpha)
        else:
            _table_panel(ax, payload, panel_title)

    pdf.savefig(fig)
    plt.close(fig)


def build_pdf(ledger_path: str | Path, pdf_path: str | Path) -> int:
    """Rebuild the whole multi-page PDF from the ledger. Returns the page count."""
    import matplotlib
    matplotlib.use("Agg")           # no display needed, and safe under nohup/cron
    from matplotlib.backends.backend_pdf import PdfPages

    records = sorted_records(read_ledger(ledger_path))
    pdf_path = Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = pdf_path.with_suffix(".pdf.tmp")

    with PdfPages(tmp) as pdf:
        if not records:
            import matplotlib.pyplot as plt
            fig = plt.figure(figsize=(_PAGE_W, _PAGE_H))
            fig.text(0.5, 0.5, "no experiments in ledger yet", ha="center", fontsize=14)
            pdf.savefig(fig)
            plt.close(fig)
        # Page N = ledger record N (1-based) -- the same enumeration build_csv uses for
        # its 'page' column, so a CSV row always points at the matching PDF page.
        total = len(records)
        for i, rec in enumerate(records, start=1):
            render_page(rec, pdf, page_num=i, total=total)

    os.replace(tmp, pdf_path)       # atomic: the old PDF stays valid until this instant
    return len(records)


# --------------------------------------------------------------------------- #
# CSV export
# --------------------------------------------------------------------------- #
def _row_for(record: dict, page_num: int) -> dict:
    """Flatten one ledger record into one CSV row.

    `page_num` is the same 1-based index build_pdf stamps onto that record's page (both
    enumerate the same ledger, in the same order), so `row["page"] == N` <-> PDF page N.
    """
    cfg = record.get("cfg") or {}
    row: dict = {
        "experiment": record.get("experiment", ""),
        "page": page_num,
        "timestamp": record.get("timestamp", ""),
        "status": record.get("status", ""),
        "run_dir": record.get("run_dir", ""),
        "param_diff": record.get("title", ""),
    }

    payloads = record.get("payloads") or {}

    # Risk-table-derived columns (alpha / p-value per portfolio) -- no Sharpe, by request.
    # BundleTableViz.compute reset_index()es the risk table, so the portfolio label
    # arrives under the literal column name "index" (the parquet calls it "portfolio")
    # -- accept either.
    for r in (payloads.get("risk") or {}).get("rows") or []:
        label = r.get("index") or r.get("portfolio")
        if not label:
            continue
        row[f"alpha__{label}"] = _num(r.get("Alpha"))
        row[f"pval__{label}"] = _num(r.get("p-value(alpha)"))

    for r in (payloads.get("coverage") or {}).get("rows") or []:
        label = r.get("label")
        if label:
            row[f"coverage_pct__{label}"] = _num(r.get("pct_months_at_least_x"))

    # One column per scalar cfg knob.
    for k, v in cfg.items():
        if _is_scalar(v):
            row[k] = v
    # The complete config, containers included, as one cell.
    row["cfg_json"] = json.dumps(cfg, default=str, sort_keys=True)

    if record.get("error"):
        row["error"] = str(record["error"])[:500]
    return row


# Fixed leading (identifying) columns.
_LEAD_COLS = ["experiment", "page", "timestamp", "status", "run_dir", "param_diff"]


def build_csv(ledger_path: str | Path, csv_path: str | Path) -> int:
    """Rebuild results.csv from the ledger. Returns the row count.

    Rebuilt rather than appended precisely because the column set grows: a later
    experiment with a different action_characterization introduces portfolio columns the
    earlier rows never had, and only a full rewrite can take the union safely.

    Column layout, left to right: identifying columns, then the RISK TABLE (alpha /
    p-value / coverage per portfolio -- the run's results), then PARAMETERS (the scalar
    cfg knobs, then the full cfg as one JSON cell) -- results on the left, config on the
    right, matching the PDF page's own layout.
    """
    # Same ordering function build_pdf uses -- row N must describe page N.
    records = sorted_records(read_ledger(ledger_path))
    rows = [_row_for(r, page_num=i) for i, r in enumerate(records, start=1)]

    risk_cols, param_cols = [], []
    for r in rows:
        for k in r:
            if k in _LEAD_COLS or k in ("cfg_json", "error"):
                continue
            bucket = risk_cols if k.startswith(("alpha__", "pval__", "coverage_pct__")) else param_cols
            if k not in bucket:
                bucket.append(k)

    cols = list(_LEAD_COLS) + risk_cols + param_cols
    # cfg_json is wide and unreadable inline -- keep it out of the way at the far right;
    # error (only present on failed rows) goes with it.
    for tail in ("cfg_json", "error"):
        if any(tail in r for r in rows):
            cols.append(tail)

    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = csv_path.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    os.replace(tmp, csv_path)
    return len(rows)
