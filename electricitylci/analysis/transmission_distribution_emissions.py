# -*- coding: utf-8 -*-
import pandas as pd


def add_transmission_distribution_emissions(td_df, agg_df, subregion="BA"):
    """Adds emissions for transmission and distribution by scaling all of
    the regional emissions to the amount lost through transmission and distribution.
    For example, if the transmission and distribution loss factor is 4% then
    transmission and distribution emissions are 4% of each emission that occurs
    in the life cycle of that region.
    
    Parameters
    ----------
    td_df : dataframe
        The dataframe containing the transmission and distribution losses for
        each region.
    agg_df : dataframe
        The dataframe containing the aggregated emissions for each region
    subregion : str, optional
        The regions represented in the td_df and agg_df dataframes, by default "BA"

    Returns
    -------
    dataframe
        A dataframe containing transmission and distribution losses as a separate
        stage.
    """

    import electricitylci.aggregation_selector as agg

    region_column = agg.subregion_col(subregion)
    td_df_emissions = td_df.merge(right=agg_df, on=region_column, how="left")
    td_df_emissions["FlowAmount"] = (
        td_df_emissions["FlowAmount"] * td_df_emissions["t_d_losses"]
    )
    td_df_emissions["Emission_factor"] = (
        td_df_emissions["Emission_factor"] * td_df_emissions["t_d_losses"]
    )
    td_df_emissions["stage_code"] = "t_d_losses"
    agg_df_with_td = pd.concat([agg_df, td_df_emissions])
    return agg_df_with_td
