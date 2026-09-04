"""Shared pipeline infrastructure: the single ProcessStore and small schema helpers.

Kept out of the node modules so every ``New_Pipeline/nodes/<name>.py`` can import one
shared ``store`` (register + Node must use the same instance) without import cycles.
"""

from __future__ import annotations

import warnings
from pathlib import Path

from leonardo_nodes import ColumnSchema, ProcessStore

# ---- Silence pandas' ChainedAssignmentError FALSE POSITIVES -------------------- #
# pandas 2.2 emits a ChainedAssignmentError FutureWarning ("behaviour will change in
# pandas 3.0") for a plain, correct `df[col] = <series>` whenever the target frame has
# a low reference count — which is the norm inside a function body, i.e. inside every
# leonardo_nodes process. The heuristic is refcount-based, not lineage-based: it is a
# known pandas false positive (GH #56019 / #57734) that fires even for the recommended
# single-step assignment and cannot be silenced with `.copy()` or Copy-on-Write (both
# were verified to leave the warning count unchanged). The assignments themselves are
# correct — bit-for-bit parity against the notebook oracle proves the numbers are right.
# A genuine chained-assignment bug would instead surface as a wrong number (caught by
# parity) or, under real Copy-on-Write, as a hard ChainedAssignmentError (not a
# FutureWarning), so this narrow filter does not mask real problems. Scoped to exactly
# this message; every other warning still shows. Set here because _common is imported by
# every node module, so all entry points (run / dashboard / parity) inherit it.
warnings.filterwarnings("ignore", category=FutureWarning, message="ChainedAssignmentError")
try:  # under Copy-on-Write the same event is raised as ChainedAssignmentError itself
    from pandas.errors import ChainedAssignmentError as _ChainedAssignmentError

    warnings.filterwarnings("ignore", category=_ChainedAssignmentError)
except Exception:  # pragma: no cover - older/newer pandas without this symbol
    pass

# One content-addressed archive per project (gitignored).
STORE_ROOT = Path(__file__).resolve().parent.parent / ".leonardo_nodes_store"
store = ProcessStore(root=str(STORE_ROOT))


def cfg_schema() -> ColumnSchema:
    """Schema for the ``cfg`` external-input frame: a one-row frame whose ``json``
    column carries every scalar + JSON-encoded dict the run needs (config is data,
    not framework config — it must enter each Process as an input frame)."""
    return ColumnSchema(columns={"json": "str"}, non_null=["json"])


def open_schema() -> ColumnSchema:
    """Permissive data-frame schema (accepts any columns).

    Used at boundaries during the parity-first build so validation never blocks
    progress; real column/dtype schemas are tightened once each node's output is
    stable (see plan's hardening pass)."""
    return ColumnSchema(allow_extra=True)


def mktcap_filter_kwargs(cfg: dict) -> dict:
    """The market-cap-screen arguments for ``process_global_universe``, read from cfg.

    Extracted so the four interchangeable ESG Processes don't each carry a copy of the
    same blob, and so the screen's knobs are threaded from exactly one place. Passed as
    **keywords** deliberately: every other call site of ``process_global_universe`` in
    this repo passes positionally, which is how a new parameter silently mis-binds.

    ``.get()`` with the frozen defaults, not ``[...]``: a hand-built cfg (or one written
    before these keys existed) then still runs the original screen rather than raising.
    """
    return dict(
        market_cap_filter=cfg.get("market_cap_filter", "percent_total_mcap"),
        percentage_stocks_removed_if_percent_stocks_true=cfg.get(
            "percentage_stocks_removed_if_percent_stocks_true", 0.01
        ),
        floor_if_percent_stocks_true=cfg.get("floor_if_percent_stocks_true", 100e6),
    )


_MATERIALITY_PREFIXES = ("material__", "immaterial__")


