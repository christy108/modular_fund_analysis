


def dict_4_signals_Action_1D_Pre_Nikkei_Employees(signal_0_name="Advocacy_employees", signal_1_name="Upskilling_employees", signal_2_name="Adaptation-change_employees", signal_3_name="Innovation_employees"):
    return{
    
    "TYPE_SREC: donation & funding - employees": 0, 
    "TYPE_SREC: communication - employees": 0, 
    "TYPE_SREC: association - employees": 0, 

    
    "TYPE_SREC: training - employees": 1, 
    "TYPE_SREC: volunteerism - employees": 1,    


    "TYPE_SREC: adoption of standards and rules - employees": 2, 
    "TYPE_SREC: assessment and measurement - employees": 2, 
    "TYPE_SREC: incentives - employees": 2, 
    "TYPE_SREC: organizational structuring - employees": 2, 
    "TYPE_SREC: asset modification - employees": 2, 
    "TYPE_SREC: modification of procedures - employees": 2, 
   


    "TYPE_SREC: new products - employees": 3, 
    "TYPE_SREC: r&d investments - employees": 3, 

    }, signal_0_name, signal_1_name, signal_2_name, signal_3_name



def dict_4_signals_Action_1D_Pre_Nikkei_Customers(signal_0_name="Advocacy_customers", signal_1_name="Upskilling_customers", signal_2_name="Adaptation-change_customers", signal_3_name="Innovation_customers"):
    return{
    
    "TYPE_SREC: donation & funding - customers": 0, 
    "TYPE_SREC: communication - customers": 0, 
    "TYPE_SREC: association - customers": 0, 

    
    "TYPE_SREC: training - customers": 1, 
    "TYPE_SREC: volunteerism - customers": 1,    


    "TYPE_SREC: adoption of standards and rules - customers": 2, 
    "TYPE_SREC: assessment and measurement - customers": 2, 
    "TYPE_SREC: incentives - customers": 2, 
    "TYPE_SREC: organizational structuring - customers": 2, 
    "TYPE_SREC: asset modification - customers": 2, 
    "TYPE_SREC: modification of procedures - customers": 2, 
   


    "TYPE_SREC: new products - customers": 3, 
    "TYPE_SREC: r&d investments - customers": 3, 

    }, signal_0_name, signal_1_name, signal_2_name, signal_3_name




def dict_4_signals_Action_1D_Pre_Nikkei_Suppliers(signal_0_name="Advocacy_suppliers", signal_1_name="Upskilling_suppliers", signal_2_name="Adaptation-change_suppliers", signal_3_name="Innovation_suppliers"):
    return{
    
    "TYPE_SREC: donation & funding - suppliers": 0, 
    "TYPE_SREC: communication - suppliers": 0, 
    "TYPE_SREC: association - suppliers": 0, 

    
    "TYPE_SREC: training - suppliers": 1, 
    "TYPE_SREC: volunteerism - suppliers": 1,    


    "TYPE_SREC: adoption of standards and rules - suppliers": 2, 
    "TYPE_SREC: assessment and measurement - suppliers": 2, 
    "TYPE_SREC: incentives - suppliers": 2, 
    "TYPE_SREC: organizational structuring - suppliers": 2, 
    "TYPE_SREC: asset modification - suppliers": 2, 
    "TYPE_SREC: modification of procedures - suppliers": 2, 
   


    "TYPE_SREC: new products - suppliers": 3, 
    "TYPE_SREC: r&d investments - suppliers": 3, 

    }, signal_0_name, signal_1_name, signal_2_name, signal_3_name


