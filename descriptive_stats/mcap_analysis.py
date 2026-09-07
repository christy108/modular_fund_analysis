"""Market-cap distribution / 95%-screen threshold analysis, per region and sample."""
import os, sys, pickle
import numpy as np
import pandas as pd

SC = "/private/tmp/claude-502/-Users-cbruce1-Documents-GitHub-modular-fund-analysis/c5a94f00-1987-4b15-9182-120ccdd97304/scratchpad"
os.chdir("/Users/cbruce1/Documents/GitHub/modular_fund_analysis")
sys.path.insert(0, os.getcwd())

MCAP_COVERED = 0.95
YEARS = list(range(2016, 2025))          # cfg start_year..end_year
SPLIT = {"United_States": 6, "Europe": 6, "Japan": 3}   # last_year split month
UNIT = {"United_States": "USD", "Europe": "USD (converted)", "Japan": "JPY (NOT converted)"}

LADDER_USD = [1e7, 5e7, 1e8, 2.5e8, 5e8, 1e9, 2e9, 5e9, 1e10, 5e10, 1e11]
LADDER_JPY = [1e9, 5e9, 1e10, 2.5e10, 5e10, 1e11, 2e11, 5e11, 1e12, 5e12, 1e13]

lck = pickle.load(open(f"{SC}/lc_keys.pkl", "rb"))


def screen(panel):
    """Replay percent_total_mcap per (year, month), pooled. Returns per-month audit."""
    d = panel.sort_values(["year", "month", "last_mktcap"], kind="mergesort").copy()
    g = d.groupby(["year", "month"], sort=False)["last_mktcap"]
    d["cum"] = g.cumsum()
    d["tot"] = g.transform("sum")
    d["keep"] = d["cum"] > (1 - MCAP_COVERED) * d["tot"]
    rows = []
    for (y, m), sub in d.groupby(["year", "month"], sort=True):
        kept = sub[sub["keep"]]
        drop = sub[~sub["keep"]]
        rows.append(dict(
            year=y, month=m, n_pre=len(sub), n_kept=len(kept),
            pct_listings_dropped=100 * len(drop) / len(sub),
            total_mktcap=sub["last_mktcap"].sum(),
            cum_threshold=(1 - MCAP_COVERED) * sub["last_mktcap"].sum(),
            size_floor=kept["last_mktcap"].min() if len(kept) else np.nan,
            largest_dropped=drop["last_mktcap"].max() if len(drop) else np.nan,
        ))
    return pd.DataFrame(rows), d


def dist_table(panel, unit_div, label):
    """Per-year distribution of last_mktcap over listing-months."""
    q = [0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
    rows = []
    for y, sub in panel.groupby("year"):
        v = sub["last_mktcap"] / unit_div
        r = dict(year=y, n_listing_months=len(sub),
                 n_firms=sub["gvkey"].nunique(),
                 mean=v.mean(), total=v.sum())
        for qq in q:
            r[f"p{int(qq*100)}"] = v.quantile(qq)
        rows.append(r)
    out = pd.DataFrame(rows)
    out.insert(0, "sample", label)
    return out


def above_table(panel, ladder, unit_div, label):
    """Per year: distinct firms whose LAST-DECEMBER (or last month present) cap > X.
    Measured on the December listing-month so 'number of firms' is a point-in-time count."""
    rows = []
    for y, sub in panel.groupby("year"):
        last_m = sub["month"].max()
        snap = sub[sub["month"] == last_m]
        # one cap per firm (largest listing if a firm has several iids)
        firm = snap.groupby("gvkey")["last_mktcap"].max()
        r = dict(sample=label, year=y, snapshot_month=last_m, n_firms=len(firm))
        for x in ladder:
            r[f">{x:.0e}"] = int((firm > x).sum())
        rows.append(r)
    return pd.DataFrame(rows)


results = {}
for region in ["United_States", "Europe", "Japan"]:
    panel = pd.read_parquet(f"{SC}/panel_{region}.parquet")
    panel["gvkey"] = panel["gvkey"].astype(str)
    keys = lck[region]["gvkeys"]
    pairs = lck[region]["pairs"].copy()
    pairs["gvkey"] = pairs["gvkey"].astype(str)

    # last_year, for the firm-year LC match
    sp = SPLIT[region]
    panel["last_year"] = np.where(panel["month"] <= sp, panel["year"] - 2, panel["year"] - 1)

    samples = {
        "compustat": panel,
        "lc_gvkey": panel[panel["gvkey"].isin(keys)],
        "lc_firmyear": panel.merge(pairs.rename(columns={"rfyear": "last_year"}),
                                   on=["gvkey", "last_year"], how="inner"),
    }
    results[region] = {}
    for name, p in samples.items():
        results[region][name] = dict(panel=p)
    # the screen only ever runs on the full compustat panel; also replay on lc samples
    for name, p in samples.items():
        if len(p) == 0:
            continue
        audit, _ = screen(p)
        results[region][name]["audit"] = audit

pickle.dump({r: {n: {"audit": v.get("audit"),
                     "panel": v["panel"][["year","month","gvkey","iid","last_mktcap"]]}
                 for n, v in d.items()} for r, d in results.items()},
            open(f"{SC}/results.pkl", "wb"))

# ---------------- report ---------------- #
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 60)
pd.set_option("display.float_format", lambda x: f"{x:,.3f}")

lines = []
def P(*a):
    s = " ".join(str(x) for x in a)
    print(s); lines.append(s)

for region in ["United_States", "Europe", "Japan"]:
    unit_div = 1e9
    unit = "bn " + UNIT[region]
    ladder = LADDER_JPY if region == "Japan" else LADDER_USD
    P("\n" + "#" * 100)
    P(f"# {region}   —   market cap in {unit}")
    P("#" * 100)
    for name, lbl in [("compustat", "Compustat only"),
                      ("lc_gvkey", "Compustat ∩ LC (gvkey)"),
                      ("lc_firmyear", "Compustat ⋈ LC (gvkey, fiscal year)")]:
        d = results[region][name]
        p = d["panel"]
        P(f"\n--- {lbl}  [all years in extract: {p['year'].min()}-{p['year'].max()}] ---")
        t = dist_table(p, unit_div, lbl)
        P(t[t.year.isin(YEARS)].to_string(index=False))
        P(f"\n  firms above X ({'JPY' if region=='Japan' else 'USD'}), December snapshot:")
        a = above_table(p, ladder, unit_div, lbl)
        P(a[a.year.isin(YEARS)].to_string(index=False))

    P(f"\n=== 95% screen threshold (size_floor = smallest cap KEPT), {region} ===")
    for name, lbl in [("compustat", "screen as the pipeline runs it (Compustat panel)"),
                      ("lc_firmyear", "same screen replayed on the LC-matched sample")]:
        a = results[region][name].get("audit")
        if a is None:
            continue
        s = (a[a.year.isin(YEARS)].groupby("year")
             .agg(months=("month", "size"),
                  n_pre=("n_pre", "mean"), n_kept=("n_kept", "mean"),
                  pct_listings_dropped=("pct_listings_dropped", "mean"),
                  floor_mean=("size_floor", "mean"),
                  floor_min=("size_floor", "min"),
                  floor_max=("size_floor", "max"),
                  floor_dec=("size_floor", "last"))
             .reset_index())
        for c in ["floor_mean", "floor_min", "floor_max", "floor_dec"]:
            s[c] = s[c] / unit_div
        P(f"\n  [{lbl}]")
        P(s.to_string(index=False))

open(f"{SC}/report.txt", "w").write("\n".join(lines))
print("\nwrote report.txt")
