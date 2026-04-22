import pandas as pd
import numpy as np
import wrds


#### 2.2.1 Recover dollar returns from Compustat

# From WRDS tutorials:

# To compute returns, you will need to apply a DAILY RETURN FACTOR (variable TRFD) to the close price. 
# That is, multiplying the current adjusted close price (PRCCD/AJEXDI) by the current total return factor (TRFD)
# and dividing the result by the product of the adjusted close price of the prior period multiplied by the 
# Total Return Factor of the prior period.

# In other words:
# 1. Adjust the close price for corporate actions
# 2. Compute the close price + dividends by multiplying PRCCD/AJEXDI for TRFD
# 3. Compute daily returns

# This can be aggregated to compute monthly figures.

def get_usa_universe(start_year, end_year, download_wrds_data=False):
    if download_wrds_data:

        conn=wrds.Connection(wrds_username='cbruce1')
        print("Connecting to WRDS...")


        usa_universe = conn.raw_sql(f"""
            WITH 
                usa_listings AS (
                    SELECT gvkey, priusa
                    FROM comp.company
                    WHERE priusa IS NOT NULL
                )
            
            SELECT 
                secd.datadate AS date, 
                secd.gvkey, 
                secd.iid, 
                secd.cusip, 
                (secd.prccd * secd.cshoc) as mktcap, 
                CASE WHEN secd.ajexdi <> 0 THEN (secd.trfd * secd.prccd / secd.ajexdi) ELSE NULL END AS tri
            FROM 
                comp.secd AS secd
            JOIN
                usa_listings
                ON (secd.gvkey=usa_listings.gvkey AND secd.iid=usa_listings.priusa)
            WHERE
                (secd.datadate BETWEEN '01/01/{start_year}' AND '12/31/{end_year}')
                AND (secd.secstat='A')
                AND (secd.tpci='0')
                AND (secd.prccd>0)
                AND (secd.cshtrd>0)
                AND (secd.exchg IN (11, 12, 14))
            ORDER BY 
                date;
        """, date_cols=['date'])

        # Keep entries with non-missing total return index
        usa_universe = usa_universe[usa_universe['tri'].notna()].reset_index(drop=True)
        usa_universe['year'] = pd.to_datetime(usa_universe['date']).dt.year
        usa_universe = usa_universe[usa_universe['year'] <= end_year]
        usa_universe = usa_universe.drop(columns=['year'])
        # Save to disk
        print('Saving to disk!')
        usa_universe.to_csv('./data/usa_universe.csv')
        return usa_universe

    # Load from file
    else:
        usa_universe = pd.read_csv('./data/usa_universe.csv').iloc[:, 1:]
        usa_universe['year'] = pd.to_datetime(usa_universe['date']).dt.year
        usa_universe = usa_universe[usa_universe['year'] <= end_year]

        return usa_universe






