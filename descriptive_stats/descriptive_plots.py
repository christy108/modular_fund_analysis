"""
Descriptive plots for the GOLDEN (LC) sustainability-initiative dataset.

Each function takes the `lc` DataFrame (with `signal_0..signal_n` already added the
same way as in Main.ipynb) and returns ``(fig, data, stats)``:
  * ``fig``   - the matplotlib figure, optionally saved to ``save_path``
  * ``data``  - the underlying numeric table, optionally written to ``excel_path``
  * ``stats`` - sample descriptives (unique gvkeys / gvkey-year observations / total
    initiatives) for the rows that plot actually used, also drawn as a caption on the
    figure and written to a ``descriptives`` sheet alongside ``data``

``stats`` describes each plot's EFFECTIVE sample, which is not always the frame passed in:
``plot_signal_shares_by_sector`` drops rows with a missing sector and applies ``min_obs``,
so its counts come out below the other two.

Plots
-----
1. ``plot_firms_and_initiatives``   - unique companies + total initiatives over time (dual axis)
2. ``plot_signal_shares_over_time`` - average behavioural-bucket shares per year (100% stacked bars)
3. ``plot_signal_shares_by_sector`` - average behavioural-bucket shares per sector (horizontal 100% bars)
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# One colour per behavioural bucket, reused across every plot in this module.
SIGNAL_COLORS = {
    "advocacy": "#2E5FA3",        # blue
    "preparation": "#6A3D9A",     # purple
    "transformation": "#1B9E62",  # green
    "innovation": "#E8A33D",      # amber (only used if a 4th bucket exists)
}
_FALLBACK_COLORS = ["#2E5FA3", "#6A3D9A", "#1B9E62", "#E8A33D", "#D62728", "#17BECF"]


def _signal_columns(lc: pd.DataFrame, signal_names: dict[str, str]) -> list[str]:
    """Signal columns present in `lc`, in signal_0, signal_1, ... order."""
    cols = [c for c in signal_names if c in lc.columns]
    if not cols:
        raise ValueError(
            "None of the signal columns were found in lc. Run the signal-definition "
            f"cell first (looked for: {list(signal_names)})."
        )
    return sorted(cols, key=lambda c: int(c.rsplit("_", 1)[1]))


def _colors_for(labels: list[str]) -> list[str]:
    return [
        SIGNAL_COLORS.get(str(lab).lower(), _FALLBACK_COLORS[i % len(_FALLBACK_COLORS)])
        for i, lab in enumerate(labels)
    ]


# --------------------------------------------------------------------------- #
# Sample descriptives (shared by every plot)
# --------------------------------------------------------------------------- #
def sample_descriptives(
    df: pd.DataFrame,
    *,
    year_col: str = "rfyear",
    gvkey_col: str = "gvkey",
    initiatives_col: str = "n_predicted_initiatives",
) -> pd.DataFrame:
    """One-row frame: unique gvkeys, unique gvkey-year observations, total initiatives.

    ``gvkey_year_obs`` counts DISTINCT ``(gvkey, year)`` pairs rather than rows, so it stays
    correct if the frame ever carries duplicate firm-years. Today the two agree (LC holds one
    row per firm-year), which is why the plots show ``unique_companies ==
    firm_year_observations`` in every year.
    """
    return pd.DataFrame([{
        "unique_gvkeys": df[gvkey_col].nunique(),
        "gvkey_year_obs": len(df[[gvkey_col, year_col]].drop_duplicates()),
        "total_initiatives": int(df[initiatives_col].sum()),
    }])


def _descriptives_caption(stats: pd.DataFrame) -> str:
    """Single-line figure caption summarising the sample the plot was built on."""
    row = stats.iloc[0]
    return (
        f"Unique firms: {row['unique_gvkeys']:,}    |    "
        f"Firm-year observations: {row['gvkey_year_obs']:,}    |    "
        f"Total initiatives: {row['total_initiatives']:,}"
    )


def _add_caption(fig, stats: pd.DataFrame) -> None:
    """Reserve a strip at the bottom of the figure and write the descriptives caption there.

    Called after the plot's own ``tight_layout()``; ``bbox_inches="tight"`` at save time picks
    the text up even when the inline preview crops it.
    """
    fig.tight_layout(rect=[0, 0.05, 1, 1])
    fig.text(
        0.5, 0.012, _descriptives_caption(stats),
        ha="center", va="bottom", fontsize=9, color="#444444",
    )


def _save(
    fig,
    data: pd.DataFrame,
    save_path,
    excel_path,
    sheet_name: str,
    stats: pd.DataFrame | None = None,
) -> None:
    """Write the figure and/or the numeric table (plus descriptives) to disk."""
    if save_path is not None:
        out = Path(save_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=200, bbox_inches="tight")
        print(f"[plot] saved {out}")
    if excel_path is not None:
        out = Path(excel_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        # ExcelWriter (not data.to_excel) so the descriptives land in the same workbook.
        with pd.ExcelWriter(out) as xl:
            data.to_excel(xl, sheet_name=sheet_name)
            if stats is not None:
                stats.to_excel(xl, sheet_name="descriptives", index=False)
        print(f"[data] saved {out}")


# --------------------------------------------------------------------------- #
# 1. Unique companies + total initiatives over time
# --------------------------------------------------------------------------- #
def plot_firms_and_initiatives(
    lc: pd.DataFrame,
    *,
    year_col: str = "rfyear",
    gvkey_col: str = "gvkey",
    initiatives_col: str = "n_predicted_initiatives",
    title: str = "Unique Companies and Total Initiatives Over Time",
    save_path: str | Path | None = None,
    excel_path: str | Path | None = None,
    figsize: tuple[float, float] = (10, 5.5),
    show: bool = True,
):
    """Firm-year observations (unique companies) and total initiatives, by fiscal year."""
    data = (
        lc.groupby(year_col)
        .agg(
            unique_companies=(gvkey_col, "nunique"),
            firm_year_observations=(gvkey_col, "size"),
            total_initiatives=(initiatives_col, "sum"),
        )
        .sort_index()
    )
    # Effective sample = the whole frame; this plot drops nothing.
    stats = sample_descriptives(
        lc, year_col=year_col, gvkey_col=gvkey_col, initiatives_col=initiatives_col
    )

    fig, ax_left = plt.subplots(figsize=figsize)
    ax_right = ax_left.twinx()

    # Plot against evenly-spaced positions, not the year values themselves (the other two
    # plots are categorical too). On an unfiltered frame a single corrupt year — the raw
    # Golden file contains an rfyear of 203 — would otherwise stretch the axis over
    # centuries and squash every real year into one unreadable spike. For a contiguous
    # run of years this renders identically to plotting the values.
    positions = list(range(len(data.index)))

    c_left, c_right = "#2E5FA3", "#C0392B"
    ax_left.plot(
        positions, data["unique_companies"],
        marker="o", markersize=5, linewidth=2.2, color=c_left,
        label="Unique Companies (left)",
    )
    ax_right.plot(
        positions, data["total_initiatives"],
        marker="o", markersize=5, linewidth=2.2, color=c_right, linestyle="--",
        label="Total Initiatives (right)",
    )

    ax_left.set_xlabel("Year")
    ax_left.set_ylabel("Unique Companies", color=c_left, fontweight="bold")
    ax_right.set_ylabel("Total Initiatives", color=c_right, fontweight="bold")
    ax_left.tick_params(axis="y", labelcolor=c_left)
    ax_right.tick_params(axis="y", labelcolor=c_right)
    ax_left.set_xticks(positions)
    ax_left.set_xticklabels([str(y) for y in data.index], rotation=45)
    ax_left.grid(True, axis="y", alpha=0.3)
    ax_left.set_axisbelow(True)
    ax_left.set_title(title, fontweight="bold")

    handles = ax_left.get_lines() + ax_right.get_lines()
    ax_left.legend(
        handles, [h.get_label() for h in handles],
        loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2, frameon=False,
    )
    fig.tight_layout()
    _add_caption(fig, stats)

    _save(fig, data, save_path, excel_path, "firms_and_initiatives", stats)
    plt.show() if show else plt.close(fig)
    return fig, data, stats


# --------------------------------------------------------------------------- #
# 2. Average behavioural-bucket shares over time (100% stacked bars)
# --------------------------------------------------------------------------- #
def plot_signal_shares_over_time(
    lc: pd.DataFrame,
    signal_names: dict[str, str],
    *,
    year_col: str = "rfyear",
    gvkey_col: str = "gvkey",
    initiatives_col: str = "n_predicted_initiatives",
    title: str | None = None,
    save_path: str | Path | None = None,
    excel_path: str | Path | None = None,
    figsize: tuple[float, float] = (12, 6),
    min_label_pct: float = 3.0,
    show_change: bool = True,
    show: bool = True,
):
    """
    Average behavioural-bucket share per fiscal year, as 100% stacked bars.

    Each bar is one year; segment heights are the cross-firm mean of `signal_i`
    (shares that sum to 1 per firm-year). When `show_change` is True the relative
    change in each bucket's share between the first and last year is annotated on
    the right, matching the report figure.
    """
    cols = _signal_columns(lc, signal_names)
    labels = [signal_names[c] for c in cols]

    # groupby().mean() skips NaN, so rows with no signal (sum_activities == 0 -> 0/0)
    # contribute to nothing plotted. Count the rows that actually reach the bars.
    stats = sample_descriptives(
        lc.dropna(subset=cols),
        year_col=year_col, gvkey_col=gvkey_col, initiatives_col=initiatives_col,
    )

    data = lc.groupby(year_col)[cols].mean().sort_index() * 100.0
    data.columns = labels
    # Renormalise so each year sums to exactly 100% (guards against NaN signals).
    data = data.div(data.sum(axis=1), axis=0) * 100.0

    fig, ax = plt.subplots(figsize=figsize)
    years = [str(y) for y in data.index]
    colors = _colors_for(labels)

    bottom = pd.Series(0.0, index=data.index)
    for label, color in zip(labels, colors):
        vals = data[label]
        ax.bar(years, vals, bottom=bottom, color=color, label=label, width=0.72)
        for x, (v, b) in enumerate(zip(vals, bottom)):
            if v >= min_label_pct:
                ax.text(
                    x, b + v / 2, f"{v:.0f}%",
                    ha="center", va="center", fontsize=9, color="white", fontweight="bold",
                )
        bottom += vals

    # Relative change in each bucket's share, first year -> last year.
    if show_change and len(data) >= 2:
        first, last = data.iloc[0], data.iloc[-1]
        mid = last.cumsum() - last / 2.0
        for label in labels:
            pct = (last[label] - first[label]) / first[label] * 100.0 if first[label] else 0.0
            face = "#DFF3E4" if pct > 0 else ("#FBE3E3" if pct < 0 else "#EDEDED")
            edge = "#1B9E62" if pct > 0 else ("#C0392B" if pct < 0 else "#999999")
            ax.annotate(
                f"{pct:+.1f}%",
                xy=(len(years) - 0.6, mid[label]), xytext=(len(years) + 0.15, mid[label]),
                va="center", ha="left", fontsize=9, fontweight="bold", color=edge,
                bbox=dict(boxstyle="round,pad=0.3", facecolor=face, edgecolor=edge, linewidth=0.8),
                annotation_clip=False,
            )

    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.set_xlim(-0.6, len(years) + 1.2 if show_change else len(years) - 0.4)
    ax.set_ylabel("Share of initiatives")
    plt.setp(ax.get_xticklabels(), rotation=45)
    ax.grid(True, axis="y", alpha=0.3)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    if title:
        ax.set_title(title, fontweight="bold")
    ax.legend(
        loc="lower center", bbox_to_anchor=(0.5, 1.02),
        ncol=len(labels), frameon=False,
    )
    fig.tight_layout()
    _add_caption(fig, stats)

    _save(fig, data, save_path, excel_path, "signal_shares_over_time", stats)
    plt.show() if show else plt.close(fig)
    return fig, data, stats


# --------------------------------------------------------------------------- #
# 3. Average behavioural-bucket shares by sector (horizontal 100% bars)
# --------------------------------------------------------------------------- #
def plot_signal_shares_by_sector(
    lc: pd.DataFrame,
    signal_names: dict[str, str],
    *,
    sector_col: str = "GICS_level_1",
    year_col: str = "rfyear",
    gvkey_col: str = "gvkey",
    initiatives_col: str = "n_predicted_initiatives",
    title: str | None = None,
    save_path: str | Path | None = None,
    excel_path: str | Path | None = None,
    figsize: tuple[float, float] = (12, 7),
    min_label_pct: float = 3.0,
    min_obs: int = 1,
    show: bool = True,
):
    """
    Average behavioural-bucket share per sector, as horizontal 100% stacked bars.

    Sectors are listed alphabetically (top to bottom), matching the report figure.
    `min_obs` drops sectors with fewer than that many firm-year observations.
    """
    cols = _signal_columns(lc, signal_names)
    labels = [signal_names[c] for c in cols]

    df = lc.dropna(subset=[sector_col])
    counts = df.groupby(sector_col)[cols[0]].size()
    keep = counts[counts >= min_obs].index

    # This plot's sample is genuinely smaller than the frame it was handed: rows with no
    # sector are dropped above, sectors below min_obs are excluded, and groupby().mean()
    # skips rows with no signal. Count what actually reaches the bars.
    stats = sample_descriptives(
        df[df[sector_col].isin(keep)].dropna(subset=cols),
        year_col=year_col, gvkey_col=gvkey_col, initiatives_col=initiatives_col,
    )

    data = df[df[sector_col].isin(keep)].groupby(sector_col)[cols].mean() * 100.0
    data.columns = labels
    data = data.div(data.sum(axis=1), axis=0) * 100.0
    data = data.sort_index(ascending=False)          # alphabetical top -> bottom
    data["n_obs"] = counts.reindex(data.index).values

    fig, ax = plt.subplots(figsize=figsize)
    sectors = list(data.index)
    colors = _colors_for(labels)

    left = pd.Series(0.0, index=data.index)
    for label, color in zip(labels, colors):
        vals = data[label]
        ax.barh(sectors, vals, left=left, color=color, label=label, height=0.72)
        for y, (v, l) in enumerate(zip(vals, left)):
            if v >= min_label_pct:
                ax.text(
                    l + v / 2, y, f"{v:.0f}%",
                    ha="center", va="center", fontsize=9, color="white", fontweight="bold",
                )
        left += vals

    ax.set_xlim(0, 100)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.set_xlabel("Share of initiatives")
    ax.grid(True, axis="x", alpha=0.3)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    if title:
        ax.set_title(title, fontweight="bold")
    ax.legend(
        loc="lower center", bbox_to_anchor=(0.5, 1.02),
        ncol=len(labels), frameon=False,
    )
    fig.tight_layout()
    _add_caption(fig, stats)

    _save(fig, data, save_path, excel_path, "signal_shares_by_sector", stats)
    plt.show() if show else plt.close(fig)
    return fig, data, stats
