"""Merge LC signals into the universe and build the standardised monthly sorting panel.

Node `prepare_panel`: reproduces Main.ipynb cell 29 verbatim. Two interchangeable
Processes implement the two universes (LC-merged vs full ESG universe); the
Experiment picks one via process_selection. Reuses
functions/portfolio_strategy_design/univariate_sorting_preprocess.py unchanged.
Output is a lossless (pickle) bundle of the prep results consumed downstream.

This node is where the analysis sample is finally fixed — the universe intersection,
the monthly collapse and the standardisation-key dropna all happen inside the prep
routine — so the bundle also carries two DIAGNOSTIC tables describing the surviving
sample (``sample_descriptives``, ``firms_and_initiatives``). They are audit-only: no
downstream node reads them and no numeric path depends on them.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process

from New_Pipeline._common import cfg_schema, open_schema, store
from New_Pipeline.dashboard_viz import BundleDualAxisViz, BundleTableViz


# ---- Dashboard extractors (bundle -> widget payloads; no computation happens here) --- #

def _sample_descriptives(bundle):
    """One row: unique gvkeys, unique gvkey-year observations, and total initiatives in
    the sample that survived this node. None on the ESG-universe path (no LC)."""
    return bundle.get("sample_descriptives")


def _firms_and_initiatives(bundle):
    """Per-fiscal-year unique companies / firm-year observations / total initiatives for
    the surviving sample. None on the ESG-universe path (no LC, no rfyear)."""
    return bundle.get("firms_and_initiatives")


CONTRACT = Contract(
    name="prepare_panel",
    intent="""Produce the monthly panel the portfolio sort consumes: align returns to the universe,
apply the cross-signal NaN mask, and standardise (z-score) the sorting signals within the configured
groups. Two interchangeable Processes implement the two universes (LC-merged signals vs the full ESG
universe with the ESG score as the sole signal); the Experiment picks one via process_selection.

This is the last stage at which the analysis sample changes (gvkey intersection with the tradable
universe, the monthly collapse, and the dropna on standardisation keys all happen here), so the node
also reports descriptive statistics of the sample that survives it — per experiment, since each ESG
provider intersects against a different universe and therefore keeps a different set of firms.

Mandatory measures (enforced by schema / audits):
- output bundles returns + standardised signals + aligned factors + the modified universe
- return dates and signal dates are aligned by the prepare routine
- the reported descriptives count firm-fiscal-years, not panel rows (the panel repeats each
  firm-fiscal-year across months and share issues)

