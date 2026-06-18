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
                g_secd.prccd,
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
        japan_universe.to_csv("./data/japan_universe_new.csv")
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
        FRB_H10 = pd.read_csv(f'./data/FRB/FRB_H10_2024.csv')
        FRB_H10.replace('ND', np.nan, inplace=True)
        FRB_H10.columns = ['date', 'EUR', 'GBP','DKK','JPY', 'NOK', 'SEK', 'CHF']

        # Foreign exchange rate data
        fx_rates = FRB_H10.iloc[5:].copy()

        # Set rates to float (safer: coerce non-numeric to NaN)
        fx_rates.iloc[:, 1:] = fx_rates.iloc[:, 1:].apply(pd.to_numeric, errors='coerce')

        # FRB H.10 quotes EUR and GBP as USD-per-unit (RXI$US series) but all
        # other currencies as units-per-USD (RXI series). Invert only EUR/GBP so
        # every rate is "foreign per USD"; then `mktcap_lcu / rate` is correct.
        for c in ["EUR", "GBP"]:
            fx_rates[c] = 1 / fx_rates[c]
        # JPY/DKK/NOK/SEK/CHF already in "foreign per USD" — leave as-is

        # Forward-fill fx rates (in levels)
        fx_rates = fx_rates.ffill(axis=0)

        # Convert to long format
        fx_rates = fx_rates.melt(id_vars=['date'], var_name='curcdd', value_name='rate')

        # Set dates to datetime format
        fx_rates["date"] = pd.to_datetime(fx_rates["date"], format="%d/%m/%Y")
        #fx_rates["date"] = pd.to_datetime(fx_rates["date"], format="%d/%m/%Y")

        fx_rates = fx_rates[fx_rates['date'] <= f'12/31/{end_year}']

        return fx_rates
    
    except Exception as e:
        print(f"Error retrieving FX rates: {e}")
        print("Make sure you have the FRB_H10_{end_year}.csv file in the data/FRB folder")






def get_snp_esg_merge_to_universe(usa_universe, row_universe, japan_universe=None):

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
    if japan_universe is not None:
        japan_universe = japan_universe.sort_values(by=["date", "gvkey"])

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
    if japan_universe is not None:
        japan_universe = pd.merge_asof(
            japan_universe,
            esg_to_merge,
            left_on="date",
            right_on="esg_date",
            by="gvkey",
            direction="backward",
            tolerance=pd.Timedelta("335 days"),
        )
        return usa_universe, row_universe, japan_universe

    return usa_universe, row_universe




