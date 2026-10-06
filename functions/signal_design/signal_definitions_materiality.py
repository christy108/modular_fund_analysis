
# Which SDGs sit in each group lives in signal_definitions.py, so the plain-SDG designs
# there and the material/immaterial ones here are cut from the same groups and can never
# drift apart. Change a split there, not here. Re-exported under the same names this
# module has always used.
# The loader owns the action-type spelling: a name it does not select is never on lc, so
# Materiality_Action_Aggregate validates against the same tuple the merge is built from and a
# design can never ask for a column that was never loaded.
from functions.data_functions.process_materiality import (
    MATERIALITY_ACTION_TYPES,
    MATERIALITY_SDG_ACTIONS,
)

from functions.signal_design.signal_definitions import (  # noqa: F401
    CLIMATE_NATURAL_CAPITAL_VS_EACH_SDG,
    PEOPLE_PLANET_PROSPERITY,
    PEOPLE_Plus_PROSPERITY_VS_PLANET,
    Health_SDGS_Groups,
    PLANET_SDGS_Groups,

    ACTION_SLUG_TO_LC_TYPE,
    KEVIN_4_BEHAVIOURS,

    SDG_5_BRACKETS,
    _check_groups_disjoint,
    _group_slug,
    _one_group_vs_each_sdg,
)


def Materiality_Signals(signal_0_name="Material", signal_1_name="Immaterial"):
    return{
    
    "material__total": 0, 
    "immaterial__total": 1, 

    }, signal_0_name, signal_1_name




# Which per-SDG ACTION families process_materiality.py brings onto lc: the 7 behaviour buckets
# + total, and the 14 individual action types. ALIASED to the loader's tuple rather than
# restated -- a design naming an action outside the loader's set would ask for a column that
# was never merged, and the sort would come back empty rather than raise. Kept under the
# private name every design in this module already validates against.
_SDG_ACTIONS = MATERIALITY_SDG_ACTIONS


def _action_tag(action):
    """``'r_d_investments'`` -> ``'R_D_Investments'`` — an action's signal-name spelling.

    Shared by the per-SDG designs below and Materiality_Action_Aggregate so the two families
    spell the same action identically in portfolio labels and parity artifacts.
    """
    return action.replace("_", " ").title().replace(" ", "_")


def _check_action_partition(groups, universe=MATERIALITY_ACTION_TYPES):
    """Raise unless `groups` partitions `universe` exactly: no strays, no repeats, no gaps.

    The action-space twin of _check_groups_disjoint, which is reused rather than copied
    everywhere else in this module -- but not here, for two reasons. Its message is
    SDG-flavoured ("SDG_donation_funding appears in both ...") and would send the reader to
    the wrong file, and it checks DISJOINTNESS ONLY. Coverage is the part that matters for an
    action cut: the 14 action types sum exactly to `{state}__total` by construction
    (process_materiality.py), so a cut that silently drops one produces signals that no
    longer reconstruct the total, with no error anywhere.

    A STRAY action is the failure that actually bites. The loader selects the aggregate
    action columns opportunistically, so a misspelled slug names a column that was never
    merged; node 02 does now raise on that, but only at run time, twenty minutes in. Checked
    at import instead, like initiative_brackets.py checks its own scheme dicts.
    """
    seen = {}
    for group_name, actions in groups.items():
        for action in actions:
            if action not in universe:
                raise ValueError(
                    f"{action!r} in group {group_name!r} is not one of {sorted(universe)}; "
                    f"the loader never selects a material__{action} column, so the design "
                    f"would ask for a column that was never merged"
                )
            if action in seen:
                raise ValueError(
                    f"action {action!r} appears in both {seen[action]!r} and {group_name!r}; "
                    f"each action must belong to exactly one bucket"
                )
            seen[action] = group_name
    missing = sorted(set(universe) - set(seen))
    if missing:
        raise ValueError(
            f"groups {sorted(groups)} cover {len(seen)}/{len(universe)} action types; missing "
            f"{missing}. The 14 sum exactly to __total, so a partial cut's signals do not "
            f"reconstruct it and its shares are not comparable with a bucket design's."
        )
    return seen


