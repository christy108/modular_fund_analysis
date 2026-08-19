
# Which SDGs sit in each group lives in signal_definitions.py, so the plain-SDG designs
# there and the material/immaterial ones here are cut from the same groups and can never
# drift apart. Change a split there, not here. Re-exported under the same names this
# module has always used.
from functions.signal_design.signal_definitions import (  # noqa: F401
    CLIMATE_NATURAL_CAPITAL_VS_EACH_SDG,
    PEOPLE_PLANET_PROSPERITY,
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




def _signals_from_groups(groups):
    """Expand {group_name: [sdg, ...]} into ({lc_column: signal_index}, *signal_names).

    Every group yields two signals — material first, then immaterial — so indices
    run 0..2*len(groups)-1 in group order, matching the (dict, s0, s1, ...) tuple
    the callers unpack.

    Raises on an SDG listed in two groups: a duplicate dict key would silently keep the
    last write and leave the earlier group short (or empty), which is exactly the bug
    the hand-written versions of these dicts had.
    """
    _check_groups_disjoint(groups)

    categories = {}
    names = []
    for group_name, sdgs in groups.items():
        slug = _group_slug(group_name)
        for materiality in ("material", "immaterial"):
            index = len(names)
            names.append(f"{materiality.capitalize()}_{slug}")
            for sdg in sdgs:
                categories[f"{materiality}__total__SDG_{sdg}"] = index
    return (categories, *names)


def Materiality_Signals_3_groups_people_planet_prosperity_SDG():
    """6 signals: material/immaterial x People, Prosperity, Planet."""
    return _signals_from_groups(PEOPLE_PLANET_PROSPERITY)


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

    

    "immaterial__advocacy": 0, 
    "immaterial__adaptation": 1, 
    "immaterial__upskilling":2,
    "immaterial__innovation": 3,

    "material__advocacy": 4, 
    "material__adaptation": 5, 
    "material__upskilling":6,
    "material__innovation": 7,

    }, signal_0_name, signal_1_name, signal_2_name, signal_3_name, signal_4_name, signal_5_name, signal_6_name, signal_7_name



def immaterial_4_Behavioural_Signals(signal_0_name="Immaterial__Advocacy", signal_1_name="Immaterial__Adaptation", 
signal_2_name="Immaterial__Upskilling", signal_3_name="Immaterial__Innovation"):
    return{

    "immaterial__advocacy": 0, 
    "immaterial__adaptation": 1, 
    "immaterial__upskilling":2,
    "immaterial__innovation": 3,

    }, signal_0_name, signal_1_name, signal_2_name, signal_3_name




def material_4_Behavioural_Signals(signal_0_name="Material__Advocacy", signal_1_name="Material__Adaptation", 
signal_2_name="Material__Upskilling", signal_3_name="Material__Innovation"):
    return{

    "material__advocacy": 0, 
    "material__adaptation": 1, 
    "material__upskilling":2,
    "material__innovation": 3,

    }, signal_0_name, signal_1_name, signal_2_name, signal_3_name











def Combined_Material_Immaterial_3_Matteo_Signals(signal_0_name = "Immaterial__Advocacy", signal_1_name = "Immaterial__Preparation", 
signal_2_name = "Immaterial__Transformation", signal_3_name = "Material__Advocacy", signal_4_name = "Material__Preparation", 
signal_5_name = "Material__Transformation"):
    return{

    "immaterial__advocacy": 0, 
    "immaterial__preparation": 1, 
    "immaterial__transformation": 2,

    "material__advocacy": 3, 
    "material__preparation": 4, 
    "material__transformation": 5,

    }, signal_0_name, signal_1_name, signal_2_name, signal_3_name, signal_4_name, signal_5_name




def immaterial_3_Matteo_Signals(signal_0_name="Immaterial__Advocacy", signal_1_name= "Immaterial__Preparation", 
signal_2_name="Immaterial__Transformation"):
    return{

    "immaterial__advocacy": 0, 
    "immaterial__preparation": 1, 
    "immaterial__transformation": 2,

    }, signal_0_name, signal_1_name, signal_2_name


def material_3_Matteo_Signals(signal_0_name="Material__Advocacy", signal_1_name= "Material__Preparation", 
signal_2_name="Material__Transformation"):
    return{

    "material__advocacy": 0, 
    "material__preparation": 1, 
    "material__transformation": 2,

    }, signal_0_name, signal_1_name, signal_2_name





    

