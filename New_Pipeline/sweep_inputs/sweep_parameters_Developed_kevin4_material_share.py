"""Kevin4 MATERIAL SHARE: (All SDGs / People / Planet) x (the 4 Kevin4 buckets), Developed.

Sorts on MATERIALITY. Each cell asks "of this group's <bucket> initiatives, what share is
material?" -- 2 signals, material vs immaterial, a mirror pair.

The twin file sweep_parameters_Developed_kevin4_no_materiality.py sorts on BEHAVIOUR
instead and has no materiality dimension at all. Same sample, same groups, same Kevin4
cut, same FIXED block bar one knob -- read the two together.

12 cells. The same grid shape as sweep_parameters_Developed_action_types_4_behaviours.py,
cut on the KEVIN4 buckets instead of the workbook's pre-aggregated ones:

    Advocacy    donation_funding, communication, association, volunteerism
    Upskilling  training, assessment_and_measurement, organizational_structuring
    Adaptation  adoption_of_standards_and_rules, incentives, pricing, asset_modification,
                modification_of_procedures
    Innovation  new_products, r_d_investments

WHY THIS IS A DIFFERENT SWEEP AND NOT A FLAG ON THAT ONE. The sibling file's behaviour axis
reads ONE pre-aggregated column per cell (material__advocacy_new_def__SDG_n), which bakes in
the Pre_Nikkei cut. The Kevin4 cut moves four actions relative to it -- volunteerism
Upskilling -> Advocacy, assessment_and_measurement and organizational_structuring
Adaptation -> Upskilling, and pricing Advocacy -> Adaptation -- so no pre-aggregated column
expresses any of these four buckets.

On pricing: it is absent from dict_4_signals_Action_1D_Pre_Nikkei (the LC-column design), but
the WORKBOOK column is not the same thing -- material__advocacy_new_def == donation_funding +
communication + association + pricing, exact on all 72,412 firm-years of v_2A1. So the
sibling sweep's Advocacy cell has always carried pricing, and Kevin4 MOVES it to Adaptation
rather than introducing it. The two Advocacy cells are therefore closer than the raw bucket
lists suggest, and the two Adaptation cells further apart. Every cell here re-sums the
per-SDG ACTION cube instead, which is exact: the 14 action types sum to __total by
construction, so a Kevin4 share is read against the same denominator a bucket share is.

Everything outside the two design axes is pinned to a single value, so every cell differs
from every other only in (SDG group, behaviour bucket). That is the point of the file: a
difference in alpha between two cells is attributable to the design, not to a weighting or
screen that moved with it.

    5 quantiles | Developed | mktcap weights | mktcap 0.99 | alpha bound 0.05
    WITH Real Estate + Utilities | weighted materiality (signal_i = share)

"GLOBAL" IS region_analysis="Developed". There is no Global region: the two that once came
closest, "Europe_and_North_America" and "Europe_and_North_America_and_Japan", now raise on
purpose (they applied no geography screen, admitting ~6,294 LC firms outside the Developed
factor's countries, while their currency filter dropped GBP/CHF/NOK/SEK/DKK). "Developed" is
what that raise message points at: US + Canada + the 16 FF-Europe countries + Japan, all
eight listing currencies, USD-converted, priced against data/FAMA/Developed_*.csv. Note its
market-cap screen pools across currency areas, so US mega-caps set the implied size floor.
"""

from functions.signal_design.signal_definitions_materiality import (
    KEVIN_4_BEHAVIOURS,
    _SDG_GROUPS,
)

# --------------------------------------------------------------------------- #
# GRID: empty, deliberately.
#
# Unlike the sibling sweep -- where each SDG group read a DIFFERENT cfg key and a cartesian
# product would have built combinations in which the action silently did not apply -- both
# axes here are ordinary independent keys (sdg_group, materiality_kevin4_bucket) under ONE
# action_characterization, so a GRID product would in fact be correct.
#
# EXPLICIT is still used, for two reasons. The cell list then reads as the 12 designs it is
# rather than as a product the reader has to multiply out, and it stays shaped like the
# sibling file, so the two sweeps can be diffed against each other line for line.
#
# Kept rather than deleted: sweep.py reads GRID unconditionally.
# --------------------------------------------------------------------------- #
GRID: dict = {}


# Both axes come from the dicts the DESIGN validates against (Materiality_Kevin4_SDG raises
# on anything outside them), so this file cannot name a group or bucket that does not exist,
# and re-cutting KEVIN_4_BEHAVIOURS in signal_definitions.py re-cuts the sweep with it.
#
# _SDG_GROUPS is {All_SDGs: 1-17, People: 1-5/8/10, Planet: 6/7/12-15} -- exactly the three
# groups requested, and the same three the sibling sweep runs.
_GROUPS = list(_SDG_GROUPS)
_BUCKETS = list(KEVIN_4_BEHAVIOURS)