def _derive_action_slug(lc_name):
    """``'TYPE: r&d investments'`` -> ``'r_d_investments'`` -- the computable direction.

    Slug -> LC name is NOT computable (the slug has lost the '&' and its position), which is
    why ACTION_SLUG_TO_LC_TYPE is written out by hand. This derives the slug back out of the
    LC name so the hand-written table can still be checked rather than trusted.
    """
    return (lc_name.removeprefix("TYPE: ")
            .replace(" & ", "_").replace("&", "_").replace(" ", "_"))


# Fail on IMPORT, not twenty minutes into a run: a bad cut should take the repo down before
# any config is built, the same stance initiative_brackets.py takes for its scheme dicts.
_check_action_partition(KEVIN_4_BEHAVIOURS)

# ...and that the hand-written LC spellings really are those same 14 actions. Checked by
# DERIVING the slug back out of each LC name -- the only direction that is computable -- so a
# typo in either dict raises here rather than naming a column that is not on the lc frame.
if set(ACTION_SLUG_TO_LC_TYPE) != set(MATERIALITY_ACTION_TYPES):
    raise ValueError(
        f"ACTION_SLUG_TO_LC_TYPE and MATERIALITY_ACTION_TYPES disagree on "
        f"{sorted(set(ACTION_SLUG_TO_LC_TYPE) ^ set(MATERIALITY_ACTION_TYPES))}"
    )
for _slug, _lc in ACTION_SLUG_TO_LC_TYPE.items():
    if not _lc.startswith("TYPE: ") or _derive_action_slug(_lc) != _slug:
        raise ValueError(
            f"ACTION_SLUG_TO_LC_TYPE[{_slug!r}] = {_lc!r} does not derive back to {_slug!r}"
        )


def _signals_from_groups(groups, action="total"):
    """Expand {group_name: [sdg, ...]} into ({lc_column: signal_index}, *signal_names).

    Every group yields two signals — material first, then immaterial — so indices
    run 0..2*len(groups)-1 in group order, matching the (dict, s0, s1, ...) tuple
    the callers unpack.

    ``action`` picks WHICH per-SDG count family the columns come from:
    ``material__{action}__SDG_{n}``. It defaults to "total" — every initiative of that
    SDG — which is what every design here used before the parameter existed, so all of
    them are bit-identical to their pre-parameter selves. Pass e.g. "innovation" to sort
    on one behavioural action's material share instead of the whole SDG total.

    A non-"total" action is TAGGED INTO THE SIGNAL NAME (Material_Innovation_People rather
    than Material_People). Two designs differing only by action would otherwise emit the
    same signal names and collide in portfolio labels and parity artifacts — the same trap
    Materiality_People_Plus_Prosperity_SDG's docstring warns about for group keys.

    Raises on an SDG listed in two groups: a duplicate dict key would silently keep the
    last write and leave the earlier group short (or empty), which is exactly the bug
    the hand-written versions of these dicts had.

    Raises on an unknown action, rather than emitting columns the materiality merge never
    loaded — those would merge as NaN and empty the sort with no error anywhere.
    """
    if action not in _SDG_ACTIONS:
        raise ValueError(f"action {action!r} is not one of {sorted(_SDG_ACTIONS)}")

    _check_groups_disjoint(groups)

    # "total" stays unlabelled so existing signal names are untouched.
    action_tag = "" if action == "total" else f"{_action_tag(action)}_"

    categories = {}
    names = []
    for group_name, sdgs in groups.items():
        slug = _group_slug(group_name)
        for materiality in ("material", "immaterial"):
            index = len(names)
            names.append(f"{materiality.capitalize()}_{action_tag}{slug}")
            for sdg in sdgs:
                categories[f"{materiality}__{action}__SDG_{sdg}"] = index
    return (categories, *names)


def Materiality_Signals_3_groups_people_planet_prosperity_SDG():
    """6 signals: material/immaterial x People, Prosperity, Planet."""
    return _signals_from_groups(PEOPLE_PLANET_PROSPERITY)


def Materiality_People_SDG():
    """2 signals: Material_People, Immaterial_People.

    A single group, so with signal_denominator="Sum_All_Signals" the denominator is
    material_People + immaterial_People and signal_0 is the People material share
    (signal_1 == 1 - signal_0, a mirror pair like Material_Immaterial_only).
    _signals_from_groups takes {group_name: [sdg, ...]}, so the group has to be
    re-wrapped in a one-entry dict -- passing the bare list raises.
    """
    return _signals_from_groups({"People": PEOPLE_PLANET_PROSPERITY["People"]})