def get_refinitive_snp_merge_to_universe(usa_universe, row_universe, japan_universe=None):
    """Merge LSEG / Refinitiv ESG scores onto the regional universes.

    Data source: ``./data/ESG/ESG Ratings/LSEG ESG Score.csv`` (LSEG is the new Refinitiv
    export). Unlike the previous export this file already carries ``cusip`` and ``isin``
    inline, so the old RIC -> identifier crosswalk (``identifiers_table.parquet``) is not
    needed.

    Design notes / why this is correct and consistent with the previous implementation:
      * Output column is still ``esg_refinitive`` -> drop-in compatible with process_data,
        Main.ipynb (``universe_signals``/rolling alpha) and output_paths.
      * Merge keys are identical to the old logic:
            USA         -> ['cusip', 'last_year'] == ['cusip', 'year']
            ROW / Japan -> ['isin',  'last_year'] == ['isin',  'year']
        and ``how='left'`` preserves every universe row (``esg_refinitive`` is NaN when
        unmatched), exactly as before.
      * ``cusip``/``isin`` are read as strings so leading zeros / alpha check chars survive
        and match the universe identifier format (universe cusip is a 9-char string).
      * The raw file is already one row per (orgpermid, year); we additionally collapse to
        UNIQUE (cusip, year) and (isin, year) keys so the left-join cannot duplicate a
        universe row in the rare case (1 cusip, 2 isin in this file) where two issuers share
        an identifier+year. ``mean`` resolves those ties.

    IMPORTANT: LSEG ``valuescore`` is already on a 0-1 scale, so ``process_global_universe``
    must NOT divide ``esg_refinitive`` by 100 (the old 0-100 score did). See process_data.py.

    The previous RIC-based implementation is preserved verbatim as
    ``get_refinitive_snp_merge_to_universe_OLD`` in case we want to revert.
    """

    # --- Load new LSEG / Refinitiv export (cusip + isin already inline) ---
    refinitiv_esg_table = pd.read_csv(
        './data/ESG/ESG Ratings/LSEG ESG Score.csv',
        dtype={'cusip': str, 'isin': str},
    )

    # --- Keep usable ESG score rows only ---
    # ``.copy()`` so the subsequent column assignments operate on an owned frame
    # (avoids the pandas SettingWithCopy / chained-assignment FutureWarning).
    refinitiv_esg_table = refinitiv_esg_table[refinitiv_esg_table['fieldname'] == 'ESGScore'].copy()
    refinitiv_esg_table = refinitiv_esg_table.dropna(subset=['valuescore'])

    # Keep the downstream column name; valuescore is already 0-1 (no rescaling here).
    refinitiv_esg_table = refinitiv_esg_table.rename(columns={'valuescore': 'esg_refinitive'})

    # Year as int to match the universe-side `last_year` (also int).
    refinitiv_esg_table['year'] = refinitiv_esg_table['year'].astype(int)

    # --- Collapse to UNIQUE merge keys (guards against row duplication on the left-join) ---
    usa_esg = (
        refinitiv_esg_table.dropna(subset=['cusip'])
        .groupby(['cusip', 'year'], as_index=False)['esg_refinitive'].mean()
    )
    row_esg = (
        refinitiv_esg_table.dropna(subset=['isin'])
        .groupby(['isin', 'year'], as_index=False)['esg_refinitive'].mean()
    )

    # --- Map esg data onto `usa_universe` (merge on CUSIP) ---
    usa_universe = pd.merge(
        usa_universe,
        usa_esg,
        left_on=['cusip', 'last_year'],
        right_on=['cusip', 'year'],
        how='left',
    )

    # --- Map esg data onto `row_universe` (merge on ISIN) ---
    row_universe = pd.merge(
        row_universe,
        row_esg,
        left_on=['isin', 'last_year'],
        right_on=['isin', 'year'],
        how='left',
    )

    # --- Map esg data onto `japan_universe` (Japan universe uses ISIN like ROW) ---
    if japan_universe is not None:
        japan_universe = pd.merge(
            japan_universe,
            row_esg,
            left_on=['isin', 'last_year'],
            right_on=['isin', 'year'],
            how='left',
        )
        return usa_universe, row_universe, japan_universe

    return usa_universe, row_universe


