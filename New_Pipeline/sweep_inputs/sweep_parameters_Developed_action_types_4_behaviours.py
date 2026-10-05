"""Developed: (All SDGs / People / Planet) x (4 behaviour buckets + 13 action types).

51 cells. The SDG-group x behaviour cross of sweep_parameters_Developed.py, pushed one level
finer on the behaviour axis: as well as the four behaviour BUCKETS it runs each INDIVIDUAL
action type, which the workbook only started carrying per-SDG from the vintage that added the
action-level pivot upstream.

Everything outside the two design axes is pinned to a single value, so every cell differs
from every other only in (SDG group, behaviour). That is the whole point of the file: a
difference in alpha between two cells is attributable to the design, not to a weighting or
screen that moved with it.

    5 quantiles | Developed | mktcap weights | mktcap 0.99 | alpha bound 0.05
    WITH Real Estate + Utilities | weighted materiality (signal_i = share)

NO `pricing`. It is the 14th action type in the workbook and is carried everywhere else, but
it is zero for 94.2% of firm-years with 39 distinct signal values in the entire panel -- a
quantile sort on it cuts ties rather than ranking. Add it to _ACTION_TYPES below if you want
the degeneracy on the record; the ledger makes the re-run incremental.
"""

from functions.data_functions.process_materiality import MATERIALITY_ACTION_TYPES

# --------------------------------------------------------------------------- #
# GRID: empty, deliberately.
#
# The SDG group and its behaviour cannot be two independent axes: each group reads a
# DIFFERENT cfg key (materiality_all_action / materiality_people_action /
# materiality_planet_action), so a cartesian product would build combinations in which the
# action silently does not apply. The (group, behaviour) pair is therefore enumerated as one
# axis in EXPLICIT, and every other knob is single-valued and lives in FIXED.
#
# Kept rather than deleted: sweep.py reads GRID unconditionally.
# --------------------------------------------------------------------------- #
GRID: dict = {}


# (action_characterization, the one cfg key that characterization reads). One row per group.
# Materiality_Planet_Action_SDG is the WIDE Planet (6, 7, 12, 13, 14, 15); the width is read
# off the characterization name, so Narrow_Planet would be a different ac, not a third key.
_GROUPS = [
    ("Materiality_All_Action_SDG", "materiality_all_action"),        # all 17 SDGs
    ("Materiality_People_Action_SDG", "materiality_people_action"),  # 1-5, 8, 10
    ("Materiality_Planet_Action_SDG", "materiality_planet_action"),  # 6, 7, 12, 13, 14, 15
]

# The 4-bucket behavioural split. NOT the Matteo 3 (advocacy_old_def / preparation /
# transformation) that sweep_parameters_Developed.py runs -- these are the newer buckets, and
# the 13 action types below are exactly their constituents, so the two halves of the
# behaviour axis are the same initiatives at two granularities.
_BUCKETS = ["advocacy_new_def", "upskilling", "adaptation", "innovation"]

# The 13 individual action types: every action in the workbook except `pricing` (see the
# module docstring). Derived from the loader's tuple rather than listed out, so a renamed or
# added action cannot leave this file naming a column that is no longer selected.
_ACTION_TYPES = [a for a in MATERIALITY_ACTION_TYPES if a != "pricing"]

_BEHAVIOURS = _BUCKETS + _ACTION_TYPES


# --------------------------------------------------------------------------- #
# EXPLICIT: 3 groups x 17 behaviours = 51 cells.
# --------------------------------------------------------------------------- #
EXPLICIT: list[dict] = [
    {"action_characterization": ac, action_key: behaviour}
    for ac, action_key in _GROUPS
    for behaviour in _BEHAVIOURS
]


SWEEP_NAME: str = "developed_materiality_sdg_groups_x_action_types_x_4_behaviour_buckets"


# --------------------------------------------------------------------------- #
# FIXED: merged into every cell. An EXPLICIT entry wins for the same key.
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

    # Market-cap weighted legs, universe truncated at 99% of cumulative market cap. Both are
    # EXPLICIT axes in sweep_parameters_Developed.py; here they are pinned, so neither
    # reaches the cfg diff and neither appears in a run name.
    "portfolio_weighting": "mktcap",
    "mktcap_covered_if_filter_by_cum_market_cap": 0.99,

    # WITH Real Estate and Utilities. build_cfg defaults both to True (drop them); moved
    # together because the request is "with RE/Utilities" vs "without", not four variants.
    "drop_real_estate": False,
    "drop_utilities": False,

    # "Weighted materiality": signal_i = sum_with_i / sum_activities, i.e. the material SHARE
    # of that (group, behaviour) rather than a raw level. The build_cfg baseline; stated
    # explicitly because it is the half of the request that is easiest to assume.
    "signal_type": "weights",

    # ---- materiality: what makes these designs possible at all ------------ #
    # version 2 is the 17-SDG workbook; the per-SDG action-type cube only exists there.
    "add_materiality": True,
    "materiality_version": 2,

    # No materiality-split floor: a firm-year splits however few initiatives it has.
    # Baseline. WORTH REVISITING for the thinner action types -- see the note below.
    "minimum_initatives_needed_to_split_by_materiality": 0,

    # Filter 2 only (drop suspicious gvkeys), matching the sibling Developed sweep. Filter 3
    # is SKIPPED under this mode (01_process_lc.py gates it on _all3), so that knob has no
    # effect here at any value.
    "execute_3_filters": "suspicious_only",

    # The thin-portfolio gate, at baseline: a High/Low leg is HIDDEN unless it holds at least
    # min_stocks_per_portfolio names in at least min_portfolio_coverage of formation months.
    #
    # THIS IS WHERE THIS SWEEP WILL BITE. The action types are far thinner than the buckets
    # containing them -- measured on v_2A1, incentives is zero for 83.2% of firm-years and
    # adoption_of_standards_and_rules for 89.7%, against 12.5% for donation_funding -- and
    # People/Planet narrow the sample again on top of that. Expect hidden legs in the
    # bottom rows of the behaviour axis, and read each run's signal_sparsity audit before
    # treating any of those cells as a result.
    "min_stocks_per_portfolio": 25,
    "min_portfolio_coverage": 0.8,

    # start_year / end_year absent: the full 2016-2024 sample.
}
