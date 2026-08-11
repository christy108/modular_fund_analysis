"""ESG coverage diagnostic (gated).

Node `esg_coverage`: reproduces Main.ipynb cell 63 when enabled; returns a sentinel
frame when the gate is off. Needs the raw per-region universes (from
build_global_universe), the raw LC snapshot (from load_signal_lc, taken only when
show_esg_coverage), and the prepared returns/universe (from prepare_panel).
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process

from New_Pipeline._common import cfg_schema, open_schema, store

CONTRACT = Contract(
    name="esg_coverage",
    intent="""Diagnostic: % of firm-years with a non-NaN ESG score per provider for two samples
(raw-LC signal-active firm-years; post-filter traded stock-years), plus firms-with-ESG per fiscal
year. Gated by cfg.show_esg_coverage; returns a sentinel frame when off.

Mandatory measures (enforced by schema / audits):
- when enabled, coverage fractions are in [0, 1] per provider per sample

Surfaces: (none — output is a lossless pickle bundle (or a sentinel when gated off), not a
tidy frame; a plain ``RowCountViz`` would always report 1 and add no information).""",
    input_schema={
        "universe": open_schema(),
        "lc": open_schema(),
        "prep": open_schema(),
        "cfg": cfg_schema(),
    },
    output_schema=open_schema(),
    audits=[],
)


@process(tag="esg_coverage@v1", contract="esg_coverage", author="refactor")
def esg_coverage_v1(universe, lc, prep, cfg):
    import json

    from functions.data_functions.ESG_coverage import (
        build_esg_lookup,
        coverage_sample1_lc,
        coverage_sample2_returns,
        esg_coverage_table,
        firms_with_esg_data_by_year,
    )
    from functions.data_functions.get_data import merge_all_esg_to_universe
    from New_Pipeline.boundary import empty_sentinel, pack_obj, unpack_obj

    C = json.loads(cfg["json"][0])
    if not C["show_esg_coverage"]:
        return empty_sentinel()

    U = unpack_obj(universe)
    L = unpack_obj(lc)
    P = unpack_obj(prep)
    usa_universe, row_universe, japan_universe = U["usa_universe"], U["row_universe"], U["japan_universe"]
    lc_raw_for_coverage = L["lc_raw_for_coverage"]
    global_returns, prep_global_universe = P["global_returns"], P["global_universe"]
    msci_col = C["msci_score_column"]

    _usa_cov, _row_cov, _jpn_cov = merge_all_esg_to_universe(
        usa_universe, row_universe, japan_universe, msci_score_column=msci_col
    )
    esg_lookup = build_esg_lookup(_usa_cov, _row_cov, _jpn_cov)
    cov1 = coverage_sample1_lc(lc_raw_for_coverage, esg_lookup, C["categories_dict"], C["signal_denominator"])
    cov2 = coverage_sample2_returns(global_returns, prep_global_universe, esg_lookup)
    esg_coverage_table_df = esg_coverage_table(cov1, cov2)
    print("Number of firms with ESG data")
    firms_with_esg_data_df = firms_with_esg_data_by_year(japan_universe, msci_score_column=msci_col)

    return pack_obj({
        "esg_coverage_table_df": esg_coverage_table_df,
        "firms_with_esg_data_df": firms_with_esg_data_df,
    })


NODE = Node(
    name="esg_coverage",
    contract=CONTRACT,
    store=store,
    inputs=("universe", "lc", "prep", "cfg"),
    outputs=("out",),
)