def get_msci_esg_merge_to_universe(usa_universe, row_universe, japan_universe=None, score_column="industry"):
    """Merge MSCI ESG scores onto the regional universes.

    Data source: ``./data/ESG/ESG Ratings/MSCI ESG Updated.csv`` — a MONTHLY panel
    (``issuer_isin`` x ``as_of_date``) of MSCI ESG metrics spanning ~2007-2025.

    Design notes / consistency with the LSEG and S&P merge functions:
      * Output column is ``esg_msci`` -> drop-in for process_data, Main.ipynb
        (``universe_signals`` / rolling alpha) and output_paths.
      * Annual collapse: keep the LAST month of each calendar year per issuer, then
        left-merge on the universe ``last_year`` lag key (USA on cusip, ROW/Japan on
        isin). ``how='left'`` preserves every universe row (``esg_msci`` is NaN when
        unmatched), exactly like the other ESG merges. Picking December-of-year-Y and
        merging via ``last_year`` keeps the join point-in-time safe (no look-ahead).
      * MSCI carries ISIN only; the USA universe matches via a derived CUSIP
        (``cusip = isin[2:11]`` for US ISINs, whose NSIN is the 9-char CUSIP).
      * Scores are on a 0-10 scale; ``process_global_universe`` divides ``esg_msci`` by
        10 for 0-1 consistency with ``esg_refinitive`` / ``esg_sp``.

    ``score_column`` toggle (set via ``msci_score_column`` in Main.ipynb):
        "industry" -> ``industry_adjusted_score`` (100% populated; default)
        "weighted" -> ``weighted_average_score``  (~85% populated)
    """

    _MSCI_COLS = {"industry": "industry_adjusted_score", "weighted": "weighted_average_score"}
    if score_column not in _MSCI_COLS:
        raise ValueError(
            f"score_column must be one of {list(_MSCI_COLS)}, got {score_column!r}"
        )
    raw_col = _MSCI_COLS[score_column]

    # --- Load MSCI monthly panel (ISIN inline; no identifier crosswalk needed) ---
    msci = pd.read_csv(
        './data/ESG/ESG Ratings/MSCI ESG Updated.csv',
        dtype={'issuer_isin': str},
        low_memory=False,
    )

    # --- Standardise types and keep usable score rows only ---
    msci['as_of_date'] = pd.to_datetime(msci['as_of_date'], format='%d/%m/%Y', errors='coerce')
    msci[raw_col] = pd.to_numeric(msci[raw_col], errors='coerce')  # drops any '#REF!'-type junk
    msci = msci.dropna(subset=['issuer_isin', 'as_of_date', raw_col]).copy()
    msci['year'] = msci['as_of_date'].dt.year.astype(int)

    # --- Collapse to the LAST month of each calendar year per issuer ---
    msci = (
        msci.sort_values('as_of_date')
        .groupby(['issuer_isin', 'year'], as_index=False)
        .tail(1)
    )
    msci = msci.rename(columns={raw_col: 'esg_msci'})

    # --- Collapse to UNIQUE merge keys (guards the left-join against row duplication) ---
    row_esg = (
        msci.groupby(['issuer_isin', 'year'], as_index=False)['esg_msci'].mean()
        .rename(columns={'issuer_isin': 'isin'})
    )

    usa_src = msci[msci['issuer_isin'].str[:2] == 'US'].copy()
    usa_src['cusip'] = usa_src['issuer_isin'].str[2:11]
    usa_esg = usa_src.groupby(['cusip', 'year'], as_index=False)['esg_msci'].mean()

    # --- Map esg data onto `usa_universe` (merge on derived CUSIP) ---
    usa_universe = pd.merge(
        usa_universe,
        usa_esg,
        left_on=['cusip', 'last_year'],
        right_on=['cusip', 'year'],
        how='left',
    )

    # --- Map esg data onto `row_universe` (merge on ISIN) ---
    row_universe = pd.merge(
        row_universe,
        row_esg,
        left_on=['isin', 'last_year'],
        right_on=['isin', 'year'],
        how='left',
    )

    # --- Map esg data onto `japan_universe` (Japan universe uses ISIN like ROW) ---
    if japan_universe is not None:
        japan_universe = pd.merge(
            japan_universe,
            row_esg,
            left_on=['isin', 'last_year'],
            right_on=['isin', 'year'],
            how='left',
        )
        return usa_universe, row_universe, japan_universe

    return usa_universe, row_universe


def _coverage_snp_exact_year(usa_universe, row_universe, japan_universe=None):
    """Coverage-only S&P attach on an EXACT fiscal-year basis (NO ffill / merge_asof /
    tolerance), so the diagnostic compares S&P like-for-like with MSCI/Refinitiv.

    The production merge ``get_snp_esg_merge_to_universe`` forward-fills scores and attaches
    as-of the trading date with an ~11-month tolerance, which carries a score into later
    (even data-absent) years and overstates S&P coverage relative to the exact-year
    MSCI/Refinitiv merges. Here a score counts only when the firm's own fiscal year
    (``last_year``) has a raw S&P observation. NOT used by the pipeline.
    """
    sp = pd.read_csv('./data/ESG/SP_ESG_20231231.csv')
    sp['gvkey'] = sp['gvkey'].astype(float).astype(str)   # same gvkey form as the pipeline merge
    sp = sp.dropna(subset=['esg_sp'])
    # one row per exact (gvkey, fiscal year); mean resolves the quarterly observations
    sp_year = sp.groupby(['gvkey', 'year'], as_index=False)['esg_sp'].mean()
    sp_year['year'] = sp_year['year'].astype(int)

    def _attach(u):
        if u is None:
            return None
        return u.merge(
            sp_year, left_on=['gvkey', 'last_year'], right_on=['gvkey', 'year'], how='left'
        )

    if japan_universe is not None:
        return _attach(usa_universe), _attach(row_universe), _attach(japan_universe)
    return _attach(usa_universe), _attach(row_universe)


