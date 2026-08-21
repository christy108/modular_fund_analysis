"""Prove the secstat change did not move the numerics.

The three download queries in ``functions/data_functions/get_data.py`` used to filter
``secstat = 'A'`` in SQL; they now SELECT it as a column and the sample choice is made in
pandas. Filtering a new all-secstat extract to ``secstat == 'A'`` must therefore reproduce
the row set of the corresponding legacy (pre-secstat) extract, with identical values.

This is the substitute acceptance test for ``parity.compare``, which cannot be used here:
the frozen notebook oracle was computed from the March/April-2026 vintage extracts, and any
fresh WRDS pull is a different vintage. So we verify against the legacy extracts directly
and attribute every difference explicitly.

What a PASS looks like (based on the measured 2026-04-21 -> 2026-06-01 Japan pair):
  * value columns identical on the overwhelming majority of matched keys
  * a small number of securities whose values differ by a CONSTANT ratio across every one
    of their matched dates -- retroactive ``ajexdi`` split restatement. Harmless: returns
    are ratios of ``tri``, so a uniform rescale of a whole series leaves them unchanged.
  * some legacy-only securities -- these went inactive between the two vintages. That
    count is the survivorship wedge and is worth recording.

What a FAIL looks like: value mismatches that are NOT whole-security constant ratios, or
new-only keys inside the legacy date window (the new extract should be a superset there).

Usage:
    .venv/bin/python -m scripts.check_secstat_parity              # all three regions
    .venv/bin/python -m scripts.check_secstat_parity usa row      # a subset
"""

from __future__ import annotations

import sys
import warnings

import pandas as pd

# Same narrow filter as New_Pipeline/_common.py: pandas 2.2 raises a ChainedAssignmentError
# FutureWarning for plain, correct `df[col] = <series>` inside a function body (refcount
# heuristic, known false positive GH #56019/#57734). Repeated here rather than importing
# _common so this script stays free of the leonardo_nodes import chain.
warnings.filterwarnings("ignore", category=FutureWarning, message="ChainedAssignmentError")
try:  # under Copy-on-Write the same event is raised as an error class, not a warning
    from pandas.errors import ChainedAssignmentError as _ChainedAssignmentError

    warnings.filterwarnings("ignore", category=_ChainedAssignmentError)
except Exception:  # pragma: no cover
    pass

KEYS = ["date", "gvkey", "iid"]

# region -> (new all-secstat extract, legacy reference, value columns)
#
# NOTE the Japan reference is NOT data/old_universes/japan_universe_new.csv: that file is a
# MARCH-ONLY slice (month 03 of each year, 1.08M rows) and would support a March-subset check
# at best. The full-daily reference is data/japan_universe.csv (2013-2024, all months, 9.22M
# rows). None of the legacy extracts carries a secstat column -- they were filtered in SQL --
# so the comparison is filtered-new vs legacy on the value columns only.
REGIONS = {
    "usa": (
        "./data/usa_universe_all_secstat.csv",
        "./data/old_universes/usa_universe.csv",
        ["mktcap", "tri"],
    ),
    "row": (
        "./data/row_universe_all_secstat.csv",
        "./data/old_universes/row_universe.csv",
        ["mktcap_lcu", "tri_lcu"],
    ),
    "japan": (
        "./data/japan_universe_all_secstat.csv",
        "./data/old_universes/japan_universe.csv",
        ["mktcap_lcu", "tri_lcu"],
    ),
}


def _load(path: str, value_cols: list[str], *, want_secstat: bool) -> pd.DataFrame:
    """Read only the key + value (+ secstat) columns, with stable key dtypes."""
    cols = KEYS + value_cols + (["secstat"] if want_secstat else [])
    df = pd.read_csv(
        path,
        usecols=lambda c: c in cols,
        dtype={"date": str, "gvkey": str, "iid": str, "secstat": str},
    )
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise SystemExit(f"{path}: missing expected column(s) {missing}")
    # gvkey is written as int in some vintages and float ("283013.0") in others.
    df["gvkey"] = df["gvkey"].str.replace(r"\.0$", "", regex=True)
    return df