def materiality_split_groups(categories_dict: dict) -> list:
    """Pair up the material/immaterial signal indices of a materiality design.

    Returns one dict per group -- ``{"group", "material_index", "immaterial_index",
    "columns"}``, ``columns`` being every material AND immaterial column of that group --
    ordered by ``material_index``. Returns ``[]`` when this is not a materiality design at
    all, so "is this a materiality design" and "what are its groups" are one question.

    Shared by ``build_cfg``'s validation of
    ``minimum_initatives_needed_to_split_by_materiality`` and by the filter itself in
    ``02_derive_signals``, so the two cannot disagree about what a group is.

    A design counts as materiality iff EVERY category column starts with ``material__`` or
    ``immaterial__``. Group identity is the column name with that prefix stripped
    (``material__total__SDG_1`` -> ``total__SDG_1``); two signal indices are one group iff
    their stripped-suffix SETS are equal and one side is wholly material while the other is
    wholly immaterial.

    Pairing on the suffix set rather than on index parity is deliberate: it holds for the
    ``_signals_from_groups`` designs, which emit material-then-immaterial per group (0/1,
    2/3, ...), AND for ``Combined_Material_Immaterial_4_Behavioural_Signals``, which emits
    all four immaterial signals first and all four material ones after (0-3 / 4-7). Index
    parity would silently mis-pair the latter.

    An unpaired index (a single-sided design like ``material_4_Behavioural_Signals``, where
    no immaterial counterpart is in ``categories_dict``) yields NO group -- there is no
    material/immaterial split to gate, which is what the caller needs to know.
    """
    if not categories_dict or not all(
        str(c).startswith(_MATERIALITY_PREFIXES) for c in categories_dict
    ):
        return []

    # index -> (set of stripped suffixes, set of prefixes seen)
    per_index: dict = {}
    for col, idx in categories_dict.items():
        col = str(col)
        prefix = next(p for p in _MATERIALITY_PREFIXES if col.startswith(p))
        suffixes, prefixes, cols = per_index.setdefault(int(idx), (set(), set(), []))
        suffixes.add(col[len(prefix):])
        prefixes.add(prefix)
        cols.append(col)

    groups = []
    for m_idx, (m_suffixes, m_prefixes, m_cols) in sorted(per_index.items()):
        # Only start from the material side, so each group is emitted exactly once.
        if m_prefixes != {"material__"}:
            continue
        for i_idx, (i_suffixes, i_prefixes, i_cols) in sorted(per_index.items()):
            if i_prefixes == {"immaterial__"} and i_suffixes == m_suffixes:
                groups.append({
                    "group": ",".join(sorted(m_suffixes)),
                    "material_index": m_idx,
                    "immaterial_index": i_idx,
                    "columns": m_cols + i_cols,
                })
                break
    return groups


def normalise_gvkeys(gvkeys: "pd.Series") -> "pd.Series":
    """Normalise a gvkey Series to the repo-standard zero-padded 6-char string.

    Bit-for-bit equivalent to the ``.astype(str).str.zfill(6)`` idiom used across the
    pipeline, extracted so the canonical gvkey format lives in exactly one place.
    Assumes the input is already an integer-valued gvkey (int or int-string); a
    float-valued column would keep its ``.0`` — matching the pre-refactor behaviour.
    """
    return gvkeys.astype(str).str.strip().str.zfill(6)   #didnt have .str.strip()



# ---- Sample filter funnel: shared measurement helpers -------------------------- #
# The funnel table (rendered by the sample_funnel_audit node) is assembled from rows
# CONTRIBUTED BY each node where a filter actually runs, rather than replayed from the
# raw data in one place. These three helpers are what the contributing nodes share so a
# "firms surviving" count means the same thing at every stage.
#
# Called from inside Process bodies (like mktcap_filter_kwargs above): a Process may not
# rely on module-level helpers of its OWN module, but importing another module inside the
# body is the established pattern and survives archived-Process replay.

def count_firms(gvkeys: "pd.Series") -> int:
    """Distinct firms in a gvkey Series, counted independently of gvkey FORMAT.

    The same firm is spelled three ways along the pipeline: ``process_lc`` casts to
    ``.astype(int).astype(str)`` ("1004"), ``process_global_universe`` casts to
    ``.astype(float).astype(int).astype(str)``, and the nodes then zero-pad to six
    ("001004") — while a raw Golden/WRDS column can still be float ("1004.0"). Comparing
    or counting those as strings silently reports different firms as distinct, which is
    the trap ``nodes/10_mktcap_filter_audit.py`` avoids by never joining on gvkey.
    Coercing to a number first makes every stage's count comparable to every other's.
    """
    import pandas as pd

    return int(pd.to_numeric(gvkeys, errors="coerce").nunique())