Surfaces: final-sample descriptives — unique gvkeys, unique gvkey-year observations, total
initiatives (``BundleTableViz``); the same three measures per fiscal year (``BundleTableViz``);
and unique companies against total initiatives over time on separate y-axes
(``BundleDualAxisViz``, since the two differ by orders of magnitude). All are empty on the
ESG-universe path, which carries no LC data.""",
    input_schema={
        "global_universe": open_schema(),
        "lc": open_schema(),
        "fama_french_raw": open_schema(),
        "cfg": cfg_schema(),
    },
    output_schema=open_schema(),
    audits=[
        # Explicit keys throughout: an unkeyed BundleTableViz collapses to the literal
        # "table:" and collides with every other unkeyed one on the same Contract.
        BundleTableViz(_sample_descriptives, title="Final sample descriptives",
                       key="table:sample_descriptives"),
        BundleDualAxisViz(
            _firms_and_initiatives,
            title="Unique companies and total initiatives over time",
            x_col="rfyear", left_col="unique_companies", right_col="total_initiatives",
            left_label="Unique companies", right_label="Total initiatives",
            x_label="Fiscal year",
            key="dual_axis:firms_and_initiatives",
        ),
        BundleTableViz(_firms_and_initiatives, title="Firms and initiatives by year",
                       key="table:firms_and_initiatives"),
    ],
)


@process(tag="prepare_lc@v1", contract="prepare_panel", author="refactor")
def prepare_lc_v1(global_universe, lc, fama_french_raw, cfg):
    import json

    import numpy as np
    import pandas as pd

    from functions.portfolio_strategy_design.univariate_sorting_preprocess import (
        prepare_univariate_sorting_inputs,
    )
    from New_Pipeline._common import count_firms, funnel_frame, normalise_gvkeys
    from New_Pipeline.boundary import pack_obj, unpack_obj

    C = json.loads(cfg["json"][0])
    GU = unpack_obj(global_universe)
    L = unpack_obj(lc)
    guniv = GU["global_universe"]
    lc_df = L["lc"]
    ff = unpack_obj(fama_french_raw)["fama_french"]

    # cell 26 tail: ensure gvkey is 6 digits for merging (idempotent).
    lc_df["gvkey"] = normalise_gvkeys(lc_df["gvkey"])

    # ---- audit: sample filter funnel, panel side (stages inside the prep call) ------- #
    # prepare_univariate_sorting_inputs returns only its endpoint, but three of these four
    # counts are readable off what it already gives back and the fourth is one mask, so
    # none of the heavy path is re-run:
    #
    #  * the intersection is np.intersect1d on two gvkey arrays -- mirrored here rather
    #    than by calling intersect_gvkeys_and_filter, which MUTATES its lc argument
    #    (univariate_sorting_preprocess.py:43).
    #  * the date/tri dropna needs no merge: those are universe columns, and
    #    merge_lc_into_global_universe is a LEFT merge that can duplicate rows but never
    #    drops them and never touches date/tri, so a mask on the intersected universe
    #    gives the exact distinct-firm count.
    #  * the standardisation-key dropna is prep.global_universe itself.
    #  * the cross-signal mask must be read off prep.global_returns, NOT prep.signals:
    #    global_returns is exactly apply_cross_signal_nan_mask's output, while the bundled
    #    signals are post-standardize_all_signals, which can add NaNs of its own (a
    #    singleton standardisation group gives std=0).
    #
    # to_monthly_last_trading_date and compute_monthly_returns_long's 36-day gap mask are
    # not stages: the first is a groupby().last() collapse that cannot drop a firm, the
    # second nulls a value rather than dropping a row (it feeds the cross-signal mask).
    _lc_keys = lc_df["gvkey"].unique()
    _gu_keys = guniv["gvkey"].unique()
    _common_keys = np.intersect1d(_lc_keys, _gu_keys)
    _in_common = guniv["gvkey"].isin(_common_keys)
    funnel_rows = [
        ("MERGE: LC intersect Compustat universe (np.intersect1d)", "both",
         "univariate_sorting_preprocess.py:37 / intersect_gvkeys_and_filter",
         int(len(_common_keys))),
        ('dropna(subset=["date", "tri"]) - drop listings with no price history',
         "merged panel",
         "univariate_sorting_preprocess.py:70 / add_gvkey_iid_sort_clean",
         count_firms(guniv.loc[
             _in_common & guniv["date"].notna() & guniv["tri"].notna(), "gvkey"
         ])),
    ]

    prep = prepare_univariate_sorting_inputs(
        global_universe=guniv,
        lc=lc_df,
        fama_french=ff,
        lc_signals=C["lc_signals"],
        universe_signals=C["universe_signals"],
        category_columns=sorted(C["categories_dict"].keys()),
        cols_standardization=["rfyear", "curcdd", "Industry"],
        apply_geo_filter=False,
        show_corr_matrices=C["show_esg_corr_matricies"],
        corr_method=C["esg_corr_method"],
    )

    funnel_rows.append((
        'dropna(subset=["rfyear", "curcdd", "Industry"]) - standardisation keys',
        "merged panel",
        "univariate_sorting_preprocess.py:151 / dropna_std_cols_and_build_pivots",
        count_firms(prep.global_universe["gvkey"]),
    ))
    # Surviving firms after the mask = the gvkey_iid columns of global_returns that still
    # hold at least one non-NaN cell, mapped back to their gvkey prefix.
    _live = prep.global_returns.columns[prep.global_returns.notna().any(axis=0)]
    funnel_rows.append((
        "Cross-signal NaN mask (every surviving cell complete across return + all signals)",
        "merged panel",
        "univariate_sorting_preprocess.py:170 / apply_cross_signal_nan_mask",
        count_firms(pd.Series([str(c).split("_")[0] for c in _live])),
    ))
    funnel = funnel_frame(funnel_rows)
    _prev = [f for f in (L.get("funnel"), GU.get("funnel")) if f is not None]
    if _prev:
        funnel = pd.concat(_prev + [funnel], axis=0, ignore_index=True)

    # ---- audit: descriptives of the sample that SURVIVED this node ------------------ #
    # prep.global_universe is (gvkey_iid, year, month) — each firm-fiscal-year repeated
    # across ~12 months and N share issues — so dedupe to (gvkey, rfyear) before counting.
    surviving = prep.global_universe[["gvkey", "rfyear"]].drop_duplicates()
    # rfyear reaches the panel through a LEFT merge, so it is float64 (NaN-bearing) even
    # after the null rows are dropped, while lc's rfyear is integer. Without this cast the
    # join below matches nothing and every count silently reports 0.
    surviving["rfyear"] = surviving["rfyear"].astype("int64")

    # n_predicted_initiatives is never merged into the universe (the merge list is fixed
    # at univariate_sorting_preprocess._LC_MERGE_FIXED), so recover it from the lc input.
    # sum_activities is NOT a substitute — node 02 quantile-filters it.
    lc_fy = lc_df.drop_duplicates(subset=["gvkey", "rfyear"])
    if len(lc_fy) != len(lc_df):
        print(f"[prepare_panel] WARNING: lc had {len(lc_df) - len(lc_fy)} duplicate (gvkey, rfyear) rows")
    lc_final = lc_fy.merge(surviving, on=["gvkey", "rfyear"], how="inner")
    if lc_final.empty:
        raise ValueError(
            "final-sample join produced 0 rows — check gvkey zero-padding / rfyear dtype"
        )

    sample_descriptives = pd.DataFrame([{
        "unique_gvkeys": lc_final["gvkey"].nunique(),
        "gvkey_year_obs": len(lc_final),
        "total_initiatives": int(lc_final["n_predicted_initiatives"].sum()),
    }])

    # Same aggregation (and column names) as descriptive_stats.descriptive_plots
    # .plot_firms_and_initiatives, computed here so the pipeline needs no matplotlib.
    firms_and_initiatives = (
        lc_final.groupby("rfyear")
        .agg(
            unique_companies=("gvkey", "nunique"),
            firm_year_observations=("gvkey", "size"),
            total_initiatives=("n_predicted_initiatives", "sum"),
        )
        .sort_index()
        .reset_index()
    )

    print("[prepare_panel] final sample — unique gvkeys:", sample_descriptives.at[0, "unique_gvkeys"])
    print("[prepare_panel] final sample — gvkey-year observations:", sample_descriptives.at[0, "gvkey_year_obs"])
    print("[prepare_panel] final sample — total initiatives:", sample_descriptives.at[0, "total_initiatives"])

    # Inlined bundle (must be self-contained: archived processes run in a fresh namespace).
    return pack_obj({
        "global_universe": prep.global_universe,
        "global_returns": prep.global_returns,
        "signals": prep.signals,
        "signal_names": prep.signal_names,
        "signal_df": getattr(prep, "global_long_df", None),
        "fama_french": prep.fama_french,
        "sample_descriptives": sample_descriptives,
        "firms_and_initiatives": firms_and_initiatives,
        "funnel": funnel,
        "funnel_checks": L.get("funnel_checks"),
    })


@process(tag="prepare_esg_universe@v1", contract="prepare_panel", author="refactor")
def prepare_esg_universe_v1(global_universe, lc, fama_french_raw, cfg):
    import json

    import pandas as pd

    from functions.data_functions.get_data import get_gics_by_gvkey
    from functions.portfolio_strategy_design.univariate_sorting_preprocess import (
        prepare_esg_universe_sorting_inputs,
    )
    from New_Pipeline._common import count_firms, funnel_frame
    from New_Pipeline.boundary import pack_obj, unpack_obj

    C = json.loads(cfg["json"][0])
    GU = unpack_obj(global_universe)
    L = unpack_obj(lc)
    guniv = GU["global_universe"]
    ff = unpack_obj(fama_french_raw)["fama_french"]

    gics_by_gvkey = get_gics_by_gvkey(
        guniv, C["region_analysis"], C["end_year"], download_gics_data=C["download_gics_data"]
    )
    prep = prepare_esg_universe_sorting_inputs(
        global_universe=guniv,
        gics_by_gvkey=gics_by_gvkey,
        fama_french=ff,
        universe_signals=C["universe_signals"],
        industry_level=C["industry_level"],
        year_col="last_year",
        min_group_size=C["esg_min_group_size"],
        drop_real_estate=C["drop_real_estate_Full_ESG"],
        drop_utilities=C["drop_utilities_Full_ESG"],
    )
    # ---- audit: sample filter funnel, ESG-universe path ------------------------------ #
    # A different sequence from the LC path: no LC merge and so no gvkey intersection, its
    # own sector drops on the raw GICS sector (the LC path does those back in node 01), a
    # min-group guard the LC path does not run, and a Fama-French month intersection that
    # the LC path resolves by raising instead.
    #
    # Only TWO points on this path are observable from outside the frozen function, so only
    # two rows carry a count:
    #
    #  * prep.global_universe is what dropna_std_cols_and_build_pivots returned, and on this
    #    path that call sits AFTER both the standardisation-key dropna (:452) and the
    #    min-group guard (:459). Those two therefore cannot be told apart from out here, and
    #    are reported as ONE row rather than attributing the composite survivor count to the
    #    first of them -- which is what a split would silently do.
    #  * prep.global_returns is post-mask, giving the final count.
    #
    # The earlier stages are null, with the reason in the `where` column. Splitting them
    # would need the raw-GICS sector-name mapping replayed out of the frozen function --
    # a hardcoded dict duplicated for one config's audit, which is exactly the drift this
    # contribute-rather-than-replay design exists to avoid.
    _live = prep.global_returns.columns[prep.global_returns.notna().any(axis=0)]
    funnel = funnel_frame([
        ("MERGE: LC intersect Compustat universe (np.intersect1d)", "both",
         "not run on the ESG-universe path (no LC)", None),
        (f"drop_real_estate={C['drop_real_estate_Full_ESG']} / "
         f"drop_utilities={C['drop_utilities_Full_ESG']} on the raw GICS sector",
         "ESG universe",
         "univariate_sorting_preprocess.py:430 (not separately observable)", None),
        ('dropna(subset=["date", "tri"]) - drop listings with no price history',
         "ESG universe",
         "univariate_sorting_preprocess.py:447 (not separately observable)", None),
        (f"dropna on standardisation keys (incl. firms with no GICS) AND min-group guard "
         f"(< {C['esg_min_group_size']} issues per cell) - one composite stage",
         "ESG universe",
         "univariate_sorting_preprocess.py:452+459 / prepare_esg_universe_sorting_inputs",
         count_firms(prep.global_universe["gvkey"])),
        ("Fama-French month intersection (drops return MONTHS, not firms directly)",
         "ESG universe",
         "univariate_sorting_preprocess.py:479 (not separately observable)", None),
        ("Cross-signal NaN mask (every surviving cell complete across return + all signals)",
         "ESG universe",
         "univariate_sorting_preprocess.py:526 / apply_cross_signal_nan_mask",
         count_firms(pd.Series([str(c).split("_")[0] for c in _live]))),
    ])
    _prev = [f for f in (L.get("funnel"), GU.get("funnel")) if f is not None]
    if _prev:
        funnel = pd.concat(_prev + [funnel], axis=0, ignore_index=True)

    # Inlined bundle (must be self-contained: archived processes run in a fresh namespace).
    # sample_descriptives / firms_and_initiatives are None here: this path never reads lc
    # and standardises on `last_year`, so there is no rfyear and no initiative count to
    # describe. The audit widgets render empty rather than erroring.
    return pack_obj({
        "global_universe": prep.global_universe,
        "global_returns": prep.global_returns,
        "signals": prep.signals,
        "signal_names": prep.signal_names,
        "signal_df": getattr(prep, "global_long_df", None),
        "fama_french": prep.fama_french,
        "sample_descriptives": None,
        "firms_and_initiatives": None,
        "funnel": funnel,
        "funnel_checks": L.get("funnel_checks"),
    })


NODE = Node(
    name="prepare_panel",
    contract=CONTRACT,
    store=store,
    inputs=("global_universe", "lc", "fama_french_raw", "cfg"),
    outputs=("out",),
)
