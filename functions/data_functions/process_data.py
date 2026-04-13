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