def funnel_frame(rows: list) -> "pd.DataFrame":
    """Pack ``(filter, acts_on, where, n_firms_after)`` tuples into the funnel contract.

    ``n_firms_after`` is nullable ``Int64``: ``None`` means "this stage did not run under
    this config" (a gated filter that is off) or "not applicable on this path", and the
    audit node renders it as an em dash. It does NOT mean zero, which is why the column
    cannot be a plain int.
    """
    import pandas as pd

    rows = list(rows)
    df = pd.DataFrame(
        [r[:3] for r in rows], columns=["filter", "acts_on", "where"]
    )
    # Built from the tuples, NOT from a column of the assembled frame: a mixed int/None
    # column arrives as float64 with NaN, and `NaN is None` is False, so reading it back
    # would raise on the int() cast rather than preserving the "did not run" marker.
    df["n_firms_after"] = pd.array(
        [None if r[3] is None else int(r[3]) for r in rows], dtype="Int64"
    )
    return df


def universe_funnel_rows(pre_frames, post_frames, global_universe, cfg, provider_label):
    """Universe-side funnel rows, shared by merge_esg_provider's four ESG Processes.

    ``pre_frames`` / ``post_frames`` are ``(usa, row, japan)`` tuples — the per-region
    universes before and after the ESG merge (``japan`` may be None).

    The two row-wise predicates ``process_global_universe`` applies before its market-cap
    screen (``process_data.py:171`` mktcap-notna, ``:179`` currency) are replayed here on
    the region frames rather than after the concat. That is exact — both are purely
    row-wise and concat preserves rows — and it is what keeps this measurement off the
    ~17M RoW/Japan daily rows a single-currency config cannot keep. Same argument, and
    the same motivation, as the replay in ``nodes/10_mktcap_filter_audit.py``.

    The market-cap screen itself is NOT replayed: it is the last of the three, so its
    survivors are directly observable on ``global_universe``. (Contrast node 10, which
    must replay because it needs *pre*-filter listing counts per currency-month — rows
    that no longer exist in the output. A single overall firm count needs no such work.)
    """
    import pandas as pd

    def _n(frames, mask=None):
        keys = []
        for f in frames:
            if f is None:
                continue
            s = f["gvkey"] if mask is None else f.loc[mask(f), "gvkey"]
            keys.append(pd.to_numeric(s, errors="coerce"))
        if not keys:
            return 0
        return int(pd.concat(keys, ignore_index=True).nunique())

    currency_filter = cfg["currency_filter"]
    has_ccy = currency_filter is not None and len(currency_filter) > 0
    method = cfg.get("market_cap_filter", "percent_total_mcap")

    return funnel_frame([
        (f"Compustat universe as loaded (secstat={cfg.get('security_status', 'active_only')}, "
         f"year <= {cfg['end_year']})",
         "Compustat universe", "03_load_universes / get_*_universe", _n(pre_frames)),
        (f"ESG provider merge ({provider_label})",
         "Compustat universe", "04_merge_esg_provider / get_*_merge_to_universe",
         _n(post_frames)),
        ("Drop rows missing mktcap",
         "Compustat universe", "process_data.py:171 / process_global_universe",
         _n(post_frames, lambda f: f["mktcap"].notna())),
        (f"Currency filter (curcdd in {list(currency_filter) if has_ccy else 'n/a'})",
         "Compustat universe", "process_data.py:179 / process_global_universe",
         _n(post_frames, lambda f: f["mktcap"].notna() & f["curcdd"].isin(currency_filter))
         if has_ccy else None),
        (f"Market-cap screen ({method})",
         "Compustat universe", "process_data.py:212 / process_global_universe",
         count_firms(global_universe["gvkey"])),
    ])


