"""Load the SASB materiality file and merge it onto the LC firm-year panel.

Optional, additive step: the file contributes 15 SASB "materiality" count columns
({immaterial, material, unmapped} x {adaptation, advocacy, innovation, upskilling,
total}) keyed by (gvkey, rfyear). Merging is an INNER join, so only firm-years present
in both LC and the materiality file survive — LC gains the count columns and is filtered
to the matched sample.

Kept as a standalone plain-pandas module (no New_Pipeline dependency), matching the
style of the sibling ``process_lc.py`` so it stays usable outside the pipeline. gvkey is
zero-padded with the same ``.astype(str).str.zfill(6)`` idiom used across ``functions/``.
"""

import os
from pathlib import Path

import pandas as pd



# The 15 count columns to bring onto LC. The file's other columns (company name,
# GICS_level_1/2/3, loc, MacroRegion, conml) already exist in LC and are dropped here to
# avoid _x/_y collisions on merge.
MATERIALITY_COLUMNS = [
    f"{grp}__{act}"
    for grp in ("immaterial", "material", "unmapped")
    for act in ("adaptation", "advocacy_new_def", "innovation", "upskilling", "total")
]

# Per-SDG breakdown of the three __total__ columns, feeding the SDG-level signal designs in
# functions/signal_design/signal_definitions_materiality.py. Only the v2 (17-SDG) file carries
# these, so they are selected opportunistically below rather than required — v1 loads unchanged.
MATERIALITY_SDG_COLUMNS = [
    f"{grp}__total__SDG_{n}"
    for grp in ("immaterial", "material", "unmapped")
    for n in range(1, 18)
]


def _default_location():
    """Directory holding the materiality file; overridable via MATERIALITY_LOCATION."""
    return Path(
        os.environ.get(
            "MATERIALITY_LOCATION",
            Path.home() / "Documents" / "GitHub" / "Data" / "Materiality",
        )
    )


def load_materiality(materiality_location=None, *, version, golden_data):
    """Read the SASB materiality file; return the join keys plus the 15 count columns.

    The keys are normalised to LC's formats so a later merge actually matches: gvkey
    zero-padded to 6 chars, rfyear as pandas nullable ``Int64``. Deduped on (gvkey,
    rfyear) defensively (the file is already one row per firm-fiscal-year).
    """

    filename = f"Matched_SASB_GOLDEN_long_matchings_{golden_data}_FirmYear_17SDGs_matching_v{version}.csv"
    loc = Path(materiality_location) if materiality_location is not None else _default_location()
    df = pd.read_csv(loc / filename)
    sdg_columns = [c for c in MATERIALITY_SDG_COLUMNS if c in df.columns]
    df = df[["gvkey", "rfyear"] + MATERIALITY_COLUMNS + sdg_columns].drop_duplicates(subset=["gvkey", "rfyear"])
    df["gvkey"] = df["gvkey"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)   # match lc's gvkey format (CSV stores gvkey as float, e.g. 1004.0)
    df["rfyear"] = df["rfyear"].astype("Int64")          # match lc's nullable-Int64 rfyear
    return df


def merge_materiality_into_lc(lc, lc_materiality):
    """Inner-join materiality onto lc by (gvkey, rfyear); print shape before/after.

    Inner join: only (gvkey, rfyear) pairs present in both survive. lc may carry
    duplicate (gvkey, rfyear) rows at this stage (collapsed only later, at prepare_panel)
    while materiality is unique per key, so the join adds columns and filters rows but
    does not multiply them.
    """
    lc = lc.copy()
    lc["gvkey"] = lc["gvkey"].astype(str).str.zfill(6)   # gvkey is only conditionally padded upstream
    print("[materiality] lc shape before merge:", lc.shape)
    lc = lc.merge(lc_materiality, on=["gvkey", "rfyear"], how="inner")
    print("[materiality] lc shape after  merge:", lc.shape)
    return lc


def add_materiality_to_lc(lc, version, golden_data):
    """One-call convenience: load the materiality file and inner-merge it onto lc."""
    # Both are KEYWORD-ONLY on load_materiality (it takes materiality_location as its
    # single positional), so passing them positionally binds version to the location
    # and raises before the file is ever named.
    return merge_materiality_into_lc(
        lc, load_materiality(version=version, golden_data=golden_data)
    )




