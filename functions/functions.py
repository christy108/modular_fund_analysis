import pandas as pd
import numpy as np

def univariate_portfolio_sorting(
    series_1, 
    no_quantiles_1,
    no_extremes_quantiles_1=1,
    take_extremes=False
):
    """
    Univariate portfolio sorting. 
    """
    # Pre-allocate memory for output
    output = pd.Series(name=series_1.name, dtype=float)

    # Construct quantile numpy array
    if take_extremes:
        quantiles_1_range = np.linspace(1/no_quantiles_1, 1, num=no_quantiles_1)
        quantiles_1 = series_1.quantile([quantiles_1_range[no_extremes_quantiles_1-1], quantiles_1_range[-no_extremes_quantiles_1-1], 1.0])
    else:
        quantiles_1 = series_1.quantile(np.linspace(1/no_quantiles_1, 1, num=no_quantiles_1))

    # Loop over quantiles
    for i in range(len(quantiles_1)):

        # Sorting on `series_1`
        in_slice = series_1 <= quantiles_1.iloc[i]
        if i > 0:
            in_slice &= series_1 > quantiles_1.iloc[i-1]
        
        # Update output accordingly
        output[f"p_{i+1}"] = series_1[in_slice].index
    
    # Return output
    return output






    

def low_high(df, label):
    low_col = df.columns[0]
    high_col = df.columns[-1]
    return df[[low_col, high_col]].rename(columns={low_col: f'Low {label}', high_col: f'High {label}'})

