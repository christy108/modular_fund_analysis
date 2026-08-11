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

    import pandas as pd

    from functions.portfolio_strategy_design.univariate_sorting_preprocess import (
        prepare_univariate_sorting_inputs,
    )
    from New_Pipeline.boundary import pack_obj, unpack_obj

    C = json.loads(cfg["json"][0])
    guniv = unpack_obj(global_universe)["global_universe"]
    lc_df = unpack_obj(lc)["lc"]
    ff = unpack_obj(fama_french_raw)["fama_french"]

    # cell 26 tail: ensure gvkey is 6 digits for merging (idempotent).
    lc_df["gvkey"] = lc_df["gvkey"].astype(str).str.zfill(6)

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
    # sum_activities is NOT a substitute — node 02 quantile-filters/winsorizes it.
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
    })


@process(tag="prepare_esg_universe@v1", contract="prepare_panel", author="refactor")
def prepare_esg_universe_v1(global_universe, lc, fama_french_raw, cfg):
    import json

    from functions.data_functions.get_data import get_gics_by_gvkey
    from functions.portfolio_strategy_design.univariate_sorting_preprocess import (
        prepare_esg_universe_sorting_inputs,
    )
    from New_Pipeline.boundary import pack_obj, unpack_obj

    C = json.loads(cfg["json"][0])
    guniv = unpack_obj(global_universe)["global_universe"]
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
    })


NODE = Node(
    name="prepare_panel",
    contract=CONTRACT,
    store=store,
    inputs=("global_universe", "lc", "fama_french_raw", "cfg"),
    outputs=("out",),
)
