"""What EU screen setting reproduces the US screen's size floor?"""
import os, pickle, numpy as np, pandas as pd, sys
SC="/private/tmp/claude-502/-Users-cbruce1-Documents-GitHub-modular-fund-analysis/c5a94f00-1987-4b15-9182-120ccdd97304/scratchpad"
os.chdir("/Users/cbruce1/Documents/GitHub/modular_fund_analysis"); sys.path.insert(0,os.getcwd())
OUT="descriptive_stats/outputs"
pd.set_option("display.width",250); pd.set_option("display.max_columns",40)
YEARS=list(range(2016,2025))

from functions.data_functions.get_data import get_processed_fx_rates
fx=get_processed_fx_rates(2024); FXJ=fx[fx.curcdd=="JPY"].set_index("date")["rate"]

P={}
for r in ["United_States","Europe","Japan"]:
    p=pd.read_parquet(f"{SC}/panel_{r}.parquet")
    if r=="Japan":
        p["mcap"]=p["last_mktcap"]/FXJ.reindex(pd.to_datetime(p["last_date"])).ffill().values
    else:
        p["mcap"]=p["last_mktcap"]
    P[r]=p[p.year.isin(YEARS)][["year","month","gvkey","mcap"]].dropna()

def screen_stats(p, cov):
    """percent_total_mcap at coverage `cov`: per-month floor + kept count."""
    d=p.sort_values(["year","month","mcap"],kind="mergesort")
    g=d.groupby(["year","month"],sort=False)["mcap"]
    keep=g.cumsum() > (1-cov)*g.transform("sum")
    d=d.assign(keep=keep)
    per=(d.groupby(["year","month"])
           .apply(lambda s: pd.Series({
               "floor": s.loc[s.keep,"mcap"].min(),
               "n_kept": int(s.keep.sum()),
               "n_pre": len(s)}), include_groups=False)
           .reset_index())
    return per.groupby("year").agg(floor=("floor","mean"), n_kept=("n_kept","mean"),
                                   n_pre=("n_pre","mean")).reset_index()

COV=[0.99,0.975,0.95,0.925,0.90,0.875,0.85,0.80,0.75,0.70,0.65,0.60]
sweep=[]
for r in P:
    for cov in COV:
        s=screen_stats(P[r],cov); s.insert(0,"coverage",cov); s.insert(0,"region",r)
        sweep.append(s)
sweep=pd.concat(sweep,ignore_index=True)
sweep["pct_dropped"]=100*(1-sweep.n_kept/sweep.n_pre)
sweep.to_csv(f"{OUT}/screen_coverage_sweep.csv",index=False)

print("="*118)
print("COVERAGE SWEEP — mean monthly size floor ($bn) and mean kept listings, by region-year")
print("="*118)
for metric,scale,lab in [("floor",1e9,"SIZE FLOOR ($bn)"),("n_kept",1,"LISTINGS KEPT")]:
    print(f"\n{lab}")
    t=sweep.pivot_table(index=["region","coverage"],columns="year",values=metric)
    print((t/scale).round(2 if metric=="floor" else 0).to_string())

# ---- the US target, and the EU/JP coverage that reproduces it ----------------- #
us=sweep[(sweep.region=="United_States")&(sweep.coverage==0.95)].set_index("year")["floor"]
print("\n"+"="*118)
print("CALIBRATION — coverage that gives EU / Japan the SAME size floor the US gets at 0.95")
print("="*118)
rows=[]
for r in ["Europe","Japan"]:
    p=P[r]
    for y in YEARS:
        target=us[y]
        # solve for coverage: floor(cov) is monotone decreasing in cov, so bisect
        lo,hi=0.05,0.999
        for _ in range(40):
            mid=(lo+hi)/2
            f=screen_stats(p[p.year==y],mid)["floor"].iloc[0]
            if f>target: lo=mid
            else: hi=mid
        cov=(lo+hi)/2
        s=screen_stats(p[p.year==y],cov).iloc[0]
        u=sweep[(sweep.region=="United_States")&(sweep.coverage==0.95)&(sweep.year==y)].iloc[0]
        rows.append(dict(region=r,year=y,us_floor_bn=target/1e9,
                         coverage_needed=round(cov,4),
                         resulting_floor_bn=s["floor"]/1e9,
                         listings_kept=round(s["n_kept"],0),
                         listings_pre=round(s["n_pre"],0),
                         pct_dropped=round(100*(1-s["n_kept"]/s["n_pre"]),1),
                         us_listings_kept=round(u["n_kept"],0),
                         us_pct_dropped=round(100*(1-u["n_kept"]/u["n_pre"]),1)))
cal=pd.DataFrame(rows)
print(cal.to_string(index=False))
cal.to_csv(f"{OUT}/screen_calibration_to_us_floor.csv",index=False)

# ---- absolute-floor alternative --------------------------------------------- #
print("\n"+"="*118)
print("ABSOLUTE-FLOOR ALTERNATIVE — one USD floor applied to every region")
print("(kept listings per month, mean over the year; % of aggregate cap retained in brackets)")
print("="*118)
rows=[]
for floor in [1e9,2e9,3e9,5e9]:
    for r in P:
        p=P[r]
        for y in [2016,2020,2024]:
            s=p[p.year==y]
            per=s.groupby(["year","month"]).apply(
                lambda d: pd.Series({"n_kept":(d.mcap>floor).sum(),"n_pre":len(d),
                    "cap_kept":100*d.loc[d.mcap>floor,"mcap"].sum()/d.mcap.sum()}),
                include_groups=False)
            rows.append(dict(floor_bn=floor/1e9,region=r,year=y,
                             n_kept=round(per.n_kept.mean()),
                             pct_dropped=round(100*(1-per.n_kept.mean()/per.n_pre.mean()),1),
                             pct_cap_retained=round(per.cap_kept.mean(),2)))
ab=pd.DataFrame(rows)
print(ab.pivot_table(index=["floor_bn","region"],columns="year",
                     values=["n_kept","pct_cap_retained"]).round(1).to_string())
ab.to_csv(f"{OUT}/screen_absolute_floor_options.csv",index=False)