def merge_all_esg_to_universe(usa_universe, row_universe, japan_universe=None, msci_score_column="industry"):
    """Attach ALL THREE provider columns (``esg_refinitive``, ``esg_msci``, ``esg_sp``)
    to the regional universes regardless of ``esg_choice``.

    This is for the ESG-coverage DIAGNOSTIC only: the production pipeline still merges a
    single provider (driven by ``esg_choice``) and only standardises that one as a
    ``universe_signal``, so adding the other two columns here cannot change any analysis
    result. It simply lets the coverage table report every provider in one run.

    All three are attached on an EXACT fiscal-year basis here (MSCI/Refinitiv as in the
    pipeline; S&P via ``_coverage_snp_exact_year`` rather than the pipeline's ffill/as-of
    merge) so the coverage figures are like-for-like across providers.

    Safe to call on universes that already carry one provider's column (e.g. after the
    ``esg_choice`` merge in Main.ipynb): any pre-existing provider columns and the helper
    columns each underlying merge introduces (``year`` / ``quarter`` / ``esg_date``) are
    stripped first and between merges, so they cannot collide (``year_x`` / ``year_y``) or
    leak downstream. Operates on copies; the inputs are never mutated.
    """
    provider_cols = ["esg_refinitive", "esg_msci", "esg_sp"]
    helper_cols = ["year", "quarter", "esg_date"]

    def _strip(df, cols):
        if df is None:
            return None
        return df.drop(columns=[c for c in cols if c in df.columns], errors="ignore")

    # Start from clean copies: no stale provider/helper columns to collide on.
    u = _strip(usa_universe, provider_cols + helper_cols).copy()
    r = _strip(row_universe, provider_cols + helper_cols).copy()
    j = None if japan_universe is None else _strip(japan_universe, provider_cols + helper_cols).copy()

    if j is not None:
        u, r, j = get_refinitive_snp_merge_to_universe(u, r, j)
        u, r, j = _strip(u, helper_cols), _strip(r, helper_cols), _strip(j, helper_cols)
        u, r, j = get_msci_esg_merge_to_universe(u, r, j, score_column=msci_score_column)
        u, r, j = _strip(u, helper_cols), _strip(r, helper_cols), _strip(j, helper_cols)
        # S&P on an exact fiscal-year basis (coverage-only; see _coverage_snp_exact_year).
        u, r, j = _coverage_snp_exact_year(u, r, j)
        u, r, j = _strip(u, helper_cols), _strip(r, helper_cols), _strip(j, helper_cols)
        return u, r, j

    u, r = get_refinitive_snp_merge_to_universe(u, r)
    u, r = _strip(u, helper_cols), _strip(r, helper_cols)
    u, r = get_msci_esg_merge_to_universe(u, r, score_column=msci_score_column)
    u, r = _strip(u, helper_cols), _strip(r, helper_cols)
    # S&P on an exact fiscal-year basis (coverage-only; see _coverage_snp_exact_year).
    u, r = _coverage_snp_exact_year(u, r)
    u, r = _strip(u, helper_cols), _strip(r, helper_cols)
    return u, r


def get_refinitive_snp_merge_to_universe_OLD(usa_universe, row_universe, japan_universe=None):
    """DEPRECATED / BACKUP: original RIC-based Refinitiv merge.

    Kept verbatim so we can revert to the old ESG source. Reads the old files
    ``esg_table.csv`` + ``identifiers_table.parquet`` and joins RIC -> CUSIP/ISIN.
    Not called by the pipeline; swap the call in Main.ipynb to use it.
    """

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
    # Map esg data onto `japan_universe` (Japan universe uses ISIN like ROW)
    if japan_universe is not None:
        japan_universe = pd.merge(
            japan_universe,
            refinitiv_esg_table[["isin", "year", "esg_refinitive"]].dropna(subset=["isin"]),
            left_on=["isin", "last_year"],
            right_on=["isin", "year"],
            how="left",
        )
        return usa_universe, row_universe, japan_universe

    return usa_universe, row_universe



