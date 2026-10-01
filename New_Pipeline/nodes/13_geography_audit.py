"""Where the Compustat universes are — and where the sorted sample ended up.

Node `geography_audit`: a pure diagnostic answering "what countries and currencies is this
built on", on both sides of the sample funnel at once.

Why it needs a node of its own rather than living on `load_universes` / `merge_esg_provider`:
`run.py::_export` writes every key of a diagnostic node's bundle as a parquet, and those two
nodes' bundles carry the full multi-million-row universes. A node that holds nothing but the
summary tables is what makes them exportable.

Why the LOCATION comes from a lookup rather than off the frames: the Compustat extracts carry
no country field at all. The USA file has a `cusip`, the RoW and Japan files an `isin`, and
`process_global_universe` drops both (process_data.py:140-144) before anything downstream sees
the frame. `_common.gvkey_locations` resolves gvkey -> country through the company database
that LC's own `loc` column is drawn from, so the universe geography and the final-sample
geography are the SAME definition — which is the only thing that makes the two comparable,
and comparing them is the entire point of reporting both.

The SAMPLE-side tables are not recomputed here: `prepare_panel` already builds them next to
its other final-sample descriptives (they belong beside the firm/initiative counts on the
dashboard, not three sections away), and this node only forwards them into its bundle so they
land in the run's parquet output alongside the universe tables. Same contribute-rather-than-
replay arrangement `sample_funnel_audit` uses, and for the same reason: one measurement, made
where the data is, reported where it reads.

Nothing downstream reads this node. Its frames appear in `parity.compare` only as an
informational `(only in new: ...)` line. Its section renders LAST on the dashboard page via
`dashboard_viz._DEFERRED_SECTIONS`.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process

from New_Pipeline._common import cfg_schema, open_schema, store
from New_Pipeline.dashboard_viz import BundlePieViz, BundleTableViz


# ---- Dashboard extractors (bundle -> widget payloads; no computation happens here) --- #

def _universe_locations(bundle):
    """One row per ISO-3 country: firms contributed by each regional extract, the total,
    and how many survived into the sorted universe."""
    return bundle.get("universe_locations")


def _universe_currencies(bundle):
    """One row per listing currency: firms, the extract(s) they come from, and how many
    survived the market-cap screen and the currency filter."""
    return bundle.get("universe_currencies")


_KEPT_NOTE = (
    "- **firms** / **pct_firms** — distinct gvkeys in the raw regional extracts, before any "
    "screen. `pct_firms` is a share of this column, so it sums to 100.\n"
    "- **firms_sorted** / **pct_kept** — the same firms after `process_global_universe`, "
    "i.e. after BOTH the market-cap screen (`cfg.market_cap_filter`, which at the default "
    "0.95-of-value setting discards ~65% of listings) and `cfg.currency_filter`. A row at "
    "**0%** was excluded outright by the currency filter, not thinned by the size screen — "
    "those are two very different things reaching the same number.\n"
    "- **(unmapped)** — gvkeys the company database has no country for (~6-10% per extract). "
    "Shown rather than dropped: the unmapped share is what tells you how much of the rest to "
    "trust."
)

CONTRACT = Contract(
    name="geography_audit",
    intent="""Report the geographic and currency composition of the three Compustat universes, and
carry the matching composition of the final sorted sample alongside it, so the two can be read
against each other.

Country is not a Compustat column — the extracts carry a cusip (USA) or an isin (RoW, Japan) and
process_global_universe drops both — so it is resolved through the same gvkey -> country mapping
LC's ``loc`` column comes from. Using one mapping on both sides is what makes "where the universe
is" and "where the sample is" the same question asked twice rather than two incomparable proxies.

Both the raw extracts and the post-screen sorted universe are counted, because the difference is
the point: the market-cap screen and the currency filter fall very unevenly across countries, and
neither the universe's own output nor the sample's descriptives can show that on their own.

