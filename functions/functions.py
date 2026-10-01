import pandas as pd
import numpy as np

# test




#Limitation: If quantile_interval_bounds = closed, Cant average the buckets to generate a market average
#  (with use market factor anyway) but incase in the future we try to take the average, claude you should warn me. Thanks :)
def univariate_portfolio_sorting(
    series_1, 
    no_quantiles_1,
    no_extremes_quantiles_1=1,
    take_extremes=False,
    *,
    quantile_interval_bounds="half_open",
):
    """
    Univariate portfolio sorting.

    ``quantile_interval_bounds`` controls how an observation sitting EXACTLY on a cutpoint
    is assigned. Irrelevant for a continuous signal (nothing lands exactly on a cutpoint),
    but these signals are ratios of small integer counts, so their distribution is atomic
    and cutpoints land on tie blocks routinely.

    - ``"half_open"`` (default, the frozen behaviour): buckets are ``(q_{i-1}, q_i]``. A tie
      block on a cutpoint goes wholly to the bucket BELOW it.
    - ``"closed"``: buckets are ``[q_{i-1}, q_i]``. A tie block on a cutpoint belongs to BOTH
      adjacent buckets.

    Why "closed" exists: bucket 1 has no lower bound (the ``if i > 0`` guard below skips it)
    and bucket K's upper bound is the maximum, which is vacuous -- so each extreme bucket has
    exactly one real boundary, and under "half_open" they are treated inconsistently (bucket 1
    includes its breakpoint, bucket K excludes its own). For two signals that are affine
    complements (z_b = -z_a) that makes High_a = {z > q} while Low_b = {z >= q}: two portfolios
    that must be identical, differing by the tie mass. "closed" makes both inclusive, so they
    coincide.

    The cost is that the K buckets stop PARTITIONING the cross-section -- memberships sum to
    more than N and bucket returns no longer decompose to the market return. High and Low never
    share a cutpoint for K >= 3, so a High-Low spread is unaffected; see the K < 3 guard below.
    """
    # Pre-allocate memory for output
    output = pd.Series(name=series_1.name, dtype=float)

    # Construct quantile numpy array
    if take_extremes:
        quantiles_1_range = np.linspace(1/no_quantiles_1, 1, num=no_quantiles_1)
        quantiles_1 = series_1.quantile([quantiles_1_range[no_extremes_quantiles_1-1], quantiles_1_range[-no_extremes_quantiles_1-1], 1.0])
    else:
        quantiles_1 = series_1.quantile(np.linspace(1/no_quantiles_1, 1, num=no_quantiles_1))

    if quantile_interval_bounds not in ("half_open", "closed"):
        raise ValueError(
            f"quantile_interval_bounds must be 'half_open' or 'closed', "
            f"got {quantile_interval_bounds!r}"
        )
    # Guard on len(quantiles_1) rather than no_quantiles_1: under take_extremes the two
    # differ (that path always yields 3 slices, so this correctly never fires there).
    if quantile_interval_bounds == "closed" and len(quantiles_1) < 3:
        raise ValueError(
            f"quantile_interval_bounds='closed' requires at least 3 quantiles; got "
            f"{len(quantiles_1)}. At K=2 the single breakpoint is simultaneously the Low "
            f"bucket's upper edge and the High bucket's lower edge, so a tie block sitting "
            f"on it would be held LONG and SHORT at once in the High-Low spread."
        )

    # Loop over quantiles
    for i in range(len(quantiles_1)):

        # Sorting on `series_1`
        # Upper bound is inclusive in both modes; only the lower bound differs.
        in_slice = series_1 <= quantiles_1.iloc[i]
        if i > 0:
            if quantile_interval_bounds == "closed":
                in_slice &= series_1 >= quantiles_1.iloc[i-1]
            else:
                in_slice &= series_1 > quantiles_1.iloc[i-1]
        
        # Update output accordingly
        output[f"p_{i+1}"] = series_1[in_slice].index
    
    # Return output
    return output


    # Function to compute percentage change if the date difference is not larger than 1 months
def conditional_pct_change(df_view):

    # Generate copy from view
    df = df_view.copy()

    # Calculate the date differences
    df['date_diff'] = df['date'].diff().dt.days

    # Calculate the percentage change
    df['tr'] = df['tri'].pct_change()

    # Mask the percentage change where the date difference is larger than 1 months (the extra 4 days account for bank holidays and weekends)
    df['tr'] = np.where(df['date_diff'] <= 31+5, df['tr'], np.nan)

    # Drop the date_diff column as it's no longer needed
    df.drop(columns=['date_diff'], inplace=True)

    # Return output
    return df


    

# Function to standardize pivoted signals
def standardize_pivot(df_pivot, global_universe, cols_standardization):
    
    # Melt the dataframe to long format for groupby calculations
    df_melted = df_pivot.reset_index().melt(id_vars='date', var_name='gvkey_iid', value_name='value')
    
    # Merge with original dataframe to get groupby columns
    df_merged = df_melted.merge(
        global_universe[['date', 'gvkey_iid'] + cols_standardization],
        on=['date', 'gvkey_iid'], 
        how='left'
    )
    
    # Groupby and transform to get mean and std
    group_mean = df_merged.groupby(cols_standardization)['value'].transform('mean')
    group_stdev = df_merged.groupby(cols_standardization)['value'].transform('std')
    
    # Standardize
    df_merged['value'] = (df_merged['value'] - group_mean) / group_stdev
    
    # Pivot back to wide format
    return df_merged.pivot(index='date', columns='gvkey_iid', values='value')



def low_high(df, label):
    low_col = df.columns[0]
    high_col = df.columns[-1]
    return df[[low_col, high_col]].rename(columns={low_col: f'Low {label}', high_col: f'High {label}'})

def set_first_row_to_zero(df: pd.DataFrame, inplace: bool = False) -> pd.DataFrame:
    out = df if inplace else df.copy()
    out.iloc[0, :] = 0
    return out