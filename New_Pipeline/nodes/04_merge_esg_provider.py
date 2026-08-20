"""Attach an ESG provider to the universes and assemble the global universe.

Node `merge_esg_provider`: reproduces the ESG-merge portion of Main.ipynb cell 26,
reusing functions/data_functions/{get_data,process_data}.py unchanged. Downstream
half of the former ``build_global_universe`` split. The former ``if/elif`` on
``cfg.esg_choice`` is now modelled as **four interchangeable Processes**:

  * ``esg_none@v1``      — attach a neutral esg=100 column (no provider)
  * ``esg_refinitiv@v1`` — merge Refinitiv/LSEG scores
  * ``esg_msci@v1``      — merge MSCI scores (uses cfg.msci_score_column)
  * ``esg_snp@v1``       — merge S&P Global scores

The ``Experiment`` picks one via ``process_selection[merge_esg_provider]`` (see
``experiments.py``). This is the framework-idiomatic way to A/B provider choice —
each run's manifest records the exact ESG process that ran, content-hashed, and
adding a new provider is a new ``@process`` next to the existing four rather than
another ``elif``. Every process ends with the same ``process_global_universe`` call
so downstream nodes see an unchanged bundle shape.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process

from New_Pipeline._common import cfg_schema, open_schema, store

CONTRACT = Contract(
    name="merge_esg_provider",
    intent="""Attach a single ESG provider's score to the per-region universes and assemble the
global universe. Which provider (or the neutral constant) is picked at Experiment time via
``process_selection[merge_esg_provider]`` — not branched inside a single Process. Currency and
mkt-cap filters, plus the provider-specific column choice (MSCI weighted vs industry-adjusted),
are read from cfg.

Mandatory measures (enforced by schema / audits):
- one row per gvkey-month over the configured window, with a return and market-cap column
- the ESG column reflects exactly the provider chosen by the Experiment's process_selection

