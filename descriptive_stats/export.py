import os, pickle, numpy as np, pandas as pd
SC = "/private/tmp/claude-502/-Users-cbruce1-Documents-GitHub-modular-fund-analysis/c5a94f00-1987-4b15-9182-120ccdd97304/scratchpad"
OUT = "/Users/cbruce1/Documents/GitHub/modular_fund_analysis/descriptive_stats/outputs"
R = pickle.load(open(f"{SC}/results.pkl", "rb"))
YEARS = list(range(2016, 2025))
LAD = {"United_States": [1e7,5e7,1e8,2.5e8,5e8,1e9,2e9,5e9,1e10,5e10,1e11],
       "Europe":        [1e7,5e7,1e8,2.5e8,5e8,1e9,2e9,5e9,1e10,5e10,1e11],
       "Japan":         [1e9,5e9,1e10,2.5e10,5e10,1e11,2e11,5e11,1e12,5e12,1e13]}
LBL = {"compustat":"Compustat only","lc_gvkey":"Compustat n LC (gvkey)",
       "lc_firmyear":"Compustat x LC (gvkey,fiscal-year)"}
Q=[0.01,0.05,0.10,0.25,0.50,0.75,0.90,0.95,0.99]

dist, above, floors = [], [], []
for region in R:
    for key, lbl in LBL.items():
        p = R[region][key]["panel"]
        for y in YEARS:
            sub = p[p.year==y]
            if sub.empty: continue
            v = sub["last_mktcap"]
            r = dict(region=region, sample=lbl, year=y, n_listing_months=len(sub),
                     n_firms=sub.gvkey.nunique(), mean=v.mean(), total=v.sum())
            r.update({f"p{int(q*100)}": v.quantile(q) for q in Q})
            dist.append(r)
            snap = sub[sub.month==sub.month.max()]
            firm = snap.groupby("gvkey")["last_mktcap"].max()
            ar = dict(region=region, sample=lbl, year=y, snapshot_month=int(sub.month.max()),
                      n_firms_in_snapshot=len(firm))
            for x in LAD[region]:
                ar[f"n_above_{x:.0f}"] = int((firm > x).sum())
            above.append(ar)
        a = R[region][key].get("audit")
        if a is None: continue
        a = a[a.year.isin(YEARS)].copy()
        a.insert(0,"sample",lbl); a.insert(0,"region",region)
        floors.append(a)

pd.DataFrame(dist).to_csv(f"{OUT}/mcap_distribution_by_year.csv", index=False)
pd.DataFrame(above).to_csv(f"{OUT}/mcap_firms_above_threshold.csv", index=False)
fl = pd.concat(floors, ignore_index=True)
fl.to_csv(f"{OUT}/mcap_95pct_screen_by_month.csv", index=False)

# headline: the actual filter value, per region-year, on the panel the pipeline screens
h = (fl[fl["sample"]=="Compustat only"].groupby(["region","year"])
     .agg(months=("month","size"), n_listings_pre=("n_pre","mean"),
          n_listings_kept=("n_kept","mean"), pct_listings_dropped=("pct_listings_dropped","mean"),
          cum_threshold_mean=("cum_threshold","mean"),
          size_floor_mean=("size_floor","mean"), size_floor_min=("size_floor","min"),
          size_floor_max=("size_floor","max"), size_floor_dec=("size_floor","last"))
     .reset_index())
h.to_csv(f"{OUT}/mcap_95pct_screen_headline.csv", index=False)
pd.set_option("display.width",250); pd.set_option("display.max_columns",30)
pd.set_option("display.float_format", lambda x: f"{x:,.2f}")
hh = h.copy()
for c in ["size_floor_mean","size_floor_min","size_floor_max","size_floor_dec","cum_threshold_mean"]:
    hh[c] = hh[c]/1e9
print("THE FILTER VALUE — smallest market cap kept by the 95% cumulative screen")
print("(size_floor in BILLIONS; USD for US/Europe, JPY for Japan)\n")
print(hh.to_string(index=False))
print("\nwrote CSVs to", OUT)
