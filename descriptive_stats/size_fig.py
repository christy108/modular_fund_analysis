import os, pickle, numpy as np, pandas as pd, sys
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
SC="/private/tmp/claude-502/-Users-cbruce1-Documents-GitHub-modular-fund-analysis/c5a94f00-1987-4b15-9182-120ccdd97304/scratchpad"
os.chdir("/Users/cbruce1/Documents/GitHub/modular_fund_analysis"); sys.path.insert(0,os.getcwd())
OUT="descriptive_stats/outputs"
from functions.data_functions.get_data import get_processed_fx_rates
FXJ=get_processed_fx_rates(2024).query("curcdd=='JPY'").set_index("date")["rate"]

P={}
for r in ["United_States","Europe","Japan"]:
    p=pd.read_parquet(f"{SC}/panel_{r}.parquet")
    p["mcap"]=(p["last_mktcap"]/FXJ.reindex(pd.to_datetime(p["last_date"])).ffill().values
               if r=="Japan" else p["last_mktcap"])
    P[r]=p
COL={"United_States":"#2f6ea8","Europe":"#c9691e","Japan":"#4c8b5a"}
SHORT={"United_States":"US","Europe":"Europe","Japan":"Japan"}
EDGES=[0,50e6,100e6,250e6,500e6,1e9,2e9,5e9,10e9,50e9,np.inf]
NAMES=["<$50m","$50–\n100m","$100–\n250m","$250–\n500m","$500m–\n$1bn","$1–\n2bn","$2–\n5bn","$5–\n10bn","$10–\n50bn",">$50bn"]

def snap(r,y=2024):
    s=P[r].query("year==@y and month==12")
    return s.groupby("gvkey")["mcap"].max()

def money(x,_=None):
    for d,s in [(1e12,"T"),(1e9,"bn"),(1e6,"m")]:
        if abs(x)>=d: return f"${x/d:,.3g}{s}"
    return f"${x:,.0f}"

fig=plt.figure(figsize=(16,10.5))
gs=fig.add_gridspec(2,2,hspace=0.35,wspace=0.22)

# A: firm counts by bucket
ax=fig.add_subplot(gs[0,0]); w=0.27
for i,r in enumerate(["United_States","Europe","Japan"]):
    f=snap(r); c=pd.cut(f,EDGES,labels=NAMES,right=False).value_counts().reindex(NAMES)
    ax.bar(np.arange(len(NAMES))+(i-1)*w, c.values, w, color=COL[r],
           label=f"{SHORT[r]}  (n={len(f):,})", alpha=0.9)
    for j,v in enumerate(c.values):
        ax.text(j+(i-1)*w, v+25, f"{v:,}", ha="center", fontsize=6.5, rotation=90, color=COL[r])
ax.set_xticks(range(len(NAMES))); ax.set_xticklabels(NAMES, fontsize=7.5)
ax.set_ylabel("number of firms"); ax.legend(fontsize=9)
ax.set_title("A.  Europe has ~8× as many sub-$100m firms as the US — and a third as many above $50bn\n"
             "December 2024, Compustat tradable universe (pre-screen)", fontsize=10.5, loc="left")
ax.grid(axis="y", alpha=0.25); ax.set_axisbelow(True)

# B: share of aggregate cap by bucket
ax=fig.add_subplot(gs[0,1])
for i,r in enumerate(["United_States","Europe","Japan"]):
    f=snap(r); b=pd.cut(f,EDGES,labels=NAMES,right=False)
    cap=100*f.groupby(b,observed=False).sum().reindex(NAMES)/f.sum()
    ax.bar(np.arange(len(NAMES))+(i-1)*w, cap.values, w, color=COL[r],
           label=f"{SHORT[r]}  (${f.sum()/1e12:.1f}tn)", alpha=0.9)
ax.set_xticks(range(len(NAMES))); ax.set_xticklabels(NAMES, fontsize=7.5)
ax.set_ylabel("% of the region's aggregate market cap"); ax.legend(fontsize=9)
ax.set_title("B.  …but those small firms hold almost no value, in either region\n"
             "so a screen defined on VALUE cannot see them", fontsize=10.5, loc="left")
