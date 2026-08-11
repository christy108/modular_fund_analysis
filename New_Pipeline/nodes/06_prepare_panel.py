"""Merge LC signals into the universe and build the standardised monthly sorting panel.

Node `prepare_panel`: reproduces Main.ipynb cell 29 verbatim. Two interchangeable
Processes implement the two universes (LC-merged vs full ESG universe); the
Experiment picks one via process_selection. Reuses
functions/portfolio_strategy_design/univariate_sorting_preprocess.py unchanged.
Output is a lossless (pickle) bundle of the prep results consumed downstream.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process

from New_Pipeline._common import cfg_schema, open_schema, store

CONTRACT = Contract(
    name="prepare_panel",
    intent="""Produce the monthly panel the portfolio sort consumes: align returns to the universe,
apply the cross-signal NaN mask, and standardise (z-score) the sorting signals within the configured
groups. Two interchangeable Processes implement the two universes (LC-merged signals vs the full ESG
universe with the ESG score as the sole signal); the Experiment picks one via process_selection.

Mandatory measures (enforced by schema / audits):
- output bundles returns + standardised signals + aligned factors + the modified universe
- return dates and signal dates are aligned by the prepare routine

Surfaces: (none — output is a lossless pickle bundle, not a tidy frame; a plain
``RowCountViz`` would always report 1 and add no information).""",
    input_schema={
        "global_universe": open_schema(),
        "lc": open_schema(),
        "fama_french_raw": open_schema(),
        "cfg": cfg_schema(),
    },
    output_schema=open_schema(),
    audits=[],
)


@process(tag="prepare_lc@v1", contract="prepare_panel", author="refactor")
def prepare_lc_v1(global_universe, lc, fama_french_raw, cfg):
    import json

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
    # Inlined bundle (must be self-contained: archived processes run in a fresh namespace).
    return pack_obj({
        "global_universe": prep.global_universe,
        "global_returns": prep.global_returns,
        "signals": prep.signals,
        "signal_names": prep.signal_names,
        "signal_df": getattr(prep, "global_long_df", None),
        "fama_french": prep.fama_french,
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
    return pack_obj({
        "global_universe": prep.global_universe,
        "global_returns": prep.global_returns,
        "signals": prep.signals,
        "signal_names": prep.signal_names,
        "signal_df": getattr(prep, "global_long_df", None),
        "fama_french": prep.fama_french,
    })


NODE = Node(
    name="prepare_panel",
    contract=CONTRACT,
    store=store,
    inputs=("global_universe", "lc", "fama_french_raw", "cfg"),
    outputs=("out",),
)
