
# People vs Planet SDGs
categories_dict_sdgs = {
  'SDG: 1': 0,
  'SDG: 2': 0,
  'SDG: 3': 0,
  'SDG: 4': 0,
  'SDG: 5': 0,
  'SDG: 8': 0,
  'SDG: 10': 0,
  'SDG: 6': 1,
  'SDG: 7': 1,
  'SDG: 12': 1,
  'SDG: 13': 1,
  'SDG: 14': 1,
  'SDG: 15': 1,

  'SDG: 9': 2,
  'SDG: 11': 2,
  'SDG: 16': 2,
  'SDG: 17': 2,
}




#####THIS FILE IS OUTDATED######
#"FOR NOTHING --- GET most recent file from sdg investigation branch"

def people_vs_planet(categories_dict_actions):

    # Initialise dictionary
    all_sdgs_dict = {}
    categories_dict_people = {}
    categories_dict_planet = {}
    categories_dict_prosperity = {}

    # Initialise other dictionaries
    categories_dict_people_advocacy = {}
    categories_dict_planet_advocacy = {}
    categories_dict_prosperity_advocacy = {}
    all_sdgs_dict_advocacy = {}

    # Loop over actions
    for key_action, value_action in categories_dict_actions.items():

        # Loop over sdgs
        for key_sdg, value_sdg in categories_dict_sdgs.items():
            
            #Build: "<action> - SDG X - <stakeholder>", where stakeholder defaults to "nothing"
            raw = (key_action.strip().lower().replace("type_srec:", "").replace("type:", "")).strip()
            if " - " in raw:
                action, stakeholder = raw.rsplit(" - ", 1)
                action = action.strip()
                stakeholder = stakeholder.strip() or "nothing"
            else:
                action = raw
                stakeholder = "nothing"
            sdg = key_sdg.replace(":", "").strip()  # "SDG: 1" -> "SDG 1"
            label = f"{action} - {sdg} - {stakeholder}"


            all_sdgs_dict[label] = value_action
            all_sdgs_dict_advocacy[label] = 2 - value_action

            if value_sdg == 1:
                #print(key_action)
                categories_dict_planet[label] = value_action
                categories_dict_planet_advocacy[label] = 2 - value_action
            elif value_sdg == 0:
                categories_dict_people[label] = value_action
                categories_dict_people_advocacy[label] = 2 - value_action

            elif value_sdg == 2:
                categories_dict_prosperity[label] = value_action
                categories_dict_people_advocacy[label] = 2 - value_action

    return categories_dict_people, categories_dict_planet, categories_dict_people_advocacy, categories_dict_planet_advocacy, categories_dict_prosperity, categories_dict_prosperity_advocacy, all_sdgs_dict, all_sdgs_dict_advocacy