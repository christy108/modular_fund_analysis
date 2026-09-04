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
from New_Pipeline.dashboard_viz import (
    BundleColoredTableViz,
    BundleDualAxisViz,
    BundleHistogramViz,
    BundlePieViz,
    BundleTableViz,
    histogram_series,
)


# ---- Dashboard extractors (bundle -> widget payloads; no computation happens here) --- #

def _sample_descriptives(bundle):
    """One row: unique gvkeys, unique gvkey-year observations, and total initiatives in
    the sample that survived this node. None on the ESG-universe path (no LC)."""
    return bundle.get("sample_descriptives")


def _firms_and_initiatives(bundle):
    """Per-fiscal-year unique companies / firm-year observations / total initiatives for
    the surviving sample. None on the ESG-universe path (no LC, no rfyear)."""
    return bundle.get("firms_and_initiatives")


def _sample_locations(bundle):
    """Per ISO-3 country of the sample that survived this node: firms, share, firm-years
    and initiatives. None on the ESG-universe path (no LC, so no ``loc``)."""
    return bundle.get("sample_locations")


def _sample_currencies(bundle):
    """Per listing currency (``curcdd``) of the surviving sample: firms, share, firm-years."""
    return bundle.get("sample_currencies")


def _sample_loc_currency(bundle):
    """Distinct firms per (country x listing currency) cell — the cross-tab behind the two
    pies, which each collapse one of the dimensions."""
    return bundle.get("sample_loc_currency")


def _signal_histograms_std(bundle):
    """Before/after histograms across ``standardize_pivot`` — two grid rows (raw, then
    standardised) x one column per signal, over the SAME monthly cells."""
    return histogram_series(bundle.get("signal_histograms_std"))


def _signal_sparsity_standardized(bundle):
    """Per signal per calendar year, sortability of the POST-standardization monthly panel
    -- the cross-sections the sort actually cuts. Companion to node 02's raw table."""
    return bundle.get("signal_sparsity_standardized")


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
(``BundleDualAxisViz``, since the two differ by orders of magnitude).

Also surfaces the signal DISTRIBUTIONS before vs after ``standardize_pivot``
(``BundleHistogramViz``): raw on the top row, z-score on the bottom, one column per signal,
both measured over the same monthly cells so the difference is the z-score alone. This is
where the raw zero atom visibly shatters into a per-group cloud, and where a tie block that
standardisation did NOT break shows up as a surviving spike.

Also surfaces post-standardisation sortability per signal per calendar year
(``BundleColoredTableViz``): the twin of node 02's raw ``signal_sparsity_by_year``, measured on
the z-scored monthly pivots this node produces rather than on the raw firm-year signal. The two
cannot share columns. ``standardize_pivot`` z-scores within (rfyear, curcdd, Industry), so a raw
0 becomes ``-mean_g / std_g`` -- a different value per group -- which SHATTERS the zero atom and
makes ``pct_zero`` meaningless (z=0 only means "at the group mean"). The tie-block columns
(``largest_tie_pct``, ``pct_at_min``, ``pct_at_max``) replace it: after z-scoring the damaging
tie block is no longer AT a known value, so it is found by size instead. The unit is the (date,
asset) monthly cell -- exactly what ``UnivariateQuantilePortfolio`` consumes -- so ``year`` is
the CALENDAR year of the formation month, not ``rfyear``; the point-in-time lag offsets them.
Every figure is computed per formation month and then aggregated over the year, because the sort
recomputes its cutpoints from one cross-section at a time. Audit-only: nothing downstream
reads it.

Also carries (no widget of its own) the raw per-firm-year SASB materiality COUNT columns as
``materiality_counts``, purely so ``build_analyse_portfolios`` can decompose each portfolio leg's
material initiatives without needing an ``lc`` edge of its own. Audit plumbing: no numeric path
reads it, and it is None unless ``cfg.add_materiality``.

Also surfaces WHERE that sample is: distinct firms by ISO-3 country and by listing currency
as composition donuts (``BundlePieViz``), plus the country x currency cross-tab behind them
(``BundleTableViz``). Country comes from LC's own ``loc`` column, which is the same
gvkey -> country mapping the universe-side geography audit resolves through, so the sample's
composition can be read directly against the universe it was drawn from. Currency is joined
back from the universe on ``(gvkey, rfyear)``: it is a universe column, not an LC one.

