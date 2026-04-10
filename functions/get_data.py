import pandas as pd
import numpy as np
import wrds







def get_row_universe(start_year, end_year, download_wrds_data=False):
    if download_wrds_data:
        
        conn=wrds.Connection(wrds_username='cbruce1')

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





