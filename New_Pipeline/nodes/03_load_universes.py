"""Load and regionally-process the tradable universe — pure data ingestion.

Node `load_universes`: reproduces the ingestion portion of Main.ipynb cell 26
verbatim, reusing functions/data_functions/{get_data,process_data}.py unchanged.
First of two nodes that used to be one (``build_global_universe``); the paired
downstream node (``merge_esg_provider``) handles the ESG merge + assembly. The
split makes ingestion identical across every ESG configuration — the ESG choice
becomes a genuinely interchangeable Process, not an ``if/elif`` inside one process.

Output is a lossless (pickle) bundle carrying the three regionally-processed
universes plus fx_rates. No ESG column is attached yet.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process

from New_Pipeline._common import cfg_schema, open_schema, store

CONTRACT = Contract(
    name="load_universes",
    intent="""Load the three regional Compustat universes (USA / RoW / Japan) and FX rates for the
configured window, then regionally-process each (currency conversion when configured, Japan
fiscal-year alignment). No ESG columns are attached here — that belongs to the paired
``merge_esg_provider`` node so the ESG choice is picked as an interchangeable Process rather
than branched inside this Process. The window, FX-conversion and security-status knobs are
read from cfg.

``cfg.security_status`` selects the survivorship sample: "active_only" keeps Compustat
securities whose secstat is 'A' as of the extract date (the frozen behaviour), while
"all_firms_even_delisted" retains the full price history of securities that have since
gone inactive. Both arms read the SAME on-disk extract and differ only by an in-memory
filter, so they cannot diverge by data vintage.

Mandatory measures (enforced by schema / audits):
- three per-region universes with return and market-cap columns, no ESG column
- fx_rates present for the configured end year
- the configured security_status sample applied identically across all three regions

Surfaces: (none — output is a lossless pickle bundle, not a tidy frame; a plain
``RowCountViz`` would always report 1 and add no information).""",
    input_schema={"cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[],
)


@process(tag="load_universes@v1", contract="load_universes", author="refactor")
def load_universes_v1(cfg):
    import json

    from functions.data_functions.get_data import (
        get_japan_universe,
        get_processed_fx_rates,
        get_row_universe,
        get_usa_universe,
    )
    from functions.data_functions.process_data import (
        process_japan_universe,
        process_row_universe,
        process_usa_universe,
    )
    from New_Pipeline.boundary import pack_obj

    # Listing currencies each extract can contain. Used ONLY to decide whether a file is
    # worth reading -- the authoritative screen stays process_global_universe's
    # `curcdd.isin(currency_filter)`, which still runs on whatever is loaded. `usa` has no
    # curcdd in its CSV; process_usa_universe stamps every row 'USD', so it is exact by
    # construction. `row` and `japan` were verified by a full curcdd scan of both extracts.
    # _assert_currencies re-checks a file whenever it IS loaded, so a re-extract that widens
    # one of these fails loudly here instead of silently changing a skip decision.
    _UNIVERSE_CURRENCIES = {
        "usa": frozenset({"USD"}),
        "row": frozenset({"CHF", "GBP", "EUR", "NOK", "SEK", "DKK"}),
        "japan": frozenset({"JPY"}),
    }


    def _needs(label, currency_filter):
        """True when this extract can contribute a row that survives currency_filter."""
        if not currency_filter:
            return True
        return bool(_UNIVERSE_CURRENCIES[label] & set(currency_filter))


    def _assert_currencies(df, label, was_loaded):
        """Fail loudly if an extract holds a currency _UNIVERSE_CURRENCIES does not declare.

        Only meaningful on a frame that was actually read -- a schema-only stub has no rows
        to check, and the whole point is that we never paid to look at them.
        """
        if not was_loaded or "curcdd" not in df.columns or df.empty:
            return
        unexpected = set(df["curcdd"].dropna().unique()) - _UNIVERSE_CURRENCIES[label]
        if unexpected:
            raise ValueError(
                f"{label}_universe holds currencies {sorted(unexpected)} that "
                f"nodes/03_load_universes._UNIVERSE_CURRENCIES does not declare. The skip "
                f"decision for OTHER regions is derived from that mapping, so it must be "
                f"widened (and the affected baselines re-checked) before this run is trusted."
            )

    C = json.loads(cfg["json"][0])
    start_year, end_year = C["start_year"], C["end_year"]
    # .get() with the frozen default, not C[...]: a cfg built before this key existed then
    # still runs the original survivor-only screen rather than raising. Same rationale as
    # _common.mktcap_filter_kwargs.
    security_status = C.get("security_status", "active_only")

    fx_rates = get_processed_fx_rates(end_year)

    # Which extracts this region actually needs. The three files partition the universe by
    # listing currency with NO overlap (verified by a full scan of each extract's curcdd:
    # usa is stamped 'USD' by process_usa_universe, row is exactly the 6 European
    # currencies, japan is 100% JPY), so a universe whose currencies are disjoint from
    # currency_filter contributes nothing: process_global_universe drops every one of its
    # rows at the `curcdd.isin(currency_filter)` screen anyway.
    #
    # It is dropped HERE instead, before the read, because the screen runs only after all
    # three frames have been loaded AND concatenated -- ~37M daily rows / ~10GB resident
    # for a region that keeps at most one file's worth. currency_filter=None means "every
    # currency in the data", so it loads everything, as it must.
    #
    # A skipped universe is still returned as a REAL, correctly-typed zero-row frame
    # rather than None: usa_universe.columns is process_global_universe's reindex template
    # and pd.concat resolves dtypes across every part, so the schema has to survive even
    # when the rows do not. See get_data._read_universe_csv.
    load = {k: _needs(k, C["currency_filter"]) for k in _UNIVERSE_CURRENCIES}
    print(f"[load_universes] currency_filter={C['currency_filter']} -> loading "
          f"{sorted(k for k, v in load.items() if v)}, "
          f"schema-only {sorted(k for k, v in load.items() if not v)}")

    # download_wrds_data stays False: network I/O inside a content-addressed Process would
    # break replay. The extracts are produced offline by the same functions.
    usa_universe = get_usa_universe(start_year, end_year, download_wrds_data=False,
                                    security_status=security_status,
                                    load_rows=load["usa"])
    usa_universe = process_usa_universe(usa_universe)

    row_universe = get_row_universe(start_year, end_year, download_wrds_data=False,
                                    security_status=security_status,
                                    load_rows=load["row"])
    _assert_currencies(row_universe, "row", load["row"])
    row_universe = process_row_universe(row_universe, fx_rates, C["convert_to_USD"])

    japan_universe = get_japan_universe(start_year, end_year, download_wrds_data=False,
                                        security_status=security_status,
                                        load_rows=load["japan"])
    _assert_currencies(japan_universe, "japan", load["japan"])
    japan_universe = process_japan_universe(
        japan_universe, fx_rates, C["convert_to_USD"],
        C["japan_year_adjustment_split_month_for_two_or_one"],
    )

    return pack_obj({
        "fx_rates": fx_rates,
        "usa_universe": usa_universe,
        "row_universe": row_universe,
        "japan_universe": japan_universe,
    })


NODE = Node(
    name="load_universes",
    contract=CONTRACT,
    store=store,
    inputs=("cfg",),
    outputs=("out",),
)