Surfaces: (none — output is a lossless pickle bundle, not a tidy frame; a plain
``RowCountViz`` would always report 1 and add no information).""",
    input_schema={"universes": open_schema(), "cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[],
)


# --------------------------------------------------------------------------- #
# Four interchangeable Processes — one per ESG provider (or the neutral case).
# Each ends with process_global_universe + the gvkey zfill so downstream sees an
# unchanged bundle shape regardless of which provider ran.
# --------------------------------------------------------------------------- #

@process(tag="esg_none@v1", contract="merge_esg_provider", author="refactor")
def esg_none_v1(universes, cfg):
    """Neutral: attach esg=100 on each region (no provider merged)."""
    import json

    from functions.data_functions.process_data import process_global_universe
    from New_Pipeline._common import mktcap_filter_kwargs, normalise_gvkeys
    from New_Pipeline.boundary import pack_obj, unpack_obj

    C = json.loads(cfg["json"][0])
    U = unpack_obj(universes)
    usa_universe, row_universe, japan_universe = U["usa_universe"], U["row_universe"], U["japan_universe"]

    usa_universe["esg"] = 100
    row_universe["esg"] = 100
    japan_universe["esg"] = 100

    print("usa_universe unique gvkeys:", usa_universe["gvkey"].nunique())
    print("row_universe unique gvkeys:", row_universe["gvkey"].nunique())
    print("japan_universe unique gvkeys:", japan_universe["gvkey"].nunique())

    global_universe = process_global_universe(
        usa_universe, row_universe, japan_universe,
        C["currency_filter"],
        C["mktcap_covered_if_filter_by_cum_market_cap"],
        "none",
        **mktcap_filter_kwargs(C),
    )
    print("columns with year")
    print([c for c in global_universe.columns if c == "year" or c.startswith("year_")])
    global_universe["gvkey"] = normalise_gvkeys(global_universe["gvkey"])
    print("global_universe unique gvkeys:", global_universe["gvkey"].nunique())

    return pack_obj({
        "global_universe": global_universe,
        "usa_universe": usa_universe,
        "row_universe": row_universe,
        "japan_universe": japan_universe,
        "fx_rates": U["fx_rates"],
    })


@process(tag="esg_refinitiv@v1", contract="merge_esg_provider", author="refactor")
def esg_refinitiv_v1(universes, cfg):
    """Merge Refinitiv (LSEG) ESG scores into the per-region universes."""
    import json

    from functions.data_functions.get_data import get_refinitive_snp_merge_to_universe
    from functions.data_functions.process_data import process_global_universe
    from New_Pipeline._common import mktcap_filter_kwargs, normalise_gvkeys
    from New_Pipeline.boundary import pack_obj, unpack_obj

    C = json.loads(cfg["json"][0])
    U = unpack_obj(universes)
    usa_universe, row_universe, japan_universe = get_refinitive_snp_merge_to_universe(
        U["usa_universe"], U["row_universe"], U["japan_universe"]
    )

    print("usa_universe unique gvkeys:", usa_universe["gvkey"].nunique())
    print("row_universe unique gvkeys:", row_universe["gvkey"].nunique())
    print("japan_universe unique gvkeys:", japan_universe["gvkey"].nunique())

    global_universe = process_global_universe(
        usa_universe, row_universe, japan_universe,
        C["currency_filter"],
        C["mktcap_covered_if_filter_by_cum_market_cap"],
        "refinitiv",
        **mktcap_filter_kwargs(C),
    )
    print("columns with year")
    print([c for c in global_universe.columns if c == "year" or c.startswith("year_")])
    global_universe["gvkey"] = normalise_gvkeys(global_universe["gvkey"])
    print("global_universe unique gvkeys:", global_universe["gvkey"].nunique())

    return pack_obj({
        "global_universe": global_universe,
        "usa_universe": usa_universe,
        "row_universe": row_universe,
        "japan_universe": japan_universe,
        "fx_rates": U["fx_rates"],
    })


@process(tag="esg_msci@v1", contract="merge_esg_provider", author="refactor")
def esg_msci_v1(universes, cfg):
    """Merge MSCI ESG scores into the per-region universes.

    Uses ``cfg.msci_score_column`` to pick between the industry-adjusted and the
    weighted-average score column — the one methodological knob MSCI has.
    """
    import json

    from functions.data_functions.get_data import get_msci_esg_merge_to_universe
    from functions.data_functions.process_data import process_global_universe
    from New_Pipeline._common import mktcap_filter_kwargs, normalise_gvkeys
    from New_Pipeline.boundary import pack_obj, unpack_obj

    C = json.loads(cfg["json"][0])
    U = unpack_obj(universes)
    usa_universe, row_universe, japan_universe = get_msci_esg_merge_to_universe(
        U["usa_universe"], U["row_universe"], U["japan_universe"],
        score_column=C["msci_score_column"],
    )

    print("usa_universe unique gvkeys:", usa_universe["gvkey"].nunique())
    print("row_universe unique gvkeys:", row_universe["gvkey"].nunique())
    print("japan_universe unique gvkeys:", japan_universe["gvkey"].nunique())

    global_universe = process_global_universe(
        usa_universe, row_universe, japan_universe,
        C["currency_filter"],
        C["mktcap_covered_if_filter_by_cum_market_cap"],
        "msci",
        **mktcap_filter_kwargs(C),
    )
    print("columns with year")
    print([c for c in global_universe.columns if c == "year" or c.startswith("year_")])
    global_universe["gvkey"] = normalise_gvkeys(global_universe["gvkey"])
    print("global_universe unique gvkeys:", global_universe["gvkey"].nunique())

    return pack_obj({
        "global_universe": global_universe,
        "usa_universe": usa_universe,
        "row_universe": row_universe,
        "japan_universe": japan_universe,
        "fx_rates": U["fx_rates"],
    })


@process(tag="esg_snp@v1", contract="merge_esg_provider", author="refactor")
def esg_snp_v1(universes, cfg):
    """Merge S&P Global ESG scores into the per-region universes."""
    import json

    from functions.data_functions.get_data import get_snp_esg_merge_to_universe
    from functions.data_functions.process_data import process_global_universe
    from New_Pipeline._common import mktcap_filter_kwargs, normalise_gvkeys
    from New_Pipeline.boundary import pack_obj, unpack_obj

    C = json.loads(cfg["json"][0])
    U = unpack_obj(universes)
    usa_universe, row_universe, japan_universe = get_snp_esg_merge_to_universe(
        U["usa_universe"], U["row_universe"], U["japan_universe"]
    )

    print("usa_universe unique gvkeys:", usa_universe["gvkey"].nunique())
    print("row_universe unique gvkeys:", row_universe["gvkey"].nunique())
    print("japan_universe unique gvkeys:", japan_universe["gvkey"].nunique())

    global_universe = process_global_universe(
        usa_universe, row_universe, japan_universe,
        C["currency_filter"],
        C["mktcap_covered_if_filter_by_cum_market_cap"],
        "s&p",
        **mktcap_filter_kwargs(C),
    )
    print("columns with year")
    print([c for c in global_universe.columns if c == "year" or c.startswith("year_")])
    global_universe["gvkey"] = normalise_gvkeys(global_universe["gvkey"])
    print("global_universe unique gvkeys:", global_universe["gvkey"].nunique())

    return pack_obj({
        "global_universe": global_universe,
        "usa_universe": usa_universe,
        "row_universe": row_universe,
        "japan_universe": japan_universe,
        "fx_rates": U["fx_rates"],
    })


NODE = Node(
    name="merge_esg_provider",
    contract=CONTRACT,
    store=store,
    inputs=("universes", "cfg"),
    outputs=("out",),
)
