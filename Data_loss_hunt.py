def _checkpoint(df: pd.DataFrame, label: str) -> None:
    dmin = pd.to_datetime(df["date"], errors="coerce").min() if "date" in df.columns else None
    dmax = pd.to_datetime(df["date"], errors="coerce").max() if "date" in df.columns else None
    print(f"[{label}] rows={len(df):,}  min_date={dmin}  max_date={dmax}")
    for c in ["tri", "rfyear", "curcdd", "Industry", "loc", "MacroRegion", "sum_activities"]:
        if c in df.columns:
            print(f"  - {c}: null_rate={df[c].isna().mean():.3f}")


_checkpoint(global_universe, "START")

# Compute intersection of gvkeys
lc_gvkey = lc["gvkey"].unique()
global_universe_gvkey = global_universe["gvkey"].unique()
lc_global_universe_mapping = np.intersect1d(lc_gvkey, global_universe_gvkey)

# Limit focus on the gvkeys in `lc`
global_universe = global_universe[global_universe["gvkey"].isin(lc_global_universe_mapping)]
_checkpoint(global_universe, "after gvkey intersection filter")

# Join
global_universe = pd.merge(
    global_universe,
    lc[[
        "gvkey",
        "rfyear",
        "MacroRegion",
        "loc",
        "Industry",
        "signal_0",
        "signal_1",
        "signal_2",
        "sum_activities",
    ] + sorted(categories_dict.keys())],
    left_on=["gvkey", "last_year"],
    right_on=["gvkey", "rfyear"],
    how="left",
)
_checkpoint(global_universe, "after merge with lc")

# Generate single issues identifier
global_universe["gvkey_iid"] = global_universe["gvkey"].astype(str) + "_" + global_universe["iid"].astype(str)

# Sort the DataFrame by 'gvkey_iid' and 'date'
global_universe = global_universe.sort_values(by=["gvkey_iid", "date"])

# Drop rows with invalid dates if any
global_universe.dropna(subset=["date", "tri"], inplace=True)
_checkpoint(global_universe, "after dropna(date, tri)")

# Create new columns for year and month
global_universe["year"] = global_universe["date"].dt.year
global_universe["month"] = global_universe["date"].dt.month

# Group by 'year' and 'month' and get the last date for each group
last_dates = global_universe.groupby(["year", "month"])["date"].last().reset_index()

# Merge this result back to the original DataFrame
global_universe = global_universe.merge(last_dates, on=["year", "month"], suffixes=("", "_last"))

# Assign the last trading day for each (year, month) pair to the original 'date' column
global_universe["date"] = global_universe["date_last"]

# Drop the temporary 'date_last' column
global_universe.drop(columns=["date_last"], inplace=True)

# Convert to monthly frequency
global_universe = global_universe.groupby(["gvkey_iid", "year", "month"]).last().reset_index()
_checkpoint(global_universe, "after monthly last() aggregation")

# Apply the function to each group
global_universe = global_universe.groupby("gvkey_iid").apply(conditional_pct_change).reset_index(drop=True)
_checkpoint(global_universe, "after conditional_pct_change")

# Standardise actions
global_universe[sorted(categories_dict.keys())] = global_universe[sorted(categories_dict.keys())].div(
    global_universe["sum_activities"], axis=0
)

# Get final data for descriptive figures
global_universe.to_csv('./descriptives/global_universe_' + res_suffix + '.csv', index=False)
"""
# Remove companies domiciled outside the Eurozone or the USA
global_universe = global_universe[~global_universe['loc'].isin(['CAN', 'CHE', 'GBR'])]

# Remove foreign listed companies
foreign_listed  = (global_universe['MacroRegion'] == 'Europe') & (global_universe['curcdd'] != 'EUR')
foreign_listed |= (global_universe['MacroRegion'] == 'United States and Canada') & (global_universe['curcdd'] != 'USD')
global_universe = global_universe[~foreign_listed]
"""

# Setup standardization
cols_standardization = ['rfyear', 'curcdd', 'Industry']

# Remove entries without enough data to zscore signals
global_universe.dropna(subset=cols_standardization, inplace=True)
_checkpoint(global_universe, "after dropna(standardization cols)")

# Relevant pivot tables
print("Pivot Tables!")
global_returns   = global_universe.pivot(index='date', columns='gvkey_iid', values='tr')
global_signal_0  = global_universe.pivot(index='date', columns='gvkey_iid', values='signal_0')
global_signal_1  = global_universe.pivot(index='date', columns='gvkey_iid', values='signal_1')
global_signal_2  = global_universe.pivot(index='date', columns='gvkey_iid', values='signal_2')
#global_emissions = global_universe.pivot(index='date', columns='gvkey_iid', values='scope1_abs')
#global_ros_data  = global_universe.pivot(index='date', columns='gvkey_iid', values='ros0')
#global_esg = global_universe.pivot(index='date', columns='gvkey_iid', values='esg')
#global_ros_beta  = global_ros_data.apply(
    # lambda y: rolling_regressions(
    #     y.diff(), 
    #     pd.DataFrame([]), 
    #     global_signal_2[y.name].to_frame().diff(), 
    #     1, 
    #     60, # 24 to 60 months as in FF92
    # ),
#     axis=0
# )