def Materiality_Planet_SDG():
    """2 signals: Material_Planet, Immaterial_Planet.

    A single group, so with signal_denominator="Sum_All_Signals" the denominator is
    material_Planet + immaterial_Planet and signal_0 is the Planet material share
    (signal_1 == 1 - signal_0, a mirror pair like Material_Immaterial_only).
    _signals_from_groups takes {group_name: [sdg, ...]}, so the group has to be
    re-wrapped in a one-entry dict -- passing the bare list raises.
    """
    return _signals_from_groups({"Planet": PLANET_SDGS_Groups["Planet"]})

def Materiality_Narrow_Planet_SDG():
    """2 signals: Material_Narrow_Planet, Immaterial_Narrow_Planet.

    A single group, so with signal_denominator="Sum_All_Signals" the denominator is
    material_Narrow_Planet + immaterial_Narrow_Planet and signal_0 is the Narrow_Planet
    material share
    (signal_1 == 1 - signal_0, a mirror pair like Material_Immaterial_only).
    _signals_from_groups takes {group_name: [sdg, ...]}, so the group has to be
    re-wrapped in a one-entry dict -- passing the bare list raises.
    """
    return _signals_from_groups({"Narrow_Planet": PLANET_SDGS_Groups["Narrow_Planet"]})






def Materiality_Planet_Action_SDG(width, action):
    """2 signals: material/immaterial Planet for ONE behavioural action.

    `width` is a PLANET_SDGS_Groups key -- "Planet" (6, 7, 12, 13, 14, 15) or
    "Narrow_Planet" (13, 14, 15); `action` one of _SDG_ACTIONS. Same mirror-pair shape and
    the same advocacy_old_def / advocacy_new_def naming trap as
    Materiality_People_Plus_Prosperity_Action_SDG -- read its docstring. action="total"
    reproduces Materiality_Planet_SDG / Materiality_Narrow_Planet_SDG above, so no _total
    config is registered.
    """
    if width not in PLANET_SDGS_Groups:
        raise ValueError(f"width {width!r} is not one of {sorted(PLANET_SDGS_Groups)}")
    return _signals_from_groups({width: PLANET_SDGS_Groups[width]}, action=action)


def Materiality_People_Action_SDG(action):
    """2 signals: material/immaterial People for ONE behavioural action.

    The People twin of ``Materiality_People_Plus_Prosperity_Action_SDG`` -- same
    one-group mirror-pair shape as ``Materiality_People_SDG`` (PEOPLE_PLANET_PROSPERITY
    ["People"]), restricted to a single action, so the columns are
    ``material__<action>__SDG_n`` rather than ``material__total__SDG_n``.

    Same NAMING TRAP as the People+Prosperity version: ``advocacy_old_def`` is the
    advocacy leg of the ORIGINAL 3-way split (advocacy_old_def / preparation /
    transformation), ``advocacy_new_def`` the one from the newer 4-way split. Both are
    real, different columns -- picking the wrong one sorts on a different quantity with
    no error.

    ``action="total"`` reproduces ``Materiality_People_SDG`` exactly (same columns, same
    untagged names), so the two are interchangeable at that value.

    Read the signal_sparsity audit before trusting any non-total action here: People is a
    NARROWER group than People+Prosperity, so every action's density is lower than the
    measured table in experiments.py::_register_pp_action_experiments reports.
    """
    return _signals_from_groups(
        {"People": PEOPLE_PLANET_PROSPERITY["People"]}, action=action
    )


# Every SDG, as ONE group. Used by Materiality_All_Action_SDG below.
_ALL_SDGS = list(range(1, 18))


def Materiality_All_Action_SDG(action):
    """2 signals: material/immaterial across ALL 17 SDGs for ONE behavioural action.

    NOT the same construction as ``Materiality_Signals`` (the ``Material_Immaterial_only``
    design), and the difference matters if you put the two side by side:

    * ``Materiality_Signals`` reads the AGGREGATE columns ``material__total`` /
      ``immaterial__total`` -- one pair, no SDG dimension.
    * this reads the per-SDG cube and sums ``material__<action>__SDG_1..17``.

    Those two need not be equal even at ``action="total"``: an initiative mapped to more
    than one SDG is counted once per SDG here but once in total there, and anything the
    workbook left unmapped to any SDG is in the aggregate column and in NO per-SDG column.
    So use THIS function for every cell of an all-SDG x behaviour block, including the
    "all behaviours" cell (``action="total"``), rather than mixing it with
    ``Material_Immaterial_only`` -- otherwise one cell of the block is built on a
    different denominator from the other three and the block is not internally comparable.

    One group, so signal_0 is the material share and signal_1 its exact mirror.
    """
    return _signals_from_groups({"All_SDGs": _ALL_SDGS}, action=action)


