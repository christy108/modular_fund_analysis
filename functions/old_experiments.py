

def base_none_all_firms():
    # base_none, but the universe retains securities that are INACTIVE as of the Compustat
    # extract date (secstat != 'A') instead of dropping their entire price history. The
    # survivorship arm to compare against base_none.
    #
    # Reads the same on-disk extract as base_none -- one download, filtered in memory --
    # so the two arms cannot differ by data vintage, only by the filter. Removes the
    # whole-firm erasure channel only: cshtrd/exchg still eject a surviving firm's worst
    # months, and Compustat carries no delisting return, so terminal losses are still
    # missing from both arms.
    #
    # Expect: more listings per currency-month pre-screen, weaker long-leg alpha, and a
    # materially worse short leg. Per-region kept/dropped counts land in
    # runs/<ts>_base_none_all_firms/debug_prints.log.
    return make_experiment("base_none_all_firms",
                           build_cfg(security_status="all_firms_even_delisted"))







#4
def base_none_v_2A1_percent_stocks_5_100M_floor(): #  market_cap_filter="percent_total_mcap",   # or "percent_stocks"
    return make_experiment("base_none_v_2A1_percent_stocks_5_100M_floor", build_cfg(golden_data = "v_2A1", market_cap_filter="percent_stocks", 
    percentage_stocks_removed_if_percent_stocks_true=0.05, floor_if_percent_stocks_true=100e6))

def base_none_v_2A1_percent_stocks_20_100M_floor(): #  market_cap_filter="percent_total_mcap",   # or "percent_stocks"
    return make_experiment("base_none_v_2A1_percent_stocks_20_100M_floor", build_cfg(golden_data = "v_2A1", market_cap_filter="percent_stocks", 
    percentage_stocks_removed_if_percent_stocks_true=0.2, floor_if_percent_stocks_true=100e6))

def base_none_v_2A1_percent_stocks_50_200M_floor(): #  market_cap_filter="percent_total_mcap",   # or "percent_stocks"
    return make_experiment("base_none_v_2A1_percent_stocks_50_200M_floor", build_cfg(golden_data = "v_2A1", market_cap_filter="percent_stocks", 
    percentage_stocks_removed_if_percent_stocks_true=0.5, floor_if_percent_stocks_true=200e6))





def base_none_v_2A1_no_mcap_filter_no_3filter(): 
    return make_experiment("base_none_v_2A1_no_mcap_filter_no_3filter", build_cfg(golden_data = "v_2A1", 
    mktcap_covered_if_filter_by_cum_market_cap = 1, execute_3_filters = False,
     market_cap_filter="percent_total_mcap"))





def base_none_v_2A1_no_3filter_with_delisted_firms(): 
    return make_experiment("base_none_v_2A1_no_3filter_with_delisted_firms", build_cfg(golden_data = "v_2A1", execute_3_filters = False,
     market_cap_filter="percent_total_mcap",  security_status="all_firms_even_delisted"))


def base_none_v_2A1_no_mcap_filter_with_delisted_firms(): 
    return make_experiment("base_none_v_2A1_no_mcap_filter_with_delisted_firms", build_cfg(golden_data = "v_2A1", 
    mktcap_covered_if_filter_by_cum_market_cap = 1,
     market_cap_filter="percent_total_mcap",   security_status="all_firms_even_delisted" ))




def base_none_v_2A1_no_mcap_filter_no_3filter_with_delisted_firms_q10(): 
    return make_experiment("base_none_v_2A1_no_mcap_filter_no_3filter_with_delisted_firms", build_cfg(golden_data = "v_2A1", 
    mktcap_covered_if_filter_by_cum_market_cap = 1, execute_3_filters = False,
     market_cap_filter="percent_total_mcap",   security_status="all_firms_even_delisted", no_simple_quantiles = 10 ))


def base_none_v_2A1_no_mcap_filter_no_3filter_with_delisted_firms_q5(): 
    return make_experiment("base_none_v_2A1_no_mcap_filter_no_3filter_with_delisted_firms", build_cfg(golden_data = "v_2A1", 
    mktcap_covered_if_filter_by_cum_market_cap = 1, execute_3_filters = False,
     market_cap_filter="percent_total_mcap",   security_status="all_firms_even_delisted", no_simple_quantiles = 5 ))





def base_none_v_2A1_no_mcap_filter_no_3filter_with_delisted_firms(): 
    return make_experiment("base_none_v_2A1_no_mcap_filter_no_3filter_with_delisted_firms", build_cfg(golden_data = "v_2A1", 
    mktcap_covered_if_filter_by_cum_market_cap = 1, execute_3_filters = False,
     market_cap_filter="percent_total_mcap",   security_status="all_firms_even_delisted" ))






def esg_refinitiv():
    return make_experiment("esg_refinitiv", build_cfg(esg_choice="refinitiv"))


def esg_msci():
    return make_experiment("esg_msci", build_cfg(esg_choice="msci"))


def esg_snp():
    return make_experiment("esg_snp", build_cfg(esg_choice="s&p"))


def esg_full_universe():
    return make_experiment("esg_full_universe", build_cfg(esg_full_universe=True, esg_choice="msci"))


def show_corr():
    return make_experiment(
        "show_corr", build_cfg(esg_choice="refinitiv", show_esg_corr_matricies=True, show_esg_coverage=True)
    )
