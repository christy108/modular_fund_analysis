"""Signal-value correlation diagnostic.

Correlation matrix between the standardized SIGNAL VALUES (not portfolio returns).
Reads the already-computed long-format ``signal_df`` (``prep.global_long_df``), which has
one column per signal (``signal_0..n`` plus the ESG column, e.g. ``esg_refinitive``) at the
firm-month level. Nothing is recomputed.

For the ESG signal it can include BOTH:
  * ``esg_standardised``     -- the z-scored ESG signal (as used in the sort), from ``signal_df``
  * ``esg_non_standardised`` -- the raw 0-1 ESG rating (NOT standardized by industry/year),
                                supplied via ``raw_esg_df`` (from ``global_universe[esg_col]``)
This is purely for the correlation diagnostic; the rest of the pipeline is unchanged.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def signal_correlation(
    signal_df,
    signal_names,
    *,
    raw_esg_df=None,
    esg_key=None,
    method="pearson",
    save_path=None,
    csv_path=None,
    title="Signal correlation (standardized values)",
    show=True,
):
    """Correlation matrix between the standardized signal values in ``signal_df``.

    Parameters
    ----------
    signal_df : pd.DataFrame
        Long-format firm-month signals (``prep.global_long_df``): one column per signal
        (``signal_0..n`` + the ESG column) plus ``date``/``gvkey_iid``.
    signal_names : Mapping[str, str]
        Signal key -> display name. Also selects/orders the signal columns to correlate.
    raw_esg_df : pd.DataFrame, optional
        Long-format raw (0-1, NON-standardized) ESG, with columns ``date``, ``gvkey_iid``,
        ``esg_non_standardised``. If given, an extra ``esg_non_standardised`` column is added
        to the matrix (the standardized ESG is labelled ``esg_standardised``).
    esg_key : str, optional
        The ESG signal key in ``signal_df``; auto-detected (key starting with ``"esg"``).
    method, save_path, csv_path, title, show : see module usage.

    Returns
    -------
    pd.DataFrame
        Square correlation matrix, labelled with display names.
    """
    signal_cols = [k for k in signal_names if k in signal_df.columns]
    if not signal_cols:
        raise ValueError("No signal columns found to correlate.")

    if esg_key is None:
        _esg = [k for k in signal_cols if str(k).startswith("esg")]
        esg_key = _esg[0] if _esg else None

    # Build the value panel keyed by (date, gvkey_iid) so we can merge the raw ESG.
    keep = [c for c in ("date", "gvkey_iid") if c in signal_df.columns]
    panel = signal_df[keep + signal_cols].copy()

    # Label columns: LC signals -> display name; standardized ESG -> "esg_standardised".
    rename = {
        k: ("esg_standardised" if k == esg_key else signal_names.get(k, k))
        for k in signal_cols
    }
    panel = panel.rename(columns=rename)
    value_cols = [rename[k] for k in signal_cols]

    # Optionally append the raw (0-1) non-standardized ESG, merged on (date, gvkey_iid).
    if raw_esg_df is not None:
        need = {"date", "gvkey_iid", "esg_non_standardised"}
        missing = need - set(raw_esg_df.columns)
        if missing:
            raise ValueError(f"raw_esg_df missing columns: {sorted(missing)}")
        panel = panel.merge(
            raw_esg_df[["date", "gvkey_iid", "esg_non_standardised"]],
            on=["date", "gvkey_iid"], how="left",
        )
        value_cols = value_cols + ["esg_non_standardised"]

    corr = panel[value_cols].corr(method=method)

    if csv_path is not None:
        csv_path = Path(csv_path)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        corr.to_csv(csv_path)

    # --- annotated heatmap (pure matplotlib; no seaborn dependency) ---
    n = len(value_cols)
    fig, ax = plt.subplots(figsize=(1.1 * n + 2, 1.1 * n + 2))
    im = ax.imshow(corr.values, vmin=-1, vmax=1, cmap="coolwarm", aspect="auto")

    ax.set_xticks(range(n))
    ax.set_xticklabels(value_cols, rotation=45, ha="right")
    ax.set_yticks(range(n))
    ax.set_yticklabels(value_cols)

    for i in range(n):
        for j in range(n):
            v = corr.values[i, j]
            ax.text(
                j, i, f"{v:.2f}", ha="center", va="center",
                color="white" if abs(v) > 0.55 else "black", fontsize=9,
            )

    ax.set_title(title)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="correlation")
    fig.tight_layout()

    if save_path is not None:
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    if show:
        plt.show()
    else:
        plt.close(fig)

    return corr