def standardized_sparsity_by_year(signals, signal_names, n_quantiles):
    """Sortability of the POST-standardization monthly panel, per signal per calendar year.

    The companion to node 02's ``signal_sparsity_by_year``, which measures the RAW
    ``signal_i`` on firm-years. Standardization changes what "sparse" means, so the two
    tables cannot share columns:

    * ``standardize_pivot`` z-scores within (rfyear, curcdd, Industry), so a raw 0 becomes
      ``-mean_g / std_g`` -- a DIFFERENT value in every group. The zero atom is shattered,
      which is why an exactly-empty bucket is rarer here than the raw ``pct_zero`` implies.
      ``pct_zero`` is also meaningless post-z-score (0 just means "at the group mean"), so
      the tie measures below replace it.
    * The unit is the (date, gvkey_iid) monthly cell, not the firm-year: this is literally
      what ``UnivariateQuantilePortfolio`` consumes, one cross-section per formation date.
      ``year`` is therefore the CALENDAR year of the formation month, not ``rfyear`` -- the
      point-in-time accounting lag offsets the two.

    Everything is computed per formation month and then aggregated over the months of a
    year, because the sort recomputes its cutpoints from one month's cross-section alone.
    """
    import pandas as pd

    K = int(n_quantiles)
    label = dict(signal_names or {})
    rows = []
    for col, wide in (signals or {}).items():
        if wide is None or getattr(wide, "empty", True):
            continue
        per_month = []
        for dt, month in wide.iterrows():
            s = month.dropna()
            n = len(s)
            if n == 0:
                continue
            counts = s.value_counts()
            per_month.append({
                "year": int(pd.Timestamp(dt).year),
                "n": n,
                "n_distinct": int(s.nunique()),
                # Biggest block of exactly-equal values: the post-standardization
                # generalisation of pct_zero. After z-scoring the damaging tie block is no
                # longer AT zero, so it has to be found by size rather than by value.
                "largest_tie_pct": 100.0 * int(counts.iloc[0]) / n,
                "pct_at_min": 100.0 * float((s == s.min()).mean()),
                "pct_at_max": 100.0 * float((s == s.max()).mean()),
            })
        if not per_month:
            continue
        pm = pd.DataFrame(per_month)
        for yr, g in pm.groupby("year", sort=True):
            med = float(g["n"].median())
            rows.append({
                "signal": label.get(col, col),
                "year": int(yr),
                "n_months": int(len(g)),
                "median_assets": int(round(med)),
                "min_assets": int(g["n"].min()),
                "assets_per_bucket": round(med / K, 1),
                "median_n_distinct": int(g["n_distinct"].median()),
                "largest_tie_pct": round(float(g["largest_tie_pct"].median()), 1),
                "worst_month_tie_pct": round(float(g["largest_tie_pct"].max()), 1),
                "pct_at_min": round(float(g["pct_at_min"].median()), 1),
                "pct_at_max": round(float(g["pct_at_max"].median()), 1),
            })
    return pd.DataFrame(rows)


HISTOGRAM_BINS = 40


