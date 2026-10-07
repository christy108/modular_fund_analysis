"""Kevin4 NO MATERIALITY: (All SDGs / People / Planet) x the 4 Kevin4 buckets, Developed.

Sorts on BEHAVIOUR. Each cell asks "of this group's initiatives, what share is <bucket>?"
-- 4 signals, one per bucket, sorted jointly. Materiality is SUMMED AWAY, not read.

The twin file sweep_parameters_Developed_kevin4_material_share.py sorts on MATERIALITY
instead. Same sample, same groups, same Kevin4 cut -- read the two together.

3 cells, 4 signals each. The non-materiality companion to
sweep_parameters_Developed_kevin4_sdg_groups.py: same sample, same three SDG groups, same
Kevin4 cut, same everything in FIXED -- the only difference is what a signal MEANS.

    that sweep   "of this group's <bucket> initiatives, what share is MATERIAL?"
                 12 cells, 2 signals each (material vs immaterial), one bucket per cell
    this sweep   "of this group's initiatives, what share is <bucket>?"
                 3 cells, 4 signals each (one per bucket), sorted jointly

HOW MATERIALITY IS REMOVED -- no new column namespace and no new machinery. Both the
material__ and immaterial__ columns of an action land on the SAME signal index, and node 02
sums every column sharing an index into sum_with_i. The split is undone by where the columns
point, not by reading somewhere else. So add_materiality MUST still be True: the workbook is
the DATA SOURCE here, not the split.

Consequence: materiality_split_groups returns 0 groups (an index holding both prefixes is not
wholly material), so everything materiality-flavoured downstream is inert. The decomposition
PDF gate never opens, which is why -- unlike the sibling sweep -- this file does NOT have to
pin area_material_initatives_plots_per_signal_to_PDF, and why
minimum_initatives_needed_to_split_by_materiality must stay 0.

This is the same shape as the existing base_behaviour_behavioural4_<group> experiments, cut
on Kevin4 instead. Running both answers whether the re-cut moves anything: the two taxonomies
span the same 14 action types and therefore share a denominator, so their cells are
comparable one for one. (action13 is NOT comparable to either -- it drops pricing.)

    5 quantiles | Developed | mktcap weights | mktcap 0.99 | alpha bound 0.05
    WITH Real Estate + Utilities | behaviour shares (signal_i = share of the group)

"GLOBAL" IS region_analysis="Developed", for the reason spelled out in the sibling file: there
is no Global region, and the two that came closest now raise on purpose.
"""

from functions.signal_design.signal_definitions_materiality import _SDG_GROUPS

# Kept rather than deleted: sweep.py reads GRID unconditionally. The one axis is enumerated in
# EXPLICIT so the file reads as the three designs it is.
GRID: dict = {}


# --------------------------------------------------------------------------- #
# EXPLICIT: 3 groups x 1 taxonomy = 3 cells. The behaviour axis is INSIDE each cell here --
# SDG_Behaviour_Signals emits one signal per bucket and sorts them jointly -- which is why
# this is 3 runs and the materiality sibling is 12.
# --------------------------------------------------------------------------- #
EXPLICIT: list[dict] = [
    {"action_characterization": "SDG_Behaviour_Signals",
     "sdg_group": group,
     "behaviour_taxonomy": "kevin4"}
    for group in _SDG_GROUPS
]


SWEEP_NAME: str = "kevin4_NO_MATERIALITY_by_sdg_group"


# --------------------------------------------------------------------------- #
# FIXED: merged into every cell. Identical to the materiality sibling's block except that
# area_material_initatives_plots_per_signal_to_PDF is absent (see the docstring), so the two
# sweeps differ only in the design and can be read against each other.
# --------------------------------------------------------------------------- #
FIXED: dict = {
    "region_analysis": "Developed",

    "no_simple_quantiles": 5,
    "alpha_bound": 0.05,
    "portfolio_weighting": "mktcap",
    "mktcap_covered_if_filter_by_cum_market_cap": 0.99,
    "drop_real_estate": False,
    "drop_utilities": False,

    # signal_i = sum_with_i / sum_activities, i.e. bucket i's SHARE of the group's
    # initiatives. The four signals sum to 1 across the row, so no two of them are a mirror
    # pair -- unlike every cell of the materiality sibling.
    "signal_type": "weights",

    # The workbook is the DATA SOURCE, not the split: these are per-SDG action columns and
    # exist only in the v2 (17-SDG) file, from the vintage that added the action-level pivot.
    "add_materiality": True,
    "materiality_version": 2,

    # Must stay 0: there is no material/immaterial split here to gate, and build_cfg raises if
    # this is non-zero on a design with no split group.
    "minimum_initatives_needed_to_split_by_materiality": 0,

    "execute_3_filters": "suspicious_only",

    # The thin-portfolio gate at baseline. LESS likely to bite than in the materiality
    # sibling: a signal here is a bucket's share of ALL the group's initiatives, so its
    # denominator is the whole group rather than one bucket, and every firm-year with any
    # initiative in the group gets a value for all four signals. The 12-cell sibling ran at
    # 100% coverage throughout, so this one should too.
    "min_stocks_per_portfolio": 25,
    "min_portfolio_coverage": 0.8,

    # start_year / end_year absent: the full 2016-2024 sample.
}
