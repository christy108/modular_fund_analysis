"""US vs EU firm-size structure, and what screen makes the two comparable."""
import os, pickle, numpy as np, pandas as pd
SC="/private/tmp/claude-502/-Users-cbruce1-Documents-GitHub-modular-fund-analysis/c5a94f00-1987-4b15-9182-120ccdd97304/scratchpad"
os.chdir("/Users/cbruce1/Documents/GitHub/modular_fund_analysis")
OUT="descriptive_stats/outputs"
pd.set_option("display.width",250); pd.set_option("display.max_columns",40)

FX_JPY = None   # filled below from the FRB file, for a USD-comparable Japan view
import sys; sys.path.insert(0,os.getcwd())
from functions.data_functions.get_data import get_processed_fx_rates
fx = get_processed_fx_rates(2024)
FX_JPY = fx[(fx.curcdd=="JPY")].set_index("date")["rate"]

panels = {}
for r in ["United_States","Europe","Japan"]:
    p = pd.read_parquet(f"{SC}/panel_{r}.parquet")
    p["gvkey"]=p["gvkey"].astype(str)
    if r=="Japan":   # put Japan on a USD footing for the cross-region comparison only
        rate = FX_JPY.reindex(pd.to_datetime(p["last_date"])).ffill().values
        p["mcap_usd"] = p["last_mktcap"]/rate
    else:
        p["mcap_usd"] = p["last_mktcap"]
    panels[r]=p

lck = pickle.load(open(f"{SC}/lc_keys.pkl","rb"))

# ---------------- 1. size-bucket census, December snapshots -------------------- #
EDGES = [0, 50e6, 100e6, 250e6, 500e6, 1e9, 2e9, 5e9, 10e9, 50e6*1e3, np.inf]
NAMES = ["<$50m","$50-100m","$100-250m","$250-500m","$500m-1bn","$1-2bn","$2-5bn",
         "$5-10bn","$10-50bn",">$50bn"]

def snapshot(region, year, sample="compustat"):
    p = panels[region]
    if sample=="lc_gvkey":
        p = p[p.gvkey.isin(lck[region]["gvkeys"])]
    s = p[(p.year==year)&(p.month==12)]
    return s.groupby("gvkey")["mcap_usd"].max()

rows=[]
for year in [2016, 2024]:
    for sample in ["compustat","lc_gvkey"]:
        for region in ["United_States","Europe","Japan"]:
            f = snapshot(region, year, sample)
            b = pd.cut(f, EDGES, labels=NAMES, right=False)
            cnt = b.value_counts().reindex(NAMES)
            cap = f.groupby(b, observed=False).sum().reindex(NAMES)
            rows.append(dict(year=year, sample=sample, region=region, n_firms=len(f),
                             total_cap_usd_tn=f.sum()/1e12,
                             **{f"n {k}": int(v) for k,v in cnt.items()},
                             **{f"cap% {k}": 100*v/f.sum() for k,v in cap.items()}))
census = pd.DataFrame(rows)
census.to_csv(f"{OUT}/size_census_us_vs_eu.csv", index=False)

print("="*110)
print("FIRM COUNTS BY SIZE BUCKET — December snapshot, Compustat universe (Japan shown FX-converted for comparability)")
print("="*110)
c = census[census["sample"]=="compustat"]
print(c[["year","region","n_firms","total_cap_usd_tn"]+[f"n {k}" for k in NAMES]].to_string(index=False))
print()
print("SHARE OF AGGREGATE MARKET CAP HELD BY EACH BUCKET (%)")
print(c[["year","region"]+[f"cap% {k}" for k in NAMES]].round(2).to_string(index=False))
print()
print("SAME, restricted to firms in the LC panel (Compustat n LC)")
c2 = census[census["sample"]=="lc_gvkey"]
print(c2[["year","region","n_firms","total_cap_usd_tn"]+[f"n {k}" for k in NAMES]].to_string(index=False))

# ---------------- 2. concentration: how little value the small tail holds ------ #
print()
print("="*110)
print("CONCENTRATION — Dec 2024, Compustat universe. 'bottom N% of firms by cap hold X% of aggregate cap'")
print("="*110)
rows=[]
for region in ["United_States","Europe","Japan"]:
    f = snapshot(region, 2024).sort_values()
    cum = f.cumsum()/f.sum()
    r = dict(region=region, n_firms=len(f))
    for q in [0.25,0.50,0.60,0.70,0.75,0.80,0.90]:
        k = int(np.floor(q*len(f)))
        r[f"bottom {int(q*100)}% of firms hold"] = round(100*cum.iloc[k-1],3)
    # the inverse: what share of firms the 5%-of-value budget buys
    r["firms below the 5%-of-value line"] = round(100*(cum<0.05).mean(),1)
    r["cap of the largest firm dropped ($m)"] = round(f[cum<0.05].max()/1e6,1)
    rows.append(r)
conc = pd.DataFrame(rows)
print(conc.to_string(index=False))
conc.to_csv(f"{OUT}/size_concentration_dec2024.csv", index=False)

# ---------------- 3. where is the EU small-cap tail? -------------------------- #
print()
print("="*110)
print("EUROPE'S SMALL-CAP TAIL BY LISTING CURRENCY — Dec 2024, Compustat universe")
print("="*110)
p = panels["Europe"]
s = p[(p.year==2024)&(p.month==12)]
s = s.loc[s.groupby("gvkey")["mcap_usd"].idxmax()]
t = (s.assign(bucket=pd.cut(s["mcap_usd"], EDGES, labels=NAMES, right=False))
       .pivot_table(index="curcdd", columns="bucket", values="gvkey",
                    aggfunc="count", observed=False).fillna(0).astype(int))
t["total"]=t.sum(axis=1)
t["% under $100m"]=(100*(t["<$50m"]+t["$50-100m"])/t["total"]).round(1)
print(t.sort_values("total",ascending=False).to_string())
t.to_csv(f"{OUT}/size_eu_tail_by_currency.csv")
