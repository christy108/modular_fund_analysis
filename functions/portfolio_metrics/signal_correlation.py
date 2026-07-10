"""ESG-vs-behavioural-signal relationship diagnostics.

For the ONE ESG provider chosen by ``esg_choice`` (auto-detected as the signal key starting
with ``"esg"`` -- works for ``esg_msci`` / ``esg_refinitive`` / ``esg_sp``), only ESG-to-signal
relationships are reported (never signal-vs-signal). Reads already-computed objects.

Two kinds of output, each with a "from a value DataFrame" and a "from signal pivots" entry:
* ``esg_signal_regressions`` / ``..._from_pivots``        -- univariate OLS ``esg ~ const + signal_i``
  per behavioural signal: Coefficient / SE / P-value / N.
* ``signal_correlation_matrix`` / ``..._from_pivots``     -- RECTANGULAR correlation table:
  columns = behavioural signals, rows = correlation / p-value / SE of ESG vs each signal.
  Plots an r-only heatmap strip (signals on the x-axis); prints the corr/p/SE table.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

_CORR_FUNCS = {"pearson": stats.pearsonr, "spearman": stats.spearmanr, "kendall": stats.kendalltau}


def _detect_esg_key(keys, present):
    esg = [k for k in keys if str(k).startswith("esg") and k in present]
    if not esg:
        raise ValueError("No ESG signal found (expected a key starting with 'esg').")
    return esg[0]


def _display(obj, *, header=None):
    if header:
        print(header)
    try:
        from IPython.display import display
        display(obj.round(3) if hasattr(obj, "round") else obj)
    except Exception:
        print(obj.round(3).to_string() if hasattr(obj, "round") else obj)


# --------------------------------------------------------------------------- #
# Univariate regression: esg ~ signal_i
# --------------------------------------------------------------------------- #
def _ols_esg_on_signals(value_df, signal_names, esg_key):
    behavioural = [k for k in signal_names if k in value_df.columns and k != esg_key]
    if not behavioural:
        raise ValueError("No behavioural signal columns found to regress against.")
    rows = []
    for k in behavioural:
        d = value_df[[esg_key, k]].dropna()
        if len(d) < 3:
            rows.append({"Signal": signal_names.get(k, k), "Coefficient": np.nan,
                         "SE": np.nan, "P-value": np.nan, "N": int(len(d))})
            continue
        res = sm.OLS(d[esg_key], sm.add_constant(d[[k]])).fit()
        rows.append({"Signal": signal_names.get(k, k), "Coefficient": res.params[k],
                     "SE": res.bse[k], "P-value": res.pvalues[k], "N": int(res.nobs)})
    return pd.DataFrame(rows).set_index("Signal")


def esg_signal_regressions(value_df, signal_names, *, esg_key=None, csv_path=None,
                           title="ESG vs behavioural signals (univariate regression)", show=True):
    esg_key = esg_key or _detect_esg_key(signal_names, value_df.columns)
    table = _ols_esg_on_signals(value_df, signal_names, esg_key)
    table.insert(0, "Score", signal_names.get(esg_key, esg_key))
    if csv_path is not None:
        csv_path = Path(csv_path); csv_path.parent.mkdir(parents=True, exist_ok=True); table.to_csv(csv_path)
    if show:
        _display(table, header=f"{title} (Score = {signal_names.get(esg_key, esg_key)})")
    return table


def esg_signal_regressions_from_pivots(signals, signal_names, **kw):
    esg_key = kw.pop("esg_key", None) or _detect_esg_key(signals, signals)
    value_df = pd.DataFrame({k: pv.stack(dropna=True) for k, pv in signals.items()})
    return esg_signal_regressions(value_df, signal_names, esg_key=esg_key, **kw)


# --------------------------------------------------------------------------- #
# Rectangular correlation table: ESG vs each behavioural signal
# --------------------------------------------------------------------------- #
def _corr_strip_heatmap(r_row, *, title, save_path=None, show=True):
    """r-only heatmap strip: one ESG row, behavioural signals on the x-axis."""
    cols = list(r_row.columns)
    nc = len(cols)
    fig, ax = plt.subplots(figsize=(1.5 * nc + 2, 2.4))
    im = ax.imshow(r_row.values, vmin=-1, vmax=1, cmap="coolwarm", aspect="auto")
    ax.set_xticks(range(nc)); ax.set_xticklabels(cols, rotation=45, ha="right")
    ax.set_yticks([0]); ax.set_yticklabels(list(r_row.index))
    for j in range(nc):
        v = r_row.values[0, j]
        ax.text(j, 0, f"{v:.2f}", ha="center", va="center",
                color="white" if abs(v) > 0.55 else "black", fontsize=9)
    ax.set_title(title)
    fig.colorbar(im, ax=ax, fraction=0.08, pad=0.04, label="correlation")
    fig.tight_layout()
    if save_path is not None:
        save_path = Path(save_path); save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    if show:
        plt.show()
    else:
        plt.close(fig)


def signal_correlation_matrix(value_df, signal_names, *, method="pearson", esg_key=None,
                              save_path=None, csv_path=None,
                              title="ESG-signal correlation", show=True):
    """Rectangular ESG-vs-behavioural correlation table (no signal-vs-signal).

    Columns = behavioural signals; rows = correlation / p-value / SE of the ESG signal
    against each. Prints the table; plots an r-only heatmap strip. Returns the table.
    SE = sqrt((1 - r**2) / (n - 2)) (the SE consistent with the correlation t-test).
    """
    esg_key = esg_key or _detect_esg_key(signal_names, value_df.columns)
    func = _CORR_FUNCS[method]
    behavioural = [k for k in signal_names if k in value_df.columns and k != esg_key]
    if not behavioural:
        raise ValueError("No behavioural signal columns found to correlate against ESG.")

    r, p, se = {}, {}, {}
    for k in behavioural:
        lab = signal_names.get(k, k)
        d = value_df[[esg_key, k]].dropna()
        n = len(d)
        if n < 3:
            r[lab] = p[lab] = se[lab] = np.nan
            continue
        out = func(d[esg_key].to_numpy(), d[k].to_numpy())
        rr, pp = float(out[0]), float(out[1])
        r[lab] = rr; p[lab] = pp
        se[lab] = float(np.sqrt((1 - rr**2) / (n - 2))) if abs(rr) < 1 else 0.0

    table = pd.DataFrame({"correlation": r, "p-value": p, "SE": se}).T   # rows: corr/p/SE, cols: signals
    if csv_path is not None:
        csv_path = Path(csv_path); csv_path.parent.mkdir(parents=True, exist_ok=True); table.to_csv(csv_path)

    esg_label = signal_names.get(esg_key, esg_key)
    if show:
        _display(table, header=f"{title}: {esg_label} vs behavioural signals ({method})")
    r_row = table.loc[["correlation"]].copy(); r_row.index = [esg_label]
    _corr_strip_heatmap(r_row, title=f"{title}: {esg_label} vs signals ({method})",
                        save_path=save_path, show=show)
    return table


def signal_correlation_matrix_from_pivots(signals, signal_names, *, method="pearson", **kw):
    esg_key = kw.pop("esg_key", None) or _detect_esg_key(signals, signals)
    value_df = pd.DataFrame({k: pv.stack(dropna=True) for k, pv in signals.items()})
    return signal_correlation_matrix(value_df, signal_names, method=method, esg_key=esg_key, **kw)


# --------------------------------------------------------------------------- #
# Save both tables, with scale + ESG provider in the filenames
# --------------------------------------------------------------------------- #
def masked_raw_value_df(global_universe, signal_df, signal_names):
    """Raw (non-standardised) signal values on the masked analysis sample.

    Uses the ``(date, gvkey_iid)`` keys of ``signal_df`` (the masked, standardised long form)
    and attaches the raw signal + raw 0-1 ESG columns from ``global_universe`` -- so the
    non-standardised tables cover the same firm-months as the standardised ones.
    """
    cols = [c for c in signal_names if c in global_universe.columns]
    gu = global_universe[["date", "gvkey_iid", *cols]].drop_duplicates(["date", "gvkey_iid"])
    keys = signal_df[["date", "gvkey_iid"]].drop_duplicates()
    return keys.merge(gu, on=["date", "gvkey_iid"], how="left")


def esg_signal_relationship_outputs(value_df, signal_names, img_dir, csv_dir, *,
                                    method="pearson", esg_key=None,
                                    scale_tag="standardised", show=True):
    """Run AND save both the regression table and the rectangular correlation table.

    Filenames embed the scale (``standardised`` / ``non_standardised``) and the ESG provider
    key (``esg_refinitive`` / ``esg_msci`` / ``esg_sp``). Returns (regression_df, correlation_df).
    """
    esg_key = esg_key or _detect_esg_key(signal_names, value_df.columns)
    tag = f"{scale_tag}_{esg_key}"
    img_dir, csv_dir = Path(img_dir), Path(csv_dir)
    reg = esg_signal_regressions(
        value_df, signal_names, esg_key=esg_key,
        csv_path=csv_dir / f"esg_vs_signals_regression_{tag}.csv",
        title=f"ESG vs behavioural signals — {scale_tag} (regression)", show=show)
    corr = signal_correlation_matrix(
        value_df, signal_names, method=method, esg_key=esg_key,
        save_path=img_dir / f"esg_vs_signals_correlation_{tag}.png",
        csv_path=csv_dir / f"esg_vs_signals_correlation_{tag}.csv",
        title=f"ESG vs behavioural signals — {scale_tag} (correlation)", show=show)
    return reg, corr
