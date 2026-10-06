"""Developed: (All SDGs / People / Planet) x (matteo3 / behavioural4 / action13), NO materiality.

9 cells. The companion to sweep_parameters_Developed_action_types_4_behaviours.py: identical
sample, identical SDG groups, identical everything in FIXED -- the one difference is what a
signal MEANS.

    that sweep  signal_0 = of this group's <behaviour> initiatives, the MATERIAL share
    this sweep  signal_i = of this group's initiatives, the share that is <behaviour i>

So the two can be read against each other cell for cell.

WHY A CELL IS A WHOLE TAXONOMY, NOT ONE BEHAVIOUR. Drop the materiality split and a
(group, one behaviour) cell has a single signal, which signal_denominator="Sum_All_Signals"
turns into x/x = 1 -- constant, unsortable. The behaviours have to be CO-signals sharing a
denominator. That is why this file is 9 cells and its sibling is 51: the action13 cells carry
13 signals each, so you still get a sort per action, inside one run rather than thirteen.

WHY add_materiality IS STILL True, in a sweep with "no_materiality" in its name. The design
reads `material__<action>__SDG_n` AND `immaterial__<action>__SDG_n` and points both at the
same signal index, so node 02 sums them -- the workbook is the DATA SOURCE, not the split.
LC's own "<action> - SDG {n}" columns would avoid the merge entirely, but matteo3 is
unreachable from them (its buckets are action x stakeholder, which has no per-SDG form
outside a 1,666-column file this repo never loads). The merge is an inner join but costs no
sample on this vintage: the workbook covers 100% of LC firm-years, 72,412 -> 72,412.

DENOMINATORS DIFFER BETWEEN THE THREE TAXONOMIES, so shares do not reconcile across them:
behavioural4 spans all 14 actions, action13 omits `pricing`, and matteo3 omits both `pricing`
and `association` by construction upstream. Compare cells WITHIN a taxonomy.
"""

from functions.signal_design.signal_definitions_materiality import (
    BEHAVIOUR_TAXONOMIES,
    _SDG_GROUPS,
)

# --------------------------------------------------------------------------- #
# GRID: empty, deliberately -- sweep.py reads it unconditionally.
#
# Unlike the materiality sibling, the two axes here ARE independent (both are plain cfg keys
# on one characterization, so no combination is meaningless) and a GRID would work. EXPLICIT
# is used anyway so the two files stay diffable and the worklist stays readable as a list.
# --------------------------------------------------------------------------- #
GRID: dict = {}


# 3 taxonomies x 3 SDG groups. Driven off the design module's own dicts rather than literals,
# so adding a taxonomy or a group there extends this sweep without touching this file.
EXPLICIT: list[dict] = [
    {"action_characterization": "SDG_Behaviour_Signals",
     "behaviour_taxonomy": taxonomy,
     "sdg_group": group}
    for taxonomy in BEHAVIOUR_TAXONOMIES
    for group in _SDG_GROUPS
]


SWEEP_NAME: str = "developed_no_materiality_sdg_groups_x_behaviour_taxonomies"


# --------------------------------------------------------------------------- #
# FIXED: merged into every cell. An EXPLICIT entry wins for the same key.
# Byte-identical to the materiality sibling's FIXED -- that is the point.
# --------------------------------------------------------------------------- #
FIXED: dict = {
    # THE REGION. Drives currency_filter, region_filter, convert_to_USD=True,
    # fama_factor_region="Developed" and the 19-country loc whitelist in 01_process_lc.py.
    "region_analysis": "Developed",

    # ---- the requested single-valued axes --------------------------------- #
    "no_simple_quantiles": 5,

    # "Alpha 0.95" = keep the middle 95% of sum_activities, i.e. a 0.05 trim PER TAIL, which
    # is what alpha_bound means here. Also the build_cfg baseline.
    "alpha_bound": 0.05,

    # Market-cap weighted legs, universe truncated at 99% of cumulative market cap.
    "portfolio_weighting": "mktcap",
    "mktcap_covered_if_filter_by_cum_market_cap": 0.99,

    

    # signal_i = sum_with_i / sum_activities, i.e. a SHARE rather than a raw level. Here that
    # makes each signal the behaviour's share of the group, and the taxonomy's signals sum to
    # 1 across a row -- the first thing to check on the first completed cell.
    "signal_type": "weights",

    # ---- the workbook, as data source rather than as a split -------------- #
    # See the module docstring. version 2 is the 17-SDG workbook; the per-SDG behaviour
    # columns exist only there.
    "add_materiality": True,
    "materiality_version": 2,

    # MUST stay 0. build_cfg raises above 0 unless the design has exactly ONE
    # material/immaterial group, and these designs deliberately have NONE -- both prefixes
    # share a signal index, so materiality_split_groups does not see a split to gate.
    "minimum_initatives_needed_to_split_by_materiality": 0,

    # Filter 2 only (drop suspicious gvkeys), matching the sibling sweeps. Filter 3 is
    # SKIPPED under this mode (01_process_lc.py gates it on _all3), so that knob has no
    # effect here at any value.
    "execute_3_filters": "suspicious_only",

    # The thin-portfolio gate, at baseline: a High/Low leg is HIDDEN unless it holds at least
    # min_stocks_per_portfolio names in at least min_portfolio_coverage of formation months.
    #
    # Expect this to bite FAR LESS than in the materiality sibling. There a cell's signal was
    # one behaviour's material share, so a firm needed initiatives in that behaviour AND a
    # non-zero split; here a firm needs only a non-zero denominator across the whole taxonomy,
    # and an empty behaviour scores 0.0 rather than dropping the firm. Only a firm-year with
    # no initiatives at all in the taxonomy goes 0/0 and leaves the sample.
    "min_stocks_per_portfolio": 25,
    "min_portfolio_coverage": 0.8,

    # start_year / end_year absent: the full 2016-2024 sample.
}