ax.grid(axis="y", alpha=0.25); ax.set_axisbelow(True)

# C: concentration curve
ax=fig.add_subplot(gs[1,0])
for r in ["United_States","Europe","Japan"]:
    f=snap(r).sort_values(); cum=100*f.cumsum()/f.sum()
    x=100*np.arange(1,len(f)+1)/len(f)
    ax.plot(x,cum,color=COL[r],lw=2,label=SHORT[r])
    k=int((cum<5).sum())
    ax.plot([x[k-1]],[5],"o",color=COL[r],ms=8,mec="k",mew=0.8)
    _off={"United_States":(-14,52),"Europe":(16,20),"Japan":(-14,20)}[r]
    ax.annotate(f"{SHORT[r]}: {x[k-1]:.1f}% of firms dropped\nfloor = {money(f.iloc[k])}",
                (x[k-1],5), textcoords="offset points", xytext=_off,
                fontsize=8.5, color=COL[r], ha="left" if _off[0]>0 else "right",
                arrowprops=dict(arrowstyle="->",color=COL[r],lw=0.9))
ax.axhline(5,color="crimson",ls="--",lw=1.3)
ax.text(1,2.2,"the 5%-of-value budget the 0.95 screen spends",color="crimson",fontsize=9)
ax.set_xlim(0,100); ax.set_ylim(0,45)
ax.set_xlabel("firms, smallest → largest (cumulative %)")
ax.set_ylabel("cumulative % of aggregate market cap")
ax.set_title("C.  Why the same 0.95 setting bites harder in Europe\n"
             "Europe's bottom 80% of firms hold 4.8% of value; the US bottom 80% hold 8.8%",
             fontsize=10.5, loc="left")
ax.grid(alpha=0.25); ax.legend(fontsize=9, loc="upper left")

# D: floor vs coverage — the calibration
ax=fig.add_subplot(gs[1,1])
sw=pd.read_csv(f"{OUT}/screen_coverage_sweep.csv")
for r in ["United_States","Europe","Japan"]:
    s=sw[(sw.region==r)&(sw.year==2024)].sort_values("coverage")
    ax.plot(s.coverage,s.floor,"o-",color=COL[r],lw=1.8,ms=4,label=SHORT[r])
us=sw.query("region=='United_States' and year==2024 and coverage==0.95").floor.iloc[0]
ax.axhline(us,color="crimson",ls="--",lw=1.3)
ax.annotate(f"US floor at 0.95 = {money(us)}", (0.60,us*1.30), color="crimson", fontsize=9)
for r,cov in [("Europe",0.850),("Japan",0.7347)]:
    ax.plot([cov],[us],"*",color=COL[r],ms=17,mec="k",mew=0.7)
    ax.annotate(f"{SHORT[r]} needs\ncoverage ≈ {cov:.3g}",(cov,us),
                textcoords="offset points",xytext=(-4,-44),fontsize=9,color=COL[r])
ax.plot([0.95],[us],"*",color=COL["United_States"],ms=17,mec="k",mew=0.7)
ax.set_yscale("log"); ax.yaxis.set_major_formatter(FuncFormatter(money))
ax.set_xlabel("mktcap_covered_if_filter_by_cum_market_cap")
ax.set_ylabel("resulting size floor (2024 mean of months)")
ax.set_title("D.  Calibration: to reach the US size floor, Europe needs 0.85 and Japan 0.735\n"
             "the coverage parameter is not comparable across regions", fontsize=10.5, loc="left")
ax.grid(alpha=0.25, which="both"); ax.legend(fontsize=9)

fig.suptitle("Firm-size structure, US vs Europe vs Japan — and why one `mktcap_covered` value "
             "does not mean the same thing in each", fontsize=13.5, y=0.975)
f=f"{OUT}/size_structure_us_vs_eu.png"
fig.savefig(f,dpi=135,bbox_inches="tight"); print("wrote",f)