def Materiality_People_Plus_Prosperity_SDG():
    """2 signals: Material_People_Plus_Prosperity, Immaterial_People_Plus_Prosperity.

    People + Prosperity pooled (SDGs 1-5, 8-11, 16, 17), material vs immaterial. Same
    one-group mirror-pair shape as Materiality_People_SDG. The dict KEY is what
    _group_slug turns into the signal name, so it has to be the pooled group's own name
    -- keying it "People" would silently emit Material_People and collide with
    Materiality_People_SDG's names in portfolio labels and parity artifacts.
    """
    _group = "People_Plus_Prosperity"
    return _signals_from_groups({_group: PEOPLE_Plus_PROSPERITY_VS_PLANET[_group]})


def Materiality_People_Plus_Prosperity_Action_SDG(action):
    """2 signals: material/immaterial People+Prosperity for ONE behavioural action.

    Same one-group People+Prosperity cut as Materiality_People_Plus_Prosperity_SDG (SDGs
    1-5, 8-11, 16, 17), restricted to a single action: the columns are
    ``material__<action>__SDG_n`` / ``immaterial__<action>__SDG_n`` rather than the
    ``__total__`` ones.

    Parameterised rather than written out once per action, for the same reason
    Materiality_SDG_X is: the column spelling and the signal naming then come from one
    place, and a new action needs no new function. `action` must be one of _SDG_ACTIONS;
    anything else raises rather than asking the merge for a column that was never loaded
    (which would hand every firm-year a NaN signal and empty the sort silently).

    One group, so signal_0 is that action's material share within People+Prosperity and
    signal_1 is its exact mirror (1 - signal_0) -- the same mirror-pair shape as the
    __total__ designs, so every one of these qualifies for the initiative-decomposition
    PDF and for minimum_initatives_needed_to_split_by_materiality.

    NAMING TRAP: ``advocacy_old_def`` is the advocacy leg of the ORIGINAL (pre-SDG-rework)
    "Matteo" 3-way split (advocacy_old_def / preparation / transformation);
    ``advocacy_new_def`` is the one from the newer 4-way split (adaptation /
    advocacy_new_def / innovation / upskilling). Both are real, different columns in the
    same workbook -- picking the wrong one sorts on a different quantity with no error.

    DENSITY VARIES ENORMOUSLY BY ACTION -- see the measured table in
    New_Pipeline/experiments.py::_register_pp_action_experiments. innovation is
    near-degenerate (81.6% of firm-years zero, 92 distinct signal values); advocacy_old_def
    is almost as usable as __total__. Always read the signal_sparsity audit before the alpha.

    ``action="total"`` is accepted and returns exactly what
    Materiality_People_Plus_Prosperity_SDG returns (same columns, same untagged names), so
    the two are interchangeable -- which is why no separate "pp_total" experiment is
    registered. Sort on signal_0 only.
    """
    return _signals_from_groups(
        {"People_Plus_Prosperity": PEOPLE_Plus_PROSPERITY_VS_PLANET["People_Plus_Prosperity"]},
        action=action,
    )


def Materiality_People_Plus_Prosperity_VS_Planet_SDG():
    """4 signals: Material_People_Plus_Prosperity, Immaterial_People_Plus_Prosperity,
    Material_Planet, Immaterial_Planet.

    PEOPLE_Plus_PROSPERITY_VS_PLANET is already {group: [sdg, ...]}, so it goes to
    _signals_from_groups bare -- wrapping it in braces builds a set holding a dict,
    which is a TypeError (dicts are unhashable).

    NOTE the denominator changes relative to Materiality_People_Plus_Prosperity_SDG.
    Both groups together cover all 17 SDGs, so with signal_denominator="Sum_All_Signals"
    sum_activities is every material+immaterial SDG count and signal_0 is
    "material People+Prosperity as a share of ALL initiatives", not "...of the firm's
    People+Prosperity initiatives". The four signals sum to 1 across the row, so no two
    of them are an exact mirror pair -- unlike the one-group designs above.
    """
    return _signals_from_groups(PEOPLE_Plus_PROSPERITY_VS_PLANET)