def dict_4_signals_Action_1D_Pre_Nikkei_Shareholders(signal_0_name="Advocacy_shareholders", signal_1_name="Upskilling_shareholders", signal_2_name="Adaptation-change_shareholders", signal_3_name="Innovation_shareholders"):
    return{
    
    "TYPE_SREC: donation & funding - shareholders": 0, 
    "TYPE_SREC: communication - shareholders": 0, 
    "TYPE_SREC: association - shareholders": 0, 

    
    "TYPE_SREC: training - shareholders": 1, 
    "TYPE_SREC: volunteerism - shareholders": 1,    


    "TYPE_SREC: adoption of standards and rules - shareholders": 2, 
    "TYPE_SREC: assessment and measurement - shareholders": 2, 
    "TYPE_SREC: incentives - shareholders": 2, 
    "TYPE_SREC: organizational structuring - shareholders": 2, 
    "TYPE_SREC: asset modification - shareholders": 2, 
    "TYPE_SREC: modification of procedures - shareholders": 2, 
   


    "TYPE_SREC: new products - shareholders": 3, 
    "TYPE_SREC: r&d investments - shareholders": 3, 

    }, signal_0_name, signal_1_name, signal_2_name, signal_3_name


def dict_4_signals_Action_1D_Pre_Nikkei_Local_Communities_and_Society(signal_0_name="Advocacy_local_communities_and_society", signal_1_name="Upskilling_local_communities_and_society", signal_2_name="Adaptation-change_local_communities_and_society", signal_3_name="Innovation_local_communities_and_society"):
    return{
    
    "TYPE_SREC: donation & funding - local communities and society": 0, 
    "TYPE_SREC: communication - local communities and society": 0, 
    "TYPE_SREC: association - local communities and society": 0, 

    
    "TYPE_SREC: training - local communities and society": 1, 
    "TYPE_SREC: volunteerism - local communities and society": 1,    


    "TYPE_SREC: adoption of standards and rules - local communities and society": 2, 
    "TYPE_SREC: assessment and measurement - local communities and society": 2, 
    "TYPE_SREC: incentives - local communities and society": 2, 
    "TYPE_SREC: organizational structuring - local communities and society": 2, 
    "TYPE_SREC: asset modification - local communities and society": 2, 
    "TYPE_SREC: modification of procedures - local communities and society": 2, 
   

    "TYPE_SREC: new products - local communities and society": 3, 
    "TYPE_SREC: r&d investments - local communities and society": 3, 

    }, signal_0_name, signal_1_name, signal_2_name, signal_3_name





if action_characterization == "4_signals_Pre_Nikkei_Employees":
    categories_dict, signal_0_name, signal_1_name, signal_2_name, signal_3_name = dict_4_signals_Action_1D_Pre_Nikkei_Employees()
    lc_signals = {
        "signal_0": signal_0_name,
        "signal_1": signal_1_name,
        "signal_2": signal_2_name,
        "signal_3": signal_3_name,
    }

elif action_characterization == "4_signals_Pre_Nikkei_Suppliers":
    categories_dict, signal_0_name, signal_1_name, signal_2_name, signal_3_name = dict_4_signals_Action_1D_Pre_Nikkei_Suppliers()
    lc_signals = {
        "signal_0": signal_0_name,
        "signal_1": signal_1_name,
        "signal_2": signal_2_name,
        "signal_3": signal_3_name,
    }

elif action_characterization == "4_signals_Pre_Nikkei_Local_Communities_and_Society":
    categories_dict, signal_0_name, signal_1_name, signal_2_name, signal_3_name = dict_4_signals_Action_1D_Pre_Nikkei_Local_Communities_and_Society()
    lc_signals = {
        "signal_0": signal_0_name,
        "signal_1": signal_1_name,
        "signal_2": signal_2_name,
        "signal_3": signal_3_name,
    }  

elif action_characterization == "4_signals_Pre_Nikkei_Shareholders":
    categories_dict, signal_0_name, signal_1_name, signal_2_name, signal_3_name = dict_4_signals_Action_1D_Pre_Nikkei_Shareholders()
    lc_signals = {
        "signal_0": signal_0_name,
        "signal_1": signal_1_name,
        "signal_2": signal_2_name,
        "signal_3": signal_3_name,
    }

elif action_characterization == "4_signals_Pre_Nikkei_Customers":
    categories_dict, signal_0_name, signal_1_name, signal_2_name, signal_3_name = dict_4_signals_Action_1D_Pre_Nikkei_Customers()
    lc_signals = {
        "signal_0": signal_0_name,
        "signal_1": signal_1_name,
        "signal_2": signal_2_name,
        "signal_3": signal_3_name,
    }


