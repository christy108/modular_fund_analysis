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
signal_summary_stats, signal_histograms, signal_correlation_matrix, category_column_stats, signal_sparsity,
signal_sparsity_by_year}`` — everything after ``lc_raw_for_coverage`` is
diagnostic tables only (no effect on ``lc`` or downstream nodes), added purely so the dashboard can
audit the signal construction across experiments; same ``lc`` shape as before plus the signal
columns, so downstream (``prepare_panel``) keeps a single lc port.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process

from New_Pipeline._common import cfg_schema, open_schema, store
from New_Pipeline.dashboard_viz import (
    BundleColoredTableViz,
    BundleHeatmapViz,
    BundleHistogramViz,
    BundleTableViz,
    histogram_series,
)


# ---- Dashboard extractors (bundle -> widget payloads; no computation happens here) --- #

def _sum_activities_outlier_stats(bundle):
    """describe() stats for sum_activities, one row per stat, one column per stage
    (before_alpha_bound vs after_alpha_bound, plus after_min_initiatives when the
    materiality split floor ran) — read left-to-right as a before/after comparison of the
    filters applied to the denominator."""
    return bundle["sum_activities_outlier_stats"]


def _materiality_split_floor(bundle):
    """What each candidate minimum-initiatives floor would cost, and what it would buy.

    Empty unless the design has exactly one material/immaterial group — the only shape
    ``cfg.minimum_initatives_needed_to_split_by_materiality`` is allowed on."""
    return bundle.get("materiality_split_floor")


def _signal_summary_stats(bundle):
    """One row per signal_i with its describe() stats — signals compared side by side."""
    return bundle["signal_summary_stats"]


def _signal_histograms(bundle):
    """One small histogram per signal: bin centres and the % of firm-years in each bin.

    This is the RAW signal on firm-years. Its post-standardisation twin — the same signals
    as the sort actually sees them — is on the ``prepare_panel`` section."""
    return histogram_series(bundle.get("signal_histograms"))


def _winsorise_stats(bundle):
    """Per signal, how much the winsorise clip actually bit: values capped at each tail,
    and std/max before vs after. Empty frame when cfg.winsorise_signal_pct is 0."""
    return bundle.get("winsorise_stats")


def _signal_correlation_matrix(bundle):
    """Pearson correlation matrix between the behavioural signals."""
    return bundle["signal_correlation_matrix"]


def _category_column_stats(bundle):
    """describe() stats for each raw category column that feeds a signal's sum_with_i
    aggregation — one row per column, tinted by which signal it belongs to."""
    return bundle["category_column_stats"]


def _signal_sparsity(bundle):
    """Per signal: how much of the panel is exactly zero, and how thin the non-zero side
    is. describe() alone hides this — a signal can look healthy on mean/std while being
    zero for 99% of firm-years, which makes a quantile sort collapse into ties and leaves
    the top bucket empty or near-empty."""
    return bundle["signal_sparsity"]


def _signal_sparsity_by_year(bundle):
    """The sparsity table split by fiscal year — one row per (signal, rfyear). Shows
    whether a signal is uniformly sparse or only sparse in early years, which decides
    whether a sample restriction rescues it."""
    return bundle["signal_sparsity_by_year"]


