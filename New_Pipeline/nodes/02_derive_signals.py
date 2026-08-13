"""Derive behavioural signals from the cleaned LC panel.

Node `derive_signals`: reproduces Main.ipynb cells 16, 18, 21 verbatim, reusing
functions/data_functions/process_lc.filter_sum_activities_by_fiscal_year_quantiles
unchanged. Paired with the upstream ``process_lc`` node (cells 4, 14, 15 —
loading + sample selection + industry mapping); this node handles the
signal-engineering half: category aggregation into ``sum_with_<i>``, denominator
choice for ``sum_activities``, the winsor alpha-trim on ``sum_activities`` per
fiscal year, and the ``signal_i = sum_with_i / sum_activities`` ratio.

Splitting the two concerns means you can A/B different signal-construction
methodologies (denominator, alpha-trim, category groupings, additional signal
transforms) without touching the data-ingestion node — the LC input is unchanged.

Output is a lossless (pickle) bundle: ``{lc, lc_raw_for_coverage, sum_activities_outlier_stats,
signal_summary_stats, signal_correlation_matrix, category_column_stats}`` — the last four are
diagnostic tables only (no effect on ``lc`` or downstream nodes), added purely so the dashboard can
audit the signal construction across experiments; same ``lc`` shape as before plus the signal
columns, so downstream (``prepare_panel``) keeps a single lc port.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process

from New_Pipeline._common import cfg_schema, open_schema, store
from New_Pipeline.dashboard_viz import BundleColoredTableViz, BundleHeatmapViz, BundleTableViz


# ---- Dashboard extractors (bundle -> widget payloads; no computation happens here) --- #

def _sum_activities_outlier_stats(bundle):
    """describe() stats for sum_activities, one row per stat, one column per stage
    (before_alpha_bound vs after_alpha_bound) — read left-to-right as a before/after
    comparison of the alpha-bound trim."""
    return bundle["sum_activities_outlier_stats"]


def _signal_summary_stats(bundle):
    """One row per signal_i with its describe() stats — signals compared side by side."""
    return bundle["signal_summary_stats"]


def _signal_correlation_matrix(bundle):
    """Pearson correlation matrix between the behavioural signals."""
    return bundle["signal_correlation_matrix"]


def _category_column_stats(bundle):
    """describe() stats for each raw category column that feeds a signal's sum_with_i
    aggregation — one row per column, tinted by which signal it belongs to."""
    return bundle["category_column_stats"]


CONTRACT = Contract(
    name="derive_signals",
    intent="""Turn the cleaned LC panel into a behavioural-signal panel: aggregate the raw category
columns into ``sum_with_<i>``, pick the ``sum_activities`` denominator (Sum_All_Signals vs
Sum_All_Initiatives), winsor-trim ``sum_activities`` per fiscal year, then set
``signal_i = sum_with_i / sum_activities`` for each category group i. Which categories map to which
group, the denominator, and the trim bound are read from cfg. Sample selection and industry mapping
are NOT redone here — they belong to the upstream ``process_lc`` node.

Mandatory measures (enforced by schema / audits):
- one row per surviving gvkey-fiscal-year with the behavioural signal columns present
- rows only drop via the declared winsor trim