All the LC-derived tables above are empty on the
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
        # Composition of the SAME final sample the three widgets above count, split the
        # other way: by where the firms are and what currency they trade in. Deliberately
        # sited here rather than in a section of their own — "how many firms" and "which
        # firms" are one question, and reading the second one three screens away from the
        # first is what makes a sample look bigger than it is.
        BundlePieViz(
            _sample_locations,
            title="Final sample by country",
            label_col="loc", value_col="firms", unit="firms",
            key="pie:sample_locations",
            description=(
                "Distinct firms in the final sorted sample per ISO-3 country, as a share "
                "of the sample. `loc` rides in on the LC dataset, so this is the same "
                "country definition the universe geography uses — the two are directly "
                "comparable.\n\n"
                "**Expect a single wedge under the default config.** `region_analysis` "
                "defaults to `United_States`, which filters LC to `loc == \"USA\"` at "
                "`01_process_lc.py:179`; the chart only becomes informative for the "
                "regions that leave `execute_region_filters` off "
                "(`Europe_and_North_America`, `..._and_Japan`). A single wedge is still "
                "worth showing: it is the confirmation that the regional screen ran."
            ),
        ),
        BundlePieViz(
            _sample_currencies,
            title="Final sample by listing currency",
            label_col="curcdd", value_col="firms", unit="firms",
            key="pie:sample_currencies",
            description=(
                "Distinct firms per listing currency (`curcdd`) — the same key the "
                "market-cap filter cuts on and one of the three `standardize_pivot` "
                "grouping columns, so this is the composition of the cross-sections the "
                "sort actually standardises within.\n\n"
                "Bounded by `cfg.currency_filter`, which the `region_analysis` block sets "
                "(USD alone for `United_States`, EUR+USD for `Europe_and_North_America`)."
            ),
        ),
        BundleTableViz(
            _sample_loc_currency,
            title="Final sample: country x listing currency",
            key="table:sample_loc_currency",
            description=(
                "Distinct firms per (country, currency) cell — the tail the two pies fold "
                "into `Other`, and the only place a country that trades in more than one "
                "currency is visible. Row totals count each firm once; the COLUMN totals "
                "can therefore exceed the sample size, because a gvkey listed in two "
                "currency areas is one firm in two cells."
            ),
        ),
        BundleHistogramViz(
            _signal_histograms_std,
            title="Signal distributions — before vs after standardisation",
            key="histogram:signal_histograms_std",
            description=(
                "What `standardize_pivot` does to the shape of each signal. **Top row** is "
                "the raw signal, **bottom row** the z-score the sort actually cuts; one "
                "column per signal. 40 bins over each panel's own observed range, bars in "
                "% of observations.\n\n"
                "Both rows are measured on the **same unit and the same cells** — the "
                "(date, gvkey_iid) monthly cross-section cells that survive into the sort. "
                "The raw row is re-pivoted out of `global_universe` (which still carries "
                "the raw signal columns) and then masked by the standardised pivot's own "
                "NaN pattern, so a shape difference between the rows is the z-score and "
                "nothing else. Note this makes the top row **not** the same picture as node "
                "02's *Signal distributions*, which is over firm-years — a firm-year "
                "appears here roughly twelve times per share issue.\n\n"
                "The x-axes are deliberately **not** shared between rows: a raw share "
                "lives in [0, 1] while a z-score is unbounded and centred on 0, so a "
                "common axis would flatten one row into a spike. Compare by shape.\n\n"
                "What to look for:\n"
                "- **The zero atom shatters.** Standardisation happens within (rfyear, "
                "curcdd, Industry), so a raw 0 becomes `-mean_g/std_g` — a *different* "
                "value in every group. A single tall bar at 0 in the top row should spread "
                "into a left-hand cloud in the bottom row. That is why exactly-empty "
                "buckets are rarer than the raw `pct_zero` implies.\n"
                "- **A surviving spike** in the bottom row is a tie block that z-scoring "
                "did *not* break — a whole standardisation group at the same value. "
                "That block can swallow a cutpoint; `largest_tie_pct` in the table below "
                "measures it.\n"
                "- **Heavy z-score tails** (well beyond ±3) come from small "
                "standardisation groups, where one firm's deviation is divided by a tiny "
                "within-group std. Those are the observations most likely to occupy a "
                "corner bucket on their own."
            ),
        ),
        BundleColoredTableViz(
            _signal_sparsity_standardized,
            title="Signal sparsity by year — AFTER standardisation (as sorted)",
            color_col="signal", n=1000,
            key="colored_table:signal_sparsity_standardized",
            description=(
                "The post-standardisation twin of node 02's *Signal sparsity by fiscal "
                "year*. Node 02 measures the RAW `signal_i` on firm-years; this measures "
                "the z-scored monthly pivots that `UnivariateQuantilePortfolio` actually "
                "cuts. Read them together: the raw table says whether the *signal* has "
                "support, this one says whether the *sort* does.\n\n"
                "Two things change at the boundary, so the columns cannot match:\n\n"
                "1. `standardize_pivot` z-scores within (rfyear, curcdd, Industry), so a "
                "raw 0 becomes `-mean_g/std_g` \u2014 a **different value in every group**. "
                "The zero atom is *shattered*, which is why exactly-empty buckets are "
                "rarer than the raw `pct_zero` suggests. And `pct_zero` stops meaning "
                "anything (z=0 is just 'at the group mean'), so the tie columns below "
                "replace it.\n"
                "2. The unit is the (date, asset) monthly cell, not the firm-year. `year` "
                "is the **calendar year of the formation month**, not `rfyear` \u2014 the "
                "point-in-time accounting lag offsets the two, so rows do not line up "
                "one-to-one with the raw table.\n\n"
                "Every figure is computed per formation month and then aggregated over "
                "that year's months, because the sort recomputes its cutpoints from one "
                "cross-section at a time.\n\n"
                "- **n_months** \u2014 formation months contributing to this year.\n"
                "- **median_assets** / **min_assets** \u2014 sortable (non-NaN) assets in "
                "a typical / the thinnest month. This is the population the sort divides.\n"
                "- **assets_per_bucket** \u2014 `median_assets / K`. The headline gate: "
                "the expected size of one quantile bucket. Compare against a minimum group "
                "size (5 is the `cfg.esg_min_group_size` precedent).\n"
                "- **median_n_distinct** \u2014 distinct z-values per month. Below K the "
                "month cannot fill K buckets however many assets it has.\n"
                "- **largest_tie_pct** / **worst_month_tie_pct** \u2014 the biggest block "
                "of exactly-equal values, as a % of that month's cross-section (median and "
                "worst month). This is the post-standardisation replacement for "
                "`pct_zero`: after z-scoring the damaging tie block is no longer *at* "
                "zero, so it has to be found by size rather than by value. At or above "
                "`1/K` a cutpoint can land inside the block and a bucket can collapse.\n"
                "- **pct_at_min** / **pct_at_max** \u2014 mass sitting exactly at the "
                "cross-sectional extremes. These are the ends the sort treats "
                "asymmetrically: the low bucket is `s <= q_1` and **keeps** a tie block on "
                "its cutpoint, the high bucket is `s > q_K-1` and **drops** one. So "
                "`pct_at_max` is what predicts an under-populated HIGH bucket."
            ),
        ),
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
    from New_Pipeline._common import (
        count_firms,
        firm_counts,
        funnel_frame,
        normalise_gvkeys,
        raw_vs_standardized_histograms,
        standardized_sparsity_by_year,
    )
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
        cols_standardization=["rfyear", "Industry"],
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

    # ---- audit: WHERE the surviving sample is --------------------------------------- #
    # Same final sample as the three descriptives above, cut by geography instead of by
    # count. `loc` / `MacroRegion` ride in on lc (they are LC columns, and process_lc drops
    # any row missing them, so they are never null here). `curcdd` does NOT: it is a
    # universe column, so it is joined back from prep.global_universe on the same
    # (gvkey, rfyear) firm-year key `surviving` was built on.
    #
    # The join is one-to-MANY: a firm-year carries one curcdd per currency area it lists in,
    # which is >1 whenever currency_filter admits more than one (EUR+USD under
    # region_analysis="Europe_and_North_America"). That is why the currency counts are taken
    # with nunique per group rather than summed, and why the cross-tab is worth having.
    _ccy = (prep.global_universe[["gvkey", "rfyear", "curcdd"]]
            .dropna(subset=["rfyear"])
            .drop_duplicates())
    _ccy["rfyear"] = _ccy["rfyear"].astype("int64")
    geo = lc_final[["gvkey", "rfyear", "loc", "MacroRegion", "n_predicted_initiatives"]].merge(
        _ccy, on=["gvkey", "rfyear"], how="left"
    )

    # firm_counts gives (group, firms, pct_firms); the firm-YEAR and initiative totals are
    # added on top, deduped back to one row per (firm-year, group) so the one-to-many
    # currency join cannot inflate them.
    _loc_extra = (
        geo.drop_duplicates(subset=["gvkey", "rfyear", "loc"])
        .groupby("loc")
        .agg(MacroRegion=("MacroRegion", "first"),
             firm_years=("rfyear", "size"),
             initiatives=("n_predicted_initiatives", "sum"))
        .reset_index()
    )
    sample_locations = firm_counts(geo, "loc").merge(_loc_extra, on="loc", how="left")

    _ccy_extra = (
        geo.drop_duplicates(subset=["gvkey", "rfyear", "curcdd"])
        .assign(curcdd=lambda d: d["curcdd"].where(d["curcdd"].notna(), "(unmapped)").astype(str))
        .groupby("curcdd")
        .agg(firm_years=("rfyear", "size"))
        .reset_index()
    )
    sample_currencies = firm_counts(geo, "curcdd").merge(_ccy_extra, on="curcdd", how="left")

    # Wide, not long: currencies are capped at five by currency_filter, so one column each
    # reads as a matrix. Row totals count a firm once; column totals may not (see the widget).
    _pair = geo[["gvkey", "loc", "curcdd"]].copy()
    _pair["curcdd"] = _pair["curcdd"].where(_pair["curcdd"].notna(), "(unmapped)").astype(str)
    _pair["_gv"] = pd.to_numeric(_pair["gvkey"], errors="coerce")
    sample_loc_currency = _pair.pivot_table(
        index="loc", columns="curcdd", values="_gv", aggfunc="nunique", fill_value=0
    ).reset_index()
    sample_loc_currency.columns.name = None
    _cells = [c for c in sample_loc_currency.columns if c != "loc"]
    sample_loc_currency["total_firms"] = (
        _pair.groupby("loc")["_gv"].nunique().reindex(sample_loc_currency["loc"]).to_numpy()
    )
    sample_loc_currency = (
        sample_loc_currency.sort_values(["total_firms", "loc"], ascending=[False, True])
        .reset_index(drop=True)
    )

    print(f"[prepare_panel] final sample — {len(sample_locations)} countries, "
          f"{len(sample_currencies)} listing currencies "
          f"({', '.join(sample_currencies['curcdd'])})")

    # ---- audit plumbing: raw materiality counts for node 07's decomposition ---------- #
    # Node 07 decomposes each portfolio leg's MATERIAL initiatives into behavioural/SDG
    # brackets, which needs the per-firm-year count columns. Those live on lc, which node 07
    # does not receive -- and giving it an lc edge would change the DAG for an audit widget.
    # This node already has lc in hand, so carry a slim (gvkey, rfyear) -> counts frame in the
    # bundle instead. Same shape as the two descriptive frames above: audit-only, no numeric
    # path reads it, and adding a bundle key creates no parquet (run.py's _MERGED_EXPORTS is an
    # explicit allow-list covering node 07 only), so parity cannot move.
    #
    # lc_df here is POST node-02's alpha-bound trim, so it is exactly the firm-year sample the
    # sort ran on. None when add_materiality is off -- node 07 .get()s it and renders empty.
    _mat_cols = [c for c in lc_df.columns
                 if c.startswith(("material__", "immaterial__", "unmapped__"))]
    materiality_counts = None
    if _mat_cols:
        _keep = ["gvkey", "rfyear", "n_predicted_initiatives"] + _mat_cols
        materiality_counts = lc_df[_keep].drop_duplicates(subset=["gvkey", "rfyear"])
        print(f"[prepare_panel] materiality_counts: {len(materiality_counts)} firm-years x "
              f"{len(_mat_cols)} count columns")

    print("[prepare_panel] final sample — unique gvkeys:", sample_descriptives.at[0, "unique_gvkeys"])
    print("[prepare_panel] final sample — gvkey-year observations:", sample_descriptives.at[0, "gvkey_year_obs"])
    print("[prepare_panel] final sample — total initiatives:", sample_descriptives.at[0, "total_initiatives"])

    # Inlined bundle (must be self-contained: archived processes run in a fresh namespace).
    return pack_obj({
        "global_universe": prep.global_universe,
        "global_returns": prep.global_returns,
        "signals": prep.signals,
        "signal_names": prep.signal_names,
        # Audit-only: sortability of the standardized cross-sections. Nothing reads it.
        "signal_sparsity_standardized": standardized_sparsity_by_year(
            prep.signals, prep.signal_names, C["no_simple_quantiles"]
        ),
        # Audit-only: the signal distributions BEFORE vs AFTER standardize_pivot, on the
        # same monthly cells. Nothing reads it.
        "signal_histograms_std": raw_vs_standardized_histograms(
            prep.global_universe, prep.signals, prep.signal_names
        ),
        "signal_df": getattr(prep, "global_long_df", None),
        "fama_french": prep.fama_french,
        "sample_descriptives": sample_descriptives,
        "firms_and_initiatives": firms_and_initiatives,
        # Audit-only: geography of the same final sample. Nothing downstream reads these;
        # node 13 passes them through so they land in the run's parquet output next to the
        # universe-side tables they are meant to be compared against.
        "sample_locations": sample_locations,
        "sample_currencies": sample_currencies,
        "sample_loc_currency": sample_loc_currency,
        # Audit-only: feeds node 07's material-initiative decomposition. None without
        # add_materiality.
        "materiality_counts": materiality_counts,
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
    from New_Pipeline._common import (
        count_firms,
        firm_counts,
        funnel_frame,
        gvkey_locations,
        raw_vs_standardized_histograms,
        standardized_sparsity_by_year,
    )
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

    # ---- audit: WHERE the surviving sample is --------------------------------------- #
    # The geography widgets DO work on this path, unlike the LC descriptives above.
    # `curcdd` is a universe column, present here as on the other path; `loc` comes from the
    # gvkey -> country lookup rather than from LC's own column, which is exactly the point of
    # resolving both sides through the same mapping. No firm-year or initiative columns
    # though: this path standardises on `last_year` and has no rfyear and no LC to count.
    _locs = gvkey_locations()
    _geo = prep.global_universe[["gvkey", "curcdd"]].drop_duplicates().copy()
    _geo["gvkey_num"] = pd.to_numeric(_geo["gvkey"], errors="coerce")
    _geo = _geo.merge(_locs, on="gvkey_num", how="left")
    sample_locations = firm_counts(_geo, "loc")
    sample_currencies = firm_counts(_geo, "curcdd")
    _geo["curcdd"] = _geo["curcdd"].where(_geo["curcdd"].notna(), "(unmapped)").astype(str)
    _geo["loc"] = _geo["loc"].where(_geo["loc"].notna(), "(unmapped)").astype(str)
    sample_loc_currency = _geo.pivot_table(
        index="loc", columns="curcdd", values="gvkey_num", aggfunc="nunique", fill_value=0
    ).reset_index()
    sample_loc_currency.columns.name = None
    sample_loc_currency["total_firms"] = (
        _geo.groupby("loc")["gvkey_num"].nunique()
        .reindex(sample_loc_currency["loc"]).to_numpy()
    )
    sample_loc_currency = (
        sample_loc_currency.sort_values(["total_firms", "loc"], ascending=[False, True])
        .reset_index(drop=True)
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
        # Audit-only: sortability of the standardized cross-sections. Nothing reads it.
        "signal_sparsity_standardized": standardized_sparsity_by_year(
            prep.signals, prep.signal_names, C["no_simple_quantiles"]
        ),
        # Audit-only: the signal distributions BEFORE vs AFTER standardize_pivot, on the
        # same monthly cells. Nothing reads it.
        "signal_histograms_std": raw_vs_standardized_histograms(
            prep.global_universe, prep.signals, prep.signal_names
        ),
        "signal_df": getattr(prep, "global_long_df", None),
        "fama_french": prep.fama_french,
        "sample_descriptives": None,
        "firms_and_initiatives": None,
        # Audit-only geography, populated on this path too (see above).
        "sample_locations": sample_locations,
        "sample_currencies": sample_currencies,
        "sample_loc_currency": sample_loc_currency,
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
