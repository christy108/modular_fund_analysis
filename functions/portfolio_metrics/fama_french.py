from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

# Factor column -> the row label its loading is reported under. One mapping, so the
# regression tables and every downstream .loc["beta_..."] cannot drift apart.
_BETA_NAMES = {
    "mktrf": "beta_mkt",
    "smb": "beta_smb",
    "hml": "beta_hml",
    "rmw": "beta_rmw",
    "cma": "beta_cma",
    "mom": "beta_mom",
}


def _momentum_factors(factors, with_momentum):
    """Append the momentum regressor when a run asked for it."""
    return list(factors) + (["mom"] if with_momentum else [])


def _factor_regressions(excess_returns, fama_french, factors):
    """HC1 OLS of each portfolio's excess return on `factors`, one column per portfolio.

    Returns a (statistic x portfolio) frame whose rows run alpha, the betas in factor
    order, p-value(alpha), the p-values in the same order, then Adj. R^2. Both sides are
    scaled by 100, so alphas read as monthly percent.

    `fama_french` keeps its own index while the dependent series is rebuilt on a fresh
    RangeIndex, which is what makes the concat align positionally -- callers pass a
    reset_index(drop=True) factor frame for exactly that reason.
    """
    betas = [_BETA_NAMES[f] for f in factors]
    stat_index = [
        'alpha', *betas,
        'p-value(alpha)', *(f'p-value({b})' for b in betas),
        'Adj. R^2',
    ]

    output = pd.DataFrame(np.nan, index=stat_index, columns=excess_returns.columns)

    # Gather factors
    independent_data = fama_french[list(factors)]

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
        mod = smf.ols(formula='excrt ~ ' + ' + '.join(factors), data=ols_data)

        # Estimate and show output
        fitted_model = mod.fit(cov_type='HC1')

        coef = fitted_model.params
        pval = fitted_model.pvalues

        output.loc['alpha', col] = coef.get('Intercept', np.nan)
        output.loc['p-value(alpha)', col] = pval.get('Intercept', np.nan)
        for factor, beta in zip(factors, betas):
            output.loc[beta, col] = coef.get(factor, np.nan)
            output.loc[f'p-value({beta})', col] = pval.get(factor, np.nan)
        output.loc['Adj. R^2', col] = fitted_model.rsquared_adj

    # Return regression output
    return output


def ff3_regressions(excess_returns, fama_french, with_momentum=False):
    """FF3 loadings, plus momentum (Carhart's 4-factor model) when `with_momentum`."""
    return _factor_regressions(
        excess_returns, fama_french,
        _momentum_factors(['mktrf', 'smb', 'hml'], with_momentum),
    )


def ff5_regressions(excess_returns, fama_french, with_momentum=False):
    """FF5 loadings, plus momentum (the 6-factor model) when `with_momentum`."""
    return _factor_regressions(
        excess_returns, fama_french,
        _momentum_factors(['mktrf', 'smb', 'hml', 'rmw', 'cma'], with_momentum),
    )


def rolling_ff_alphas(
    signals: list[dict],
    *,
    fama_french: pd.DataFrame,
    window_size: int,
    n_factors: int = 3,
    with_momentum: bool = False,
) -> dict[str, pd.Series]:
    """
    Compute rolling-window FF factors alphas for multiple signals.

    Parameters
    ----------
    signals:
        List of dicts with keys:
          - label: str (legend/plot label)
          - returns: pd.DataFrame (excess returns; index=date, columns=portfolios)
          - alpha_column: str (which column in `returns` to extract alpha for)
    fama_french:
        Fama-French factor DataFrame. For FF3: mktrf, smb, hml. For FF5: also rmw, cma.
        Should be aligned in time with `returns` (same number of rows, same ordering).
    window_size:
        Rolling window length in rows (e.g. 40 months).
    n_factors:
        3 for FF3 (`ff3_regressions`) or 5 for FF5 (`ff5_regressions`).
    with_momentum:
        Add the `mom` regressor to whichever base model `n_factors` selects, giving
        Carhart's 4-factor or the 6-factor specification. Requires a `mom` column.

    Returns
    -------
    dict[label -> pd.Series]
        Each series is indexed by the window end date, values are monthly alpha (%),
        matching `ff3_regressions` / `ff5_regressions` output convention.
    """
    if n_factors not in (3, 5):
        raise ValueError("n_factors must be 3 or 5")

    if n_factors == 3:
        base_regress = ff3_regressions
        required_cols = _momentum_factors(["mktrf", "smb", "hml"], with_momentum)
    else:
        base_regress = ff5_regressions
        required_cols = _momentum_factors(["mktrf", "smb", "hml", "rmw", "cma"], with_momentum)

    def regress(window_returns, window_factors):
        return base_regress(window_returns, window_factors, with_momentum=with_momentum)

    missing_cols = [c for c in required_cols if c not in fama_french.columns]
    if missing_cols:
        raise ValueError(
            f"n_factors={n_factors} (with_momentum={with_momentum}) requires columns "
            f"{required_cols}; missing from fama_french: {missing_cols}"
        )

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

            ff_out = regress(ret_w, ff_w.reset_index(drop=True))
            alpha = ff_out.loc["alpha", alpha_column]

            window_end_dates.append(ret_w.index[-1])
            alpha_vals.append(alpha)

        rolling_alphas[label] = pd.Series(alpha_vals, index=pd.Index(window_end_dates, name="date"))

    return rolling_alphas