Surfaces: sum_activities summary stats, before vs after the alpha-bound trim side by
side as columns (``BundleTableViz``); per-signal summary statistics compared side by side
(``BundleTableViz``); the signal correlation matrix as a diverging blue/white/red heatmap
(``BundleHeatmapViz``); and descriptive statistics for each raw category column that feeds a
signal's aggregation, one row per column, tinted by which signal it belongs to
(``BundleColoredTableViz``). All four stack/subplot across experiments — the tables via the
dashboard's per-config ``experiment`` column, the heatmap via one subplot per config sharing a
colour scale — when comparing multiple configs.""",
    input_schema={"lc": open_schema(), "cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[
        # Explicit keys are required: BundleTableViz's default key collapses to the
        # literal "table:" for every instance (it always passes columns=[] to
        # SampleTableViz), so multiple unkeyed BundleTableViz on one Contract silently
        # collide in the dashboard's per-node audit_stats dict — only the last one
        # computed survives and gets shown under all the matching widgets.
        BundleTableViz(_sum_activities_outlier_stats,
                       title="sum_activities — before vs after alpha-bound trim",
                       key="table:sum_activities_outlier_stats"),
        BundleTableViz(_signal_summary_stats, title="Signal summary statistics",
                       key="table:signal_summary_stats"),
        BundleHeatmapViz(_signal_correlation_matrix, title="Signal correlation matrix",
                         key="heatmap:signal_correlation_matrix"),
        BundleColoredTableViz(_category_column_stats,
                              title="Category column descriptive statistics (per signal)",
                              color_col="signal",
                              key="colored_table:category_column_stats"),
    ],
)


@process(tag="derive_signals@v1", contract="derive_signals", author="refactor")
def derive_signals_v1(lc, cfg):
    import json

    import pandas as pd

    from functions.data_functions.process_lc import (
        filter_sum_activities_by_fiscal_year_quantiles,
    )
    from New_Pipeline.boundary import pack_obj, unpack_obj

    C = json.loads(cfg["json"][0])
    L = unpack_obj(lc)
    lc_df = L["lc"]

    # ---- cell 16: category aggregation ----------------------------------- #
    categories_dict = C["categories_dict"]  # {category_col: group_int}
    for key, value in categories_dict.items():
        if f"sum_with_{value}" in lc_df.columns:
            lc_df[f"sum_with_{value}"] += lc_df[key]
        else:
            lc_df[f"sum_with_{value}"] = lc_df[key].values

    if C["signal_denominator"] == "Sum_All_Signals":
        lc_df["sum_activities"] = lc_df.loc[:, list(categories_dict.keys())].sum(axis=1)
    elif C["signal_denominator"] == "Sum_All_Initiatives":
        lc_df["sum_activities"] = lc_df["n_predicted_initiatives"]

    print(lc_df["sum_activities"].describe())

    # ---- audit: sum_activities BEFORE the alpha-bound trim ------------------ #
    desc_before = lc_df["sum_activities"].describe()
    # (stage_name, describe() Series) pairs, in display order — the final table gets
    # one column per stage, built at the end once every stage has been captured.
    outlier_stages = [("before_alpha_bound", desc_before)]

    # ---- cell 18: winsor alpha-trim -------------------------------------- #
    if C["use_alpha_bound"]:
        lc_df = filter_sum_activities_by_fiscal_year_quantiles(
            lc_df, lower_exclude=(C["alpha_bound"] / 2), upper_exclude=(C["alpha_bound"] / 2)
        )
    else:
        lower_exclude = 0.2 * 2
        upper_exclude = 0.05 * 2
        lc_df = filter_sum_activities_by_fiscal_year_quantiles(
            lc_df, lower_exclude=(lower_exclude / 2), upper_exclude=(upper_exclude / 2)
        )

    print(lc_df["sum_activities"].describe())

    # ---- audit: sum_activities AFTER the alpha-bound trim ------------------- #
    desc_after = lc_df["sum_activities"].describe()
    outlier_stages.append(("after_alpha_bound", desc_after))

    # Wide table: one row per stat, one column per stage (in the order captured above).
    # describe() always emits the same stat index (count/mean/std/min/25%/50%/75%/max)
    # regardless of the data, so aligning by position across stages is safe.
    sum_activities_outlier_stats = pd.DataFrame({"stat": outlier_stages[0][1].index})
    for stage_name, desc in outlier_stages:
        sum_activities_outlier_stats[stage_name] = desc.values

    # ---- cell 21: signal_i ----------------------------------------------- #
    max_category = max(int(v) for v in categories_dict.values())
    signal_cols = [f"signal_{i}" for i in range(max_category + 1)]
    for i in range(max_category + 1):
        lc_df[f"signal_{i}"] = lc_df[f"sum_with_{i}"] / lc_df["sum_activities"]

    # Human-readable label per signal column (e.g. "signal_2" -> "transformation"), from
    # cfg.lc_signals — the same {column: name} mapping used to name portfolios downstream
    # (functions/portfolio_strategy_design/univariate_sorting_preprocess.py). Generalised
    # over any action_characterization; falls back to the raw column name if unmapped
    # (e.g. under esg_full_universe, where lc_signals is emptied). Only the AUDIT tables
    # below are relabelled — lc_df keeps signal_i column names, required downstream.
    signal_label = {c: C.get("lc_signals", {}).get(c, c) for c in signal_cols}

    # ---- audit: per-signal summary stats, compared side by side ------------- #
    signal_summary_stats = lc_df[signal_cols].describe().T.reset_index(names="signal")
    signal_summary_stats["signal"] = signal_summary_stats["signal"].map(signal_label)

    # ---- audit: signal correlation matrix ------------------------------------ #
    signal_correlation_matrix = (
        lc_df[signal_cols].corr(method="pearson")
        .rename(index=signal_label, columns=signal_label)
        .reset_index(names="signal")
    )

    # ---- audit: per-raw-column stats, grouped/tinted by which signal they feed ------ #
    category_cols = list(categories_dict.keys())
    category_column_stats = lc_df[category_cols].describe().T.reset_index(names="column")
    category_column_stats.insert(0, "signal", category_column_stats["column"].map(
        lambda c: signal_label.get(f"signal_{categories_dict[c]}", str(categories_dict[c]))
    ))
    # Sort by signal so same-tint rows are contiguous (stable within a signal, so the
    # categories_dict declaration order is preserved inside each block).
    category_column_stats = category_column_stats.sort_values("signal", kind="stable").reset_index(drop=True)

    # Carry lc_raw_for_coverage forward untouched so esg_coverage can still read
    # from this node if the topology is later rewired to consume derive_signals'
    # output. Today only process_lc feeds esg_coverage — see registry.EDGES.
    return pack_obj({
        "lc": lc_df,
        "lc_raw_for_coverage": L.get("lc_raw_for_coverage"),
        "sum_activities_outlier_stats": sum_activities_outlier_stats,
        "signal_summary_stats": signal_summary_stats,
        "signal_correlation_matrix": signal_correlation_matrix,
        "category_column_stats": category_column_stats,
    })


NODE = Node(
    name="derive_signals",
    contract=CONTRACT,
    store=store,
    inputs=("lc", "cfg"),
    outputs=("out",),
)
