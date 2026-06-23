"""Signal-value correlation diagnostic.

Correlation matrix between the standardized SIGNAL VALUES (not portfolio returns).
Reads the already-computed long-format ``signal_df`` (``prep.global_long_df``), which has
one column per signal (``signal_0..n`` plus the ESG column, e.g. ``esg_refinitive``) at the
firm-month level. Nothing is recomputed. Used at the end of Main.ipynb.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def signal_correlation(
    signal_df,
    signal_names,
    *,
    signal_cols=None,
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
    signal_cols : list[str], optional
        Explicit signal columns; defaults to the keys of ``signal_names`` present in ``signal_df``.
    method : str
        Correlation method passed to ``DataFrame.corr`` ("pearson"/"spearman"/"kendall").
    save_path, csv_path : path-like, optional
        If given, save the heatmap PNG / correlation CSV.

    Returns
    -------
    pd.DataFrame
        Square correlation matrix, labelled with display names.
    """
    if signal_cols is None:
        signal_cols = [k for k in signal_names if k in signal_df.columns]
    missing = [c for c in signal_cols if c not in signal_df.columns]
    if missing:
        raise ValueError(f"signal_df is missing signal columns: {missing}")
    if not signal_cols:
        raise ValueError("No signal columns found to correlate.")

    corr = signal_df[signal_cols].corr(method=method)
    labels = [signal_names.get(c, c) for c in signal_cols]
    corr.index = labels
    corr.columns = labels

    if csv_path is not None:
        csv_path = Path(csv_path)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        corr.to_csv(csv_path)

    # --- annotated heatmap (pure matplotlib; no seaborn dependency) ---
    n = len(labels)
    fig, ax = plt.subplots(figsize=(1.1 * n + 2, 1.1 * n + 2))
    im = ax.imshow(corr.values, vmin=-1, vmax=1, cmap="coolwarm", aspect="auto")

    ax.set_xticks(range(n))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_yticks(range(n))
    ax.set_yticklabels(labels)

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