Mandatory measures (enforced by schema / audits):
- counts are distinct FIRMS (gvkeys), coerced to a numeric key so the same firm spelled
  "1004" / "001004" / "1004.0" at different stages is counted once
- the pre-screen counts come from the three regional extracts, the post-screen counts from the
  assembled global_universe — never from each other
- unmapped gvkeys are reported as their own row, never silently dropped

Surfaces: universe composition by country and by listing currency, each as a composition donut
over the largest groups (``BundlePieViz``) plus the full table including the tail
(``BundleTableViz``).

Audit-only: nothing downstream reads this node, and it recomputes nothing that any other node
already measured — the final-sample tables in its bundle are forwarded verbatim from
``prepare_panel``, which builds them beside its other sample descriptives.""",
    input_schema={
        "universe": open_schema(),
        "panel": open_schema(),
        "cfg": cfg_schema(),
    },
    output_schema=open_schema(),
    audits=[
        BundlePieViz(
            _universe_locations,
            title="Compustat universes by country",
            label_col="loc", value_col="firms", unit="firms",
            key="pie:universe_locations",
            description=(
                "Distinct firms in the three raw regional extracts, by ISO-3 country. The "
                "regional split is by EXCHANGE, not by domicile, so this is not three "
                "national buckets: US-exchange listings include a long tail of foreign "
                "issuers (BMU, ISR, GBR, CHN...), and the RoW extract's CHF/GBP/EUR screen "
                "spans ~15 countries. Read the tail off the table below."
            ),
        ),
        BundleTableViz(
            _universe_locations,
            title="Compustat universes by country — full table",
            key="table:universe_locations",
            description=(
                "Every country, with the extract each firm came from.\n\n"
                "- **firms_usa** / **firms_row** / **firms_japan** — which regional extract "
                "contributed the firm. A country can appear in more than one.\n"
                f"{_KEPT_NOTE}"
            ),
        ),
        BundlePieViz(
            _universe_currencies,
            title="Compustat universes by listing currency",
            label_col="curcdd", value_col="firms", unit="firms",
            key="pie:universe_currencies",
            description=(
                "Distinct firms by listing currency across the raw extracts. Currency is "
                "near-determined by extract — USA is USD by construction "
                "(`process_data.py:88`), Japan is JPY by query, and the RoW query admits "
                "only CHF/GBP/EUR — so this is mostly a size comparison of the three "
                "extracts, with RoW split three ways."
            ),
        ),
        BundleTableViz(
            _universe_currencies,
            title="Compustat universes by listing currency — full table",
            key="table:universe_currencies",
            description=(
                "- **region** — the extract(s) the currency appears in.\n"
                "- Firms, not listings: all three extracts join on the PRIMARY issue "
                "(`priusa` / `prirow`), so each gvkey contributes exactly one `iid` and the "
                "two counts are the same number.\n"
                f"{_KEPT_NOTE}"
            ),
        ),
    ],
)


@process(tag="geography_audit@v1", contract="geography_audit", author="refactor")
def geography_audit_v1(universe, panel, cfg):
    import pandas as pd

    from New_Pipeline._common import firm_counts, gvkey_locations
    from New_Pipeline.boundary import pack_obj, unpack_obj

    U = unpack_obj(universe)
    P = unpack_obj(panel)
    locs = gvkey_locations()

    def _resolve(df, cols):
        """Distinct listing keys + the country each gvkey resolves to.

        Deduped to (gvkey, iid, curcdd) FIRST: the universes are daily security-month
        panels of a few million rows, and every count below is over listings, not days.
        """
        d = df[cols].drop_duplicates().copy()
        d["gvkey_num"] = pd.to_numeric(d["gvkey"], errors="coerce")
        return d.merge(locs, on="gvkey_num", how="left")

    # ---- pre-screen: the three raw regional extracts -------------------------------- #
    # japan_universe is None under configs that exclude it, so the region list is built
    # from what is actually present rather than assumed to be all three.
    _regions = [("usa", U.get("usa_universe")), ("row", U.get("row_universe")),
                ("japan", U.get("japan_universe"))]
    parts = []
    for name, df in _regions:
        if df is None or len(df) == 0:
            continue
        d = _resolve(df, ["gvkey", "iid", "curcdd"])
        d["region"] = name
        parts.append(d)
    pre = pd.concat(parts, ignore_index=True)

    # ---- post-screen: the assembled, filtered universe the sort is drawn from -------- #
    post = _resolve(U["global_universe"], ["gvkey", "iid", "curcdd"])

    # ---- by country ------------------------------------------------------------------ #
    loc_tbl = firm_counts(pre, "loc")
    # Which extract contributed each firm — one column per region, distinct firms.
    _by_region = (
        pre.assign(loc=lambda d: d["loc"].where(d["loc"].notna(), "(unmapped)").astype(str))
        .pivot_table(index="loc", columns="region", values="gvkey_num",
                     aggfunc="nunique", fill_value=0)
        .rename(columns=lambda c: f"firms_{c}")
        .reset_index()
    )
    _by_region.columns.name = None
    _macro = (
        pre.dropna(subset=["loc"])
        .drop_duplicates(subset=["loc"])[["loc", "MacroRegion"]]
    )
    _kept_loc = (
        firm_counts(post, "loc", name="firms_sorted")[["loc", "firms_sorted"]]
    )
    universe_locations = (
        loc_tbl.merge(_macro, on="loc", how="left")
        .merge(_by_region, on="loc", how="left")
        .merge(_kept_loc, on="loc", how="left")
    )
    universe_locations["firms_sorted"] = (
        universe_locations["firms_sorted"].fillna(0).astype("int64")
    )
    universe_locations["pct_kept"] = (
        100.0 * universe_locations["firms_sorted"] / universe_locations["firms"]
    ).round(2)

    # ---- by listing currency --------------------------------------------------------- #
    cur_tbl = firm_counts(pre, "curcdd")
    # No separate "listings" count: the three extracts join on priusa/prirow
    # (get_data.py:114/172/230), so each gvkey contributes exactly ONE iid and a listing
    # count would be a verbatim copy of the firm count.
    _cur_extra = (
        pre.groupby("curcdd")
        # Sorted + comma-joined, not `first`: a currency present in two extracts must say
        # so, and the order has to be stable across runs.
        .agg(region=("region", lambda s: ", ".join(sorted(set(s)))))
        .reset_index()
    )
    _kept_cur = firm_counts(post, "curcdd", name="firms_sorted")[["curcdd", "firms_sorted"]]
    universe_currencies = (
        cur_tbl.merge(_cur_extra, on="curcdd", how="left")
        .merge(_kept_cur, on="curcdd", how="left")
    )
    universe_currencies["firms_sorted"] = (
        universe_currencies["firms_sorted"].fillna(0).astype("int64")
    )
    universe_currencies["pct_kept"] = (
        100.0 * universe_currencies["firms_sorted"] / universe_currencies["firms"]
    ).round(2)

    print(f"[geography_audit] universes: {len(universe_locations)} countries, "
          f"{len(universe_currencies)} currencies, "
          f"{int(universe_locations['firms'].sum())} firms -> "
          f"{int(universe_locations['firms_sorted'].sum())} after the screens")

    return pack_obj({
        "universe_locations": universe_locations,
        "universe_currencies": universe_currencies,
        # Forwarded verbatim from prepare_panel — measured there, exported here. None on no
        # path currently, but .get() rather than [] so a Process version that stops emitting
        # them degrades to a missing parquet instead of failing the run.
        "sample_locations": P.get("sample_locations"),
        "sample_currencies": P.get("sample_currencies"),
        "sample_loc_currency": P.get("sample_loc_currency"),
    })


NODE = Node(
    name="geography_audit",
    contract=CONTRACT,
    store=store,
    inputs=("universe", "panel", "cfg"),
    outputs=("out",),
)