def get_famafrench_factors(start_year, end_year, region, factors_number, download_developed_ff_data=False):
        if download_developed_ff_data:

            # download manually from:
            # https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html

            if factors_number == 3:
                import pandas_datareader.data as web
                ff3 = web.FamaFrenchReader('Developed_3_Factors', start=f'01-01-{start_year}', end=f'31-12-{end_year}').read()
                ff = ff3[0].reset_index().rename(columns={'Date':'date','Mkt-RF': 'mktrf', 'SMB': 'smb', 'HML': 'hml', 'RF': 'rf'})
                ff.to_csv('./data/Developed_3_Factors.csv', index=False)
            elif factors_number == 5:
                ff5 = web.FamaFrenchReader('Developed_5_Factors', start=f'01-01-{start_year}', end=f'31-12-{end_year}').read()
                ff= ff5[0].reset_index().rename(columns={'Date':'date','Mkt-RF': 'mktrf', 'SMB': 'smb', 'HML': 'hml', 'RF': 'rf', 'RMW': 'rmw', 'CMA': 'cma'})
                ff.to_csv('./data/Developed_5_Factors.csv', index=False)
            else:
                raise ValueError(f"Invalid factors number: {factors_number}, try one of the following: 3, 5")
        else:
            if factors_number == 3:
                if region == "Developed":
                    ff_file = "./data/FAMA/Developed_3_Factors.csv"
                elif region == "Europe":
                    ff_file = "./data/FAMA/Europe_3_Factors.csv"
                elif region == "Japan":
                    ff_file = "./data/FAMA/Japan_3_Factors.csv"
                elif region == "North_America_and_Canada":
                    ff_file = "./data/FAMA/North_America_3_Factors.csv"
                elif region == "United_States":
                    ff_file = "./data/FAMA/United_States_3_Factors.csv"
                else:
                    raise ValueError(f"Invalid region: {region}, try one of the following: Developed, Europe, Japan, North_America_and_Canada")
            elif factors_number == 5:
                if region == "Developed":
                    ff_file = "./data/FAMA/Developed_5_Factors.csv"
                elif region == "Europe":
                    ff_file = "./data/FAMA/Europe_5_Factors.csv"
                elif region == "Japan":
                    ff_file = "./data/FAMA/Japan_5_Factors.csv"
                elif region == "North_America_and_Canada":
                    ff_file = "./data/FAMA/North_America_5_Factors.csv"
                elif region == "United_States":
                    ff_file = "./data/FAMA/United_States_5_Factors.csv"
                else:
                    raise ValueError(f"Invalid region: {region}, try one of the following: Developed, Europe, Japan, North_America")
            else:
                raise ValueError(f"Invalid factors number: {factors_number}, try one of the following: 3, 5")



            ff = pd.read_csv(ff_file)
            
            if factors_number == 3:
                ff= ff.rename(columns={'Date':'date','Mkt-RF': 'mktrf', 'SMB': 'smb', 'HML': 'hml', 'RF': 'rf'})
            elif factors_number == 5:
                ff= ff.rename(columns={'Date':'date','Mkt-RF': 'mktrf', 'SMB': 'smb', 'HML': 'hml', 'RMW': 'rmw', 'CMA': 'cma', 'RF': 'rf'})
            else:
                raise ValueError(f"Invalid factors number: {factors_number}, try one of the following: 3, 5")

            # Some provided CSVs have trailing blank rows, which forces float dtype for `date`
            # (e.g. 199007.0) and breaks strict "%Y%m" parsing.
            ff["date"] = pd.to_numeric(ff["date"], errors="coerce")
            ff = ff.dropna(subset=["date"]).copy()
            ff["date"] = ff["date"].astype("int64").astype(str)
            ff["date"] = pd.to_datetime(ff["date"], format="%Y%m")

        year = pd.to_datetime(ff["date"]).dt.year
        ff = ff[(year <= end_year) & (year > start_year - 1)].copy()
        ff["date"] = pd.to_datetime(ff["date"]).dt.to_period("M")

        # Scale factor returns from percent to decimal without touching the date column
        fama_french = ff.set_index("date").div(100).reset_index()
        return fama_french


    
