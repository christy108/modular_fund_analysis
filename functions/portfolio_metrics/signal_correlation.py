"""ESG-vs-signals return correlation diagnostic.

Builds a rectangular correlation matrix of ALREADY-COMPUTED portfolio returns:

  * rows  = each LC signal's High / Low / High-Low monthly return series
  * cols  = the ESG signal's High / Low / High-Low series
  * cells = Pearson correlation of the two monthly return series

Reads ``signal_quantiles`` directly (Low = ``p_1``, High = ``p_{no_simple_quantiles}``,
High-Low = High - Low) -- nothing is recomputed. Used at the end of Main.ipynb on the LC
path (``esg_choice != "none"`` and ``esg_full_universe == False``).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def esg_signal_correlation(
    signal_quantiles,
    signal_names,
    no_simple_quantiles,
    *,
    esg_key=None,
    save_path=None,
    csv_path=None,
    title="ESG vs signals — return correlation",
    show=True,
):
    """Rectangular correlation of already-computed portfolio returns (no recomputation).

    Parameters
    ----------
    signal_quantiles : dict[str, pd.DataFrame]
        Per-signal quantile-return panels (columns ``p_1..p_{no_simple_quantiles}``,
        dates index). Keys are the LC signals (``signal_0..n``) plus the ESG column.
    signal_names : Mapping[str, str]
        Display names keyed by the same signal keys (for readable labels).
    no_simple_quantiles : int
        Number of quantiles, so High = ``p_{no_simple_quantiles}``, Low = ``p_1``.
    esg_key : str, optional
        The ESG signal key; auto-detected as the key starting with ``"esg"`` if omitted.
    save_path, csv_path : path-like, optional
        If given, save the heatmap PNG / correlation CSV.
    show : bool
        Whether to ``plt.show()`` (else the figure is closed after saving).

    Returns
    -------
    pd.DataFrame
        Rectangular correlation matrix (LC-signal series as rows, ESG series as columns).
    """
    hi, lo = f"p_{no_simple_quantiles}", "p_1"

    if esg_key is None:
        esg_keys = [k for k in signal_quantiles if str(k).startswith("esg")]
        if not esg_keys:
            raise ValueError(
                "No ESG signal found in signal_quantiles (expected a key starting with 'esg'). "
                "This diagnostic is for the LC path with esg_choice != 'none'."
            )
        esg_key = esg_keys[0]

    lc_keys = [k for k in signal_quantiles if k != esg_key]

    def _legs(key):
        nm = signal_names.get(key, key)
        df = signal_quantiles[key]
        return {
            f"High {nm}": df[hi],
            f"Low {nm}": df[lo],
            f"High-Low {nm}": df[hi] - df[lo],
        }

    rows: dict[str, pd.Series] = {}
    for k in lc_keys:
        rows.update(_legs(k))
    cols = _legs(esg_key)

    panel = pd.DataFrame({**rows, **cols})
    corr = panel.corr().loc[list(rows), list(cols)]

    if csv_path is not None:
        csv_path = Path(csv_path)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        corr.to_csv(csv_path)

    # --- annotated heatmap (pure matplotlib; no seaborn dependency) ---
    n_rows, n_cols = corr.shape
    fig, ax = plt.subplots(figsize=(1.4 * n_cols + 3, 0.5 * n_rows + 2))
    im = ax.imshow(corr.values, vmin=-1, vmax=1, cmap="coolwarm", aspect="auto")

    ax.set_xticks(range(n_cols))
    ax.set_xticklabels(corr.columns, rotation=45, ha="right")
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(corr.index)

    for i in range(n_rows):
        for j in range(n_cols):
            v = corr.values[i, j]
            ax.text(
                j, i, f"{v:.2f}", ha="center", va="center",
                color="white" if abs(v) > 0.55 else "black", fontsize=8,
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