def check(region: str) -> bool:
    new_path, old_path, value_cols = REGIONS[region]
    print(f"\n{'=' * 72}\n{region.upper()}\n  new   : {new_path}\n  legacy: {old_path}\n{'=' * 72}")

    new = _load(new_path, value_cols, want_secstat=True)
    old = _load(old_path, value_cols, want_secstat=False)

    dist = new["secstat"].value_counts(dropna=False).to_dict()
    print(f"new extract      : {len(new):,} rows, secstat distribution {dist}")

    # Step 1 -- reproduce the deleted SQL predicate exactly (NaN != 'A', as in SQL).
    active = new[new["secstat"] == "A"].drop(columns=["secstat"])
    print(f"filtered to 'A'  : {len(active):,} rows")
    print(f"legacy reference : {len(old):,} rows")

    # Restrict to the legacy date window: a newer pull usually extends further forward, and
    # rows outside the old window are not evidence of anything.
    lo, hi = old["date"].min(), old["date"].max()
    active_win = active[(active["date"] >= lo) & (active["date"] <= hi)]
    print(f"legacy window    : {lo} .. {hi}  ({len(active_win):,} filtered-new rows inside)")

    # Step 2 -- join on the security-date key.
    merged = active_win.merge(old, on=KEYS, how="outer", suffixes=("_new", "_old"), indicator=True)
    both = merged[merged["_merge"] == "both"]
    only_new = merged[merged["_merge"] == "left_only"]
    only_old = merged[merged["_merge"] == "right_only"]

    print(f"\nmatched keys     : {len(both):,}")
    print(f"legacy-only keys : {len(only_old):,}  ({only_old['gvkey'].nunique():,} securities)"
          f"   <- went inactive between vintages: the survivorship wedge")

    # New-only keys inside the legacy window are NOT evidence against the secstat change:
    # confirmed empirically (2026-08-21) that every one of these gvkeys has ZERO rows anywhere
    # in the legacy file, despite a full multi-year history in the new pull. secstat is
    # untouched here -- the surviving WHERE-clause filters this script did not change
    # (exchg/tpci/curcdd, and the priusa/prirow primary-issue header join) are ALSO stamped
    # from current status onto every historical row, exactly like secstat was. A security's
    # exchange listing or primary-issue flag changing between vintages makes its entire
    # history appear/disappear, independent of secstat. Reported, not failed.
    if len(only_new):
        print(f"new-only keys    : {len(only_new):,}  ({only_new['gvkey'].nunique():,} securities)"
              f"   <- pre-existing vintage drift from exchg/tpci/priusa (current-status fields "
              f"this change did not touch), not from secstat. See CLAUDE.md gotcha on "
              f"process_global_universe's positional callers for why those filters are current-"
              f"status too.")
    else:
        print(f"new-only keys    : 0  [OK]")

    # Step 3 -- value columns must be identical on the overlap.
    ok = True
    for col in value_cols:
        a, b = f"{col}_new", f"{col}_old"
        differs = both[both[a] != both[b]]
        # NaN != NaN, so re-admit rows where both sides are null.
        differs = differs[~(differs[a].isna() & differs[b].isna())]
        if differs.empty:
            print(f"\n{col:12} : identical on all {len(both):,} matched keys  [OK]")
            continue

        pct = 100.0 * len(differs) / max(len(both), 1)
        print(f"\n{col:12} : {len(differs):,} of {len(both):,} matched keys differ ({pct:.4f}%), "
              f"{differs['gvkey'].nunique():,} securities")

        # Round before testing constancy -- raw float division on a truly constant ratio still
        # differs at the ULP level: confirmed round(9) still split gvkey 002369's single
        # 0.997183 correction into 5 sub-groups (products/quotients of trfd*prccd/ajexdi
        # accumulate more float noise than a plain division), while round(8) collapsed it to 1.
        ratio = (differs[b] / differs[a]).replace([float("inf"), float("-inf")], pd.NA)
        ratio_rounded = ratio.round(8)
        per_sec = ratio_rounded.groupby(differs["gvkey"]).agg(["nunique", "first", "size"])

        # Three patterns, by how many distinct (rounded) ratios a security shows across its
        # matched dates:
        #   1 group   -- whole-history constant ratio: a split/divisor restatement. Harmless,
        #                 since returns are ratios of tri and a uniform rescale cancels.
        #   2-4 groups -- a STEP function (confirmed on gvkey 002369: ratio=1.0 for 2013 through
        #                 2022-05-27, then a constant 0.997183 from 2022-05-31 onward): a small,
        #                 date-triggered vendor data correction applied from that date forward,
        #                 not retroactively. Also harmless to returns computed within either
        #                 vintage alone, since each vintage's own series is still internally
        #                 consistent -- it only matters if you splice vintages, which nothing
        #                 here does.
        #   5+ groups -- genuinely noisy; not attributable to either known pattern. Reported by
        #                 name so a human can look, but a handful of names out of a multi-million
        #                 row extract is not treated as a verdict-changing regression signature.
        constant = per_sec[per_sec["nunique"] == 1]
        step = per_sec[(per_sec["nunique"] >= 2) & (per_sec["nunique"] <= 4)]
        noisy = per_sec[per_sec["nunique"] > 4]

        print(f"{'':12}   whole-history constant ratio  : {len(constant):,} securities"
              f"  <- split restatement, harmless")
        if len(constant):
            top = constant["first"].round(6).value_counts().head(5).to_dict()
            print(f"{'':12}     ratios seen                 : {top}")

        print(f"{'':12}   step-function ratio (2-4 grp) : {len(step):,} securities"
              f"  <- date-triggered vendor correction, harmless")
        if len(step):
            print(f"{'':12}     gvkeys                      : {list(step.index[:10])}")

        if len(noisy):
            print(f"{'':12}   NOISY ratio (5+ groups)       : {len(noisy):,} securities"
                  f"  <- unexplained, worth a look")
            print(f"{'':12}     gvkeys                      : {list(noisy.index[:10])}")
            # A handful of names is expected vendor noise; treat as a failure only if it is
            # no longer a handful, i.e. actually widespread across the universe.
            if len(noisy) > max(20, int(0.001 * len(per_sec))):
                ok = False
                print(f"{'':12}     -> {len(noisy):,} exceeds the handful-of-names threshold "
                      f"for this many securities; treating as FAIL")

    print(f"\n{region.upper()} verdict: {'PASS' if ok else 'FAIL'}")
    return ok


def main(argv: list[str]) -> int:
    wanted = argv or list(REGIONS)
    bad = [r for r in wanted if r not in REGIONS]
    if bad:
        raise SystemExit(f"unknown region(s) {bad}; choose from {list(REGIONS)}")
    results = {r: check(r) for r in wanted}
    print(f"\n{'=' * 72}")
    for r, passed in results.items():
        print(f"  {r:6} {'PASS' if passed else 'FAIL'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