#Always download accounting data, each subdata has unique gvkeys to download.
def get_accounting_data(global_universe, region_analysis, start_year, end_year, dowload_acc_data = True):

    conn=wrds.Connection(wrds_username='cbruce1')

    # Get accounting ratios
    full_gvkeys = [str.zfill(gvkey, 6) for gvkey in global_universe['gvkey'].astype(float).astype(int).astype(str).unique()]
    table = 'funda'
    varlist = ['gvkey', 'datadate', 'at', 'sale', 'ebitda', 'ebit']
    start_date = f'{start_year}-01-01'
    end_date = f'{end_year}-12-30'

    # Download from WRDS
    if dowload_acc_data:
        na_call = "SELECT " + ', '.join(varlist + ['ni']) + '\n' + "FROM comp_na_daily_all." + table + '\n'+ """
            WHERE gvkey IN %(gvkey_list)s
            AND datadate BETWEEN %(start_date)s AND %(end_date)s
        """
        compustat_na = conn.raw_sql(
            na_call,
            params={
                    "gvkey_list": tuple(full_gvkeys),
                    "start_date": start_date,
                    "end_date": end_date}
        )
        df = pd.DataFrame(compustat_na)
        
        global_call = "SELECT " + ', '.join(varlist + ['nicon']) + '\n' + "FROM comp_global_daily.g_" + table + '\n' + """     
            WHERE gvkey IN %(gvkey_list)s
            AND datadate BETWEEN %(start_date)s AND %(end_date)s
        """
        compustat_global = conn.raw_sql(
            global_call,
            params={
                    "gvkey_list": tuple(full_gvkeys),
                    "start_date": start_date,
                    "end_date": end_date}
        )
        df2 = pd.DataFrame(compustat_global)
        
        # rename col in df2 called nicon to ni
        df2 = df2.rename(columns={'nicon': 'ni'})

        # Concatenate output
        dt = pd.concat([df, df2])

        #select only profitable stocks
        dt = dt[(dt['at']>0) & (dt['sale']>0)]

        dt['roa0'] = dt['ebitda']/dt['at']
        dt['roa1'] = dt['ebit']/dt['at']
        dt['roa2'] = dt['ni']/dt['at']
        dt['ros0'] = dt['ebitda']/dt['sale']
        dt['ros1'] = dt['ebit']/dt['sale']
        dt['ros2'] = dt['ni']/dt['sale']
        
        dt['sales_intensity'] = dt['sale']/dt['at']
        
        dt['year'] = pd.to_datetime(dt['datadate']).dt.year
        dt = dt.drop(columns=['ni', 'ebitda', 'at', 'sale', 'datadate'])

        # Save to disk
        print('Downloaded Fresh Accounting Data and Saving to disk!')
        dt.to_csv(f'./data/ACC/acc_comp_{region_analysis}_{end_year}.csv', index=False)
        
    else:
        print("Read CSV")
        dt = pd.read_csv(f'./data/ACC/acc_comp_{region_analysis}_{end_year}.csv')

    #Remove the ".0" In GVKEY
    dt['gvkey'] = dt['gvkey'].astype(str).str.replace(r'\.0$', '', regex=True)
    import numpy as np
    dt["year"] = dt["year"].astype(np.int64)

    #convert gvkey removing any ".0" and adding 00 to the from ensuring 6 numbers
    global_universe['gvkey'] = global_universe['gvkey'].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(6)

    # Merge data with global universe
    global_universe = pd.merge(
        global_universe, 
        dt, 
        left_on=['gvkey', 'last_year'], 
        right_on=['gvkey', 'year'], 
        how='left'
    )

    return global_universe




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







