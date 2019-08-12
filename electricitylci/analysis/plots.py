# -*- coding: utf-8 -*-

import matplotlib.pyplot as plt
import seaborn as sns
from electricitylci.aggregation_selector import subregion_col
import electricitylci.analysis.utils as an_util
import pandas as pd


def impact_plot_comparison(df, fuelcat="all", subregion="BA", sort=False):
    """Generates a stacked bar plot showing a comparison of the life cycle
    impact analysis contained in the passed dataframe (e.g., a comparison of
    global warming potential). 
    
    Parameters
    ----------
    df : dataframe
        A dataframe containing the impact emission factors for various stages
        of the electricity life cycle.
    fuelcat : str, optional
        The comparison can be specified to contain only a certain
        fuel category. For example one may compare "GAS" plants across all
        balancing authority areas. By default "all" - the plot will contain all 
        fuel categories for all regions.
    subregion : str, optional
        The regions contained in the passed df, by default "BA".
    sort : bool, optional
        Sort the columns according to the total impacts, by default False

    Returns
    -------
    matplotlib.axes
        A figure containing a stacked column comparison of the life cycle
        impact analysis contained in the passed dataframe. 
    """

    

    cat_column = subregion_col(subregion)
    if fuelcat != "all":
        df_red = df.loc[df["FuelCategory"] == fuelcat, :].copy()
    else:
        df_red = df.copy()
    df_generic = an_util.apply_generic_stage_names(df_red)
    #The application of a categorical type to the stage name may be unnecessary
    #and removed. This was a change implemented to try and get the desired format
    #of column names - it did not work.
    df_generic["generic_stage_name"] = df_generic["generic_stage_name"].astype(
        "category"
    )
    df_generic["FuelCategory"] = df_generic["FuelCategory"].astype("category")
    df_generic_grouped = df_generic.groupby(
        by=cat_column + ["FuelCategory", "generic_stage_name"], as_index=False
    )["impact_emission_factor"].sum()
    
    width = max(
        5,
        int(
            df_generic_grouped[cat_column].nunique().values
            * df_generic_grouped["FuelCategory"].nunique()
            * 0.2
        ),
    )
    df_generic_grouped.set_index(
        pd.MultiIndex.from_frame(
            df_generic_grouped[cat_column + ["FuelCategory"]]
        ),
        inplace=True,
    )
    df_generic_grouped.drop(
        columns=cat_column + ["FuelCategory"], inplace=True
    )
    df_generic_grouped = df_generic_grouped.pivot(columns="generic_stage_name")
    df_generic_grouped.columns = df_generic_grouped.columns.droplevel()
    df_generic_grouped.columns = df_generic_grouped.columns.to_list()
    sns.set()
    if sort:
        old_cols = df_generic_grouped.columns
        df_generic_grouped["total"] = df_generic_grouped.sum(axis=1)
        df_generic_grouped.sort_values(
            by=["total"], inplace=True, ascending=False
        )
        impact_plot = df_generic_grouped[old_cols].plot(
            kind="bar", stacked=True, figsize=(width, 10)
        )
    else:
        impact_plot = df_generic_grouped[[]].plot(
            kind="bar", stacked=True, figsize=(width, 10)
        )
    return impact_plot