def Materiality_One_Health_SDGS():
    """2 signals: Material_One_Health, Immaterial_One_Health.

    Health_SDGS_Groups is already {group: [sdg, ...]}, so it goes to
    _signals_from_groups bare -- wrapping it in braces builds a set holding a dict,
    which is a TypeError (dicts are unhashable).
    """
    _group = "One_Health"
    return _signals_from_groups({_group: Health_SDGS_Groups[_group]})




def Materiality_One_Health_Ex_SDG_8_SDGS():
    """2 signals: Material_One_Health, Immaterial_One_Health.

    Health_SDGS_Groups is already {group: [sdg, ...]}, so it goes to
    _signals_from_groups bare -- wrapping it in braces builds a set holding a dict,
    which is a TypeError (dicts are unhashable).
    """
    _group = "One_Health_Ex_SDG_8"
    return _signals_from_groups({_group: Health_SDGS_Groups[_group]})




def Materiality_Narrow_Health_SDGS():
    """2 signals: Material_Narrow_Health, Immaterial_Narrow_Health.

    Health_SDGS_Groups is already {group: [sdg, ...]}, so it goes to
    _signals_from_groups bare -- wrapping it in braces builds a set holding a dict,
    which is a TypeError (dicts are unhashable).
    """
    _group = "Narrow_Health"
    return _signals_from_groups({_group: Health_SDGS_Groups[_group]})

def Materiality_Health_and_Work_SDGS():
    """2 signals: Material_Health_and_Work, Immaterial_Health_and_Work.

    Health_SDGS_Groups is already {group: [sdg, ...]}, so it goes to
    _signals_from_groups bare -- wrapping it in braces builds a set holding a dict,
    which is a TypeError (dicts are unhashable).
    """
    _group = "Health_and_Work"
    return _signals_from_groups({_group: Health_SDGS_Groups[_group]})












def Materiality_SDG_X(x):
    """2 signals: Material_SDG_<x>, Immaterial_SDG_<x> -- one SDG, material vs immaterial.

    Goes through _signals_from_groups rather than writing the dict by hand so the column
    spelling and the signal naming come from the same place as every other design here.
    Names come out "Material_SDG_5", matching the group naming
    CLIMATE_NATURAL_CAPITAL_VS_EACH_SDG already uses -- not the raw column name, which
    would put "material__total__SDG_5" into every portfolio label and parity artifact.

    Single group, so with signal_denominator="Sum_All_Signals" the denominator is this
    SDG's material + immaterial count: signal_0 is the SDG's material share and signal_1
    its exact mirror. Sort on signal_0 only.

    Raises on an SDG outside 1-17: the LC frame has no such column, so the merge would
    hand every firm-year a NaN signal and the sort would silently come back empty.
    """
    valid = {sdg for sdgs in SDG_5_BRACKETS.values() for sdg in sdgs}
    if x not in valid:
        raise ValueError(f"SDG {x!r} is not one of {sorted(valid)}")
    return _signals_from_groups({f"SDG_{x}": [x]})






def Materiality_Signals_5_groups_SDG_brackets():
    """10 signals: material/immaterial x the five SDG_BRACKETS."""
    return _signals_from_groups(SDG_5_BRACKETS)




def Materiality_Signals_Climate_Natural_Capital_vs_All_SDGS():
    """30 signals: material/immaterial x (Climate & Natural Capital, then SDGs 1-12/16/17
    each on its own — the 14 non-climate SDGs are NOT pooled)."""
    return _signals_from_groups(CLIMATE_NATURAL_CAPITAL_VS_EACH_SDG)







# The three SDG groups the behaviour designs below are cut on. A SUBSET of the group dicts
# re-exported at the top of this module, spelled out here because "All_SDGs" is not one of
# them -- PEOPLE_PLANET_PROSPERITY partitions the 17 into People/Prosperity/Planet, and the
# all-17 group is the union, which no dict there carries on its own.
_SDG_GROUPS = {
    "All_SDGs": list(range(1, 18)),
    "People":   PEOPLE_PLANET_PROSPERITY["People"],
    "Planet":   PEOPLE_PLANET_PROSPERITY["Planet"],
}


