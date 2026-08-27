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