def rolling_ff3_alphas(
    signals: list[dict],
    *,
    fama_french: pd.DataFrame,
    window_size: int,
    with_momentum: bool = False,
) -> dict[str, pd.Series]:
    """Rolling FF3 alphas; alias for ``rolling_ff_alphas(..., n_factors=3)``."""
    return rolling_ff_alphas(
        signals,
        fama_french=fama_french,
        window_size=window_size,
        n_factors=3,
        with_momentum=with_momentum,
    )


def rolling_ff5_alphas(
    signals: list[dict],
    *,
    fama_french: pd.DataFrame,
    window_size: int,
    with_momentum: bool = False,
) -> dict[str, pd.Series]:
    """Rolling FF5 alphas; alias for ``rolling_ff_alphas(..., n_factors=5)``."""
    return rolling_ff_alphas(
        signals,
        fama_french=fama_french,
        window_size=window_size,
        n_factors=5,
        with_momentum=with_momentum,
    )


def rolling_alphas_to_dataframe(rolling_alphas: dict[str, pd.Series]) -> pd.DataFrame:
    """Wide DataFrame of rolling alpha series (one column per label)."""
    if not rolling_alphas:
        raise ValueError("rolling_alphas must be a non-empty dict of label -> pd.Series")
    return pd.DataFrame(rolling_alphas)


def save_rolling_alphas_csv(
    rolling_alphas: dict[str, pd.Series],
    csv_path: str | Path,
) -> pd.DataFrame:
    """Save rolling alpha series (plot input) to CSV."""
    df = rolling_alphas_to_dataframe(rolling_alphas)
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path)
    return df


def plot_rolling_alpha_function(
    rolling_alphas: dict[str, pd.Series],
    *,
    title: str = "Rolling alphas",
    ylabel: str = "Monthly alpha (%)",
    figsize: tuple[float, float] = (10, 6),
    cmap_name: str = "viridis",
    line_styles: list[str] | None = None,
    grid: bool = True,
    rotate_xticks: int = 45,
    legend_title: str = "Legend",
    save_path: str | None = None,
    csv_path: str | Path | None = None,
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
    if line_styles is None:
        line_styles = ["--", "-.", "-", ":"]

    for i, ((label, s), color) in enumerate(zip(zip(labels, series_list), colors)):
        if not isinstance(s, pd.Series):
            raise TypeError(f"rolling_alphas['{label}'] must be a pd.Series, got {type(s)}")
        ax.plot(
            s.index,
            s.values,
            label=label,
            color=color,
            linestyle=line_styles[i % len(line_styles)],
        )

    ax.set_title(title)
    ax.set_xlabel("")
    ax.set_ylabel(ylabel)
    ax.grid(grid)
    ax.tick_params(axis="x", rotation=rotate_xticks)
    ax.legend(title=legend_title)

    if csv_path is not None:
        save_rolling_alphas_csv(rolling_alphas, csv_path)

    if save_path is not None:
        ax.figure.savefig(save_path, bbox_inches="tight")

    if show:
        plt.show()

    return ax