def histogram_frame(values_by_name, *, bins=HISTOGRAM_BINS, stage=None):
    """Tidy long histogram frame: one row per (name, bin), ready for BundleHistogramViz.

    ``values_by_name`` is ``{display name: 1-D array-like}``; insertion order is preserved
    and becomes the panel order on the dashboard.

    Bins are per-NAME over that name's own finite ``[min, max]``, not a shared range.
    Signal ranges differ by construction -- a "weights" share lives in [0, 1], a "counts"
    or "per_revenue" signal does not, and a z-score is unbounded and centred on 0 -- so a
    shared range would leave most panels empty. The trade-off is that bin WIDTH differs
    between panels, which is why ``pct`` (share of observations) is the plotted quantity
    rather than the raw count.

    Pass ``stage`` to tag every row with a comparison stage (e.g. raw vs standardised);
    the viz turns distinct stages into rows of the panel grid.
    """
    import numpy as np
    import pandas as pd

    rows = []
    for name, values in (values_by_name or {}).items():
        v = np.asarray(values, dtype="float64").ravel()
        v = v[np.isfinite(v)]
        if v.size == 0:
            continue
        lo, hi = float(v.min()), float(v.max())
        if hi <= lo:
            # Degenerate (constant, usually all-zero): one bin, so the panel shows a
            # single full-height bar instead of raising inside np.histogram.
            edges = np.array([lo, lo + 1.0])
        else:
            edges = np.linspace(lo, hi, int(bins) + 1)
        counts, edges = np.histogram(v, bins=edges)
        n = int(counts.sum())
        for i, c in enumerate(counts):
            row = {
                "signal": str(name),
                "bin_left": float(edges[i]),
                "bin_right": float(edges[i + 1]),
                "bin_center": float((edges[i] + edges[i + 1]) / 2),
                "n": int(c),
                "pct": (100.0 * int(c) / n) if n else 0.0,
            }
            if stage is not None:
                row["stage"] = str(stage)
            rows.append(row)

    cols = ["signal", "bin_left", "bin_right", "bin_center", "n", "pct"]
    if stage is not None:
        cols.insert(1, "stage")
    return pd.DataFrame(rows, columns=cols)


def raw_vs_standardized_histograms(global_universe, signals, signal_names,
                                   bins=HISTOGRAM_BINS):
    """Before/after histograms of the sorting signals, across ``standardize_pivot``.

    Two stages, one tidy frame (see ``histogram_frame``), for the raw-vs-standardised
    panel grid on the ``prepare_panel`` dashboard section.

    Both stages are measured on the **same unit and the same cells**: the (date,
    gvkey_iid) monthly cross-section cells that survive into the sort. That is what makes
    the comparison honest, and it takes two deliberate steps:

    * the "before" values are re-pivoted out of ``global_universe``, which still carries
      the RAW signal columns — ``standardize_pivot`` returns new frames and never mutates
      its input, and this is the same pivot ``dropna_std_cols_and_build_pivots`` builds.
    * that raw pivot is then masked by the standardised pivot's own NaN pattern. Without
      it the "before" panel would be over MORE cells than the "after": the cross-signal
      NaN mask is applied to the pivots only, and z-scoring adds NaNs of its own wherever
      a standardisation group is a singleton (std=0). Masking makes the two cell-for-cell
      identical, so a shape difference is the z-score and nothing else.

    Note the units are monthly cells, not firm-years, so this is NOT directly comparable
    to node 02's raw firm-year histogram: a firm-year appears here roughly twelve times
    per share issue. The raw stage here is the like-for-like baseline for the standardised
    one; node 02's is the like-for-like baseline for the trim.
    """
    import numpy as np
    import pandas as pd

    label = dict(signal_names or {})
    raw_vals: dict = {}
    std_vals: dict = {}
    for col, std in (signals or {}).items():
        if std is None or getattr(std, "empty", True):
            continue
        name = str(label.get(col, col))
        std_vals[name] = std.to_numpy(dtype="float64").ravel()
        if col in getattr(global_universe, "columns", []):
            raw = global_universe.pivot(index="date", columns="gvkey_iid", values=col)
            raw = raw.reindex(index=std.index, columns=std.columns).where(std.notna())
            raw_vals[name] = raw.to_numpy(dtype="float64").ravel()

    # The masking above should make the two stages cover the SAME cells. It is true by
    # construction (the standardised pivot is derived FROM the raw one, so its non-NaN set
    # can only be a subset), but printed rather than asserted: a mismatch makes the
    # before/after comparison misleading without corrupting anything -- `pct` is
    # normalised within each stage -- and an audit widget should not be able to fail a run.
    for _name in std_vals:
        if _name in raw_vals:
            _nb = int(np.isfinite(np.asarray(raw_vals[_name], dtype="float64")).sum())
            _na = int(np.isfinite(np.asarray(std_vals[_name], dtype="float64")).sum())
            flag = "" if _nb == _na else "   <-- MISMATCH, stages are not the same cells"
            print(f"[prepare_panel] histogram cells {_name}: before={_nb} after={_na}{flag}")

    frames = []
    # Raw first: stage order here is the panel-grid ROW order on the dashboard, and
    # "before" above "after" is the only arrangement that reads correctly.
    if raw_vals:
        frames.append(histogram_frame(raw_vals, bins=bins, stage="before — raw"))
    if std_vals:
        frames.append(histogram_frame(std_vals, bins=bins, stage="after — standardised"))
    if not frames:
        return histogram_frame({}, bins=bins, stage="before — raw")
    return pd.concat(frames, ignore_index=True)


