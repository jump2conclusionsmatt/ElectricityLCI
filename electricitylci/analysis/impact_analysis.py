import pandas as pd
import lciafmt
import logging

module_logger = logging.getLogger("impact_analysis.py")


def convert_inventory_to_traci_impacts(df, group_cols=None):
    module_logger.info(f"Getting traci impact factors...")
    traci = lciafmt.get_traci()
    traci_mapped = lciafmt.map_flows(traci)
    module_logger.info("Applying factors to passed dataframe...")
    impact_dfs = {}
    if group_cols is None:
        module_logger.info(
            f"Parameter group_cols is None - impact amounts will be listed at the flow level"
        )
    for impact_category in traci_mapped["Indicator"].unique():
        traci_category = (
            traci_mapped.loc[traci_mapped["Indicator"] == impact_category, :]
            .drop_duplicates(subset="Flow UUID")
            .reset_index()
        )
        impact_unit = traci_category.at[0, "Indicator unit"]
        traci_category = traci_category.set_index("Flow UUID")
        impact_df = df.copy()
        impact_df["impact_factor"] = impact_df["FlowUUID"].map(
            traci_category["Factor"]
        )
        impact_df["impact_unit"] = impact_df["FlowUUID"].map(
            traci_category["Indicator unit"]
        )
        impact_df.dropna(subset=["impact_factor"], inplace=True)
        try:
            impact_df["impact_amount"] = (
                impact_df["FlowAmount"] * impact_df["impact_factor"]
            )
        except KeyError:
            module_logger.warning(
                f"Passed dataframe does not have 'FlowAmount' column"
            )
        try:
            impact_df["impact_emission_factor"] = (
                impact_df["Emission_factor"] * impact_df["impact_factor"]
            )
        except KeyError:
            module_logger.warning(
                f"Passed dataframe does not have 'Emission_factor' column"
            )
        impact_df["impact_ef_unit"] = impact_df["impact_unit"] + "/MWh"
        if group_cols is not None:
            grouped_df = impact_df.groupby(by=group_cols)
            impact_df_grouped = pd.DataFrame(index=grouped_df.groups)
            try:
                impact_df_grouped["impact_amount"] = grouped_df[
                    "impact_amount"
                ].sum()
                impact_df_grouped["impact_unit"] = impact_unit
            except KeyError:
                module_logger.warning(
                    f"Passed dataframe does not have 'FlowAmount' column"
                )
            try:
                impact_df_grouped["impact_emission_factor"] = grouped_df[
                    "impact_emission_factor"
                ].sum()
                impact_df_grouped["impact_ef_unit"] = f"{impact_unit}/MWh"
            except KeyError:
                module_logger.warning(
                    f"Passed dataframe does not have 'Emission_factor' column"
                )
            impact_df_grouped.reset_index(inplace=True)
            columns_to_rename = [
                x for x in impact_df_grouped.columns if "level_" in x
            ]
            for col in columns_to_rename:
                level_num = int(col.strip("level_"))
                impact_df_grouped.rename(
                    columns={col: group_cols[level_num]}, inplace=True
                )
            impact_df_grouped.sort_values(by=group_cols, inplace=True)
            impact_dfs[impact_category] = impact_df_grouped
        else:
            impact_dfs[impact_category] = impact_df
    return impact_dfs

