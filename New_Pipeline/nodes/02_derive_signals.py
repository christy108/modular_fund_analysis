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

Output is a lossless (pickle) bundle: ``{lc, lc_raw_for_coverage}`` — same shape
as ``process_lc``'s bundle plus the signal columns on ``lc``, so downstream
(``prepare_panel``) keeps a single lc port.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process

from New_Pipeline._common import cfg_schema, open_schema, store

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

Surfaces: (none — output is a lossless pickle bundle, not a tidy frame; a plain
``RowCountViz`` would always report 1 and add no information).""",
    input_schema={"lc": open_schema(), "cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[],
)


@process(tag="derive_signals@v1", contract="derive_signals", author="refactor")
def derive_signals_v1(lc, cfg):
    import json

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

    # ---- cell 21: signal_i ----------------------------------------------- #
    max_category = max(int(v) for v in categories_dict.values())
    for i in range(max_category + 1):
        lc_df[f"signal_{i}"] = lc_df[f"sum_with_{i}"] / lc_df["sum_activities"]

    # Carry lc_raw_for_coverage forward untouched so esg_coverage can still read
    # from this node if the topology is later rewired to consume derive_signals'
    # output. Today only process_lc feeds esg_coverage — see registry.EDGES.
    return pack_obj({"lc": lc_df, "lc_raw_for_coverage": L.get("lc_raw_for_coverage")})


NODE = Node(
    name="derive_signals",
    contract=CONTRACT,
    store=store,
    inputs=("lc", "cfg"),
    outputs=("out",),
)