def get_row_universe(start_year, end_year, download_wrds_data=False):
    if download_wrds_data:

        conn=wrds.Connection(wrds_username='cbruce1')
        print("Connecting to WRDS...")

        row_universe = conn.raw_sql(f"""
            WITH 
                row_listings AS (
                    SELECT gvkey, prirow
                    FROM comp.g_company
                    WHERE prirow IS NOT NULL
                )
            
            SELECT 
                g_secd.datadate AS date, 
                g_secd.gvkey, 
                g_secd.iid, 
                g_secd.isin, 
                g_secd.curcdd, 
                (g_secd.prccd * g_secd.cshoc / g_secd.qunit) as mktcap_lcu, 
                CASE WHEN g_secd.ajexdi <> 0 THEN (g_secd.trfd * g_secd.prccd / (g_secd.qunit * g_secd.ajexdi)) ELSE NULL END AS tri_lcu
            FROM 
                comp.g_secd AS g_secd
            JOIN
                row_listings
                ON (g_secd.gvkey=row_listings.gvkey AND g_secd.iid=row_listings.prirow)
            WHERE
                (g_secd.datadate BETWEEN '01/01/{start_year}' AND '12/31/{end_year}')
                AND (g_secd.secstat='A')
                AND (g_secd.tpci='0')
                AND (g_secd.prccd>0)
                AND (g_secd.cshtrd>0)
                AND (g_secd.exchg IN (273, 132, 294, 278, 221, 261, 286, 167, 286, 154, 171, 107, 172, 209, 198, 271, 104, 192, 122, 193, 201, 151, 194))
                AND (g_secd.curcdd IN ('CHF', 'GBP', 'EUR'))
            ORDER BY 
                date;
        """, date_cols=['date'])
        print("done downloading from WRDS")

        # Keep entries with non-missing total return index
        row_universe = row_universe[row_universe['tri_lcu'].notna()].reset_index(drop=True)
        row_universe['year'] = pd.to_datetime(row_universe['date']).dt.year
        row_universe = row_universe[row_universe['year'] <= end_year]
        row_universe = row_universe.drop(columns=['year'])
        # Save to disk
        print('Saving to disk!')
        row_universe.to_csv('./data/row_universe.csv')

        return row_universe
    # Load from file
    else:
        row_universe = pd.read_csv('./data/row_universe.csv').iloc[:, 1:]
        row_universe['year'] = pd.to_datetime(row_universe['date']).dt.year
        row_universe = row_universe[row_universe['year'] <= end_year]
    return row_universe


def get_japan_universe(start_year, end_year, download_wrds_data=False):
    if download_wrds_data:
        conn = wrds.Connection(wrds_username="cbruce1")  # or pass username like RoW/US do
        print("Connecting to WRDS...")

        japan_universe = conn.raw_sql(
            f"""
            WITH japan_listings AS (
                SELECT gvkey, prirow
                FROM comp.g_company
                WHERE prirow IS NOT NULL
            )
            SELECT
                g_secd.datadate AS date,
                g_secd.gvkey,
                g_secd.iid,
                g_secd.isin,
                g_secd.curcdd,
                (g_secd.prccd * g_secd.cshoc / g_secd.qunit) AS mktcap_lcu,
                CASE
                    WHEN g_secd.ajexdi <> 0
                    THEN (g_secd.trfd * g_secd.prccd / (g_secd.qunit * g_secd.ajexdi))
                    ELSE NULL
                END AS tri_lcu
            FROM comp.g_secd AS g_secd
            JOIN japan_listings
              ON (g_secd.gvkey = japan_listings.gvkey AND g_secd.iid = japan_listings.prirow)
            WHERE
                g_secd.datadate BETWEEN '01/01/{start_year}' AND '12/31/{end_year}'
                AND g_secd.secstat = 'A'
                AND g_secd.tpci = '0'
                AND g_secd.prccd > 0
                AND g_secd.cshtrd > 0
                AND g_secd.exchg = 264
                AND g_secd.curcdd = 'JPY'
            ORDER BY date;
            """,
            date_cols=["date"],
        )

        japan_universe = japan_universe[japan_universe["tri_lcu"].notna()].reset_index(drop=True)
        japan_universe["year"] = pd.to_datetime(japan_universe["date"]).dt.year
        japan_universe = japan_universe[japan_universe["year"] <= end_year]
        japan_universe = japan_universe.drop(columns=["year"])

        print("Saving to disk!")
        japan_universe.to_csv("./data/japan_universe.csv")
        return japan_universe

    else:
        japan_universe = pd.read_csv("./data/japan_universe.csv").iloc[:, 1:]
        japan_universe["year"] = pd.to_datetime(japan_universe["date"]).dt.year
        japan_universe = japan_universe[japan_universe["year"] <= end_year]
        return japan_universe