# The three behaviour taxonomies, as lists of WORKBOOK action names. Every entry is a key the
# materiality merge already selects per SDG, which is why all three are reachable without
# loading anything new -- including matteo3, whose buckets are defined over action x
# STAKEHOLDER upstream and have no per-SDG form anywhere in the LC panel.
#
# `pricing` is excluded from action13 to match the materiality sweep. CONSEQUENCE: the three
# taxonomies have DIFFERENT denominators under signal_denominator="Sum_All_Signals" --
# behavioural4 spans all 14 actions, action13 omits pricing, and matteo3 omits both pricing
# and association by construction upstream. Shares are comparable WITHIN a taxonomy, never
# across two of them.
#
# Declaration ORDER is load-bearing: node 07 uses the last signal in insertion order as the
# sort key for some audits, so reordering a list silently changes those tables.
BEHAVIOUR_TAXONOMIES = {
    "matteo3":      ["advocacy_old_def", "preparation", "transformation"],
    "behavioural4": ["advocacy_new_def", "upskilling", "adaptation", "innovation"],
    "action13":     [a for a in MATERIALITY_ACTION_TYPES if a != "pricing"],
}


def SDG_Behaviour_Signals(group, taxonomy):
    """One signal per behaviour within one SDG group — materiality SUMMED, not split.

    The companion to the Materiality_*_Action_SDG family: those ask "of this group's
    <behaviour> initiatives, what share is material?"; this asks "of this group's
    initiatives, what share is <behaviour>?". `group` is an _SDG_GROUPS key, `taxonomy` a
    BEHAVIOUR_TAXONOMIES key, so the nine designs are two strings apiece.

    HOW MATERIALITY IS REMOVED: both the material__ and immaterial__ columns of an action
    land on the SAME signal index, and node 02 sums every column sharing an index into
    sum_with_i. So no new column namespace and no new machinery -- the split is undone by
    where the columns point, not by reading somewhere else.

    WHY THE WORKBOOK AND NOT LC's OWN "<action> - SDG n" COLUMNS, which would need no
    materiality merge at all: matteo3 is unreachable from them. Its buckets are action x
    stakeholder, and LC's TYPE_SREC columns carry no SDG dimension -- that cube is a separate
    1,666-column file this repo never loads, whereas the workbook already carries
    advocacy_old_def/preparation/transformation per SDG, pre-aggregated upstream. The merge
    also costs nothing in sample here: it is an inner join, but the workbook covers 100% of
    LC firm-years on this vintage (72,412 -> 72,412), so these designs sit on exactly the
    sample the material-share designs sit on and the two sets of results are comparable.

    So add_materiality MUST still be True. The workbook is the DATA SOURCE here, not the
    split -- which is the one genuinely confusing thing about this design.

    NOT a materiality design by materiality_split_groups' definition: an index holding both
    prefixes is not wholly material, so it returns 0 groups. Everything materiality-flavoured
    downstream is therefore inert -- the decomposition PDF gate needs exactly 1 group and
    skips, and minimum_initatives_needed_to_split_by_materiality must stay 0.

    Excludes `unmapped__*__SDG_n` (~0.43% of initiatives), which the loader does not select.
    """
    if group not in _SDG_GROUPS:
        raise ValueError(f"group {group!r} is not one of {sorted(_SDG_GROUPS)}")
    if taxonomy not in BEHAVIOUR_TAXONOMIES:
        raise ValueError(f"taxonomy {taxonomy!r} is not one of {sorted(BEHAVIOUR_TAXONOMIES)}")

    categories, names = {}, []
    for action in BEHAVIOUR_TAXONOMIES[taxonomy]:
        index = len(names)
        names.append(f"{_action_tag(action)}_{group}")
        for materiality in ("material", "immaterial"):
            for sdg in _SDG_GROUPS[group]:
                categories[f"{materiality}__{action}__SDG_{sdg}"] = index
    return (categories, *names)


