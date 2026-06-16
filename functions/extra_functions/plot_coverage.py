"""Coverage diagnostics — intentionally isolated from the main pipeline.

Plots, over time, how much of the *investable universe* the analysis *sample*
covers, on two axes:

  * **Market-cap coverage** = sample market cap / universe market cap
  * **Name coverage**       = sample distinct names / universe distinct names

where the "universe" is the full ``process_global_universe`` output (after the
currency + ``mktcap_covered`` filters) and the "sample" is the set of gvkeys that
actually entered the portfolio analysis (``global_universe`` after
``prepare_univariate_sorting_inputs`` intersects it with the LC golden data).

Currency safety
---------------
Coverage is a *ratio*, so a single common currency must be used for both the
numerator and the denominator. We use ``global_universe['mktcap']`` which the
pipeline expresses in ONE currency per run:
  * ``convert_to_USD=True``  -> every row is USD (summable across currencies)
  * ``convert_to_USD=False`` -> ``currency_filter`` restricts the run to a single
    currency, so ``mktcap`` is that one local currency (still summable)
To make the guarantee explicit, :func:`compute_coverage_over_time` REFUSES to sum
across multiple currencies when ``convert_to_USD=False`` (raises ``ValueError``),
so we never accidentally add e.g. JPY + USD market caps.

Nothing here is imported by the core pipeline; it only reads already-computed
objects, so it cannot change any analysis result.
"""

from __future__ import annotations

from typing import Iterable

import matplotlib.pyplot as plt
import pandas as pd


def compute_coverage_over_time(
    full_universe: pd.DataFrame,
    sample_gvkeys: Iterable[str],
    *,
    convert_to_USD: bool,
    mktcap_col: str = "mktcap",
    currency_col: str = "curcdd",
    gvkey_col: str = "gvkey",
    iid_col: str = "iid",
    date_col: str = "date",
) -> pd.DataFrame:
    """Monthly name- and market-cap coverage of ``sample_gvkeys`` within ``full_universe``.

    Returns a DataFrame indexed by month (Timestamp) with columns:
    ``mktcap_total, mktcap_sample, names_total, names_sample,
    mktcap_coverage_pct, name_coverage_pct``.
    """
    needed = [date_col, gvkey_col, currency_col, mktcap_col]
    missing = [c for c in needed if c not in full_universe.columns]
    if missing:
        raise ValueError(f"full_universe is missing columns: {missing}")

    df = full_universe[[c for c in [date_col, gvkey_col, iid_col, currency_col, mktcap_col]
                        if c in full_universe.columns]].copy()
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

    # --- collapse to the last trading day per (month, listing) to avoid double-counting ---
    df["ym"] = df[date_col].dt.to_period("M")
    listing_keys = ["ym", gvkey_col] + ([iid_col] if iid_col in df.columns else [])
    df = df.sort_values(date_col).groupby(listing_keys, as_index=False).last()

    sample = {str(g) for g in sample_gvkeys}
    df["in_sample"] = df[gvkey_col].astype(str).isin(sample)

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
    out["mktcap_coverage_pct"] = 100.0 * out["mktcap_sample"] / out["mktcap_total"]
    out["name_coverage_pct"] = 100.0 * out["names_sample"] / out["names_total"]
    out.index = out.index.to_timestamp()
    return out


def plot_coverage(
    full_universe: pd.DataFrame,
    sample_gvkeys: Iterable[str],
    *,
    convert_to_USD: bool,
    currency_label: str | None = None,
    title: str = "Sample coverage of the investable universe",
    save_path=None,
    show: bool = True,
) -> pd.DataFrame:
    """Compute and plot market-cap & name coverage over time. Returns the coverage table."""
    cov = compute_coverage_over_time(
        full_universe, sample_gvkeys, convert_to_USD=convert_to_USD
    )
    cur = currency_label or ("USD" if convert_to_USD else "local currency")

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(cov.index, cov["mktcap_coverage_pct"],
            color="C0", lw=2, label=f"Market-cap coverage ({cur})")
    ax.plot(cov.index, cov["name_coverage_pct"],
            color="C1", lw=2, ls="--", label="Name coverage")

    mc_mean = cov["mktcap_coverage_pct"].mean()
    nm_mean = cov["name_coverage_pct"].mean()
    ax.axhline(mc_mean, color="C0", ls=":", alpha=0.5)
    ax.axhline(nm_mean, color="C1", ls=":", alpha=0.5)
    ax.text(cov.index[0], mc_mean + 1, f"mean {mc_mean:.1f}%", color="C0", fontsize=9)
    ax.text(cov.index[0], nm_mean + 1, f"mean {nm_mean:.1f}%", color="C1", fontsize=9)

    ax.set_ylim(0, 100)
    ax.set_ylabel("Coverage (%)")
    ax.set_xlabel("Date")
    ax.set_title(title)
    ax.grid(alpha=0.3)
    ax.legend(loc="best")
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
    sample_universe: pd.DataFrame,
    *,
    currency_filter,
    mktcap_covered: float,
    esg_choice: str,
    convert_to_USD: bool,
    region_analysis: str = "",
    gvkey_col: str = "gvkey",
    save_path=None,
    show: bool = True,
) -> pd.DataFrame:
    """Notebook-friendly wrapper: rebuild the FULL universe, then plot coverage.

    ``sample_universe`` is the post-analysis ``global_universe`` (already filtered to
    the LC-matched names by ``prepare_univariate_sorting_inputs``); its gvkeys define
    the sample. The full universe is rebuilt from the regional universes via
    ``process_global_universe`` (cell 25 overwrites the original full ``global_universe``).
    """
    # Imported lazily so this diagnostic module has no import-time effect on the pipeline.
    from functions.data_functions.process_data import process_global_universe

    full_universe = process_global_universe(
        usa_universe, row_universe, japan_universe,
        currency_filter, mktcap_covered, esg_choice,
    )
    full_universe[gvkey_col] = full_universe[gvkey_col].astype(str).str.zfill(6)
    sample_gvkeys = set(sample_universe[gvkey_col].astype(str).str.zfill(6).unique())

    currency_label = "USD" if convert_to_USD else (
        currency_filter[0] if currency_filter else None
    )
    title = "Sample coverage of investable universe"
    if region_analysis:
        title += f" — {region_analysis}"

    return plot_coverage(
        full_universe,
        sample_gvkeys,
        convert_to_USD=convert_to_USD,
        currency_label=currency_label,
        title=title,
        save_path=save_path,
        show=show,
    )