def get_processed_fx_rates(end_year):


    # Download from FRB H.10 without JPY:
    # https://www.federalreserve.gov/datadownload/Output.aspx?rel=H10&series=d3efeda92e22923be9b7c3d7250706ac&lastobs=&from=01/01/2009&to=12/31/2024&filetype=csv&label=include&layout=seriescolumn


    #With JPY:
    #https://www.federalreserve.gov/datadownload/Download.aspx?rel=H10&series=2525778bbd3442ab095d4c1f1b4dd2ab&filetype=csv&label=include&layout=seriescolumn&from=01/01/2009&to=12/31/2024
    try:
        # Load exchange rate data
        FRB_H10 = pd.read_csv(f'./data/FRB/FRB_H10_{end_year}.csv')
        FRB_H10.replace('ND', np.nan, inplace=True)
        FRB_H10.columns = ['date', 'EUR', 'GBP','DKK','JPY', 'NOK', 'SEK', 'CHF']

        # Foreign exchange rate data
        fx_rates = FRB_H10.iloc[5:].copy()

        # Set rates to float (safer: coerce non-numeric to NaN)
        fx_rates.iloc[:, 1:] = fx_rates.iloc[:, 1:].apply(pd.to_numeric, errors='coerce')

        # Invert ALL currencies (everything except date)
        fx_rates.iloc[:, 1:] = 1 / fx_rates.iloc[:, 1:]

        # Forward-fill fx rates (in levels)
        fx_rates = fx_rates.ffill(axis=0)

        # Convert to long format
        fx_rates = fx_rates.melt(id_vars=['date'], var_name='curcdd', value_name='rate')

        # Set dates to datetime format
        fx_rates["date"] = pd.to_datetime(fx_rates["date"], format="%d/%m/%Y")
        #fx_rates["date"] = pd.to_datetime(fx_rates["date"], format="%d/%m/%Y")

        return fx_rates
    
    except Exception as e:
        print(f"Error retrieving FX rates: {e}")
        print("Make sure you have the FRB_H10_{end_year}.csv file in the data/FRB folder")






def get_snp_esg_merge_to_universe(usa_universe, row_universe):

    sp_esg_table = pd.read_csv('./data/ESG/SP_ESG_20231231.csv')
    sp_esg_table['gvkey'] = sp_esg_table['gvkey'].astype(float).astype(str)
    #sp_esg_table = sp_esg_table.rename(columns={"esg_sp": "esg"})

    # Forward-fill scores to get in each quarter the last available score
    full_sp_index = pd.MultiIndex.from_product(
        [
            sp_esg_table['gvkey'].unique(),
            sorted(sp_esg_table['year'].unique()),
            sorted(sp_esg_table['quarter'].unique())
        ],
        names=['gvkey', 'year', 'quarter']
    )
    sp_esg_table = sp_esg_table.set_index(['gvkey', 'year', 'quarter']).reindex(full_sp_index).reset_index()
    sp_esg_table = sp_esg_table.sort_values(by=['gvkey', 'year', 'quarter']).reset_index(drop=True)
    sp_esg_table['esg_sp'] = sp_esg_table.groupby('gvkey')['esg_sp'].ffill()

    # Subsection of `sp_esg_table` to merge
    esg_to_merge = sp_esg_table[['gvkey', 'year', 'quarter', 'esg_sp']].dropna().copy()

    # Create a date column representing the end of the quarter. This simplifies merging!
    esg_to_merge['esg_date'] = pd.to_datetime(
        esg_to_merge['year'].astype(int).astype(str) + 'Q' + esg_to_merge['quarter'].astype(int).astype(str)
    ) + pd.tseries.offsets.QuarterEnd(0)

    # Sort by the entity identifier and the new date column, which is required for merge_asof
    esg_to_merge = esg_to_merge.sort_values(by=['esg_date', 'gvkey'])

    # Ensure `usa_universe` and `row_universe` are sorted
    usa_universe = usa_universe.sort_values(by=['date', 'gvkey'])
    row_universe = row_universe.sort_values(by=['date', 'gvkey'])

    # Merge
    # NOTE: `direction='backward'` is key: it finds the last available ESG data prior to or on the universe date.
    usa_universe = pd.merge_asof(
        usa_universe,
        esg_to_merge,
        left_on='date',
        right_on='esg_date',
        by='gvkey',
        direction='backward', 
        tolerance=pd.Timedelta('335 days')
    )

    row_universe = pd.merge_asof(
        row_universe,
        esg_to_merge,
        left_on='date',
        right_on='esg_date',
        by='gvkey',
        direction='backward', 
        tolerance=pd.Timedelta('335 days')
    )
    return usa_universe, row_universe