def Materiality_Action_Aggregate(action):
    """2 signals: Material_<Action>, Immaterial_<Action> — ONE action type, material vs immaterial.

    One level finer than the bucket designs: where material_4_Behavioural_Signals reads
    ``material__innovation`` (new products + r&d investments pooled), this reads
    ``material__new_products`` alone. ``action`` must be one of MATERIALITY_ACTION_TYPES.

    Reads the FLAT aggregate columns, so it deliberately does not go through
    _signals_from_groups -- that helper hardcodes the ``__SDG_{n}`` suffix. The per-SDG
    action columns exist in the same workbook but no design reads them yet.

    One group, so with signal_denominator="Sum_All_Signals" the denominator is this action's
    material + immaterial count: signal_0 is the action's material share and signal_1 its
    exact mirror (1 - signal_0). Sort on signal_0 only. Being a confirmed mirror pair with a
    single group, these qualify for minimum_initatives_needed_to_split_by_materiality.

    SPARSITY IS THE BINDING CONSTRAINT, worse here than anywhere else in this module. The
    measured BUCKET-level table in New_Pipeline/experiments.py::_register_pp_action_experiments
    already shows innovation at 81.6% of firm-years zero with a MEDIAN denominator of 1 — and
    that is two action types pooled. Every design here is strictly thinner than the bucket
    containing it, so several will be degenerate (a quantile sort that is mostly cutting ties).
    Read the signal_sparsity and materiality_split_floor audits before trusting any alpha.

    Raises on an unknown action rather than naming a column the materiality merge never
    selected -- that would merge as NaN and empty the sort with no error anywhere.
    """
    if action not in MATERIALITY_ACTION_TYPES:
        raise ValueError(
            f"action {action!r} is not one of {sorted(MATERIALITY_ACTION_TYPES)}"
        )
    tag = _action_tag(action)
    return (
        {f"material__{action}": 0, f"immaterial__{action}": 1},
        f"Material_{tag}",
        f"Immaterial_{tag}",
    )


def Materiality_Kevin4_Bucket(bucket):
    """2 signals: Material_Kevin4_<Bucket>, Immaterial_Kevin4_<Bucket> -- one Kevin4 bucket.

    The BUCKET-level sibling of ``Materiality_Action_Aggregate``: that reads ONE of the 14
    flat aggregate columns, this maps the several belonging to one KEVIN_4_BEHAVIOURS bucket
    onto one signal index and lets node 02 add them up (every column sharing an index is
    accumulated into ``sum_with_i`` there -- no arithmetic happens in this module).

    WHY THE 14 AND NOT THE PRE-AGGREGATED BUCKET COLUMNS. The workbook already ships
    ``material__advocacy_new_def`` / ``__upskilling`` / ``__adaptation`` / ``__innovation``,
    and ``material_4_Behavioural_Signals`` reads them -- but those bake in the Pre_Nikkei cut,
    which is NOT this one: volunteerism, assessment_and_measurement, organizational_structuring
    and pricing each sit in a different bucket here. Re-summing from the 14 is the only way to
    express the Kevin4 cut, and it is exact, because the 14 sum to ``__total`` by construction.

    FLAT columns, not the per-SDG cube, so like ``Materiality_Action_Aggregate`` this does not
    go through ``_signals_from_groups`` (that helper hardcodes the ``__SDG_{n}`` suffix). The
    denominator is therefore the bucket's whole material + immaterial count across every SDG,
    including initiatives the workbook mapped to no SDG at all.

    material is index 0 and immaterial index 1, not the other way round: ``net_materiality``
    requires signal_0 to be wholly material and signal_1 wholly immaterial, and checks it.

    ONE materiality_split_groups group (the two indices' stripped-suffix SETS are equal, one
    side wholly material and the other wholly immaterial), so signal_0 is the bucket's material
    share, signal_1 is its exact mirror (1 - signal_0), and both
    ``minimum_initatives_needed_to_split_by_materiality`` and ``net_materiality=True`` apply.
    Sort on signal_0 only.

    *** area_material_initatives_plots_per_signal_to_PDF MUST BE FORCED OFF ***, for the same
    reason ``Materiality_Action_Aggregate``'s factory forces it but via a DIFFERENT failure. It
    defaults True. Being exactly one confirmed mirror pair, node 07's decomposition gate OPENS
    and calls ``initiative_brackets.parse_numerator`` unguarded -- which raises
    ``numerator mixes actions [...]`` whenever the numerator names more than one action, and a
    Kevin4 bucket ALWAYS names between two and five. Every run would die at the final PDF.
    ``base_materiality_kevin4`` forces it False; pass True only once initiative_brackets learns
    to decompose a multi-action numerator.

    Signal names carry the ``Kevin4_`` tag for the reason the per-action designs carry an
    action tag: ``material_4_Behavioural_Signals`` already emits ``Material__Advocacy`` for the
    OTHER cut, and two designs emitting one name collide in portfolio labels and parity
    artifacts, where the later column silently overwrites the earlier.
    """
    if bucket not in KEVIN_4_BEHAVIOURS:
        raise ValueError(f"bucket {bucket!r} is not one of {sorted(KEVIN_4_BEHAVIOURS)}")

    categories = {}
    for index, materiality in ((0, "material"), (1, "immaterial")):
        for action in KEVIN_4_BEHAVIOURS[bucket]:
            categories[f"{materiality}__{action}"] = index
    return (
        categories,
        f"Material_Kevin4_{bucket}",
        f"Immaterial_Kevin4_{bucket}",
    )


