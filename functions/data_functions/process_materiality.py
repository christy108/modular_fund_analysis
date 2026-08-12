"""Load the SASB materiality workbook and merge it onto the LC firm-year panel.

Optional, additive step: the workbook contributes 15 SASB "materiality" count columns
({immaterial, material, unmapped} x {adaptation, advocacy, innovation, upskilling,
total}) keyed by (gvkey, rfyear). Merging is an INNER join, so only firm-years present
in both LC and the workbook survive — LC gains the count columns and is filtered to the
matched sample.

Kept as a standalone plain-pandas module (no New_Pipeline dependency), matching the
style of the sibling ``process_lc.py`` so it stays usable outside the pipeline. gvkey is
zero-padded with the same ``.astype(str).str.zfill(6)`` idiom used across ``functions/``.
"""

import os
from pathlib import Path

import pandas as pd

MATERIALITY_FILE = "Matched_SASB_GOLDEN_long_matchings_vZERO_FirmYear.xlsx"
MATERIALITY_SHEET = "Company-Year"
# The 15 count columns to bring onto LC. The workbook's other columns (company name,
# GICS_level_1/2/3, loc, MacroRegion, conml) already exist in LC and are dropped here to
# avoid _x/_y collisions on merge.
MATERIALITY_COLUMNS = [
    f"{grp}__{act}"
    for grp in ("immaterial", "material", "unmapped")
    for act in ("adaptation", "advocacy", "innovation", "upskilling", "total")
]


def _default_location():
    """Directory holding the materiality workbook; overridable via MATERIALITY_LOCATION."""
    return Path(
        os.environ.get(
            "MATERIALITY_LOCATION",
            Path.home() / "Documents" / "GitHub" / "Data" / "Materiality",
        )
    )


def load_materiality(materiality_location=None, *, filename=MATERIALITY_FILE, sheet=MATERIALITY_SHEET):
    """Read the SASB materiality workbook; return the join keys plus the 15 count columns.

    The keys are normalised to LC's formats so a later merge actually matches: gvkey
    zero-padded to 6 chars, rfyear as pandas nullable ``Int64``. Deduped on (gvkey,
    rfyear) defensively (the workbook is already one row per firm-fiscal-year).
    """
    loc = Path(materiality_location) if materiality_location is not None else _default_location()
    df = pd.read_excel(loc / filename, sheet_name=sheet)
    df = df[["gvkey", "rfyear"] + MATERIALITY_COLUMNS].drop_duplicates(subset=["gvkey", "rfyear"])
    df["gvkey"] = df["gvkey"].astype(str).str.zfill(6)   # match lc's gvkey format
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


def add_materiality_to_lc(lc, materiality_location=None):
    """One-call convenience: load the workbook and inner-merge it onto lc."""
    return merge_materiality_into_lc(lc, load_materiality(materiality_location))
