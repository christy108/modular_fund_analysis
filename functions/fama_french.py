import pandas as pd
import numpy as np
import statsmodels.api as sm
import statsmodels.formula.api as smf

def ff3_regressions(excess_returns, fama_french):

    stat_index = [
        'alpha',
        'beta_mkt',
        'beta_smb',
        'beta_hml',
        'p-value(alpha)',
        'p-value(beta_mkt)',
        'p-value(beta_smb)',
        'p-value(beta_hml)',
        'Adj. R^2',
    ]

    ff3_output = pd.DataFrame(np.nan, index=stat_index, columns=excess_returns.columns)

    # Gather FF3 factors
    independent_data = fama_french[['mktrf', 'smb', 'hml']]

    for col in excess_returns.columns:

        # Gather dependent data
        dependent_data = pd.Series(excess_returns[col].values, name='excrt')

        # Merge variables
        ols_data = 100 * pd.concat(
            [
                dependent_data,
                independent_data,
            ],
            axis=1,
        )

        # Skip missings
        ols_data = ols_data[ols_data.notna().all(axis=1)].reset_index(drop=True)

        if ols_data.empty:
            continue

        # Model
        mod = smf.ols(formula='excrt ~ mktrf + smb + hml', data=ols_data)

        # Estimate and show output
        fitted_model = mod.fit(cov_type='HC1')

        coef = fitted_model.params
        pval = fitted_model.pvalues

        ff3_output.loc['alpha', col] = coef.get('Intercept', np.nan)
        ff3_output.loc['beta_mkt', col] = coef.get('mktrf', np.nan)
        ff3_output.loc['beta_smb', col] = coef.get('smb', np.nan)
        ff3_output.loc['beta_hml', col] = coef.get('hml', np.nan)

        ff3_output.loc['p-value(alpha)', col] = pval.get('Intercept', np.nan)
        ff3_output.loc['p-value(beta_mkt)', col] = pval.get('mktrf', np.nan)
        ff3_output.loc['p-value(beta_smb)', col] = pval.get('smb', np.nan)
        ff3_output.loc['p-value(beta_hml)', col] = pval.get('hml', np.nan)
        ff3_output.loc['Adj. R^2', col] = fitted_model.rsquared_adj

    # Return regression output
    return ff3_output


def rolling_ff3_alphas(
    signals: list[dict],
    *,
    fama_french: pd.DataFrame,
    window_size: int,
) -> dict[str, pd.Series]:
    """
    Compute rolling-window FF3 alphas for multiple signals.

    Parameters
    ----------
    signals:
        List of dicts with keys:
          - label: str (legend/plot label)
          - returns: pd.DataFrame (excess returns; index=date, columns=portfolios)
          - alpha_column: str (which column in `returns` to extract alpha for)
    fama_french:
        FF3 factor DataFrame (must include columns: mktrf, smb, hml). Should be aligned
        in time with `returns` (same number of rows, same ordering).
    window_size:
        Rolling window length in rows (e.g. 40 months).

    Returns
    -------
    dict[label -> pd.Series]
        Each series is indexed by the window end date, values are monthly alpha (%),
        matching `ff3_regressions` output convention.
    """
    if not isinstance(window_size, int) or window_size <= 0:
        raise ValueError("window_size must be a positive integer")

    if not signals:
        raise ValueError("signals must be a non-empty list of dicts")

    rolling_alphas: dict[str, pd.Series] = {}

    for s in signals:
        if not isinstance(s, dict):
            raise TypeError("Each signal must be a dict with keys: label, returns, alpha_column")

        label = s.get("label")
        returns = s.get("returns")
        alpha_column = s.get("alpha_column")

        if not isinstance(label, str) or not label:
            raise ValueError("signal['label'] must be a non-empty str")
        if not isinstance(returns, pd.DataFrame):
            raise TypeError(f"signal['returns'] for '{label}' must be a pd.DataFrame")
        if not isinstance(alpha_column, str) or not alpha_column:
            raise ValueError(f"signal['alpha_column'] for '{label}' must be a non-empty str")
        if alpha_column not in returns.columns:
            raise KeyError(
                f"signal '{label}' alpha_column '{alpha_column}' not found in returns columns"
            )

        if len(returns) != len(fama_french):
            raise ValueError(
                f"signal '{label}' returns and fama_french must have same length "
                f"(got {len(returns)} vs {len(fama_french)})"
            )
        if window_size > len(returns):
            raise ValueError(
                f"signal '{label}' window_size={window_size} exceeds available rows={len(returns)}"
            )

        window_end_dates = []
        alpha_vals = []

        for i in range(len(returns) - window_size + 1):
            window_end_idx = i + window_size

            ret_w = returns.iloc[i:window_end_idx, :]
            ff_w = fama_french.iloc[i:window_end_idx, :]

            ff3_out = ff3_regressions(ret_w, ff_w.reset_index(drop=True))
            alpha = ff3_out.loc["alpha", alpha_column]

            window_end_dates.append(ret_w.index[-1])
            alpha_vals.append(alpha)

        rolling_alphas[label] = pd.Series(alpha_vals, index=pd.Index(window_end_dates, name="date"))

    return rolling_alphas


def plot_rolling_alpha_function(
    rolling_alphas: dict[str, pd.Series],
    *,
    title: str = "Rolling alphas",
    ylabel: str = "Monthly alpha (%)",
    figsize: tuple[float, float] = (10, 6),
    cmap_name: str = "viridis",
    grid: bool = True,
    rotate_xticks: int = 45,
    legend_title: str = "Legend",
    save_path: str | None = None,
    ax=None,
    show: bool = True,
):
    """
    Plot one or more rolling alpha time series.

    Parameters
    ----------
    rolling_alphas:
        Mapping from label -> pandas Series (indexed by date).
    """
    if not rolling_alphas:
        raise ValueError("rolling_alphas must be a non-empty dict of label -> pd.Series")

    # Local import to keep this module usable in non-plotting contexts.
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=figsize)
    else:
        ax = ax

    cmap = plt.get_cmap(cmap_name)
    labels = list(rolling_alphas.keys())
    series_list = list(rolling_alphas.values())

    n = len(series_list)
    # Match the notebook's prior behavior: it sampled 4 colors from viridis but
    # only used the first 3, which avoids the bright yellow endpoint.
    # Generalizing: sample n+1 colors and drop the endpoint.
    color_positions = np.linspace(0, 1, n + 1)[:-1] if n > 1 else [0.0]
    colors = [cmap(float(p)) for p in color_positions]

    for (label, s), color in zip(zip(labels, series_list), colors):
        if not isinstance(s, pd.Series):
            raise TypeError(f"rolling_alphas['{label}'] must be a pd.Series, got {type(s)}")
        s.plot(ax=ax, label=label, color=color)

    ax.set_title(title)
    ax.set_xlabel("")
    ax.set_ylabel(ylabel)
    ax.grid(grid)
    ax.tick_params(axis="x", rotation=rotate_xticks)
    ax.legend(title=legend_title)

    if save_path is not None:
        ax.figure.savefig(save_path, bbox_inches="tight")

    if show:
        plt.show()

    return ax