def Combined_Material_Immaterial_4_Behavioural_Signals(signal_0_name="Immaterial__Advocacy", signal_1_name="Immaterial__Adaptation",
signal_2_name="Immaterial__Upskilling", signal_3_name="Immaterial__Innovation", signal_4_name="Material__Advocacy", signal_5_name="Material__Adaptation", 
signal_6_name="Material__Upskilling", signal_7_name="Material__Innovation"):
    return{

    

    "immaterial__advocacy_new_def": 0,
    "immaterial__adaptation": 1,
    "immaterial__upskilling":2,
    "immaterial__innovation": 3,

    "material__advocacy_new_def": 4,
    "material__adaptation": 5,
    "material__upskilling":6,
    "material__innovation": 7,

    }, signal_0_name, signal_1_name, signal_2_name, signal_3_name, signal_4_name, signal_5_name, signal_6_name, signal_7_name















def Combined_Material_Immaterial_3_Matteo_Signals(signal_0_name = "Immaterial__Advocacy", signal_1_name = "Immaterial__Preparation", 
signal_2_name = "Immaterial__Transformation", signal_3_name = "Material__Advocacy", signal_4_name = "Material__Preparation", 
signal_5_name = "Material__Transformation"):
    return{

    "immaterial__advocacy_old_def": 0, 
    "immaterial__preparation": 1, 
    "immaterial__transformation": 2,

    "material__advocacy_old_def": 3, 
    "material__preparation": 4, 
    "material__transformation": 5,

    }, signal_0_name, signal_1_name, signal_2_name, signal_3_name, signal_4_name, signal_5_name



#Extra singals::>>

def immaterial_4_Behavioural_Signals(signal_0_name="Immaterial__Advocacy", signal_1_name="Immaterial__Adaptation", 
signal_2_name="Immaterial__Upskilling", signal_3_name="Immaterial__Innovation"):
    return{

    "immaterial__advocacy_new_def": 0,
    "immaterial__adaptation": 1,
    "immaterial__upskilling":2,
    "immaterial__innovation": 3,

    }, signal_0_name, signal_1_name, signal_2_name, signal_3_name




def material_4_Behavioural_Signals(signal_0_name="Material__Advocacy", signal_1_name="Material__Adaptation",
signal_2_name="Material__Upskilling", signal_3_name="Material__Innovation"):
    return{

    "material__advocacy_new_def": 0,
    "material__adaptation": 1,
    "material__upskilling":2,
    "material__innovation": 3,

    }, signal_0_name, signal_1_name, signal_2_name, signal_3_name


def immaterial_3_Matteo_Signals(signal_0_name="Immaterial__Advocacy", signal_1_name= "Immaterial__Preparation", 
signal_2_name="Immaterial__Transformation"):
    return{

    "immaterial__advocacy_old_def": 0, 
    "immaterial__preparation": 1, 
    "immaterial__transformation": 2,

    }, signal_0_name, signal_1_name, signal_2_name


def material_3_Matteo_Signals(signal_0_name="Material__Advocacy", signal_1_name= "Material__Preparation", 
signal_2_name="Material__Transformation"):
    return{

    "material__advocacy_old_def": 0, 
    "material__preparation": 1, 
    "material__transformation": 2,

    }, signal_0_name, signal_1_name, signal_2_name





    

