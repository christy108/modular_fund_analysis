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
signal_summary_stats, signal_correlation_matrix}`` — the last three are diagnostic tables only
(no effect on ``lc`` or downstream nodes), added purely so the dashboard can audit the signal
construction across experiments; same ``lc`` shape as before plus the signal columns, so
downstream (``prepare_panel``) keeps a single lc port.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process

from New_Pipeline._common import cfg_schema, open_schema, store
from New_Pipeline.dashboard_viz import BundleHeatmapViz, BundleTableViz


# ---- Dashboard extractors (bundle -> widget payloads; no computation happens here) --- #

def _sum_activities_outlier_stats(bundle):
    """describe() stats for sum_activities, one row per stat, one column per stage
    (before_outlier_control vs after_alpha_bound_filter/after_winsorize, depending on
    cfg.winsorize_outliers) — read left-to-right as a before/after comparison."""
    return bundle["sum_activities_outlier_stats"]


def _signal_summary_stats(bundle):
    """One row per signal_i with its describe() stats — signals compared side by side."""
    return bundle["signal_summary_stats"]


def _signal_correlation_matrix(bundle):
    """Pearson correlation matrix between the behavioural signals."""
    return bundle["signal_correlation_matrix"]


CONTRACT = Contract(
    name="derive_signals",
    intent="""Turn the cleaned LC panel into a behavioural-signal panel: aggregate the raw category
columns into ``sum_with_<i>``, pick the ``sum_activities`` denominator (Sum_All_Signals vs
Sum_All_Initiatives), apply a per-fiscal-year outlier control to ``sum_activities``, then set
``signal_i = sum_with_i / sum_activities`` for each category group i. The outlier control is one of
two mutually-exclusive methods (never both — build_cfg() and the process both refuse the combination):
DROP rows outside ``cfg.alpha_bound`` when ``cfg.use_alpha_bound=True`` (default, notebook-identical),
or CAP values at ``cfg.winsorize_bound`` (its own independent number, not derived from alpha_bound)
when ``cfg.winsorize_outliers=True`` — same sample size every config, no attrition. Which categories
map to which group, the denominator, and both trim bounds are read from cfg. Sample selection and
industry mapping are NOT redone here — they belong to the upstream ``process_lc`` node.

Mandatory measures (enforced by schema / audits):
- one row per surviving gvkey-fiscal-year with the behavioural signal columns present
- rows only drop via the declared winsor trim

Surfaces: sum_activities summary stats, before vs after the alpha-bound outlier control side by
side as columns (``BundleTableViz``); per-signal summary statistics compared side by side
(``BundleTableViz``); the signal correlation matrix as a diverging blue/white/red heatmap
(``BundleHeatmapViz``). All three stack/subplot across experiments — the two tables via the
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
                       title="sum_activities — before vs after outlier control",
                       key="table:sum_activities_outlier_stats"),
        BundleTableViz(_signal_summary_stats, title="Signal summary statistics",
                       key="table:signal_summary_stats"),
        BundleHeatmapViz(_signal_correlation_matrix, title="Signal correlation matrix",
                         key="heatmap:signal_correlation_matrix"),
    ],
)


@process(tag="derive_signals@v1", contract="derive_signals", author="refactor")
def derive_signals_v1(lc, cfg):
    import json

    import pandas as pd

    from functions.data_functions.process_lc import (
        filter_sum_activities_by_fiscal_year_quantiles,
        winsorize_sum_activities_by_fiscal_year_quantiles,
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

    # ---- audit: sum_activities BEFORE outlier control ---------------------- #
    desc_before = lc_df["sum_activities"].describe()
    # (stage_name, describe() Series) pairs, in display order — the final table gets
    # one column per stage, built at the end once every stage has been captured.
    outlier_stages = [("before_outlier_control", desc_before)]

    # ---- cell 18: per-year outlier control on sum_activities ---------------- #
    # Two entirely separate methods, both rfyear-grouped-quantile-based, but never
    # combined: `use_alpha_bound` (DROP rows outside cfg.alpha_bound, notebook-identical)
    # vs `winsorize_outliers` (CAP values at cfg.winsorize_bound — its own number, not
    # derived from alpha_bound). build_cfg() already refuses to set both True; re-check
    # here too since cfg is data a caller could hand-build without going through it.
    winsorize_outliers = C.get("winsorize_outliers", False)
    if C["use_alpha_bound"] and winsorize_outliers:
        raise ValueError(
            "cfg.use_alpha_bound and cfg.winsorize_outliers are separate outlier-control "
            "methods (drop vs cap) and cannot both be True."
        )

    if winsorize_outliers:
        wb = C["winsorize_bound"]
        lc_df = winsorize_sum_activities_by_fiscal_year_quantiles(
            lc_df, lower_exclude=wb / 2, upper_exclude=wb / 2
        )
        after_stage_name = "after_winsorize"
    else:
        if C["use_alpha_bound"]:
            lower_exclude, upper_exclude = C["alpha_bound"] / 2, C["alpha_bound"] / 2
        else:
            lower_exclude, upper_exclude = 0.2, 0.05
        lc_df = filter_sum_activities_by_fiscal_year_quantiles(
            lc_df, lower_exclude=lower_exclude, upper_exclude=upper_exclude
        )
        after_stage_name = "after_alpha_bound_filter"

    print(lc_df["sum_activities"].describe())

    # ---- audit: sum_activities AFTER outlier control ------------------------ #
    desc_after = lc_df["sum_activities"].describe()
    outlier_stages.append((after_stage_name, desc_after))

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

    # Carry lc_raw_for_coverage forward untouched so esg_coverage can still read
    # from this node if the topology is later rewired to consume derive_signals'
    # output. Today only process_lc feeds esg_coverage — see registry.EDGES.
    return pack_obj({
        "lc": lc_df,
        "lc_raw_for_coverage": L.get("lc_raw_for_coverage"),
        "sum_activities_outlier_stats": sum_activities_outlier_stats,
        "signal_summary_stats": signal_summary_stats,
        "signal_correlation_matrix": signal_correlation_matrix,
    })


NODE = Node(
    name="derive_signals",
    contract=CONTRACT,
    store=store,
    inputs=("lc", "cfg"),
    outputs=("out",),
)
