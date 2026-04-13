import pandas as pd
import numpy as np


def process_row_universe(row_universe, fx_rates):


    """
    standardizes date andgvkey, merges in FX rates by (date, curcdd), 
    converts mktcap_lcu and tri_lcu to base-currency mktcap/tri, and 
    creates last_year for fundamentals merging (Jan–Jun: (year-2); Jul–Dec: (year-1)).
    """


    # Set dates to datetime format
    row_universe['date'] = pd.to_datetime(row_universe['date'])
    row_universe['gvkey'] = row_universe['gvkey'].astype(float).astype(str)

    # Currency conversions
    row_universe = pd.merge(row_universe, fx_rates, on=['date', 'curcdd'], how='left')
    row_universe['mktcap'] = row_universe['mktcap_lcu'] / row_universe['rate']
    row_universe['tri'] = row_universe['tri_lcu'] / row_universe['rate']

    # Create the correct year to merge on fundamentals
    # For dates in H1 (Jan-Jun), accounting data from Y-1 isn't out yet, so use Y-2's report.
    # For dates in H2 (Jul-Dec), accounting data from Y-1 is available.
    row_universe['last_year'] = np.where(
        row_universe['date'].dt.month <= 6, 
        row_universe['date'].dt.year - 2, 
        row_universe['date'].dt.year - 1
    )

    row_universe['last_year'] = row_universe['last_year'].astype(int)

    return row_universe


def process_usa_universe(usa_universe):

    """
    Same as process_row_universe, but for USA universe,
    no FX rates needed. as its in USD.
    """


    # Set dates to datetime format
    usa_universe['date'] = pd.to_datetime(usa_universe['date'])
    usa_universe['gvkey'] = usa_universe['gvkey'].astype(float).astype(str)

    # Add column to indicate that the LCU is US dollars
    usa_universe['curcdd'] = 'USD'

    # Create the correct year to merge on fundamentals
    # For dates in H1 (Jan-Jun), accounting data from Y-1 isn't out yet, so use Y-2's report.
    # For dates in H2 (Jul-Dec), accounting data from Y-1 is available.
    usa_universe['last_year'] = np.where(
        usa_universe['date'].dt.month <= 6, 
        usa_universe['date'].dt.year - 2, 
        usa_universe['date'].dt.year - 1
    )

    usa_universe['last_year'] = usa_universe['last_year'].astype(int)

    return usa_universe


def process_global_universe(usa_universe, row_universe, currency_filter, mktcap_covered):  
    # Drop old columns
    usa_universe.drop(columns=['cusip'], inplace=True)
    row_universe.drop(columns=['isin'], inplace=True)

    # Merge and generate global universe
    global_universe = pd.concat([usa_universe, row_universe[usa_universe.columns]], axis=0)

    # Re-scale ESG ratings
    global_universe['esg'] /= 100

    # Drop missings in `mktcap`
    global_universe = global_universe[global_universe['mktcap'].notna()]

    # Add temporal identifiers
    global_universe['month'] = global_universe['date'].dt.month
    global_universe['year'] = global_universe['date'].dt.year


    # Filter to keep listing in currency of interest
    global_universe = global_universe[global_universe['curcdd'].isin(currency_filter)] 

        # First, ensure the data is sorted by date within each group
    global_universe_sorted = global_universe.sort_values(by=['date'])

    # Use the last() function to get the last available market cap values
    last_values = global_universe_sorted.groupby(['month', 'year', 'curcdd', 'gvkey', 'iid']).agg(last_mktcap=('mktcap', 'last')).reset_index()

    # Sort `last_values`
    last_values = last_values.sort_values(by=['month', 'year', 'curcdd', 'last_mktcap'])

    # Aggregate mktcap data
    last_values['cumulative_mktcap'] = last_values.groupby(['month', 'year', 'curcdd'])['last_mktcap'].cumsum()
    last_values['total_mktcap'] = last_values.groupby(['month', 'year', 'curcdd'])['last_mktcap'].transform('sum')

    # Merge this novel mktcap data
    global_universe = pd.merge(
        global_universe, 
        last_values,
        on=['month', 'year', 'curcdd', 'gvkey', 'iid'], 
        how='left'
    )

    # Keep `mktcap_covered` of total market cap (of each currency area)
    global_universe = global_universe[global_universe['cumulative_mktcap'] > (1-mktcap_covered)*global_universe['total_mktcap']]

    # Format the gvkeys
    global_universe['gvkey'] = global_universe['gvkey'].dropna().astype(float).astype(int).astype(str) 

    return global_universe