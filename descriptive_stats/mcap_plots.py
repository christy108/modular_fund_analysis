import os, pickle, numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

SC = "/private/tmp/claude-502/-Users-cbruce1-Documents-GitHub-modular-fund-analysis/c5a94f00-1987-4b15-9182-120ccdd97304/scratchpad"
OUT = "/Users/cbruce1/Documents/GitHub/modular_fund_analysis/descriptive_stats/outputs"
os.makedirs(OUT, exist_ok=True)
R = pickle.load(open(f"{SC}/results.pkl", "rb"))
YEARS = list(range(2016, 2025))
CCY = {"United_States": "USD", "Europe": "USD (FX-converted)", "Japan": "JPY (not converted)"}
SAMP = [("compustat", "Compustat only", "#3b6ea5"),
        ("lc_gvkey", "Compustat ∩ LC (gvkey)", "#c0722a"),
        ("lc_firmyear", "Compustat ⋈ LC (gvkey, fiscal yr)", "#4c8b5a")]

def money(x, ccy):
    sym = "¥" if "JPY" in ccy else "$"
    for d, s in [(1e12, "T"), (1e9, "bn"), (1e6, "m"), (1e3, "k")]:
        if abs(x) >= d:
            return f"{sym}{x/d:,.3g}{s}"
    return f"{sym}{x:,.0f}"

for region in ["United_States", "Europe", "Japan"]:
    ccy = CCY[region]
    fig = plt.figure(figsize=(15, 11))
    gs = fig.add_gridspec(3, 2, height_ratios=[1.25, 1.25, 1.0], hspace=0.42, wspace=0.22)

    # ---- (1) box plots of log10 cap by year, one panel per sample ------------- #
    for i, (key, lbl, col) in enumerate(SAMP):
        ax = fig.add_subplot(gs[i // 2, i % 2])
        p = R[region][key]["panel"]
        data, labels = [], []
        for y in YEARS:
            v = p.loc[p.year == y, "last_mktcap"]
            v = v[v > 0]
            data.append(np.log10(v.values) if len(v) else np.array([np.nan]))
            labels.append(str(y)[2:])
        bp = ax.boxplot(data, labels=labels, showfliers=False, patch_artist=True,
                        medianprops=dict(color="black", lw=1.4), widths=0.62)
        for b in bp["boxes"]:
            b.set_facecolor(col); b.set_alpha(0.55); b.set_edgecolor(col)
        # the 95% screen floor for this sample
        a = R[region][key].get("audit")
        if a is not None:
            fl = (a[a.year.isin(YEARS)].groupby("year")["size_floor"].mean()
                  .reindex(YEARS))
            ax.plot(range(1, len(YEARS) + 1), np.log10(fl.values), "o--", color="crimson",
                    lw=1.6, ms=4, label="95%-screen floor (mean of months)")
            ax.legend(fontsize=8, loc="upper left")
        ax.set_title(f"{lbl}\nmarket cap distribution by year", fontsize=10)
        ax.set_ylabel(f"market cap, log10 {ccy}", fontsize=9)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: money(10 ** v, ccy)))
        ax.grid(axis="y", alpha=0.25)
        ax.tick_params(labelsize=8)

    # ---- (2) the screen: floor level + share dropped -------------------------- #
    ax = fig.add_subplot(gs[1, 1])
    for key, lbl, col in SAMP:
        a = R[region][key].get("audit")
        if a is None:
            continue
        a = a[a.year.isin(YEARS)]
        t = a["year"] + (a["month"] - 0.5) / 12
        ax.plot(t, a["size_floor"], color=col, lw=1.4, label=lbl)
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: money(v, ccy)))
    ax.set_title("95% cumulative-cap screen: the actual size floor, monthly", fontsize=10)
    ax.set_ylabel(f"smallest cap kept ({ccy})", fontsize=9)
    ax.grid(alpha=0.25); ax.legend(fontsize=8); ax.tick_params(labelsize=8)

    ax = fig.add_subplot(gs[2, 0])
    for key, lbl, col in SAMP:
        a = R[region][key].get("audit")
        if a is None:
            continue
        a = a[a.year.isin(YEARS)]
        t = a["year"] + (a["month"] - 0.5) / 12
        ax.plot(t, a["pct_listings_dropped"], color=col, lw=1.4, label=lbl)
    ax.set_title("share of listings the 95% value screen removes", fontsize=10)
    ax.set_ylabel("% listing-months dropped", fontsize=9)
    ax.grid(alpha=0.25); ax.legend(fontsize=8); ax.tick_params(labelsize=8)

    # ---- (3) survivor function: firms above X, first vs last year ------------- #
    ax = fig.add_subplot(gs[2, 1])
    for key, lbl, col in SAMP:
        p = R[region][key]["panel"]
        for y, ls in [(2016, ":"), (2024, "-")]:
            snap = p[(p.year == y) & (p.month == 12)]
            if snap.empty:
                continue
            firm = snap.groupby("gvkey")["last_mktcap"].max().sort_values()
            v = firm[firm > 0].values
            ax.plot(v, np.arange(len(v), 0, -1), ls, color=col, lw=1.5,
                    label=f"{lbl} — Dec {y}")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: money(v, ccy)))
    ax.set_title("firms with market cap above X (December snapshot)", fontsize=10)
    ax.set_xlabel(f"X ({ccy})", fontsize=9); ax.set_ylabel("# firms above X", fontsize=9)
    ax.grid(alpha=0.25, which="both"); ax.legend(fontsize=7); ax.tick_params(labelsize=8)

    fig.suptitle(f"{region.replace('_',' ')} — market cap across 2016-2024, "
                 f"Compustat vs Compustat×LC, and the 95% screen  [{ccy}]",
                 fontsize=13, y=0.985)
    f = f"{OUT}/mcap_distribution_{region}.png"
    fig.savefig(f, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print("wrote", f)
