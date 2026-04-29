import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import pandas as pd


def corr_heatmap_xy(
    df: pd.DataFrame,
    y_vars: list[str],
    x_vars: list[str],
    *,
    method: str = "pearson",
    dropna: bool = True,
    annot: bool = True,
    fmt: str = ".2f",
    cmap: str = "vlag",
    center: float = 0.0,
    vmin: float | None = -1.0,
    vmax: float | None = 1.0,
    figsize: tuple[float, float] | None = None,
    title: str | None = None,
    save_path: str | None = None,
):
    """Plot correlation heatmap for selected row vars (y) vs column vars (x).

    Returns (corr_df, ax).
    """
    if dropna:
        cols = list(dict.fromkeys([*y_vars, *x_vars]))
        data = df.loc[:, cols].dropna(how="any")
    else:
        data = df

    corr_full = data.corr(method=method, numeric_only=True)
    corr_xy = corr_full.reindex(index=y_vars, columns=x_vars)

    if figsize is None:
        # Simple heuristic: scale with number of vars
        figsize = (max(6.0, 0.6 * len(x_vars)), max(4.5, 0.45 * len(y_vars)))

    fig, ax = plt.subplots(figsize=figsize)
    sns.heatmap(
        corr_xy,
        ax=ax,
        annot=annot,
        fmt=fmt,
        cmap=cmap,
        center=center,
        vmin=vmin,
        vmax=vmax,
        square=False,
        cbar_kws={"label": f"{method} correlation"},
    )
    ax.set_xlabel("x variables")
    ax.set_ylabel("y variables")
    if title:
        ax.set_title(title)
    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=200, bbox_inches="tight")

    return corr_xy, ax


def create_t_shifted_columns(df, columns, shift_period):
    # Keep each company's history ordered before shifting.
    df = df.sort_values(["gvkey_iid", "date"]).copy()

    for col in columns:
        df[f"{col}_t_{shift_period}"] = df.groupby("gvkey_iid")[col].shift(shift_period)

    shifted_columns = [f"{col}_t_{shift_period}" for col in columns]

    # Validation: for groups with >= shift_period + 1 rows,
    # shifted row[shift_period] equals original row[0].
    validation_col = columns[0]
    shifted_validation_col = f"{validation_col}_t_{shift_period}"

    for _, g in df.groupby("gvkey_iid", sort=False):
        if len(g) > shift_period:
            assert g[shifted_validation_col].iloc[shift_period] == g[validation_col].iloc[0], (
                f"t_{shift_period} validation failed for {validation_col}"
            )

    return df, shifted_columns