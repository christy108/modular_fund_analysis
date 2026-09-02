"""Bracket schemes for decomposing a portfolio leg's MATERIAL initiatives.

Node 07 sorts firms on ``signal_0 = material__total / (material__total + immaterial__total)``
and reports an alpha on the High-Low spread, but ``material__total`` is an opaque count: it
says how many material initiatives a firm ran, never what kind. These schemes cut that total
five different ways so the dashboard can show, per portfolio leg per month, *what the material
initiatives actually are* -- and whether that mix drifts over the sample.

Every scheme partitions the SAME quantity, ``material__total``, so the five charts share one
denominator and are directly comparable. Two of the three underlying splits are exact:

  * the 4-way behavioural split (adaptation/advocacy_new_def/innovation/upskilling) sums to
    ``material__total`` exactly;
  * the 17 per-SDG columns (``material__total__SDG_1..17``) sum to it exactly, so the SDG-3,
    SDG-5 and climate-vs-rest schemes -- all coarsenings of those 17 -- do too;
  * the 3-way "Matteo" split (advocacy_old_def/preparation/transformation) does NOT. Measured
    on the v_2A1 workbook (72,412 firm-years) it is a strict SUBSET -- never over, short on
    37,946 rows, covering 90.79% of material initiatives. ~9.2% carry no old-3-way label.

Rather than rescale that scheme to its own smaller total (which would silently hide the gap and
make its bands non-comparable with the other four), ``bands_for`` appends an explicit
``Unclassified`` residual. All five schemes then sum to ``material__total`` exactly and the gap
is visible on the chart. The residual is emitted for any scheme that needs it, so a future
workbook whose behavioural split stops being exhaustive fails loudly on the chart rather than
quietly in the arithmetic.

SDG membership is imported from ``functions/signal_design/signal_definitions.py`` -- the same
dicts the SDG *signal designs* are cut from -- so a decomposition band and a sorting signal can
never describe different SDG sets. Change a split there, not here.
"""

from __future__ import annotations

from functions.signal_design.signal_definitions import (
    CLIMATE_NATURAL_CAPITAL_VS_EACH_SDG,
    PEOPLE_PLANET_PROSPERITY,
    SDG_5_BRACKETS,
    _check_groups_disjoint,
)

# The quantity every scheme partitions. Also the denominator of every share.
TOTAL_COLUMN = "material__total"

# Band appended when a scheme's own columns fall short of TOTAL_COLUMN.
RESIDUAL_BAND = "Unclassified"

# Climate-vs-rest is NOT in signal_definitions: the closest thing there,
# CLIMATE_NATURAL_CAPITAL_VS_EACH_SDG, splits the other 14 SDGs individually (30 signals).
# Built here from the same SDG_5_BRACKETS group so this scheme is a strict coarsening of the
# 5-bracket one and the two charts reconcile band-for-band.
_CLIMATE_GROUP = "Climate & Natural Capital"
CLIMATE_VS_REST = {
    _CLIMATE_GROUP: list(SDG_5_BRACKETS[_CLIMATE_GROUP]),
    "Other SDGs": sorted(
        sdg
        for group, sdgs in SDG_5_BRACKETS.items()
        if group != _CLIMATE_GROUP
        for sdg in sdgs
    ),
}
_check_groups_disjoint(CLIMATE_VS_REST)


def _sdg_bands(groups):
    """{group: [sdg, ...]} -> {group: [material__total__SDG_n, ...]}."""
    _check_groups_disjoint(groups)
    return {g: [f"{TOTAL_COLUMN}__SDG_{n}" for n in sdgs] for g, sdgs in groups.items()}


def _behaviour_bands(pairs):
    """[(band label, lc suffix), ...] -> {band label: [material__<suffix>]}."""
    return {label: [f"material__{suffix}"] for label, suffix in pairs}


# slug -> (display title, {band label: [source column, ...]}). The slug is baked into the
# dashboard widget keys and the PDF page titles, so it is API: renaming one blanks the widget.
# Band order is the DECLARATION order below and is preserved end to end -- an area chart whose
# bands reorder between months is unreadable, so nothing downstream may sort them by size.
SCHEMES: dict[str, tuple[str, dict[str, list[str]]]] = {
    "matteo3": (
        "Original Matteo (3)",
        _behaviour_bands([
            ("Advocacy", "advocacy_old_def"),
            ("Preparation", "preparation"),
            ("Transformation", "transformation"),
        ]),
    ),
    "behavioural4": (
        "Behavioural (4)",
        _behaviour_bands([
            ("Advocacy", "advocacy_new_def"),
            ("Adaptation", "adaptation"),
            ("Upskilling", "upskilling"),
            ("Innovation", "innovation"),
        ]),
    ),
    "sdg3": ("SDG - People / Prosperity / Planet (3)", _sdg_bands(PEOPLE_PLANET_PROSPERITY)),
    "sdg5": ("SDG brackets (5)", _sdg_bands(SDG_5_BRACKETS)),
    "climate": ("Climate & Natural Capital vs rest", _sdg_bands(CLIMATE_VS_REST)),
    # The `climate` scheme above pools the other 14 SDGs into one band, which answers "how
    # much is climate" but hides which of the rest carries the weight. This is the same cut
    # with the remainder BROKEN OUT: Climate & Natural Capital stays one group, every other
    # SDG gets its own band. Straight from signal_definitions, so it matches the
    # Materiality_Climate_Natural_Capital_vs_All_SDGS *signal* design exactly.
    "climate_vs_each": (
        "Climate & Natural Capital vs each SDG",
        _sdg_bands(CLIMATE_NATURAL_CAPITAL_VS_EACH_SDG),
    ),
}

SCHEME_SLUGS: list[str] = list(SCHEMES)


def scheme_title(slug: str) -> str:
    return SCHEMES[slug][0]


def bands_for(slug: str) -> dict[str, list[str]]:
    """Band -> source columns for one scheme, in declaration order.

    The caller adds the RESIDUAL_BAND itself (it is ``TOTAL_COLUMN`` minus the sum of these
    columns, so it has no source column of its own) -- see ``residual_needed``.
    """
    return SCHEMES[slug][1]


def required_columns() -> list[str]:
    """Every lc column any scheme reads, plus the shared denominator. First-seen order."""
    cols = [TOTAL_COLUMN]
    for _, bands in SCHEMES.values():
        for band_cols in bands.values():
            for c in band_cols:
                if c not in cols:
                    cols.append(c)
    return cols
