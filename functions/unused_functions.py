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




######TRUUUUUCOOSSSSSTTTT######################################################################

try:
    truc1 = pd.read_csv('./data/TruCost_0423.csv') #load piecewise Trucost data
    truc2 = pd.read_csv('./data/TruCost_1023.csv')
    truc3 = pd.read_csv('./data/TruCost_emissions_02-23_vF.csv')
    truc1 = truc1[['DirectControl','cyear','SP_ISIN']].rename(columns={'DirectControl':'direct_control'}) #keep firm-year and direct emissions
    truc2 = truc2[['2022','cyear','SP_ISIN']].rename(columns={'2022':'direct_control'})
    truc3 = truc3[['gvkey','year','scope1_abs','scope2_loc_abs','scope3_down_abs','scope3_up_abs']]
    truc = pd.concat([truc1,truc2],axis=0).rename(columns={'cyear':'year'}) #concatenate the two pieces


    isin_gvkey = pd.read_csv('./data/ISIN_GVKEY_crosswalk.csv') #load ISIN to gvkey mapping
    truc['gvkey'] = truc['SP_ISIN'].map(isin_gvkey.set_index('isin')['gvkey']) #map ISIN to gvkey in a new column
    truc = truc.sort_values(by=['gvkey','year','direct_control']) #sort by gvkey and year
    truc = truc.drop_duplicates(subset=['gvkey','year'],keep='first') #drop duplicates


    truc = truc.dropna(subset=['gvkey']) #drop rows with missing gvkey
    truc['gvkey'] = truc['gvkey'].astype(int).astype(str) #convert gvkey to string
    truc3['gvkey'] = truc3['gvkey'].astype(int).astype(str) #convert gvkey to string


    truc = pd.merge(truc,truc3, on=['gvkey','year'],how='outer') #merge with the third piece

    truc = truc[truc['gvkey'].isin(actual_gvkeys)] #keep only gvkeys in the global universe
    truc = truc.rename(columns={'gvkey':'ids','year':'cyear'}) #rename gvkey,year to ids,cyear to aid future merging
    truc.to_csv('./data/shared_TruCost.csv',index=False) #save to disk
except:
    print('Original Trucost data not found! Trying to load processed from disk...')
    truc = pd.read_csv('./data/shared_TruCost.csv')
    print("Found it!")



# compute first differences in emissions
def robust_first_difference(df: pd.DataFrame, id_col, time_col, val_col):
    """
    Calculate the first difference of the 'val' column in a DataFrame,
    considering only consecutive time points and handling NaN values in 'val'.
    
    Parameters:
    - df: pandas DataFrame containing the data (3 necessary columns, the rest ignored)
    - id_col: string, name of the column containing the ID
    - time_col: string, name of the column containing the time
    - val_col: string, name of the column for which to calculate the first difference
    
    Returns:
    - A pandas Series representing the first difference of 'val'.
    """
    df=df.copy()
    if not df.equals(df.sort_values(by=[id_col, time_col])):
        print("Warning: DataFrame is not sorted by 'id' and 'time'. This might create complications when concatenating back.")
    
    # Ensure the DataFrame is sorted by 'id' and then by 'time'
    df_sorted = df.sort_values(by=[id_col, time_col])
    
    # Temporarily forward fill 'val' within each 'id' group for time_diff calculation
    df_sorted['val_ffill'] = df_sorted.groupby(id_col)[val_col].fillna(method='ffill')
    
    # Calculate the time difference within each 'id' group (this is computing the number of time period per id_col)
    df_sorted['time_diff'] = df_sorted.groupby(id_col)[time_col].diff()
    df_sorted['time_diff'] = df_sorted['time_diff'].astype('Int64')
    
    # Compute the first difference in 'val' using the forward-filled column
    df_sorted['val_diff_temp'] = df_sorted.groupby(id_col)['val_ffill'].pct_change() ### might become .diff(x) or .pct_change(x) if needed
    
    # Apply enhanced mask: set 'val_diff' to NaN where time_diff is not 1, or original 'val' or its preceding value is NaN
    df_sorted['val_diff'] = np.where(
        (df_sorted['time_diff'] == 1) &                         # One period difference
        df_sorted[val_col].notna() &                            # Levels at t are not missing
        df_sorted.groupby(id_col)[val_col].shift(1).notna(),    # Levels at t-1 are not missing
        df_sorted['val_diff_temp'],                             # Take the data computed from filled differences 
        np.nan)                                                 # NaN otherwise
    
    return df_sorted['val_diff']

truc = truc.sort_values(by=['ids','cyear'])
truc['direct_control_diff'] = robust_first_difference(truc, 'ids', 'cyear', 'direct_control')
truc['scope1_abs_diff'] = robust_first_difference(truc, 'ids', 'cyear', 'scope1_abs')
truc['scope2_loc_abs_diff'] = robust_first_difference(truc, 'ids', 'cyear', 'scope2_loc_abs')
truc['scope3_down_abs_diff'] = robust_first_difference(truc, 'ids', 'cyear', 'scope3_down_abs')
truc['scope3_up_abs_diff'] = robust_first_difference(truc, 'ids', 'cyear', 'scope3_up_abs')


# Convert ids to string to join
truc['ids'] = truc['ids'].astype(str)

# Merge Trucost data with global universe, using constant yearly emissions for all global universe days
global_universe = pd.merge(
    global_universe, 
    truc, 
    left_on=['gvkey', 'last_year'], 
    right_on=['ids', 'cyear'], 
    how='left'
)
global_universe = global_universe.drop(columns=['SP_ISIN','cyear','ids'])
global_universe

global_universe['direct_control'].notna().sum()
global_universe['scope1_abs_intensity'] = global_universe['scope1_abs'] / global_universe['mktcap']
