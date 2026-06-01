import pandas as pd
import wrds

start_year = 2009
end_year = 2025
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
        AND EXTRACT(MONTH FROM g_secd.datadate) = 3
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