# --------------------------------------------------------------------------- #
# EXPLICIT: 3 groups x 4 buckets = 12 cells.
# --------------------------------------------------------------------------- #
EXPLICIT: list[dict] = [
    {"action_characterization": "Materiality_Kevin4_SDG",
     "sdg_group": group,
     "materiality_kevin4_bucket": bucket}
    for group in _GROUPS
    for bucket in _BUCKETS
]


SWEEP_NAME: str = "kevin4_MATERIAL_SHARE_by_sdg_group"


# --------------------------------------------------------------------------- #
# FIXED: merged into every cell. An EXPLICIT entry wins for the same key.
# --------------------------------------------------------------------------- #
FIXED: dict = {
    # THE REGION. Drives currency_filter, region_filter, convert_to_USD=True,
    # fama_factor_region="Developed" and the 19-country loc whitelist in 01_process_lc.py.
    # See the module docstring on why this is what "Global" means here.
    "region_analysis": "Developed",

    # ---- the requested single-valued axes --------------------------------- #
    "no_simple_quantiles": 5,

    # "Alpha 0.95" = keep the middle 95% of sum_activities, i.e. a 0.05 trim PER TAIL, which
    # is what alpha_bound means here. Also the build_cfg baseline.
    "alpha_bound": 0.05,

    # Market-cap weighted legs, universe truncated at 99% of cumulative market cap.
    "portfolio_weighting": "mktcap",
    "mktcap_covered_if_filter_by_cum_market_cap": 0.99,

    # WITH Real Estate and Utilities. build_cfg defaults both to True (drop them); moved
    # together because the request is "with RE/Utilities" vs "without", not four variants.
    "drop_real_estate": False,
    "drop_utilities": False,

    # "Weighted materiality": signal_i = sum_with_i / sum_activities, i.e. the material SHARE
    # of that (group, bucket) rather than a raw level. The build_cfg baseline; stated
    # explicitly because it is the half of the request easiest to assume.
    "signal_type": "weights",

    # ---- materiality: what makes these designs possible at all ------------ #
    # version 2 is the 17-SDG workbook; the per-SDG action-type cube only exists there, and
    # only from the vintage that added the action-level pivot upstream. Verified present on
    # golden_data="v_2A1" (the build_cfg default): 476/476 per-SDG action columns, and every
    # one of these 12 cells fully covered.
    "add_materiality": True,
    "materiality_version": 2,

    # *** LOAD-BEARING, NOT TIDINESS. ***
    #
    # It defaults True, and every cell here is exactly ONE materiality_split_groups group
    # whose two signals are a perfect mirror -- so node 07's decomposition gate OPENS and
    # calls initiative_brackets.parse_numerator unguarded. That raises
    # `numerator mixes actions [...]; expected exactly one` on any numerator naming more than
    # one action, and a Kevin4 bucket always names between two and five. Without this line
    # all 12 cells die at the final PDF.
    #
    # The sibling sweep needs no such line: its numerators are a single pre-aggregated
    # action apiece, which parse_numerator accepts. This is the one knob that genuinely
    # differs between the two files' FIXED blocks.
    #
    # base_materiality_kevin4_sdg() forces the same flag; a sweep bypasses that factory and
    # builds cfgs straight from these dicts, so it has to pin it itself.
    "area_material_initatives_plots_per_signal_to_PDF": False,

    # No materiality-split floor: a firm-year splits however few initiatives it has.
    # Baseline. Usable here if wanted -- these are single-group designs, which is what
    # build_cfg requires of this knob -- and worth revisiting for the Innovation column.
    "minimum_initatives_needed_to_split_by_materiality": 0,

    # Filter 2 only (drop suspicious gvkeys), matching the sibling Developed sweeps. Filter 3
    # is SKIPPED under this mode (01_process_lc.py gates it on _all3), so that knob has no
    # effect here at any value.
    "execute_3_filters": "suspicious_only",

    # The thin-portfolio gate, at baseline: a High/Low leg is HIDDEN unless it holds at least
    # min_stocks_per_portfolio names in at least min_portfolio_coverage of formation months.
    #
    # WHERE THIS SWEEP WILL BITE: the bottom-right of the grid. Measured on v_2A1 across all
    # 72,412 firm-years, the FLAT Kevin4 buckets are zero for 5.4% (Advocacy), 16.3%
    # (Upskilling), 15.3% (Adaptation) and 57.5% (Innovation) of firm-years. Every cell here
    # is thinner than its flat counterpart -- People is 7 of the 17 SDGs and Planet 6 -- so
    # expect (People, Innovation) and (Planet, Innovation) to hit this gate. Read each cell's
    # signal_sparsity audit before treating it as a result.
    #
    # These are bounded shares, so the damaging tie block is at the TOP, not the bottom: the
    # flat buckets sit at exactly 1.0 for 20.3% / 36.7% / 51.9% / 63.5% of their non-zero
    # firm-years. The sort keeps a tie block on the bottom cutpoint and drops one on the top,
    # so it is the HIGH leg that loses names. Read pct_at_max, not pct_zero alone.
    "min_stocks_per_portfolio": 25,
    "min_portfolio_coverage": 0.8,

    # start_year / end_year absent: the full 2016-2024 sample.
}
