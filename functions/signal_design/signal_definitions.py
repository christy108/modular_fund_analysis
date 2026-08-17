'''
Dictionary specifying types categories

Stakeholders:
  - customers
  - employees
  - enviroment
  - local communities and society
  - nothing
  - shareholders
  - suppliers
'''




# ---------------------------------------------------------------------------- #
# SDG groupings — the single source of truth for "which SDGs sit in which group".
#
# Both the plain-SDG signal designs below and the material/immaterial ones in
# signal_definitions_materiality.py are generated from these dicts, so editing a
# group here changes every design that uses it and the two families can never
# drift apart. To re-cut a split, edit only these dicts.
#
# The plain-SDG designs key on the LC columns 'SDG: 1' .. 'SDG: 17'; the materiality
# ones key on 'material__total__SDG_N' / 'immaterial__total__SDG_N'. Same groups,
# different column namespace.
# ---------------------------------------------------------------------------- #

PEOPLE_PLANET_PROSPERITY = {
    "People":     [1, 2, 3, 4, 5, 8, 10],
    "Prosperity": [9, 11, 16, 17],
    "Planet":     [6, 7, 12, 13, 14, 15],
}


SDG_5_BRACKETS = {
    "Social Equity & Inclusion":            [1, 2, 5, 10],
    "Human Development & Basic Needs":        [3, 4, 6, 7],
    "Sustainable Industry & Production":       [8, 9, 12],
    "Institutions & Communities":            [11, 16, 17],
    "Climate & Natural Capital":             [13, 14, 15],
}


def _one_group_vs_each_sdg(groups, group_name):
    """`group_name` kept as one group; every OTHER SDG becomes its own group.

    Both the focus group and the individual SDGs are derived from `groups`, so the
    split always covers exactly the same SDG universe as the dict it came from.
    """
    focus = groups[group_name]
    rest = sorted(sdg for sdgs in groups.values() for sdg in sdgs if sdg not in focus)
    return {group_name: focus, **{f"SDG_{sdg}": [sdg] for sdg in rest}}


CLIMATE_NATURAL_CAPITAL_VS_EACH_SDG = _one_group_vs_each_sdg(SDG_5_BRACKETS, "Climate & Natural Capital")


def _group_slug(group_name):
    return group_name.replace(" & ", "_").replace(" ", "_")


def _check_groups_disjoint(groups):
    """Raise if an SDG is listed in two groups.

    A duplicate SDG would become a duplicate dict key downstream, where the last write
    silently wins and leaves the earlier group short (or empty) — exactly the bug the
    hand-written versions of these dicts had.
    """
    seen = {}
    for group_name, sdgs in groups.items():
        for sdg in sdgs:
            if sdg in seen:
                raise ValueError(
                    f"SDG_{sdg} appears in both {seen[sdg]!r} and {group_name!r}; "
                    "each SDG must belong to exactly one group"
                )
            seen[sdg] = group_name
    return seen


def _sdg_signals_from_groups(groups):
    """Expand {group_name: [sdg, ...]} into ({'SDG: n': signal_index}, *signal_names).

    One signal per group — no material/immaterial doubling (that lives in
    signal_definitions_materiality.py). Indices run 0..len(groups)-1 in group order,
    matching the (dict, s0, s1, ...) tuple the callers unpack.
    """
    _check_groups_disjoint(groups)

    categories = {}
    names = []
    for group_name, sdgs in groups.items():
        index = len(names)
        names.append(_group_slug(group_name))
        for sdg in sdgs:
            categories[f"SDG: {sdg}"] = index
    return (categories, *names)


def dict_SDG_3_groups_people_planet_prosperity():
    """3 signals: People, Prosperity, Planet — no materiality split.

    Same SDG membership as `dict_all_SDG_1D`, but generated from
    PEOPLE_PLANET_PROSPERITY and therefore in that dict's order
    (People=0, Prosperity=1, Planet=2, vs people/planet/prosperity there) with
    capitalised names. `dict_all_SDG_1D` is left untouched for parity.
    """
    return _sdg_signals_from_groups(PEOPLE_PLANET_PROSPERITY)


def dict_SDG_5_groups_brackets():
    """5 signals: one per SDG_5_BRACKETS group — no materiality split."""
    return _sdg_signals_from_groups(SDG_5_BRACKETS)


def dict_SDG_Climate_Natural_Capital_vs_All_SDGS():
    """15 signals: Climate & Natural Capital as one group, then each of the 14
    non-climate SDGs on its own (NOT pooled) — no materiality split."""
    return _sdg_signals_from_groups(CLIMATE_NATURAL_CAPITAL_VS_EACH_SDG)


def dict_all_SDG_1D(signal_0_name="people", signal_1_name="planet", signal_2_name="prosperity"):
    return { 
        #people
        'SDG: 1': 0,
        'SDG: 2': 0,
        'SDG: 3': 0,
        'SDG: 4': 0, 

        'SDG: 5': 0,
        'SDG: 8': 0,
        'SDG: 10': 0,

        #planet
        'SDG: 6': 1,
        'SDG: 7': 1,
        'SDG: 12': 1,
        'SDG: 13': 1,

        'SDG: 14': 1,
        'SDG: 15': 1,  

        #prosperity
        'SDG: 9': 2,
        'SDG: 11': 2,
        
        'SDG: 16': 2,
        'SDG: 17': 2, 
    
    }, signal_0_name, signal_1_name, signal_2_name



