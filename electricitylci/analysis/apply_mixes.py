# -*- coding: utf-8 -*-
"""
This module applies different mixes to an already aggregated dataframe
so that emission factors are scaled according to their contribution to that mix.
"""
import pandas as pd
from electricitylci.aggregation_selector import subregion_col

def apply_generation_mix(genmix_df,agg_df,subregion="BA"):
    """
    Apply a generation mix to an aggregated dataframe. The resulting dataframe
    will have emission factors that are scaled according to their contribution
    to that regions electricity generation mix.
    
    Parameters
    ----------
    genmix_df : dataframe
        This is the dataframe that contains the generation mix - fractions of
        each type of fuel category that contribute to 1 MWh of that regions
        electricity.
    agg_df : dataframe
        An aggregated dataframe that will serve as the source of existing emission
        factors that are on the basis of 1MWh. The emissions factor column
        in this database will be modified according to the fraction of generation
        from the associated fuel category.

    subregion : str, optional
        The region the passed dataframe is aggregated to, by default "BA".

    Returns
    -------
    dataframe
        A dataframe with the emission factors scaled such that each region
        produces 1 MWh total electricity from all associated fuel categories.
    """
    cat_column = subregion_col(subregion)
    print(cat_column)
    if cat_column is not None:
        agg_genmix_df=pd.merge(
                left=agg_df,
                right = genmix_df[["Subregion","FuelCategory","Generation_Ratio"]],
                left_on=cat_column+["FuelCategory"],
                right_on=["Subregion","FuelCategory"],
                how="left")
        agg_genmix_df.drop(columns=["Subregion"],inplace=True)
    else:
        agg_genmix_df=pd.merge(
                left=agg_df,
                right=genmix_df[["FuelCategory","Generation_Ratio"]],
                on=["FuelCategory"],
                how="left")
    agg_genmix_df["Emission_factor"]=agg_genmix_df["Emission_factor"]*agg_genmix_df["Generation_Ratio"]
    return agg_genmix_df

def apply_consumption_mix(consmix_df,genmix_agg_df,subregion="BA",target_regions=[]):
    """
    Apply a consumption mix to an aggregated dataframe. The resulting dataframe
    will have emission factors that are scaled according to their contribution
    to that regions electricity consumption mix.
    
    Parameters
    ----------
    consmix_df : dataframe
        This is the dataframe that contains the consumption mix - providing the fraction of
        1 MWh that each region supplies to other regions' electricity mix.
    
    genmix_agg_df : dataframe
        An aggregated dataframe that will serve as the source of generation mix emission
        factors that are on the basis of 1MWh supplied by the mix. The emissions factor column
        in this database will be modified according to the fraction of consumption
        for that region's generation mix.

    subregion : str, optional
        The region the passed dataframe is aggregated to, by default "BA".
    
    target_regions: list, optional
        The specific regions to calculate the consumption mix for. If none are
        provided, this function calculates the consumption mix for all regions
    
    Returns
    -------
    dictionary
        A dictionary containing a dataframe for all regions with the region
        name as the dictionary key for each region or a dictionary with only
        emissions for the specified target_region(s). Each dataframe contains
        only those regions with non-zero contributions to the consumption mix.
    """
    cat_column = subregion_col("BA")[0]
    if subregion=="BA":
        import_col="import_name"
        export_col="export_name"
    elif subregion=="FERC":
        import_col="import ferc region"
        export_col="export_name"
    elif subregion=="US":
        export_col="export_name"
        consmix_df["import_name"]="US"
        import_col="import_name"
    if target_regions==[]:
        target_regions=consmix_df[import_col].unique()
    cons_mixes_dict={}
    for reg in target_regions:
        mini_consmix=consmix_df.loc[consmix_df[import_col]==reg,[export_col,"fraction"]].set_index(export_col)
        mini_consmix.loc[mini_consmix["fraction"]==0,"fraction"]=float("nan")
        region_df=genmix_agg_df.copy()
        region_df["consumption_fraction"]=region_df["Balancing Authority Name"].map(mini_consmix["fraction"])
        region_df["Emission_factor"]=region_df["Emission_factor"]*region_df["consumption_fraction"]
        region_df.dropna(subset=["Emission_factor"],inplace=True)
        cons_mixes_dict[reg]=region_df
    return cons_mixes_dict