"""Bracket schemes for decomposing the MATERIAL initiatives a signal actually counted.

Node 07 sorts firms on ``signal_0 = material_G / (material_G + immaterial_G)`` for some group
G and reports an alpha on the High-Low spread, but that numerator is an opaque count: it says
how many material initiatives a firm ran inside G, never what kind. These schemes cut THAT
NUMERATOR up to six ways so the dashboard can show, per portfolio leg per month, *what the
material initiatives actually are* -- and whether that mix drifts over the sample.

THE DENOMINATOR IS THE SIGNAL'S OWN NUMERATOR, not ``material__total``. For
Materiality_People_Plus_Prosperity_SDG the bands cover SDGs 1-5, 8-11, 16, 17 and no Planet
band is drawn, because Planet initiatives never enter that signal. An earlier version split
``material__total`` -- all 17 SDGs -- which drew bands the signal had never looked at and
read as a bug to anyone who knew the design.

``bands_for_numerator`` restricts each scheme to the numerator's own (action, SDG set) and
DROPS a scheme that cannot inform it, rather than drawing it empty:

  * an action scheme (matteo3 / behavioural4) against a numerator that is already one action
    -- there is no ``material__preparation__innovation__SDG_3`` column to split it with;
  * any scheme left with fewer than two non-empty bands, which would draw as a single 100%
    band. A People-only numerator does this to ``sdg3``; a People+Prosperity one empties
    ``climate`` entirely.

Exactness, measured on the v_2A1 workbook (72,412 firm-years):

  * the 4-way behavioural split (adaptation/advocacy_new_def/innovation/upskilling) sums to
    ``material__total__SDG_n`` EXACTLY -- per SDG, per row, zero mismatches;
  * ``material__<action>`` == ``sum_n material__<action>__SDG_n`` exactly, all 8 actions, so
    working purely in per-SDG columns changes no number versus the old non-per-SDG bands;
  * the 3-way "Matteo" split (advocacy_old_def/preparation/transformation) does NOT. It is a
    strict SUBSET -- never over -- covering 90.79% of material initiatives, per-SDG row-match
    72.4% (SDG 12) to 99.6%. ~9.2% carry no old-3-way label.

Rather than rescale that scheme to its own smaller total (which would silently hide the gap
and make its bands non-comparable with the others), the caller appends an explicit
``Unclassified`` residual. Every applicable scheme then sums to the numerator exactly and the
gap is visible on the chart -- so a future workbook whose behavioural split stops being
exhaustive fails loudly on the chart rather than quietly in the arithmetic.

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


# The 8 action families process_materiality.py loads per SDG. Kept in sync with
# MATERIALITY_SDG_ACTIONS there and _SDG_ACTIONS in signal_definitions_materiality.py.
ACTIONS: tuple[str, ...] = ("adaptation", "advocacy_new_def", "advocacy_old_def",
                            "innovation", "preparation", "transformation", "upskilling",
                            "total")

ALL_SDGS: frozenset[int] = frozenset(range(1, 18))


def _col(action: str, sdg: int) -> str:
    return f"material__{action}__SDG_{sdg}"


# slug -> (title, kind, groups). `kind` decides how a scheme is restricted to a numerator:
#   "sdg"    -- groups is {band: [sdg, ...]}; bands are intersected with the numerator's
#               SDG set and read from the numerator's OWN action.
#   "action" -- groups is [(band label, action), ...]; each band sums that action over the
#               numerator's SDG set. Only meaningful when the numerator is not already
#               restricted to one action (see bands_for_numerator).
# The slug is baked into the dashboard widget keys and the PDF page titles, so it is API:
# renaming one blanks the widget. Band order is DECLARATION order and is preserved end to
# end -- an area chart whose bands reorder between months is unreadable, so nothing
# downstream may sort them by size.
SCHEMES: dict[str, tuple[str, str, object]] = {
    "matteo3": (
        "Original Matteo (3)",
        "action",
        [("Advocacy", "advocacy_old_def"),
         ("Preparation", "preparation"),
         ("Transformation", "transformation")],
    ),
    "behavioural4": (
        "Behavioural (4)",
        "action",
        [("Advocacy", "advocacy_new_def"),
         ("Adaptation", "adaptation"),
         ("Upskilling", "upskilling"),
         ("Innovation", "innovation")],
    ),
    "sdg3": ("SDG - People / Prosperity / Planet (3)", "sdg", PEOPLE_PLANET_PROSPERITY),
    "sdg5": ("SDG brackets (5)", "sdg", SDG_5_BRACKETS),
    "climate": ("Climate & Natural Capital vs rest", "sdg", CLIMATE_VS_REST),
    # The `climate` scheme above pools the other 14 SDGs into one band, which answers "how
    # much is climate" but hides which of the rest carries the weight. This is the same cut
    # with the remainder BROKEN OUT: Climate & Natural Capital stays one group, every other
    # SDG gets its own band. Straight from signal_definitions, so it matches the
    # Materiality_Climate_Natural_Capital_vs_All_SDGS *signal* design exactly.
    "climate_vs_each": (
        "Climate & Natural Capital vs each SDG",
        "sdg",
        CLIMATE_NATURAL_CAPITAL_VS_EACH_SDG,
    ),
}

for _slug, (_t, _kind, _groups) in SCHEMES.items():
    if _kind == "sdg":
        _check_groups_disjoint(_groups)

SCHEME_SLUGS: list[str] = list(SCHEMES)


def scheme_title(slug: str) -> str:
    return SCHEMES[slug][0]


# --------------------------------------------------------------------------- #
# Numerator parsing
# --------------------------------------------------------------------------- #
def parse_numerator(numerator_cols) -> tuple[str, frozenset[int]]:
    """``[material__… columns]`` -> ``(action, sdg_set)``.

    Accepts the three column shapes a one-group materiality design can produce:

        material__total              -> ("total", all 17)      Material_Immaterial_only
        material__total__SDG_n       -> ("total", {n, ...})    the SDG-group designs
        material__<action>__SDG_n    -> ("<action>", {n, ...}) the pp_action designs

    Raises when the columns mix actions or are not material columns at all: every caller
    divides by the sum of these columns, so a silently mixed set would produce a chart whose
    denominator is not the signal's.
    """
    actions, sdgs, sdg_free = set(), set(), False
    for col in numerator_cols:
        c = str(col)
        if not c.startswith("material__"):
            raise ValueError(f"{c!r} is not a material__ column")
        rest = c[len("material__"):]
        if "__SDG_" in rest:
            act, _, n = rest.partition("__SDG_")
            actions.add(act)
            sdgs.add(int(n))
        else:
            actions.add(rest)
            sdg_free = True
    if len(actions) != 1:
        raise ValueError(f"numerator mixes actions {sorted(actions)}; expected exactly one")
    action = actions.pop()
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}; expected one of {sorted(ACTIONS)}")
    # A column with no SDG suffix is the whole action across every SDG. Verified on the
    # v_2A1 workbook: material__<action> == sum_n material__<action>__SDG_n exactly, for all
    # 8 actions, so expanding it to the full SDG set changes no number.
    return action, frozenset(ALL_SDGS if sdg_free else sdgs)


def bands_for_numerator(numerator_cols) -> dict[str, dict[str, list[str]]]:
    """``slug -> {band: [columns]}`` for the schemes that say something about THIS numerator.

    Every returned band reads ``material__<action>__SDG_n`` columns that are inside the
    signal's own numerator, so the bands sum to the numerator and each share answers "of the
    initiatives this signal counted, how many were X".

    A scheme is DROPPED, not emptied, when it cannot inform:

    * an "action" scheme (matteo3 / behavioural4) when the numerator is already one action --
      there is no ``material__preparation__innovation__SDG_3`` column to split it with, and
      the old-3 and new-4 schemes cut across each other anyway;
    * any scheme left with fewer than 2 non-empty bands, which would draw as a single 100%
      band. A People-only numerator does this to ``sdg3``; any People+Prosperity numerator
      empties ``climate`` entirely.

    The caller keeps the full static ``SCHEME_SLUGS`` key space and stores an empty frame for
    a dropped slug -- the Contract is built at import time, so the widget keys cannot depend
    on the config.
    """
    action, sdgs = parse_numerator(numerator_cols)
    out: dict[str, dict[str, list[str]]] = {}
    for slug, (_title, kind, groups) in SCHEMES.items():
        if kind == "sdg":
            bands = {band: [_col(action, n) for n in sorted(set(g) & sdgs)]
                     for band, g in groups.items()}
        elif action != "total":
            continue                       # one action cannot be split by action
        else:
            bands = {label: [_col(act, n) for n in sorted(sdgs)] for label, act in groups}
        bands = {b: cols for b, cols in bands.items() if cols}
        if len(bands) >= 2:
            out[slug] = bands
    return out


def required_columns_for(numerator_cols) -> list[str]:
    """Every column the applicable bands read, plus the numerator itself. First-seen order."""
    cols: list[str] = [str(c) for c in numerator_cols]
    for bands in bands_for_numerator(numerator_cols).values():
        for band_cols in bands.values():
            for c in band_cols:
                if c not in cols:
                    cols.append(c)
    return cols