# Matteo's original actions and stakeholders
def dict_2d_actions_stakeholders_original_matteo(signal_0_name="advocacy", signal_1_name="preparation", signal_2_name="transformation"):
    
    return{
        # 'TYPE: association': 0, 
        # 'TYPE: pricing': 2,                                                             # For our universe, these are usually discounts to disadvantaged customers
        'TYPE: donation & funding': 0, 
        'TYPE: volunteerism': 0, 
        'TYPE_SREC: communication - local communities and society': 0, 
        'TYPE_SREC: training - local communities and society': 0,                       # For our universe, these are usually akin to volunteering activities
        'TYPE_SREC: incentives - local communities and society': 0,                     # For our universe, these are usually `donation & funding` through vouchers etc.
        'TYPE_SREC: organizational structuring - local communities and society': 0, 

        'TYPE: adoption of standards and rules': 1, 
        'TYPE: assessment and measurement': 1,                                          # For our universe, these are mostly partnerships (e.g., with ONGs) for enviromental/social impact assessments
        'TYPE_SREC: communication - employees': 1, 
        'TYPE_SREC: training - employees': 1, 
        'TYPE_SREC: incentives - employees': 1, 
        'TYPE_SREC: organizational structuring - employees': 1, 

        'TYPE: asset modification': 2,
        'TYPE: modification of procedures': 2, 
        'TYPE: new products': 2, 
        'TYPE: r&d investments': 2, 
        'TYPE_SREC: communication - customers': 2, 
        'TYPE_SREC: communication - shareholders': 2, 
        'TYPE_SREC: communication - suppliers': 2, 
        'TYPE_SREC: training - customers': 2, 
        'TYPE_SREC: training - shareholders': 2, 
        'TYPE_SREC: training - suppliers': 2, 
        'TYPE_SREC: incentives - customers': 2, 
        'TYPE_SREC: incentives - shareholders': 2, 
        'TYPE_SREC: incentives - suppliers': 2, 
        'TYPE_SREC: organizational structuring - customers': 2, 
        'TYPE_SREC: organizational structuring - shareholders': 2, 
        'TYPE_SREC: organizational structuring - suppliers': 2, 
    }, signal_0_name, signal_1_name, signal_2_name




#
# Sectors, then Stakeholders (alphas)
def dict_all_SDG_1D_prosperity_into_people(signal_0_name="people plus prosperity", signal_1_name="planet"):
    """
    SDG grouping for the first Social Impact

    Difference from dict_all_SDG_1D:
      - SDG 9, 11, 16, and 17 are moved from prosperity into people.
      - Planet stays unchanged.
      - The function returns two active signals, so it will produce:
          High people plus prosperity
          Low people plus prosperity
          High planet
          Low planet
    """
    return {
        # people plus prosperity
        'SDG: 1': 0,
        'SDG: 2': 0,
        'SDG: 3': 0,
        'SDG: 4': 0,
        'SDG: 5': 0,
        'SDG: 8': 0,
        'SDG: 10': 0,

        # former prosperity SDGs moved into people
        'SDG: 9': 0,
        'SDG: 11': 0,
        'SDG: 16': 0,
        'SDG: 17': 0,

        # planet
        'SDG: 6': 1,
        'SDG: 7': 1,
        'SDG: 12': 1,
        'SDG: 13': 1,
        'SDG: 14': 1,
        'SDG: 15': 1,
    }, signal_0_name, signal_1_name




def dict_4_signals_Action_1D_Pre_Nikkei(signal_0_name="Advocacy", signal_1_name="Upskilling", signal_2_name="Adaptation-change", signal_3_name="Innovation"):
    return{
    
    "TYPE: donation & funding": 0, 
    "TYPE: communication": 0, 
    "TYPE: association": 0, 

    
    "TYPE: training": 1, 
    "TYPE: volunteerism": 1, 


    "TYPE: adoption of standards and rules": 2, 
    "TYPE: assessment and measurement": 2, 
    "TYPE: incentives": 2, 
    "TYPE: organizational structuring": 2, 
    "TYPE: asset modification": 2, 
    "TYPE: modification of procedures": 2, 
   


    "TYPE: new products": 3, 
    "TYPE: r&d investments": 3, 

    }, signal_0_name, signal_1_name, signal_2_name, signal_3_name


    

def dict_4_stakeholder_signals_Pre_Nikkei(signal_0_name="communities", signal_1_name="employees", signal_2_name="suppliers", signal_3_name="customers"):
    return {"SREC: local communities and society": 0,
            "SREC: employees": 1,
            "SREC: suppliers": 2,
            "SREC: customers": 3,
            }, signal_0_name, signal_1_name, signal_2_name, signal_3_name




