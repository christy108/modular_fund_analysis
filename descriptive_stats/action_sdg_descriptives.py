"""
Action x SDG-group descriptive statistics for the GOLDEN (LC) sustainability-initiative
dataset, as matched to SASB materiality.

Showing how initiatives split across the three behavioural actions
-- advocacy, preparation, transformation -- within four SDG groups:

    * All SDGs            (1..17)
    * People             (1, 2, 3, 4, 5, 8, 10)
    * People + Prosperity (People + 9, 11, 16, 17)
    * Planet             (6, 7, 12, 13, 14, 15)

as COUNTS, as PERCENTAGES (action share within each SDG group), and OVER TIME (by rfyear).

Total initiatives for an (action, SDG) = the sum over the three states. Summing those over
the SDGs in a group gives the group's count for that action.

Outputs 
    fig1_action_split_counts.png        grouped bars: counts by action across the 4 groups
    fig2_action_split_pct.png           100% stacked bars: action share within each group
    fig3_action_share_over_time.png     2x2 panels: action share by rfyear, per group
    fig4_action_counts_over_time.png    2x2 panels: action counts by rfyear, per group
    action_sdg_descriptives.xlsx        backing tables (+ sample descriptives + README)

"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: write files, never pop a window
import matplotlib.pyplot as plt
import pandas as pd

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
# Default input: the matched materiality file. Overridable via --input or the
# MATERIALITY_FILE / MATERIALITY_LOCATION environment variables (same convention the alpha pipeline uses).
_DEFAULT_MATCHED_NAME = (
    "Matched_SASB_GOLDEN_long_matchings_v_2A1_FirmYear_17SDGs_matching_v2.csv"
)

# Display name -> column stem in the matched file. "advocacy / preparation / transformation" is the 3-way "Matteo" split, whose advocacy column is advocacy_old_def.
ACTIONS: dict[str, str] = {
    "advocacy": "advocacy_old_def",
    "preparation": "preparation",
    "transformation": "transformation",
}

# States summed to get "all initiatives" for an (action, SDG). Set to ["material", "immaterial"] to describe only the classified (non-unmapped) subset.
STATES = ["material", "immaterial", "unmapped"]

# One colour per action, matching descriptive_stats/descriptive_plots.py so every descriptive figure in the code base uses the same palette.
ACTION_COLORS = {
    "advocacy": "#2E5FA3",       # blue
    "preparation": "#6A3D9A",    # purple
    "transformation": "#1B9E62", # green
}

# rfyear window for the over-time panels (headline counts/% use ALL years in the file).
YEAR_MIN, YEAR_MAX = 2010, 2024

GVKEY_COL, YEAR_COL = "gvkey", "rfyear"


def _sdg_groups() -> dict[str, list[int]]:
    """The four SDG groups, pulled from signal_definitions when importable."""
    try:
        from functions.signal_design.signal_definitions import PEOPLE_PLANET_PROSPERITY as P
    except Exception:  # standalone fallback — kept identical to signal_definitions.py
        P = {
            "People": [1, 2, 3, 4, 5, 8, 10],
            "Prosperity": [9, 11, 16, 17],
            "Planet": [6, 7, 12, 13, 14, 15],
        }
    return {
        "All SDGs": list(range(1, 18)),
        "People": list(P["People"]),
        "People + Prosperity": list(P["People"]) + list(P["Prosperity"]),
        "Planet": list(P["Planet"]),
    }


# --------------------------------------------------------------------------- #
# Core computation
# --------------------------------------------------------------------------- #
def _cols_for(df: pd.DataFrame, action_stem: str, sdgs: list[int]) -> list[str]:
    """Existing {state}__{action}__SDG_{n} columns for one action over a set of SDGs."""
    wanted = {
        f"{state}__{action_stem}__SDG_{n}" for state in STATES for n in sdgs
    }
    return [c for c in df.columns if c in wanted]


def action_series(df: pd.DataFrame, action_stem: str, sdgs: list[int]) -> pd.Series:
    """Per-firm-year total initiatives for one action within an SDG set."""
    cols = _cols_for(df, action_stem, sdgs)
    if not cols:
        return pd.Series(0, index=df.index, dtype="float64")
    return df[cols].sum(axis=1)


def build_split_table(df: pd.DataFrame, groups: dict[str, list[int]]) -> pd.DataFrame:
    """Pooled count and within-group % per (SDG group, action)."""
    rows = []
    for gname, sdgs in groups.items():
        counts = {a: float(action_series(df, stem, sdgs).sum()) for a, stem in ACTIONS.items()}
        tot = sum(counts.values())
        for a in ACTIONS:
            rows.append(
                {
                    "sdg_group": gname,
                    "action": a,
                    "count": counts[a],
                    "pct_within_group": (100.0 * counts[a] / tot) if tot else 0.0,
                }
            )
    return pd.DataFrame(rows)


def build_time_table(df: pd.DataFrame, groups: dict[str, list[int]]) -> pd.DataFrame:
    """Per-rfyear count and within-group % per (SDG group, action)."""
    frames = []
    for gname, sdgs in groups.items():
        per = pd.DataFrame({a: action_series(df, stem, sdgs) for a, stem in ACTIONS.items()})
        per[YEAR_COL] = df[YEAR_COL].values
        agg = per.groupby(YEAR_COL)[list(ACTIONS)].sum()
        agg = agg[(agg.index >= YEAR_MIN) & (agg.index <= YEAR_MAX)]
        agg = agg[agg.sum(axis=1) > 0]  # drop empty years
        pct = agg.div(agg.sum(axis=1), axis=0) * 100.0
        for yr in agg.index:
            for a in ACTIONS:
                frames.append(
                    {
                        "sdg_group": gname,
                        YEAR_COL: int(yr),
                        "action": a,
                        "count": float(agg.loc[yr, a]),
                        "pct_within_group": float(pct.loc[yr, a]),
                    }
                )
    return pd.DataFrame(frames)


def sample_descriptives(df: pd.DataFrame) -> pd.DataFrame:
    """Unique gvkeys, distinct (gvkey, rfyear) obs, and total initiatives in the file."""
    total = 0.0
    for stem in ACTIONS.values():
        total += action_series(df, stem, list(range(1, 18))).sum()
    return pd.DataFrame(
        [
            {
                "unique_gvkeys": int(df[GVKEY_COL].nunique()),
                "gvkey_year_obs": int(df[[GVKEY_COL, YEAR_COL]].drop_duplicates().shape[0]),
                "total_initiatives_3_actions": int(total),
            }
        ]
    )


# --------------------------------------------------------------------------- #
# Plots
# --------------------------------------------------------------------------- #
def _style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": 150,
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.titleweight": "bold",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.25,
        }
    )


def _caption(fig, stats: pd.DataFrame) -> None:
    s = stats.iloc[0]
    fig.text(
        0.01,
        0.01,
        f"Sample: {s['unique_gvkeys']:,} firms · {s['gvkey_year_obs']:,} firm-years · "
        f"{s['total_initiatives_3_actions']:,} initiatives (advocacy+preparation+transformation)",
        fontsize=8,
        color="#666666",
    )


def plot_counts(split: pd.DataFrame, stats: pd.DataFrame, save_path: Path):
    _style()
    groups = list(dict.fromkeys(split["sdg_group"]))
    actions = list(ACTIONS)
    piv = split.pivot(index="sdg_group", columns="action", values="count").loc[groups, actions]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    import numpy as np

    x = np.arange(len(groups))
    w = 0.26
    for i, a in enumerate(actions):
        bars = ax.bar(x + (i - 1) * w, piv[a].values, w, label=a, color=ACTION_COLORS[a])
        ax.bar_label(bars, fmt="%.0f", fontsize=8, padding=2, rotation=0)
    ax.set_xticks(x)
    ax.set_xticklabels(groups)
    ax.set_ylabel("Number of initiatives")
    ax.set_title("Initiative counts by action, per SDG group")
    ax.legend(title="Action", frameon=False)
    _caption(fig, stats)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(save_path)
    plt.close(fig)


def plot_pct(split: pd.DataFrame, stats: pd.DataFrame, save_path: Path):
    _style()
    groups = list(dict.fromkeys(split["sdg_group"]))
    actions = list(ACTIONS)
    piv = split.pivot(index="sdg_group", columns="action", values="pct_within_group").loc[groups, actions]
    fig, ax = plt.subplots(figsize=(9, 5))
    left = [0.0] * len(groups)
    for a in actions:
        vals = piv[a].values
        bars = ax.barh(groups, vals, left=left, color=ACTION_COLORS[a], label=a)
        for bar, v, l in zip(bars, vals, left):
            if v >= 4:
                ax.text(l + v / 2, bar.get_y() + bar.get_height() / 2, f"{v:.0f}%",
                        ha="center", va="center", color="white", fontsize=9, fontweight="bold")
        left = [l + v for l, v in zip(left, vals)]
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of initiatives within SDG group (%)", labelpad=6)
    ax.set_title("Action mix within each SDG group (100% stacked)")
    ax.invert_yaxis()
    ax.legend(title=None, frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.16))
    _caption(fig, stats)
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    fig.savefig(save_path)
    plt.close(fig)


def _panels(time_tbl: pd.DataFrame, value: str, title: str, ylabel: str,
            stats: pd.DataFrame, save_path: Path):
    _style()
    groups = list(dict.fromkeys(time_tbl["sdg_group"]))
    actions = list(ACTIONS)
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
    for ax, g in zip(axes.ravel(), groups):
        sub = time_tbl[time_tbl["sdg_group"] == g]
        wide = sub.pivot(index=YEAR_COL, columns="action", values=value).reindex(columns=actions).fillna(0)
        ax.stackplot(wide.index, [wide[a].values for a in actions],
                     labels=actions, colors=[ACTION_COLORS[a] for a in actions], alpha=0.9)
        ax.set_title(g)
        ax.set_ylabel(ylabel)
        if value == "pct_within_group":
            ax.set_ylim(0, 100)
    axes[0, 0].legend(title="Action", frameon=False, loc="upper left", fontsize=9)
    fig.suptitle(title, fontsize=14, fontweight="bold")
    _caption(fig, stats)
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    fig.savefig(save_path)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def _resolve_input(cli_input: str | None) -> Path:
    if cli_input:
        return Path(cli_input)
    env = os.environ.get("MATERIALITY_FILE")
    if env:
        return Path(env)
    loc = os.environ.get("MATERIALITY_LOCATION")
    if loc:
        return Path(loc) / _DEFAULT_MATCHED_NAME
    return Path(_DEFAULT_MATCHED_NAME)


def run(input_file: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(input_file) if input_file.suffix == ".csv" else pd.read_parquet(input_file)
    for col in (GVKEY_COL, YEAR_COL):
        if col not in df.columns:
            raise ValueError(f"Expected column '{col}' not found in {input_file}")

    groups = _sdg_groups()
    split = build_split_table(df, groups)
    time_tbl = build_time_table(df, groups)
    stats = sample_descriptives(df)

    # figures 
    plot_counts(split, stats, out_dir / "fig1_action_split_counts.png")
    plot_pct(split, stats, out_dir / "fig2_action_split_pct.png")
    _panels(time_tbl, "pct_within_group", "Action share over time, per SDG group",
            "Share (%)", stats, out_dir / "fig3_action_share_over_time.png")
    _panels(time_tbl, "count", "Action counts over time, per SDG group",
            "Initiatives", stats, out_dir / "fig4_action_counts_over_time.png")

    # tables 
    readme = pd.DataFrame(
        {
            "field": ["source_file", "actions", "states_summed", "sdg_groups", "year_window_over_time"],
            "value": [
                str(input_file.name),
                ", ".join(f"{k} -> {v}" for k, v in ACTIONS.items()),
                ", ".join(STATES),
                "; ".join(f"{k}: {v}" for k, v in groups.items()),
                f"{YEAR_MIN}-{YEAR_MAX}",
            ],
        }
    )
    xlsx = out_dir / "action_sdg_descriptives.xlsx"
    with pd.ExcelWriter(xlsx) as xw:
        split.to_excel(xw, sheet_name="split_counts_pct", index=False)
        time_tbl.to_excel(xw, sheet_name="over_time", index=False)
        stats.to_excel(xw, sheet_name="descriptives", index=False)
        readme.to_excel(xw, sheet_name="README", index=False)

    print(f"[action_sdg_descriptives] wrote 4 figures + {xlsx.name} to {out_dir}")
    print(split.pivot(index="sdg_group", columns="action", values="pct_within_group").round(1).to_string())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", help="Matched materiality CSV/Parquet (default: env or cwd)")
    ap.add_argument("--out", help="Output directory",
                    default=str(Path(__file__).resolve().parent / "outputs" / "action_sdg_splits"))
    args = ap.parse_args()
    run(_resolve_input(args.input), Path(args.out))


if __name__ == "__main__":
    main()
