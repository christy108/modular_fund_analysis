"""Coverage diagnostics — intentionally isolated from the main pipeline.

Plots, over time, how much of the *investable universe* the analysis *sample*
covers, on two axes:

  * **Market-cap coverage** = sample market cap / universe market cap
  * **Name coverage**       = sample distinct names / universe distinct names

where the "universe" is the full ``process_global_universe`` output (after the
currency + ``mktcap_covered`` filters) and the "sample" is the EXACT monthly panel
that entered the portfolio sorts.

EXACT sample = the masked analysis panel
----------------------------------------
The sample is taken from ``global_returns`` (or any signal pivot), i.e. the
``date x gvkey_iid`` matrix returned by ``prepare_univariate_sorting_inputs`` AFTER
``apply_cross_signal_nan_mask``. A listing counts as "in sample" in a given month
**iff its cell is non-NaN that month** — exactly the rule behind the "Total Stocks
without NAN" plot. This is the real sample (post LC-intersection, post
standardization dropna, post cross-signal mask), so the curves and the count
subplot match that plot to the listing.

Year-aware (NOT membership)
---------------------------
Because masking is per (month, listing), a company contributes only in the months it
actually has a usable signal. As LC report coverage expands over time the sample
(and therefore coverage) grows across the window — it is deliberately not a static
"ever-qualifies" set.

Currency safety
---------------
Coverage is a *ratio*, so a single common currency must be used for numerator and
denominator. We use ``full_universe['mktcap']`` which the pipeline expresses in ONE
currency per run:
  * ``convert_to_USD=True``  -> every row is USD (summable across currencies)
  * ``convert_to_USD=False`` -> ``currency_filter`` restricts the run to a single
    currency, so ``mktcap`` is that one local currency (still summable)
:func:`compute_coverage_over_time` REFUSES to sum across multiple currencies when
``convert_to_USD=False`` (raises ``ValueError``).

Nothing here is imported by the core pipeline; it only reads already-computed
objects, so it cannot change any analysis result.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd


def _sample_gvkey_iid_by_month(sample_panel: pd.DataFrame) -> dict:
    """Map each calendar month (Period[M]) -> set of non-NaN ``gvkey_iid`` that month.

    ``sample_panel`` is a wide ``date x gvkey_iid`` matrix (e.g. ``global_returns`` or
    ``signals['signal_2']``). Non-NaN cell == listing is in the analysis sample that month.
    """
    panel = sample_panel.copy()
    panel.index = pd.to_datetime(panel.index)
    months = panel.index.to_period("M")
    by_month: dict = {}
    for period, (_, row) in zip(months, panel.iterrows()):
        present = row.dropna().index
        by_month.setdefault(period, set()).update(str(c) for c in present)
    return by_month


def compute_coverage_over_time(
    full_universe: pd.DataFrame,
    sample_panel: pd.DataFrame,
    *,
    convert_to_USD: bool,
    mktcap_col: str = "mktcap",
    currency_col: str = "curcdd",
    gvkey_col: str = "gvkey",
    iid_col: str = "iid",
    date_col: str = "date",
) -> pd.DataFrame:
    """Monthly, exact name- and market-cap coverage of the analysis sample within ``full_universe``.

    ``sample_panel`` is the masked ``date x gvkey_iid`` panel (``global_returns`` or a
    signal pivot). A listing is "in sample" in a month iff its panel cell is non-NaN.

    Returns a DataFrame indexed by month (Timestamp) with columns:
    ``mktcap_total, mktcap_sample, names_total, names_sample, issues_sample,
    mktcap_coverage_pct, name_coverage_pct``.
    ``issues_sample`` is the exact non-NaN column count of ``sample_panel`` that month
    (issue / share-class level), so it lines up with the "Total Stocks without NAN" plot.
    """
    needed = [date_col, gvkey_col, currency_col, mktcap_col]
    missing = [c for c in needed if c not in full_universe.columns]
    if missing:
        raise ValueError(f"full_universe is missing columns: {missing}")
    if iid_col not in full_universe.columns:
        raise ValueError(
            f"full_universe is missing column {iid_col!r}; needed to rebuild gvkey_iid "
            "for an exact match against the analysis panel."
        )

    df = full_universe[[date_col, gvkey_col, iid_col, currency_col, mktcap_col]].copy()
    df = df.dropna(subset=[mktcap_col])
    df[date_col] = pd.to_datetime(df[date_col])

    # --- currency-safety guard: never sum market caps across currencies unconverted ---
    currencies = sorted(df[currency_col].dropna().unique())
    if not convert_to_USD and len(currencies) > 1:
        raise ValueError(
            "Refusing to sum market caps across multiple currencies "
            f"{currencies} while convert_to_USD=False. Use a single-currency "
            "currency_filter or set convert_to_USD=True so mktcap is in one currency."
        )

    # --- collapse universe to last trading day per (month, listing) to avoid double-counting ---
    df["ym"] = df[date_col].dt.to_period("M")
    df["gvkey_iid"] = df[gvkey_col].astype(str) + "_" + df[iid_col].astype(str)
    df = df.sort_values(date_col).groupby(["ym", "gvkey_iid"], as_index=False).last()

    # --- exact sample membership: (month, gvkey_iid) non-NaN in the masked analysis panel ---
    sample_by_month = _sample_gvkey_iid_by_month(sample_panel)
    df["in_sample"] = [
        gi in sample_by_month.get(ym, set())
        for ym, gi in zip(df["ym"], df["gvkey_iid"])
    ]

    g = df.groupby("ym")
    out = pd.DataFrame(
        {
            "mktcap_total": g[mktcap_col].sum(),
            "mktcap_sample": g.apply(
                lambda d: d.loc[d["in_sample"], mktcap_col].sum(), include_groups=False
            ),
            "names_total": g[gvkey_col].nunique(),
            "names_sample": g.apply(
                lambda d: d.loc[d["in_sample"], gvkey_col].nunique(), include_groups=False
            ),
        }
    )

    # Exact issue-level sample count straight from the panel (matches the non-NaN plot).
    issues = pd.Series(
        {ym: len(s) for ym, s in sample_by_month.items()}, name="issues_sample"
    )
    issues.index = issues.index.astype("period[M]")
    out = out.join(issues)

    out["mktcap_coverage_pct"] = 100.0 * out["mktcap_sample"] / out["mktcap_total"]
    out["name_coverage_pct"] = 100.0 * out["names_sample"] / out["names_total"]
    out.index = out.index.to_timestamp()
    return out


def plot_coverage(
    full_universe: pd.DataFrame,
    sample_panel: pd.DataFrame,
    *,
    convert_to_USD: bool,
    currency_label: str | None = None,
    title: str = "Sample coverage of the investable universe",
    save_path=None,
    show: bool = True,
) -> pd.DataFrame:
    """Compute and plot exact market-cap & name coverage, plus a sample-count subplot. Returns the table."""
    cov = compute_coverage_over_time(
        full_universe, sample_panel, convert_to_USD=convert_to_USD
    )
    cur = currency_label or ("USD" if convert_to_USD else "local currency")

    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(11, 8), sharex=True,
        gridspec_kw={"height_ratios": [2, 1]},
    )

    # --- top: coverage ratios ---
    ax.plot(cov.index, cov["mktcap_coverage_pct"],
            color="C0", lw=2, label=f"Market-cap coverage ({cur})")
    ax.plot(cov.index, cov["name_coverage_pct"],
            color="C1", lw=2, ls="--", label="Name coverage")

    mc_mean = cov["mktcap_coverage_pct"].mean()
    nm_mean = cov["name_coverage_pct"].mean()
    ax.axhline(mc_mean, color="C0", ls=":", alpha=0.4)
    ax.axhline(nm_mean, color="C1", ls=":", alpha=0.4)

    ax.set_ylim(0, 100)
    ax.set_ylabel("Coverage (%)")
    ax.set_title(title)
    ax.grid(alpha=0.3)
    ax.legend(loc="best")

    # --- bottom: absolute sample size (matches the "Total Stocks without NAN" plot) ---
    ax2.plot(cov.index, cov["issues_sample"],
             color="C2", lw=2, label="Sample stocks (non-NaN, issue level)")
    ax2.plot(cov.index, cov["names_sample"],
             color="C3", lw=2, ls="--", label="Sample distinct names (gvkey)")
    ax2.plot(cov.index, cov["names_total"],
             color="grey", lw=1.5, ls=":", label="Universe distinct names")
    ax2.set_ylabel("Count")
    ax2.set_xlabel("Date")
    ax2.set_ylim(bottom=0)
    ax2.grid(alpha=0.3)
    ax2.legend(loc="best")

    fig.tight_layout()

    if save_path is not None:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    if show:
        plt.show()
    else:
        plt.close(fig)
    return cov


def plot_universe_coverage_from_regions(
    usa_universe: pd.DataFrame,
    row_universe: pd.DataFrame,
    japan_universe: pd.DataFrame | None,
    sample_panel: pd.DataFrame,
    *,
    currency_filter,
    mktcap_covered: float,
    esg_choice: str,
    convert_to_USD: bool,
    region_analysis: str = "",
    gvkey_col: str = "gvkey",
    iid_col: str = "iid",
    save_path=None,
    show: bool = True,
) -> pd.DataFrame:
    """Notebook-friendly wrapper: rebuild the FULL universe, then plot exact coverage.

    ``sample_panel`` is the masked analysis panel (``global_returns`` or a signal pivot,
    a ``date x gvkey_iid`` matrix). The full universe is rebuilt from the regional
    universes via ``process_global_universe``. ``gvkey`` is zero-padded to 6 digits on
    both sides so the rebuilt ``gvkey_iid`` matches the panel's columns exactly.
    """
    # Imported lazily so this diagnostic module has no import-time effect on the pipeline.
    from functions.data_functions.process_data import process_global_universe

    full_universe = process_global_universe(
        usa_universe, row_universe, japan_universe,
        currency_filter, mktcap_covered, esg_choice,
    )
    full_universe[gvkey_col] = full_universe[gvkey_col].astype(str).str.zfill(6)

    currency_label = "USD" if convert_to_USD else (
        currency_filter[0] if currency_filter else None
    )
    title = "Sample coverage of investable universe"
    if region_analysis:
        title += f" — {region_analysis}"

    return plot_coverage(
        full_universe,
        sample_panel,
        convert_to_USD=convert_to_USD,
        currency_label=currency_label,
        title=title,
        save_path=save_path,
        show=show,
    )
