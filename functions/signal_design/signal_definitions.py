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



def dict_5_signals_Action_1D_Moji(signal_0_name="Advocacy", signal_1_name="Upskilling", signal_2_name="Measurement", signal_3_name="Adaptation-change", signal_4_name="Innovation"):
    return{
    
    "TYPE: donation & funding": 0, 
    "TYPE: communication": 0, 
    "TYPE: association": 0, 

    "TYPE: incentives": 1, 
    "TYPE: training": 1, 
    "TYPE: volunteerism": 1, 


    "TYPE: adoption of standards and rules": 2, 
    "TYPE: assessment and measurement": 2, 
    


    "TYPE: organizational structuring": 3, 
    "TYPE: asset modification": 3, 
    "TYPE: modification of procedures": 3, 
    "TYPE: pricing": 3, 


    "TYPE: new products": 4, 
    "TYPE: r&d investments": 4, 

    }, signal_0_name, signal_1_name, signal_2_name, signal_3_name, signal_4_name




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



# def dict_5_stakeholder_signals_Pre_Nikkei(signal_0_name="communities", signal_1_name="employees", signal_2_name="suppliers", signal_3_name="shareholders", signal_4_name="customers"):
#     return {"SREC: local communities and society": 0,
#             "SREC: employees": 1,
#             "SREC: suppliers": 2,
#             "SREC: shareholders": 3,
#             "SREC: customers": 4,
#             }, signal_0_name, signal_1_name, signal_2_name, signal_3_name, signal_4_name


def dict_4_stakeholder_signals_Pre_Nikkei(signal_0_name="communities", signal_1_name="employees", signal_2_name="suppliers", signal_3_name="customers"):
    return {"SREC: local communities and society": 0,
            "SREC: employees": 1,
            "SREC: suppliers": 2,
            "SREC: customers": 3,
            }, signal_0_name, signal_1_name, signal_2_name, signal_3_name

def test_multiple_signals(signal_0_name="advocacy", signal_1_name="preparation", signal_2_name="transformation", signal_3_name="pricing"):
    
    return{
        # 'TYPE: association': 0, 
        #'TYPE: pricing': 3,                                                             # For our universe, these are usually discounts to disadvantaged customers
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
    }, signal_0_name, signal_1_name, signal_2_name, signal_3_name