def get_refinitive_snp_merge_to_universe(usa_universe, row_universe):

    # Function to get the last non-NaN value in each group
    def last_non_nan(series):
        return series.dropna().iloc[-1] if not series.dropna().empty else np.nan

    refinitiv_esg_table = pd.read_csv('./data/ESG/esg_table.csv')
    refinitiv_identifiers_table = pd.read_parquet('./data/ESG/identifiers_table.parquet')[['RIC', 'CUSIP', 'ISIN']]

    # Join identifiers into `refinitiv_esg_table`
    refinitiv_esg_table = pd.merge(
        refinitiv_esg_table, 
        refinitiv_identifiers_table, 
        left_on=['Instrument'], 
        right_on=['RIC'], 
        how='inner'
    )

    # Keep key elements
    refinitiv_esg_table = refinitiv_esg_table[['Date', 'RIC', 'CUSIP', 'ISIN', 'ESG Score']]

    # Drop entries without ESG score
    refinitiv_esg_table.dropna(subset=['ESG Score'], inplace=True)

    # Convert the 'Date' column to datetime
    refinitiv_esg_table['Date'] = pd.to_datetime(refinitiv_esg_table['Date'])

    # Generate column with `Date` year
    refinitiv_esg_table['Year'] = refinitiv_esg_table['Date'].dt.year

    # Sort by Date
    refinitiv_esg_table = refinitiv_esg_table.sort_values(by='Date').reset_index(drop=True)

    # Rename 'ESG Score' column to 'esg'
    refinitiv_esg_table = refinitiv_esg_table.rename(columns={'ESG Score': 'esg_refinitive'})

    # Convert all column names to lowercase
    refinitiv_esg_table.columns = refinitiv_esg_table.columns.str.lower()

    # Remove first chunk of duplicates
    refinitiv_esg_table = refinitiv_esg_table.groupby(['ric', 'year']).agg(last_non_nan).reset_index()

    # Find further duplicates
    cusip_groups = refinitiv_esg_table.groupby('cusip')['ric'].agg(lambda x: x.unique())
    isin_groups = refinitiv_esg_table.groupby('isin')['ric'].agg(lambda x: x.unique())

    duplicate_rics = \
        list(cusip_groups[cusip_groups.apply(lambda x: len(x) > 1)].apply(lambda x: x[1]).values) + \
        list(isin_groups[isin_groups.apply(lambda x: len(x) > 1)].apply(lambda x: x[1]).values)

    duplicate_rics = sorted(set(duplicate_rics))

    # Remove further duplicates
    refinitiv_esg_table = refinitiv_esg_table[~refinitiv_esg_table['ric'].isin(duplicate_rics)]

    # Map esg data onto `usa_universe`
    usa_universe = pd.merge(
        usa_universe, 
        refinitiv_esg_table[['cusip', 'year', 'esg_refinitive']].dropna(subset=['cusip']), 
        left_on=['cusip', 'last_year'], 
        right_on=['cusip', 'year'], 
        how='left'
    )

    # Map esg data onto `row_universe`
    row_universe = pd.merge(
        row_universe, 
        refinitiv_esg_table[['isin', 'year', 'esg_refinitive']].dropna(subset=['isin']), 
        left_on=['isin', 'last_year'], 
        right_on=['isin', 'year'], 
        how='left'
    )
    return usa_universe, row_universe