CONTRACT = Contract(
    name="derive_signals",
    intent="""Turn the cleaned LC panel into a behavioural-signal panel: aggregate the raw category
columns into ``sum_with_<i>``, pick the ``sum_activities`` denominator (Sum_All_Signals vs
Sum_All_Initiatives), winsor-trim ``sum_activities`` per fiscal year, then set ``signal_i`` for
each category group i: under ``signal_type="weights"`` (default) that is the share
``sum_with_i / sum_activities``; under ``signal_type="counts"`` it is the raw level
``sum_with_i`` — the group's total initiative count, with sum_activities still driving the trim
but no longer dividing (and the signal's display name suffixed ``_counts``). Which categories map
to which group, the denominator, the trim bound, and the signal_type are read from cfg. Sample
selection and industry mapping are NOT redone here — they belong to the upstream ``process_lc``
node.

One further optional filter runs here, AFTER the winsor trim (so the trim's own numbers are
unaffected by it): ``cfg.minimum_initatives_needed_to_split_by_materiality`` drops firm-years
holding fewer than N initiatives in the materiality group, so a ratio of two small integer
counts is only formed where it is estimable rather than letting ``1/1 = 1.0`` read as maximal
materiality. Off (0) by default, and ``build_cfg`` allows it only on a design with exactly ONE
material/immaterial group.

Mandatory measures (enforced by schema / audits):
- one row per surviving gvkey-fiscal-year with the behavioural signal columns present
- rows only drop via the declared winsor trim and the declared materiality split floor,
  each contributing its own sample-funnel row

Surfaces: sum_activities summary stats, before vs after the alpha-bound trim (and after the
materiality split floor, when it ran) side by side as columns (``BundleTableViz``); what each
candidate split floor would cost in firm-years and buy in ``pct_at_max``, for every candidate N
and not only the configured one (``BundleTableViz``); per-signal summary statistics side by side
(``BundleTableViz``) and, beneath them, the per-signal DISTRIBUTIONS as a strip of small
histograms (``BundleHistogramViz``, % of firm-years per bin) — describe() cannot separate a
tight cluster at the mean from a barbell of 0s and 1s, and the two sort completely
differently; the signal correlation matrix as a diverging blue/white/red heatmap
(``BundleHeatmapViz``); and descriptive statistics for each raw category column that feeds a
signal's aggregation, one row per column, tinted by which signal it belongs to
(``BundleColoredTableViz``). All four stack/subplot across experiments — the tables via the
dashboard's per-config ``experiment`` column, the heatmap via one subplot per config sharing a
colour scale — when comparing multiple configs.

Also surfaces a signal-sparsity table (``BundleTableViz``), one row per signal, sorted worst
first. It answers "can this signal actually be sorted into quantiles?", which describe() cannot:
a signal that is exactly zero for most firm-years still reports an ordinary mean and max, but
its zero mass all ties at the bottom, so the low bucket swells and the high bucket is drawn
from whatever thin non-zero tail remains. Every count is over the WHOLE post-trim panel — all
fiscal years pooled, not a single year. Columns:
- ``n_firm_years`` — rows in the panel (gvkey x fiscal-year observations), identical for every
  signal; the denominator for the counts below.
- ``n_zero`` / ``pct_zero`` — observations where the signal is exactly 0.
- ``n_nonzero`` — observations with any activity in this signal's categories.
- ``n_firms_nonzero`` — DISTINCT firms non-zero at least once, pooled over ALL years. An upper
  bound on availability, not a portfolio size: those firms need not coexist in any one year, so
  the count available to sort in a given formation year is lower.
- ``quantiles_of_pure_zero`` — how many of the ``no_simple_quantiles`` buckets the zero mass
  alone fills. At 7 quantiles, a signal 6/7 zero leaves ONE bucket able to hold a non-zero
  value; the rest are pure ties and the sort is meaningless.
- ``mean_if_nonzero`` / ``median_if_nonzero`` — centre CONDITIONAL on being non-zero, so a
  healthy non-zero side is distinguishable from a signal that is merely small everywhere.
- ``max`` — largest observed signal value.
- ``n_at_max`` / ``pct_at_max`` / ``quantiles_of_pure_max`` — the high-side mirrors of the zero
  columns. Needed because the sort treats its two ends differently: the low bucket is
  ``signal <= q_1`` and the high bucket is ``signal > q_{K-1}``, so a tie block landing on the
  bottom cutpoint is KEPT while one landing on the top cutpoint is DROPPED. A bounded ratio
  signal saturates at 1 the way it piles up at 0, so ``pct_zero`` alone diagnoses only half the
  problem — a signal can be near-zero-free and still have a badly under-populated high bucket.
- ``n_distinct_values`` — distinct values available to cut on. Below ``no_simple_quantiles`` the
  sort cannot fill K buckets at all, whatever the zero share; a ratio of small integer counts
  often has only a handful of levels.
- ``total_initiatives`` — raw ``sum_with_i`` summed over the panel: total initiatives feeding
  this signal, before any denominator.""",
    input_schema={"lc": open_schema(), "cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[
        # Explicit keys are required: BundleTableViz's default key collapses to the
        # literal "table:" for every instance (it always passes columns=[] to
        # SampleTableViz), so multiple unkeyed BundleTableViz on one Contract silently
        # collide in the dashboard's per-node audit_stats dict — only the last one
        # computed survives and gets shown under all the matching widgets.
        BundleTableViz(_sum_activities_outlier_stats,
                       title="sum_activities — before vs after alpha-bound trim",
                       key="table:sum_activities_outlier_stats"),
        BundleTableViz(
            _materiality_split_floor,
            title="Materiality split floor — what each minimum would cost",
            key="table:materiality_split_floor",
            description=(
                "`cfg.minimum_initatives_needed_to_split_by_materiality` requires a "
                "firm-year to hold at least N initiatives IN THE GROUP before it is "
                "allowed into the sort. This table is why: the signal is a ratio of two "
                "small integer counts, so a firm-year with one initiative in the group "
                "scores `1/1 = 1.0` and the sort reads it as maximal materiality on a "
                "single observation, while `4/5 = 0.8` looks weaker and is far better "
                "evidence.\n\n"
                "One row per candidate N — **the full strip regardless of the N actually "
                "configured**, so the table answers *what would N cost* and not only "
                "*what did N cost*. `is_configured` marks the row in force.\n\n"
                "- **n_firm_years / pct_firm_years_kept**, **n_firms / pct_firms_kept** — "
                "the price, measured on the post-alpha-bound-trim sample.\n"
                "- **pct_at_max** — firm-years at ratio exactly 1.0 *after* that floor. "
                "This is what the floor is bought for. The saturation atom is what damages "
                "the HIGH bucket, because the sort's top bucket is `signal > q_K-1` and "
                "excludes a tie block sitting on the cutpoint while its bottom bucket "
                "`signal <= q_1` keeps one. Read it against the same run's "
                "`pct_at_max` in *Signal sparsity*.\n"
                "- **pct_zero** — the low-end mirror (ratio exactly 0.0), which the floor "
                "also thins.\n"
                "- **n_distinct_values** — values left to cut on. Below "
                "`cfg.no_simple_quantiles` the sort cannot fill K buckets at all, so a "
                "floor that buys a lower `pct_at_max` at the cost of too few distinct "
                "levels is not a good trade.\n"
                "- **median_group_total** — centre of the surviving denominator.\n\n"
                "The ratio is reported even under `signal_type=\"counts\"`, where "
                "`signal_0` is a raw level rather than this ratio: the floor is about "
                "whether the material/immaterial SPLIT is estimable, which is a property "
                "of the counts and not of the signal flavour.\n\n"
                "Empty for any design without exactly one material/immaterial group — "
                "`build_cfg` refuses the floor there, because "
                "`apply_cross_signal_nan_mask` would turn a per-group floor into "
                "'drop unless EVERY group clears N'."
            ),
        ),
        BundleTableViz(_signal_summary_stats, title="Signal summary statistics",
                       key="table:signal_summary_stats"),
        BundleHistogramViz(
            _signal_histograms,
            title="Signal distributions",
            key="histogram:signal_histograms",
            description=(
                "One small histogram per signal, over the SAME post-trim panel the "
                "summary statistics above describe. 40 equal-width bins spanning that "
                "signal's own observed [min, max]; bars are the **% of firm-years** in "
                "each bin, so panels are comparable even where one signal has fewer "
                "finite observations.\n\n"
                "This is the shape `describe()` cannot show. A mean of 0.64 is produced "
                "equally by a tight cluster at 0.64 and by a barbell of 0s and 1s, and "
                "the two sort completely differently.\n\n"
                "Two things to look for:\n"
                "- **The leftmost bar contains the exact-zero atom.** It is not separated "
                "out here — read `pct_zero` in the sparsity table below for its true size, "
                "since the first bin also holds genuinely small non-zero values.\n"
                "- **A spike at the right edge** is the saturation mass (`pct_at_max`). "
                "It costs the HIGH bucket names, because the sort's top bucket is "
                "`signal > q_K-1` while its bottom is `signal <= q_1` — a tie block on "
                "the top cutpoint is dropped, one on the bottom cutpoint is kept.\n\n"
                "Under `action_characterization=\"Material_Immaterial_only\"` the two "
                "panels are exact mirrors (`signal_1 = 1 - signal_0`), so one is a "
                "left-right flip of the other — that is the construction, not a finding."
            ),
        ),
        BundleTableViz(
            _winsorise_stats,
            title="Signal winsorisation — what was clipped",
            key="table:winsorise_stats",
            description=(
                "Effect of `cfg.winsorise_signal_pct` (0 = off, so this table is empty "
                "for most configs). Each signal is capped above its (1-p) quantile and "
                "floored below its p quantile, WITHIN each rfyear.\n\n"
                "- **n_clipped_low / n_clipped_high** — firm-years pulled up to the floor "
                "and down to the cap.\n"
                "- **std_before / std_after** — the point of the exercise: clipping a "
                "handful of extremes can halve a signal's dispersion.\n"
                "- **max_before / max_after** — max_after is the (1-p) quantile itself.\n\n"
                "Clipping is rank-preserving, so it does NOT move the quantile sort "
                "directly. It acts only through the (rfyear, curcdd, Industry) "
                "standardisation, where a smaller within-group std spreads that group out "
                "relative to the other groups the sort pools it with. Expect a real effect "
                "under `signal_type='per_revenue'` (unbounded, right-skewed) and almost "
                "none under `'weights'` (a share bounded in [0,1])."
            ),
        ),
        BundleHeatmapViz(_signal_correlation_matrix, title="Signal correlation matrix",
                         key="heatmap:signal_correlation_matrix"),
        BundleColoredTableViz(_category_column_stats,
                              title="Category column descriptive statistics (per signal)",
                              color_col="signal",
                              key="colored_table:category_column_stats"),
        BundleTableViz(_signal_sparsity,
                       title="Signal sparsity — zero share and non-zero support",
                       key="table:signal_sparsity",
                       description=(
                           "One row per signal, sorted worst-first by `pct_zero`. A signal that is "
                           "mostly exact zeros cannot be quantile-sorted: the zero mass ties at the "
                           "bottom, so the low bucket swells and the high bucket is drawn from "
                           "whatever thin non-zero tail remains.\n\n"
                           "- **signal** — human-readable signal name (from `cfg.lc_signals`).\n"
                           "- **n_firm_years** — rows in the panel after the alpha-bound trim; the "
                           "denominator for every count here, identical across signals.\n"
                           "- **n_zero** / **pct_zero** — firm-years where the signal is *exactly* "
                           "zero, as a count and as a % of `n_firm_years`.\n"
                           "- **n_nonzero** — firm-years with a non-zero value; the rows that carry "
                           "all the sorting information (`n_firm_years - n_zero`).\n"
                           "- **n_firms_nonzero** — *distinct gvkeys* behind `n_nonzero`. Much "
                           "smaller than `n_nonzero` means the non-zero side is a few firms repeated "
                           "over years, not broad coverage.\n"
                           "- **quantiles_of_pure_zero** — how many of the "
                           "`cfg.no_simple_quantiles` buckets the zero mass alone would fill "
                           "(`pct_zero x K`). At or near K means the sort is essentially degenerate.\n"
                           "- **mean_if_nonzero** / **median_if_nonzero** — average and median over "
                           "the non-zero rows only, so the zero mass does not drag them toward 0.\n"
                           "- **max** — largest value of the signal across the panel.\n"
                           "- **n_at_max** / **pct_at_max** — firm-years sitting *exactly* at "
                           "`max`: the high-side mirror of `n_zero`/`pct_zero`. This is the column "
                           "that tells you whether the HIGH bucket is sound. A bounded ratio signal "
                           "saturates at 1 the way it piles up at 0, and the two ends are not "
                           "treated alike: the sort's low bucket is `signal <= q1` and its high "
                           "bucket is `signal > q_K-1`, so a tie block on the bottom cutpoint is "
                           "*kept* while one on the top cutpoint is *dropped*. A large `pct_at_max` "
                           "therefore costs the high bucket names — empirically, roughly "
                           "`pct_at_max` percent of them, in the months where the block straddles "
                           "the cutpoint. For a count signal the max is a single firm, so this "
                           "reads ~0 and is simply uninformative.\n"
                           "- **quantiles_of_pure_max** — high-side mirror of "
                           "`quantiles_of_pure_zero`: how many buckets the saturation mass alone "
                           "would fill. >= 1 means the top cutpoint can land inside the atom and "
                           "the high bucket can collapse or empty.\n"
                           "- **n_distinct_values** — distinct values the sort has to cut on. Below "
                           "`cfg.no_simple_quantiles` the signal *cannot* fill K buckets however "
                           "small its zero share is — a ratio of small integer counts often has "
                           "only a handful of distinct levels.\n"
                           "- **total_initiatives** — sum of the signal's raw `sum_with_i` numerator "
                           "(initiative counts) over the panel, before any ratio is taken.\n"
                           "- **n_years**, **median_firms_nonzero_per_year**, "
                           "**min_firms_nonzero_per_year**, **worst_year** — folded in from the "
                           "per-year table below, because the eligibility question ('are there "
                           "enough firms to fill K buckets in a typical year?') cannot be answered "
                           "from pooled counts: the same total arises from many firms in one year "
                           "or few firms in every year.\n"
                           "- **median_firms_per_bucket** — `median_firms_nonzero_per_year / K`. "
                           "The headline gate: compare against a minimum group size (5 is the "
                           "precedent set by `cfg.esg_min_group_size`). Below it, buckets are "
                           "undersized in a typical year no matter how the sort is configured."
                       )),
        BundleColoredTableViz(_signal_sparsity_by_year,
                              title="Signal sparsity by fiscal year — BEFORE standardisation (raw signal)",
                              color_col="signal",
                              n=1000,
                              key="colored_table:signal_sparsity_by_year",
                              description=(
                                  "The pooled table above averages across regimes, so it can "
                                  "describe no actual year: a signal that is 100% zero until 2019 "
                                  "and 30% zero after pools to ~60%, and neither half of the sample "
                                  "looks like that. The sort recomputes its cutpoints from each "
                                  "formation date's cross-section alone, so these per-year figures "
                                  "are the ones that decide whether a sort is possible — and "
                                  "whether restricting the sample rescues a signal that looks dead "
                                  "when pooled. Rows are tinted by signal; read down a colour block "
                                  "to see one signal's trajectory.\n\n"
                                  "This is the RAW `signal_i`, measured on "
                                  "firm-years. Its post-standardisation twin lives "
                                  "on `prepare_panel` (*Signal sparsity by year - "
                                  "AFTER standardisation*) and measures the z-scored "
                                  "monthly cross-sections the sort actually cuts. "
                                  "This table says whether the SIGNAL has support; "
                                  "that one says whether the SORT does.\n\n"
                                  "- **rfyear** — fiscal year; all other columns are computed "
                                  "within that year only.\n"
                                  "- **n_firm_years** — firms in the panel that year (the year's "
                                  "cross-section size).\n"
                                  "- **n_zero** / **pct_zero** / **n_nonzero** — as in the pooled "
                                  "table, but restricted to this year.\n"
                                  "- **n_firms_nonzero** — distinct firms with activity this year. "
                                  "This is the quantity the sort actually has to work with.\n"
                                  "- **firms_per_bucket** — `n_firms_nonzero / K`. Under ~5 means "
                                  "this year's buckets are too thin to form a meaningful portfolio.\n"
                                  "- **pct_at_max** / **quantiles_of_pure_max** — the same two "
                                  "measures for the *upper* end, against this year's own max. "
                                  "`pct_at_max` is what predicts damage to the HIGH bucket, the way "
                                  "`pct_zero` predicts it for the low one; the sort keeps a tie "
                                  "block on the bottom cutpoint but drops one on the top cutpoint, "
                                  "so the two ends are not symmetric.\n"
                                  "- **n_distinct_values** — distinct values this year. Below K the "
                                  "year cannot be sorted into K buckets at all.\n"
                                  "- **quantiles_of_pure_zero** — cutpoints pinned at zero *this "
                                  "year*. `>= K-1` means the top bucket has degenerated into 'any "
                                  "firm with any activity'; `>= 2` means some bucket is empty and "
                                  "that month's return is NaN."
                              )),
    ],
)


