# -*- coding: utf-8 -*-

import matplotlib.pyplot as plt
import seaborn as sns
from electricitylci.aggregation_selector import subregion_col
import electricitylci.analysis.utils as an_util



def impact_plot_comparison(df,fuelcat="all",subregion="BA"):
    cat_column = subregion_col(subregion)
    fuelcat="OIL"
    if fuelcat is not "all":
        df_red=df.loc[df["FuelCategory"]==fuelcat,:].copy()
    else:
        df_red=df.copy()
    df_generic = an_util.apply_generic_stage_names(df_red)
    df_generic["generic_stage_name"]=df_generic["generic_stage_name"].astype('category')
    df_generic["FuelCategory"]=df_generic["FuelCategory"].astype('category')
    df_generic_grouped = df_generic.groupby(by=cat_column+["FuelCategory","generic_stage_name"],as_index=False)["impact_emission_factor"].sum()
#    df_generic_grouped.sort_values(by=cat_column+["FuelCategory","generic_stage_name"],inplace=True)
    width = int(df_generic_grouped[cat_column].nunique().values*0.5)
    df_generic_grouped.set_index(pd.MultiIndex.from_frame(df_generic_grouped[cat_column+["FuelCategory"]]),inplace=True)
    df_generic_grouped.drop(columns=cat_column+["FuelCategory"],inplace=True)
#    impact_plot=df_generic_grouped.plot(y="impact_emission_factor",kind="bar",stacked=True,figsize=(width,10),label="generic_stage_name",hue="generic_stage_name")
#    impact_plot=df_generic_grouped.plot(kind="bar",stacked=True,figsize=(width,10))
#    sns.barplot(x=) 
#    blah=df_generic_grouped.piv
    df_generic_grouped=df_generic_grouped.pivot(columns="generic_stage_name")
    df_generic_grouped.columns = df_generic_grouped.columns.droplevel()
    sns.set()
    impact_plot=df_generic_grouped.plot(kind="bar",stacked=True,figsize=(width,10))