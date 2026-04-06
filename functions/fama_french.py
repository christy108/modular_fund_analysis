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