def get_famafrench_factors(start_year, end_year, region, download_developed_ff_data=False):
        if download_developed_ff_data:

            # download manually from:
            # https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html
            import pandas_datareader.data as web
            ff3 = web.FamaFrenchReader('Developed_3_Factors', start=f'01-01-{start_year}', end=f'31-12-{end_year}').read()
            ff5 = web.FamaFrenchReader('Developed_5_Factors', start=f'01-01-{start_year}', end=f'31-12-{end_year}').read()
            
            ff3 = ff3[0].reset_index().rename(columns={'Date':'date','Mkt-RF': 'mktrf', 'SMB': 'smb', 'HML': 'hml', 'RF': 'rf'})
            ff5 = ff5[0].reset_index().rename(columns={'Date':'date','Mkt-RF': 'mktrf', 'SMB': 'smb', 'HML': 'hml', 'RF': 'rf', 'RMW': 'rmw', 'CMA': 'cma'})

            ff3.to_csv('./data/Developed_3_Factors.csv', index=False)
            ff5.to_csv('./data/Developed_5_Factors.csv', index=False)
        else:

            if region == "Developed":
                ff_file = "./data/FAMA/Developed_3_Factors.csv"
            elif region == "Europe":
                ff_file = "./data/FAMA/Europe_3_Factors.csv"
            elif region == "Japan":
                ff_file = "./data/FAMA/Japan_3_Factors.csv"
            elif region == "North_America":
                ff_file = "./data/FAMA/North_America_3_Factors.csv"
            else:
                raise ValueError(f"Invalid region: {region}, try one of the following: Developed, Europe, Japan, North_America")

            ff3 = pd.read_csv(ff_file)
            
            ff3 = ff3.rename(columns={'Date':'date','Mkt-RF': 'mktrf', 'SMB': 'smb', 'HML': 'hml', 'RF': 'rf'})

            # Some provided CSVs have trailing blank rows, which forces float dtype for `date`
            # (e.g. 199007.0) and breaks strict "%Y%m" parsing.
            ff3["date"] = pd.to_numeric(ff3["date"], errors="coerce")
            ff3 = ff3.dropna(subset=["date"]).copy()
            ff3["date"] = ff3["date"].astype("int64").astype(str)
            ff3["date"] = pd.to_datetime(ff3["date"], format="%Y%m")

        year = pd.to_datetime(ff3["date"]).dt.year
        ff3 = ff3[(year <= end_year) & (year > start_year - 1)].copy()
        ff3["date"] = pd.to_datetime(ff3["date"]).dt.to_period("M")

        # Scale factor returns from percent to decimal without touching the date column
        fama_french = ff3.set_index("date").div(100).reset_index()
        return fama_french




def get_processed_index(file_path, signal_0_simple_quantiles):
    
    if file_path[-4:] == "xlsx":
        MSCI = pd.read_excel(file_path, index_col= "Date")
    elif file_path[-4:] == "csv":
        MSCI = pd.read_csv(file_path, index_col= "Date")
    elif file_path[-4:] == "parquet":
        MSCI = pd.read_parquet(file_path)

            
    MSCI["return"] = MSCI["MSCI_price"].pct_change()
    MSCI.index = pd.to_datetime(MSCI.index)


    #Intesrect the same dates:>

    # Intersect on year-month (month-end day can differ from signal_0_simple_quantiles)
    ym_msci = MSCI.index.to_period("M")
    ym_sig = signal_0_simple_quantiles.index.to_period("M")
    common_ym = ym_msci.unique().intersection(ym_sig.unique())

    MSCI = MSCI[ym_msci.isin(common_ym)].sort_index()
    # One row per month when MSCI is higher-frequency (last observation in each month)
    MSCI = MSCI.groupby(MSCI.index.to_period("M"), sort=True).last()
    MSCI.index = signal_0_simple_quantiles.index

    return MSCI