@process(tag="derive_signals@v1", contract="derive_signals", author="refactor")
def derive_signals_v1(lc, cfg):
    import json

    import pandas as pd

    from functions.data_functions.process_lc import (
        filter_sum_activities_by_fiscal_year_quantiles,
    )
    from New_Pipeline._common import (
        count_firms,
        funnel_frame,
        histogram_frame,
        materiality_split_groups,
    )
    from New_Pipeline.boundary import pack_obj, unpack_obj

    C = json.loads(cfg["json"][0])
    signal_type = C.get("signal_type", "weights")   # backwards-compat default
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

    # ---- audit: sum_activities BEFORE the alpha-bound trim ------------------ #
    desc_before = lc_df["sum_activities"].describe()
    # (stage_name, describe() Series) pairs, in display order — the final table gets
    # one column per stage, built at the end once every stage has been captured.
    outlier_stages = [("before_alpha_bound", desc_before)]

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

    # ---- audit: sum_activities AFTER the alpha-bound trim ------------------- #
    desc_after = lc_df["sum_activities"].describe()
    outlier_stages.append(("after_alpha_bound", desc_after))

    # Captured BEFORE the materiality floor below, so the trim's own funnel row reports the
    # trim's effect alone and the floor's row reports the floor's.
    _n_firms_after_alpha = count_firms(lc_df["gvkey"])

    # ---- minimum initiatives before splitting by materiality ---------------- #
    # cfg.minimum_initatives_needed_to_split_by_materiality. The signal is a ratio of two
    # small integer counts, so a firm-year holding one initiative in the group scores
    # 1/1 = 1.0 and the sort reads it as maximal materiality on a single observation.
    # This floors the group's OWN total (material_G + immaterial_G) so the ratio is only
    # formed where it is estimable.
    #
    # Deliberately AFTER the alpha-bound trim: the trim's per-fiscal-year quantiles are
    # then computed on exactly the rows they always were, so its numbers above are
    # unchanged and the whole difference from an unfloored run is this filter.
    #
    # Rows are DROPPED rather than having their signals NaN'd. For a single-group design
    # (the only shape build_cfg allows here) the two are equivalent for the sort, but a
    # NaN'd row stays in lc_df and inflates n_firm_years / pct_zero / the histograms in
    # every audit below -- so the post-floor sparsity table would not describe the
    # post-floor sample.
    min_split = int(C.get("minimum_initatives_needed_to_split_by_materiality", 0))
    split_groups = materiality_split_groups(categories_dict)
    materiality_split_floor = None
    _n_firms_after_split_floor = None

    if len(split_groups) == 1:
        _g = split_groups[0]
        _total = lc_df[_g["columns"]].sum(axis=1)
        # The RATIO's atoms, not signal_i's: under signal_type="counts" signal_0 is a raw
        # level whose pct_at_max is ~1/N and uninformative, but the ratio is still what
        # this floor is about, so the table reports it either way.
        _ratio = lc_df[f"sum_with_{_g['material_index']}"] / _total
        _n0, _f0 = len(lc_df), count_firms(lc_df["gvkey"])

        # The full candidate strip regardless of the configured N, so the table answers
        # "what would N cost" and not only "what did N cost" -- otherwise the knob is
        # settable but not choosable. Configured N is included so its row always appears.
        _cands = sorted({1, 2, 3, 5, 10, 20} | ({min_split} if min_split > 0 else set()))
        _rows = []
        for _cand in _cands:
            _keep = _total >= _cand
            _r = _ratio[_keep]
            _r = _r[_r.notna()]
            _rows.append({
                "min_initiatives": _cand,
                "is_configured": bool(_cand == min_split),
                "n_firm_years": int(_keep.sum()),
                "pct_firm_years_kept": round(100.0 * _keep.sum() / max(_n0, 1), 1),
                "n_firms": count_firms(lc_df.loc[_keep, "gvkey"]),
                "pct_firms_kept": round(100.0 * count_firms(lc_df.loc[_keep, "gvkey"])
                                        / max(_f0, 1), 1),
                "pct_at_max": round(float((_r == 1.0).mean()) * 100, 1) if len(_r) else 0.0,
                "pct_zero": round(float((_r == 0.0).mean()) * 100, 1) if len(_r) else 0.0,
                "n_distinct_values": int(_r.nunique()),
                "median_group_total": float(_total[_keep].median()) if _keep.any() else 0.0,
            })
        materiality_split_floor = pd.DataFrame(_rows)

        if min_split > 0:
            lc_df = lc_df[_total >= min_split].copy()
            _n_firms_after_split_floor = count_firms(lc_df["gvkey"])
            print(f"[derive_signals] materiality split floor N={min_split} on "
                  f"{_g['group'][:60]}: kept {len(lc_df)}/{_n0} firm-years, "
                  f"{_n_firms_after_split_floor}/{_f0} firms")
            outlier_stages.append(
                ("after_min_initiatives", lc_df["sum_activities"].describe()))

    # ---- audit: sample filter funnel, this node's one stage -------------------------- #
    # Forwarded-plus-appended, the same way lc_raw_for_coverage is carried through below.
    # Note there is no inactive case: use_alpha_bound=False does NOT mean "no trim", it
    # means the hardcoded 0.2/0.05 bounds in the else branch above ran instead — so the
    # row is labelled with whichever bounds actually applied and is never null.
    _bounds = (f"alpha_bound={C['alpha_bound']}" if C["use_alpha_bound"]
               else "use_alpha_bound=False -> hardcoded lower=0.2 upper=0.05")
    # Two stages, in execution order. The floor's count is None (rendered as an em dash,
    # "did not run") whenever it is off or the design has no single material/immaterial
    # group -- never 0, which would read as "dropped every firm".
    funnel = funnel_frame([
        (
            f"Per-fiscal-year extreme-activity trim on sum_activities ({_bounds})", "LC",
            "02_derive_signals.py:246 / filter_sum_activities_by_fiscal_year_quantiles",
            _n_firms_after_alpha,
        ),
        (
            "Minimum initiatives to split by materiality "
            + (f"(N={min_split})" if min_split > 0 else "(off)"),
            "LC",
            "02_derive_signals.py / minimum_initatives_needed_to_split_by_materiality",
            _n_firms_after_split_floor,
        ),
    ])
    _prev_funnel = L.get("funnel")
    if _prev_funnel is not None:
        funnel = pd.concat([_prev_funnel, funnel], axis=0, ignore_index=True)

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
        if signal_type == "counts":
            # Level, not share: the signal IS the group's total initiative count.
            # sum_activities is still computed above — it drives the cell-18 alpha-bound
            # trim — it just doesn't divide anything here.
            lc_df[f"signal_{i}"] = lc_df[f"sum_with_{i}"]
        elif signal_type == "per_revenue":
            # Same numerator as "counts" (the group's total initiatives), scaled by annual
            # revenue in USD millions to strip out firm size. `sale_usd` is attached by the
            # add_sales merge in process_lc; build_cfg refuses this signal_type without it.
            #
            # A firm-year with no revenue becomes NaN and leaves the sort — that is the
            # intended behaviour and its cost is reported by the "Annual revenue merge —
            # coverage" audit on node 01. Non-positive revenue never reaches here: the
            # download enforces sale > 0 in SQL, because 0 would give inf (filling the TOP
            # bucket with pre-revenue shells) and a negative would flip the ratio's sign
            # (sending high-initiative firms to the BOTTOM bucket).
            lc_df[f"signal_{i}"] = lc_df[f"sum_with_{i}"] / lc_df["sale_usd"]
        else:
            lc_df[f"signal_{i}"] = lc_df[f"sum_with_{i}"] / lc_df["sum_activities"]

    # ---- optional: winsorise each signal within its fiscal year ------------- #
    # Cap above the (1 - p) quantile, floor below p, per rfyear. Runs BEFORE the audit
    # tables below so they describe the signal as actually used downstream.
    #
    # Grouped on rfyear alone, matching the convention
    # filter_sum_activities_by_fiscal_year_quantiles already uses. Deliberately NOT
    # (rfyear, Industry) even though that would match standardize_pivot's groups exactly
    # for a single-currency run: at industry_level=2 those cells get small enough that a
    # 1% quantile is interpolation noise rather than a percentile.
    #
    # Clipping is monotonic, so this cannot reorder anything and the quantile sort is
    # untouched. It acts only through standardize_pivot's (x - mean)/std -- see the
    # cfg comment in experiments.py.
    winsorise_pct = float(C.get("winsorise_signal_pct", 0.0))
    winsorise_stats = None
    if winsorise_pct > 0:
        _rows = []
        for col in signal_cols:
            g = lc_df.groupby("rfyear")[col]
            lo = g.transform(lambda x: x.quantile(winsorise_pct))
            hi = g.transform(lambda x: x.quantile(1.0 - winsorise_pct))
            before = lc_df[col]
            after = before.clip(lo, hi)
            _rows.append({
                "signal": col,
                "n_clipped_low": int((after > before).sum()),
                "n_clipped_high": int((after < before).sum()),
                "pct_clipped": round(100.0 * (after != before).sum() / max(before.notna().sum(), 1), 2),
                "std_before": float(before.std()),
                "std_after": float(after.std()),
                "max_before": float(before.max()),
                "max_after": float(after.max()),
            })
            lc_df[col] = after
        winsorise_stats = pd.DataFrame(_rows)
        winsorise_stats["signal"] = winsorise_stats["signal"].map(
            lambda c: C.get("lc_signals", {}).get(c, c))
        print(f"[derive_signals] winsorised {len(signal_cols)} signal(s) at "
              f"{winsorise_pct:.1%} per tail, per rfyear")

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

    # ---- audit: per-signal histogram (the shape describe() cannot show) ----- #
    # Binning lives in _common.histogram_frame so this node and prepare_panel's
    # raw-vs-standardised twin bin identically -- otherwise the two widgets would not be
    # comparable. Stage is named rather than left blank because prepare_panel shows two
    # stages of its own, and a reader needs to know which sample each panel is over.
    signal_histograms = histogram_frame(
        {signal_label[c]: lc_df[c].to_numpy(dtype="float64") for c in signal_cols},
        stage="raw signal (firm-year, post-trim)",
    )

    # ---- audit: signal correlation matrix ------------------------------------ #
    signal_correlation_matrix = (
        lc_df[signal_cols].corr(method="pearson")
        .rename(index=signal_label, columns=signal_label)
        .reset_index(names="signal")
    )

    # ---- audit: per-raw-column stats, grouped/tinted by which signal they feed ------ #
    category_cols = list(categories_dict.keys())
    category_column_stats = lc_df[category_cols].describe().T.reset_index(names="column")
    category_column_stats.insert(0, "signal", category_column_stats["column"].map(
        lambda c: signal_label.get(f"signal_{categories_dict[c]}", str(categories_dict[c]))
    ))
    # Sort by signal so same-tint rows are contiguous (stable within a signal, so the
    # categories_dict declaration order is preserved inside each block).
    category_column_stats = category_column_stats.sort_values("signal", kind="stable").reset_index(drop=True)

    # ---- audit: signal sparsity ---------------------------------------------------- #
    # Why a signal can be un-sortable: a quantile sort needs the values to be spread out,
    # and a signal that is exactly zero for most firm-years cannot be. The zero mass all
    # ties at the bottom, so the low bucket swells and the high bucket is drawn from
    # whatever thin non-zero tail is left — occasionally nothing at all. describe() does
    # not show this directly (a 99%-zero signal still reports a mean and a max), so the
    # share of exact zeros, the count and firm-coverage of the non-zero side, and how
    # many quantiles the zero mass alone would swallow are computed here.
    K_q = int(C["no_simple_quantiles"])
    n_rows = len(lc_df)
    firm_col = "gvkey" if "gvkey" in lc_df.columns else None
    sparsity_rows = []
    for col in signal_cols:
        s = lc_df[col]
        nz = s[s != 0]
        raw = lc_df[f"sum_with_{int(col.rsplit('_', 1)[1])}"]
        sparsity_rows.append({
            "signal": signal_label.get(col, col),
            "n_firm_years": n_rows,
            "n_zero": int((s == 0).sum()),
            "pct_zero": round(float((s == 0).mean()) * 100, 1),
            "n_nonzero": int(len(nz)),
            "n_firms_nonzero": int(lc_df.loc[s != 0, firm_col].nunique()) if firm_col else -1,
            "quantiles_of_pure_zero": int((s == 0).mean() * K_q),
            "mean_if_nonzero": round(float(nz.mean()), 4) if len(nz) else 0.0,
            "median_if_nonzero": round(float(nz.median()), 4) if len(nz) else 0.0,
            "max": round(float(s.max()), 4),
            # High-side mirror of the zero columns. A bounded ratio signal saturates at
            # its max the same way it piles up at 0, and the sort's `>` on the top
            # cutpoint EXCLUDES a tie block sitting on it while the `<=` on the bottom
            # cutpoint INCLUDES one — so a saturation atom damages the HIGH bucket
            # exactly as a zero atom damages the LOW bucket, and pct_zero alone cannot
            # see it. For a count signal the max is one firm, so pct_at_max is ~1/N and
            # simply uninformative rather than misleading.
            "n_at_max": int((s == s.max()).sum()),
            "pct_at_max": round(float((s == s.max()).mean()) * 100, 1),
            "quantiles_of_pure_max": int((s == s.max()).mean() * K_q),
            # Distinct values available to cut on. Below K the sort cannot fill K buckets
            # from this signal at all, however the zero share looks.
            "n_distinct_values": int(s.nunique()),
            "total_initiatives": int(raw.sum()),
        })
    signal_sparsity = (
        pd.DataFrame(sparsity_rows).sort_values("pct_zero", ascending=False).reset_index(drop=True)
    )

    # ---- audit: sparsity BY FISCAL YEAR --------------------------------------------- #
    # The pooled table above averages across regimes, so it can describe no actual year:
    # a signal that is 100% zero until 2019 and 30% zero after pools to ~60%, and neither
    # half of the sample looks like that. The sort runs per formation date and recomputes
    # its cutpoints from that date's cross-section alone, so per-YEAR support is what
    # decides whether a sort is possible — and whether restricting the sample rescues a
    # signal that looks dead pooled.
    year_col = "rfyear" if "rfyear" in lc_df.columns else None
    by_year_rows = []
    if year_col and firm_col:
        for col in signal_cols:
            for yr, grp in lc_df.groupby(year_col, sort=True):
                s = grp[col]
                n_zero_y = int((s == 0).sum())
                firms_nz = int(grp.loc[s != 0, firm_col].nunique())
                by_year_rows.append({
                    "signal": signal_label.get(col, col),
                    "rfyear": int(yr),
                    "n_firm_years": int(len(s)),
                    "n_zero": n_zero_y,
                    "pct_zero": round(float((s == 0).mean()) * 100, 1),
                    "n_nonzero": int(len(s) - n_zero_y),
                    "n_firms_nonzero": firms_nz,
                    # Firms available per bucket if this year were sorted into K_q buckets —
                    # compare against a minimum group size (cfg.esg_min_group_size is 5).
                    "firms_per_bucket": round(firms_nz / K_q, 1),
                    "quantiles_of_pure_zero": int((s == 0).mean() * K_q),
                    # High-side atom within this year -- see the pooled table's comment.
                    # Computed against THIS year's max, not the panel max, because the
                    # sort's top cutpoint is set from the local cross-section.
                    "pct_at_max": round(float((s == s.max()).mean()) * 100, 1),
                    "quantiles_of_pure_max": int((s == s.max()).mean() * K_q),
                    "n_distinct_values": int(s.nunique()),
                })
    signal_sparsity_by_year = pd.DataFrame(by_year_rows)

    # Fold the per-year detail into the pooled table as decision columns: the eligibility
    # rule ("enough firms to fill K buckets in a typical year") cannot be evaluated from
    # pooled counts alone, because the same total can come from many firms in one year or
    # few firms in every year.
    if not signal_sparsity_by_year.empty:
        agg = (
            signal_sparsity_by_year.groupby("signal")
            .agg(n_years=("rfyear", "count"),
                 median_firms_nonzero_per_year=("n_firms_nonzero", "median"),
                 min_firms_nonzero_per_year=("n_firms_nonzero", "min"))
            .reset_index()
        )
        agg["median_firms_per_bucket"] = (agg["median_firms_nonzero_per_year"] / K_q).round(1)
        worst = (
            signal_sparsity_by_year
            .loc[signal_sparsity_by_year.groupby("signal")["n_firms_nonzero"].idxmin(),
                 ["signal", "rfyear"]]
            .rename(columns={"rfyear": "worst_year"})
        )
        signal_sparsity = signal_sparsity.merge(
            agg.merge(worst, on="signal", how="left"), on="signal", how="left"
        )

    # Carry lc_raw_for_coverage forward untouched so esg_coverage can still read
    # from this node if the topology is later rewired to consume derive_signals'
    # output. Today only process_lc feeds esg_coverage — see registry.EDGES.
    return pack_obj({
        "lc": lc_df,
        "lc_raw_for_coverage": L.get("lc_raw_for_coverage"),
        "funnel": funnel,
        "funnel_checks": L.get("funnel_checks"),
        "sum_activities_outlier_stats": sum_activities_outlier_stats,
        "signal_summary_stats": signal_summary_stats,
        "signal_histograms": signal_histograms,
        "winsorise_stats": winsorise_stats,
        "signal_correlation_matrix": signal_correlation_matrix,
        "category_column_stats": category_column_stats,
        "signal_sparsity": signal_sparsity,
        "signal_sparsity_by_year": signal_sparsity_by_year,
        "materiality_split_floor": materiality_split_floor,
    })


NODE = Node(
    name="derive_signals",
    contract=CONTRACT,
    store=store,
    inputs=("lc", "cfg"),
    outputs=("out",),
)
