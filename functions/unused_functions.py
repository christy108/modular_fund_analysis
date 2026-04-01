import statsmodels.api as sm
import statsmodels.formula.api as smf
from sklearn.linear_model import LinearRegression, QuantileRegressor

def rolling_regressions(y, control, X, lags, window, tail=False, user_controls=None):
    """
    Perform rolling regressions.

    Parameters:
    y : pandas Series
        Dependent variable
    control : pandas DataFrame
        Control variables
    X : pandas Series
        Independent variable
    lags : int
        Lags for the independent variable
    window : int
        Rolling window size
    tail : bool, optional
        If True, perform quantile regression at the 90th percentile. Default is False.
    user_controls : list of str, optional
        List of control variables to interact with X. Default is None.
    
    Returns:
    pandas Series
        Series containing the rolling output
    """
    
    # Initialize list to store independent variable names
    indep_vars_columns = []

    # Check for control variables
    if not control.empty:
        # Concatenate control variables and X
        indep_vars = pd.concat([control, X], axis=1)
        for j in range(control.shape[1]):
            indep_vars_columns.append(f'control_{j}')
    else:
        indep_vars = X.copy()
    
    # Add X to the list of independent variables
    indep_vars_columns.append('X')

    # Handle interactions between X and user-specified controls
    if user_controls:
        for control_col in user_controls:
            if control_col in control.columns:
                indep_vars[f'{control_col}_X'] = control[control_col] * X
                indep_vars_columns.append(f'{control_col}_X')

    # Set column names
    indep_vars.columns = indep_vars_columns

    # Initialize a series to hold the rolling coefficients
    rolling_output = pd.Series(np.nan, index=y.index, name=y.name, dtype=float)
    
    for t in range(window-1, indep_vars.shape[0]):

        # Take the last observed `window` observations in the independent variables
        indep_vars_window = indep_vars.iloc[:t+1, :].dropna()
        indep_vars_window = indep_vars_window.iloc[-window:, :]

        # Windowed data
        y_window = y.loc[indep_vars_window.index].dropna()
        
        if not y_window.empty and (y_window.shape[0] >= 0.4*window) and (indep_vars_window.shape[0] >= 0.4*window) and (y_window.std() > 1e-8) and (indep_vars_window.std() > 1e-8).all():
            
            try:
                # Add lags
                if lags > 0:
                    for col in ['X'] + [f'{control_col}_X' for control_col in user_controls or []]:
                        for i in range(1, lags+1):
                            indep_vars_window[f'{col}_lag{i}'] = indep_vars_window[col].shift(i)

                        # Skip `lags` missing observations
                        y_window = y_window[lags:]
                        indep_vars_window = indep_vars_window[lags:]
                
                # Define and fit the regressor
                if tail:
                    mod = QuantileRegressor(fit_intercept=True, alpha=1e-6, quantile=0.95, solver='highs')
                    mod.fit(indep_vars_window, y_window)
                else:
                    mod = LinearRegression(fit_intercept=True)
                    mod.fit(indep_vars_window, y_window)
                
                # Get the coefficient of 'X' (or interaction terms if needed)
                x_index = indep_vars_window.columns.get_loc('X')
                coef_value = mod.coef_[x_index]
                
                # Store standardized rolling coefficients
                rolling_output.iloc[t] = coef_value * (indep_vars_window['X'].std() / y_window.std())
            
            except:
                rolling_output.iloc[t] = rolling_output.iloc[t-1]
                
        else:
            rolling_output.iloc[t] = rolling_output.iloc[t-1]
    
    # Return output
    return rolling_output






    
def compute_weighted_average(returns, raw_weights, permnos):
    """
    Compute the weighted average of the returns for a specified subset of permnos.
    """
    
    # Get data corresponding to `permno`
    returns_selection = returns[permnos]
    raw_weights_selection = raw_weights[permnos]

    # Skip missing data in `returns_selection`
    raw_weights_selection[returns_selection.isna()] = np.nan
    
    # Compute standardised weights
    weights_selection = raw_weights_selection/raw_weights_selection.sum()

    # Compute and return weighted average of the returns
    return (returns_selection * weights_selection).sum()
