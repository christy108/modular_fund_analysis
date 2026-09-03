
# Which SDGs sit in each group lives in signal_definitions.py, so the plain-SDG designs
# there and the material/immaterial ones here are cut from the same groups and can never
# drift apart. Change a split there, not here. Re-exported under the same names this
# module has always used.
from functions.signal_design.signal_definitions import (  # noqa: F401
    CLIMATE_NATURAL_CAPITAL_VS_EACH_SDG,
    PEOPLE_PLANET_PROSPERITY,
    PEOPLE_Plus_PROSPERITY_VS_PLANET,
    Health_SDGS_Groups,
    
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




# Which per-SDG ACTION families process_materiality.py brings onto lc. Kept in sync with
# MATERIALITY_SDG_ACTIONS there -- a design naming an action outside this set would ask for a
# column that was never loaded, and the sort would come back empty rather than raise.
_SDG_ACTIONS = ("adaptation", "advocacy_new_def", "advocacy_old_def", "innovation",
                "preparation", "transformation", "upskilling", "total")


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
    action_tag = "" if action == "total" else f"{action.replace('_', ' ').title().replace(' ', '_')}_"

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





    