# ---- Geography: gvkey -> country, and share-of-column composition tables -------- #
# The Compustat extracts carry NO country field. The USA file has a `cusip`, the RoW and
# Japan files an `isin`, and `process_global_universe` drops both before the sort ever sees
# the frame -- so "where are these firms" is not answerable from the universe alone.
#
# `data/company_database_*.parquet` is the gvkey -> (loc, MacroRegion) mapping the LC
# dataset's own `loc` column is drawn from. Resolving universe locations through it (rather
# than through an ISIN prefix, or the CINS letter the 10% of USA gvkeys with a foreign issuer
# carry) makes the universe geography and the final-sample geography the SAME definition, so
# the two are directly comparable -- which is the only reason to show them together.
#
# Called from inside Process bodies, like mktcap_filter_kwargs and count_firms above.

_COMPANY_DB_GLOB = "company_database_*.parquet"


def gvkey_locations() -> "pd.DataFrame":
    """``gvkey_num`` -> ``(loc, MacroRegion)``, from the newest company database on disk.

    Joined on a NUMERIC gvkey for the reason ``count_firms`` documents: the same firm is
    spelled "1004", "001004" and "1004.0" at different stages of this pipeline, and a
    string join silently matches nothing rather than erroring.

    Audit-only, so a missing file returns an EMPTY frame (every location then reads
    "(unmapped)") rather than failing a run over a widget.
    """
    import pandas as pd

    cols = ["gvkey_num", "loc", "MacroRegion"]
    root = Path(__file__).resolve().parent.parent / "data"
    files = sorted(root.glob(_COMPANY_DB_GLOB))
    if not files:
        print(f"[geography] no {_COMPANY_DB_GLOB} under {root} — locations unresolved")
        return pd.DataFrame(columns=cols)
    path = files[-1]  # dated filenames, so the last one sorted is the newest
    db = pd.read_parquet(path, columns=["gvkey", "loc", "MacroRegion"])
    db["gvkey_num"] = pd.to_numeric(db["gvkey"], errors="coerce")
    db = db.dropna(subset=["gvkey_num", "loc"]).drop_duplicates(subset=["gvkey_num"])
    print(f"[geography] {path.name}: {len(db)} gvkeys carry a location")
    return db[cols].reset_index(drop=True)


def firm_counts(frame, by: str, *, gvkey_col: str = "gvkey", name: str = "firms"):
    """Distinct firms per group, plus that group's share of the column.

    ``pct_<name>`` is the share of the SUM of the group counts, not of the distinct firm
    total, so the column always sums to 100 and matches the pie the widget draws from it.
    The two differ only when one firm appears under more than one group -- possible for
    currency (a gvkey listed in two currency areas), never for ``loc``, which the lookup
    resolves to exactly one country per gvkey.

    Missing group values become the literal ``"(unmapped)"`` rather than being dropped:
    for geography the unmapped share IS the number a reader needs to judge the rest.
    """
    import pandas as pd

    d = pd.DataFrame({
        by: frame[by].where(frame[by].notna(), "(unmapped)").astype(str),
        "_gv": pd.to_numeric(frame[gvkey_col], errors="coerce"),
    }).dropna(subset=["_gv"])
    out = d.groupby(by, dropna=False)["_gv"].nunique().rename(name).reset_index()
    total = int(out[name].sum())
    out[f"pct_{name}"] = (100.0 * out[name] / total).round(2) if total else 0.0
    # firms desc, then label asc: without the tiebreak the row order of equal-sized groups
    # is groupby's hash order, which would churn the exported parquet between runs.
    return out.sort_values([name, by], ascending=[False, True]).reset_index(drop=True)
