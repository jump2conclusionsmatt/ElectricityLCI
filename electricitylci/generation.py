#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Created on Tue Jun  4 12:07:46 2019

@author: jamiesom
"""
from electricitylci.model_config import replace_egrid, use_primaryfuel_for_coal, model_specs
from electricitylci.elementaryflows import map_emissions_to_fedelemflows
import pandas as pd
import numpy as np
from electricitylci.globals import output_dir
from datetime import datetime
from electricitylci.dqi import lookup_score_with_bound_key
from scipy.stats import t, norm
from scipy.special import erfinv
import ast
import logging
from electricitylci.egrid_facilities import egrid_facilities,egrid_subregions
from electricitylci.eia923_generation import eia923_primary_fuel
from electricitylci.eia860_facilities import eia860_balancing_authority

egrid_facilities_w_fuel_region = egrid_facilities[['FacilityID','Subregion','PrimaryFuel','FuelCategory','NERC','PercentGenerationfromDesignatedFuelCategory','Balancing Authority Name','Balancing Authority Code']]

module_logger = logging.getLogger("generation.py")

def eia_facility_fuel_region(year):
    primary_fuel = eia923_primary_fuel(year=year)
    ba_match = eia860_balancing_authority(year)
    primary_fuel["Plant Id"]=primary_fuel["Plant Id"].astype(int)
    ba_match["Plant Id"]=ba_match["Plant Id"].astype(int)
    combined = primary_fuel.merge(ba_match, on='Plant Id')
    combined['primary fuel percent gen'] = (
        combined['primary fuel percent gen'] / 100
    )

    combined.rename(
        columns={
            'primary fuel percent gen': 'PercentGenerationfromDesignatedFuelCategory',
            'Plant Id': 'FacilityID',
            'fuel category': 'FuelCategory',
            'NERC Region': 'NERC',
        },
        inplace=True
    )

    return combined

def add_technological_correlation_score(db):
    #Create col, set to 5 by default
    # db['TechnologicalCorrelation'] = 5
    from electricitylci.dqi import technological_correlation_lower_bound_to_dqi
    #convert PercentGen to fraction
    db['PercentGenerationfromDesignatedFuelCategory'] = db['PercentGenerationfromDesignatedFuelCategory']/100
    db['TechnologicalCorrelation'] = db['PercentGenerationfromDesignatedFuelCategory'].apply(lambda x: lookup_score_with_bound_key(x,technological_correlation_lower_bound_to_dqi))
    # db = db.drop(columns='PercentGenerationfromDesignatedFuelCategory')
    return db

def add_flow_representativeness_data_quality_scores(db,total_gen):
    db = add_technological_correlation_score(db)
    db = add_temporal_correlation_score(db)
    db = add_data_collection_score(db,total_gen)
    return db

def add_temporal_correlation_score(db):
    # db['TemporalCorrelation'] = 5
    from electricitylci.dqi import temporal_correlation_lower_bound_to_dqi
    from electricitylci.model_config import electricity_lci_target_year

    #Could be more precise here with year
    db['Age'] =  electricity_lci_target_year - pd.to_numeric(db['Year'])
    db['TemporalCorrelation'] = db['Age'].apply(
        lambda x: lookup_score_with_bound_key(x, temporal_correlation_lower_bound_to_dqi))
    # db = db.drop(columns='Age')
    return db

def aggregate_facility_flows(df):
    """Thus function aggregates flows from the same source (NEI, netl, etc.) within
    a facility. The main problem this solves is that if several emissions
    are mapped to a single federal elementary flow (CO2 biotic, CO2 land use change,
    etc.) then those were showing up as separate emissions in the inventory
    and artificially inflating the number of emissions for uncertainty
    calculations.

    Parameters
    ----------
    df : dataframe
        dataframe with facility-level emissions that might contain duplicate
        emission species within the facility.

    Returns
    -------
    dataframe
    """
    emission_compartments = [
        "emission/air",
        "emission/water",
        "emission/ground",
        "emission/soil",
        "air",
        "water",
        "soil",
        "ground",
        "waste",
    ]
    groupby_cols = [
        "FuelCategory",
        "FacilityID",
        "Electricity",
        "FlowName",
        "Source",
        "Compartment_path",
        "stage_code"
    ]
    def wtd_mean(pdser, total_db, cols):
        try:
            wts = total_db.loc[pdser.index, "FlowAmount"]
            result = np.average(pdser, weights=wts)
        except:
            module_logger.debug(
                f"Error calculating weighted mean for {pdser.name}-"
                f"likely from 0 FlowAmounts"
                #f"{total_db.loc[pdser.index[0],cols]}"
            )
            try:
                with np.errstate(all='raise'):
                    result = np.average(pdser)
            except ArithmeticError or ValueError or FloatingPointError:    
                result = float("nan")
        return result

    wm = lambda x: wtd_mean(x, df, groupby_cols)
    emissions = df["Compartment"].isin(emission_compartments)
    df_emissions = df[emissions]
    df_nonemissions = df[~emissions]
    df_dupes = df_emissions.duplicated(subset=groupby_cols, keep=False)
    df_red = df_emissions.drop(df_emissions[df_dupes].index)
    group_db = (
        df_emissions.loc[df_dupes, :]
        .groupby(groupby_cols, as_index=False).agg(
                {
                        "FlowAmount":"sum",
                        "ReliabilityScore":wm
                }
        )
    )
    #    group_db=df.loc[emissions,:].groupby(groupby_cols,as_index=False)['FlowAmount'].sum()
    group_db_merge = group_db.merge(
        right=df_emissions.drop_duplicates(subset=groupby_cols),
        on=groupby_cols,
        how="left",
        suffixes=("", "_right"),
    )
    try:
        delete_cols = ["FlowAmount_right","ReliabilityScore_right"]
        group_db_merge.drop(columns=delete_cols, inplace=True)
    except KeyError:
        pass
    df = pd.concat(
        [df_nonemissions, df_red, group_db_merge], ignore_index=True
    )
    return df


def _combine_sources(p_series, df, cols, source_limit=None):
    """
    Take the list of sources from a groupby.apply and return a dataframe
    that contains one column containing a list of the sources and another
    that concatenates them into a string. This is all in an effort to find
    another approach for summing electricity for all plants in an aggregation
    that match the same data sources.

    Parameters
    ----------
    df: dataframe
        Dataframe containing merged generation and emissions data - includes
        a column for data source (i.e., eGRID, NEI, RCRAInfo...)

    Returns
    ----------
    dataframe
    """
    module_logger.debug(
        f"Combining sources for {str(df.loc[p_series.index[0],cols].values)}"
    )
    source_list = list(np.unique(p_series))
    if source_limit:
        if len(source_list) > source_limit:
            # result = pd.DataFrame()
            #            result=dict({"source_list":float("nan"),"source_string":float("nan")})
            #            result["source_list"]=float("nan")
            #            result["source_string"]=float("nan")
            result = [float("nan"), float("nan")]
            return result
        else:
            #            result = pd.DataFrame()
            source_list.sort()
            source_list_string = "_".join(source_list)
            #            result=dict({"source_list":source_list,"source_string":source_list_string})
            result = [source_list, source_list_string]
            #            result["source_list"] = pd.DataFrame(data=[source_list]).values.tolist()
            #            result["source_string"] = source_list_string

            return result
    else:
        #        result = pd.DataFrame()
        source_list.sort()
        source_list_string = "_".join(source_list)
        #        result = pd.DataFrame()
        #        result["source_list"] = pd.DataFrame(data=[source_list]).values.tolist()
        #        result["source_string"] = source_list_string
        source_list.sort()
        source_list_string = "_".join(source_list)
        #        result=dict({"source_list":source_list,"source_string":source_list_string})
        result = [source_list, source_list_string]
        return result


def add_data_collection_score(db, elec_df, subregion="BA"):
    """
    Adds the data collection score which is a function of how much of the
    total electricity generated in a subregion is captured by the denominator
    used in the final emission factor.

    Parameters
    ----------
    db : datafrane
        Dataframe containing facility-level emissions as generated by
        create_generation_process_df.
    elec_df : dataframe
        Dataframe containing the totals for various subregion/source
        combinations. These are used as the denominators in the emissions
        factors
    subregion : str, optional
        The level of subregion that the data will be aggregated to. Choices
        are 'all', 'NERC', 'BA', 'US', by default 'BA'
    """
    from electricitylci.dqi import data_collection_lower_bound_to_dqi
    from electricitylci.aggregation_selector import subregion_col

    region_agg = subregion_col(subregion)
    fuel_agg = ["FuelCategory"]
    if region_agg:
        groupby_cols = region_agg + fuel_agg + ["Year"]
    else:
        groupby_cols = fuel_agg + ["Year"]
    temp_df = db.merge(
        right=elec_df,
        left_on=groupby_cols + ["source_string"],
        right_on=groupby_cols + ["source_string"],
        how="left",
    )
    reduced_db = db.drop_duplicates(subset=groupby_cols + ["eGRID_ID"])
    region_elec = reduced_db.groupby(groupby_cols, as_index=False)[
        "Electricity"
    ].sum()
    region_elec.rename(
        columns={"Electricity": "region_fuel_electricity"}, inplace=True
    )
    temp_df = temp_df.merge(
        right=region_elec,
        left_on=groupby_cols,
        right_on=groupby_cols,
        how="left",
    )
    db["Percent_of_Gen_in_EF_Denominator"] = (
        temp_df["electricity_sum"] / temp_df["region_fuel_electricity"]
    )
    db["DataCollection"] = db["Percent_of_Gen_in_EF_Denominator"].apply(
        lambda x: lookup_score_with_bound_key(
            x, data_collection_lower_bound_to_dqi
        )
    )
    db = db.drop(columns="Percent_of_Gen_in_EF_Denominator")
    return db


def calculate_electricity_by_source(db, subregion="BA"):
    """
    This function calculates the electricity totals by region and source
    using the same approach as the original generation.py with attempts made to
    speed it up. That is each flow will have a source associated with it
    (eGRID, NEI, TRI, RCRAInfo). To develop an emission factor, the FlowAmount
    will need to be divided by electricity generation. This routine sums all
    electricity generation for all source/subregion combinations. So if
    a subregion aggregates FlowAmounts source from NEI and TRI then the
    denominator will be all production from plants that reported into NEI or
    TRI for that subregion.

    Parameters
    ----------
    db : dataframe
        Dataframe containing facility-level emissions as generated by
        create_generation_process_df.
    subregion : str, optional
        The level of subregion that the data will be aggregated to. Choices
        are 'all', 'NERC', 'BA', 'US', by default 'BA'
    """

    from electricitylci.aggregation_selector import subregion_col
    all_sources='_'.join(sorted(list(db["Source"].unique())))
    power_plant_criteria=db["stage_code"]=="Power plant"
    db_powerplant=db.loc[power_plant_criteria,:]
    db_nonpower=db.loc[~power_plant_criteria,:]
    region_agg = subregion_col(subregion)

    fuel_agg = ["FuelCategory"]
    if region_agg:
        groupby_cols = (
            region_agg
            + fuel_agg
            + ["Year", "stage_code", "FlowName", "Compartment"]
        )
        elec_groupby_cols = region_agg + fuel_agg + ["Year"]
    else:
        groupby_cols = fuel_agg + [
            "Year",
            "stage_code",
            "FlowName",
            "Compartment",
        ]
        elec_groupby_cols = fuel_agg + ["Year"]

    combine_source_by_flow = lambda x: _combine_sources(
        x, db, ["FlowName", "Compartment"], 1
    )
    combine_source_lambda = lambda x: _combine_sources(
        x, db_multiple_sources, groupby_cols
    )
    # power_db = db.loc[db["stage_code"]=='Power plant',:]

    # This is a pretty expensive process when we have to start looking at each
    # flow generated in each compartment for each balancing authority area.
    # To hopefully speed this up, we'll group by FlowName and Comparment and look
    # and try to eliminate flows where all sources are single entities.
    source_df = pd.DataFrame()
    source_df = pd.DataFrame(
        db_powerplant.groupby(["FlowName", "Compartment"])[["Source"]].apply(
            combine_source_by_flow
        ),
        columns=["source_list"],
    )
    source_df[["source_list", "source_string"]] = pd.DataFrame(
        source_df["source_list"].values.tolist(), index=source_df.index
    )
    source_df.reset_index(inplace=True)
    old_index = db_powerplant.index
    db_powerplant = db_powerplant.merge(
        right=source_df,
        left_on=["FlowName", "Compartment"],
        right_on=["FlowName", "Compartment"],
        how="left",
    )
    db_powerplant.index=old_index
    db_multiple_sources = db_powerplant.loc[db_powerplant["source_string"].isna(), :]
    if len(db_multiple_sources) > 0:
        source_df = pd.DataFrame(
            db_multiple_sources.groupby(groupby_cols)[["Source"]].apply(
                combine_source_lambda
            ),
            columns=["source_list"],
        )
        source_df[["source_list", "source_string"]] = pd.DataFrame(
            source_df["source_list"].values.tolist(), index=source_df.index
        )
        source_df.reset_index(inplace=True)
        db_multiple_sources.drop(
            columns=["source_list", "source_string"], inplace=True
        )
        old_index = db_multiple_sources.index
        db_multiple_sources = db_multiple_sources.merge(
            right=source_df,
            left_on=groupby_cols,
            right_on=groupby_cols,
            how="left",
        )
        db_multiple_sources.index = old_index
        # db[["source_string","source_list"]].fillna(db_multiple_sources[["source_string","source_list"]],inplace=True)
        db_powerplant.loc[
            db_powerplant["source_string"].isna(), ["source_string", "source_list"]
        ] = db_multiple_sources[["source_string", "source_list"]]
    unique_source_lists = list(db_powerplant["source_string"].unique())
    # unique_source_lists = [x for x in unique_source_lists if ((str(x) != "nan")&(str(x)!="netl"))]
    unique_source_lists = [
        x for x in unique_source_lists if ((str(x) != "nan"))
    ]
    # One set of emissions passed into this routine may be life cycle emissions
    # used as proxies for Canadian generation. In those cases the electricity
    # generation will be equal to the Electricity already in the dataframe.

    elec_sum_lists = list()

    unique_source_lists  = unique_source_lists+[all_sources]
    for src in unique_source_lists:
        module_logger.info(f"Calculating electricity for {src}")
        # src_filter = db.apply(lambda x: x["Source"] in src, axis=1)
        db["temp_src"] = src
        src_filter = [
            a in b
            for a, b in zip(
                db["Source"].values.tolist(), db["temp_src"].values.tolist()
            )
        ]
        #        total_filter = ~fuelcat_all & src_filter
        sub_db = db.loc[src_filter, :]
        sub_db.drop_duplicates(subset=fuel_agg + ["eGRID_ID"], inplace=True)
        sub_db_group = sub_db.groupby(elec_groupby_cols, as_index=False).agg(
            {"Electricity": [np.sum, np.mean], "eGRID_ID": "count"}
        )
        sub_db_group.columns = elec_groupby_cols + [
            "electricity_sum",
            "electricity_mean",
            "facility_count",
        ]
        #        zero_elec_filter = sub_db_group["electricity_sum"]==0
        sub_db_group["source_string"] = src
        elec_sum_lists.append(sub_db_group)
    db_nonpower["source_string"]=all_sources
    db_nonpower["source_list"]=[all_sources]*len(db_nonpower)
    elec_sums = pd.concat(elec_sum_lists, ignore_index=True)
    elec_sums.sort_values(by=elec_groupby_cols, inplace=True)
    db=pd.concat([db_powerplant,db_nonpower])
    return db, elec_sums


def create_generation_process_df():
    """
    Reads emissions and generation data from different sources to provide
    facility-level emissions. Most important inputs to this process come
    from the model configuration file.

    Parameters
    ----------
    None

    Returns
    ----------
    dataframe
        Datafrane includes all facility-level emissions
    """
    from electricitylci.eia923_generation import build_generation_data
    from electricitylci.egrid_filter import (
        egrid_facilities_to_include,
        emissions_and_waste_for_selected_egrid_facilities,
    )
    from electricitylci.generation import egrid_facilities_w_fuel_region
    from electricitylci.generation import (
        add_technological_correlation_score,
        add_temporal_correlation_score,
    )
    import electricitylci.emissions_other_sources as em_other
    import electricitylci.ampd_plant_emissions as ampd
    from electricitylci.model_config import eia_gen_year
    from electricitylci.combinator import ba_codes

    COMPARTMENT_DICT = {
        "emission/air": "air",
        "emission/water": "water",
        "emission/ground": "ground",
        "input": "input",
        "output": "output",
        "waste": "waste",
        "air": "air",
        "water": "water",
        "ground": "ground",
    }
    if replace_egrid:
        generation_data = build_generation_data().drop_duplicates()
        cems_df = ampd.generate_plant_emissions(eia_gen_year)
        cems_df.drop(columns=["FlowUUID"], inplace=True)
        emissions_and_waste_for_selected_egrid_facilities = em_other.integrate_replace_emissions(
            cems_df, emissions_and_waste_for_selected_egrid_facilities
        )
    else:
        from electricitylci.egrid_filter import electricity_for_selected_egrid_facilities
        generation_data=electricity_for_selected_egrid_facilities
        generation_data["Year"]=model_specs["egrid_year"]
        generation_data["FacilityID"]=generation_data["FacilityID"].astype(int)
#        generation_data = build_generation_data(
#            egrid_facilities_to_include=egrid_facilities_to_include
#        )
    emissions_and_waste_for_selected_egrid_facilities.drop(
        columns=["FacilityID"]
    )
    emissions_and_waste_for_selected_egrid_facilities[
        "eGRID_ID"
    ] = emissions_and_waste_for_selected_egrid_facilities["eGRID_ID"].astype(
        int
    )
    final_database = pd.merge(
        left=emissions_and_waste_for_selected_egrid_facilities,
        right=generation_data,
        right_on=["FacilityID", "Year"],
        left_on=["eGRID_ID", "Year"],
        how="left",
    )
    egrid_facilities_w_fuel_region[
        "FacilityID"
    ] = egrid_facilities_w_fuel_region["FacilityID"].astype(int)
    final_database = pd.merge(
        left=final_database,
        right=egrid_facilities_w_fuel_region,
        left_on="eGRID_ID",
        right_on="FacilityID",
        how="left",
        suffixes=["", "_right"],
    )
    key_df = (
        final_database[["eGRID_ID", "FuelCategory"]]
        .dropna()
        .drop_duplicates(subset="eGRID_ID")
        .set_index("eGRID_ID")
    )
    final_database.loc[
        final_database["FuelCategory"].isnull(), "FuelCategory"
    ] = final_database.loc[
        final_database["FuelCategory"].isnull(), "eGRID_ID"
    ].map(
        key_df["FuelCategory"]
    )
    if replace_egrid:
        final_database["FuelCategory"].fillna(
            final_database["FuelCategory_right"], inplace=True
        )
    final_database["Final_fuel_agg"] = final_database["FuelCategory"]
    if use_primaryfuel_for_coal:
        final_database.loc[
            final_database["FuelCategory"] == "COAL", ["Final_fuel_agg"]
        ] = final_database.loc[
            final_database["FuelCategory"] == "COAL", "PrimaryFuel"
        ]

    try:
        year_filter = final_database["Year_x"] == final_database["Year_y"]
        final_database = final_database.loc[year_filter, :]
        final_database.drop(columns="Year_y", inplace=True)
    except KeyError:
        pass
    final_database.rename(columns={"Year_x": "Year"}, inplace=True)
    final_database = map_emissions_to_fedelemflows(final_database)
    dup_cols_check = [
        "FacilityID",
        "FuelCategory",
        "FlowName",
        "FlowAmount",
        "Compartment",
    ]
    final_database = final_database.loc[
        :, ~final_database.columns.duplicated()
    ]
    final_database = final_database.drop_duplicates(subset=dup_cols_check)
    final_database.drop(
        columns=["FuelCategory", "FacilityID_x", "FacilityID_y"], inplace=True
    )
    final_database.rename(
        columns={
            "Final_fuel_agg": "FuelCategory",
            "TargetFlowUUID": "FlowUUID",
        },
        inplace=True,
    )
    final_database = add_temporal_correlation_score(final_database)
    final_database = add_technological_correlation_score(final_database)
    final_database["DataCollection"] = 5
    final_database["GeographicalCorrelation"] = 1

    final_database["eGRID_ID"] = final_database["eGRID_ID"].astype(int)

    final_database.sort_values(
        by=["eGRID_ID", "Compartment", "FlowName"], inplace=True
    )
    final_database["stage_code"] = "Power plant"
    final_database["Compartment_path"] = final_database["Compartment"]
    final_database["Compartment"] = final_database["Compartment_path"].map(
        COMPARTMENT_DICT
    )
    final_database["Balancing Authority Name"]=final_database["Balancing Authority Code"].map(ba_codes["BA_Name"])
    final_database["EIA_Region"] = final_database["Balancing Authority Code"].map(
        ba_codes["EIA_Region"]
    )
    final_database["FERC_Region"] = final_database["Balancing Authority Code"].map(
        ba_codes["FERC_Region"]
    )
    return final_database


def aggregate_data(total_db, subregion="BA"):
    """
    Aggregates facility-level emissions to the specified subregion and
    calculates emission factors based on the total emission and total
    electricity generation.

    Parameters
    ----------
    total_db : dataframe
        Facility-level emissions as generated by created by
        create_generation_process_df
    subregion : str, optional
        The level of subregion that the data will be aggregated to. Choices
        are 'all', 'NERC', 'BA', 'US', by default 'BA'.
    """
    from electricitylci.aggregation_selector import subregion_col

    def geometric_mean(p_series, df, cols):
        # Alternatively we can use scipy.stats.lognorm to fit a distribution
        # and provide the parameters
        if (len(p_series) > 3) & (p_series.quantile(0.5) > 0):
            # result = gmean(p_series.to_numpy()+1)-1
            module_logger.debug(
                f"Calculating confidence interval for"
                f"{df.loc[p_series.index[0],groupby_cols].values}"
            )
            module_logger.debug(f"{p_series.values}")
            with np.errstate(all='raise'):
                try:
                    data = p_series.to_numpy()
                except ArithmeticError or ValueError or FloatingPointError:
                    module_logger.debug("Problem with input data")
                    return None
                try:
                    log_data = np.log(data)
                except ArithmeticError or ValueError or FloatingPointError:
                    module_logger.debug("Problem with log function")
                    return None
                try:
                    mean = np.mean(log_data)
                except ArithmeticError or ValueError or FloatingPointError:
                    module_logger.debug("Problem with mean function")
                    return None
                l = len(data)
                try:
                    sd = np.std(log_data)/np.sqrt(l)
                    sd2 = sd ** 2
                except ArithmeticError or ValueError or FloatingPointError:
                    module_logger.debug("Problem with std function")
                    return None
                try:
                    pi1, pi2 = t.interval(alpha=0.90, df=l - 2, loc=mean, scale=sd)
                except ArithmeticError or ValueError or FloatingPointError:
                    module_logger.debug("Problem with t function")
                    return None
                try:
                    upper_interval = np.max(
                        [
                            mean
                            + sd2 / 2
                            + pi2 * np.sqrt(sd2 / l + sd2 ** 2 / (2 * (l - 1))),
                            mean
                            + sd2 / 2
                            - pi2 * np.sqrt(sd2 / l + sd2 ** 2 / (2 * (l - 1))),
                        ]
                    )
                except:
                    module_logger.debug("Problem with interval function")
                    return None
                try:
                    result = (np.exp(mean), 0, np.exp(upper_interval))
                except ArithmeticError or ValueError or FloatingPointError:
                    print("Prolem with result")
                    return None
                if result is not None:
                    return result
                else:
                    module_logger.debug(
                        f"Problem generating uncertainty parameters \n"
                        f"{df.loc[p_series.index[0],groupby_cols].values}\n"
                        f"{p_series.values}"
                        f"{p_series.values+1}"
                    )
                    return None
        else:
            return None

    def calc_geom_std(df):
        if region_agg is not None:
            debug_string=f"{df[region_agg]}-{df['FuelCategory']}-{df['FlowName']}"
        else:
            debug_string=f"{df['FuelCategory']}-{df['FlowName']}"
        module_logger.debug(debug_string)
        if df["uncertaintyLognormParams"] is None:
            return None, None
        if isinstance(df["uncertaintyLognormParams"], str):
            params = ast.literal_eval(df["uncertaintyLognormParams"])
        try:
            length = len(df["uncertaintyLognormParams"])
        except TypeError:
            module_logger.info(
                f"Error calculating length of uncertaintyLognormParams"
                f"{df['uncertaintyLognormParams']}"
            )
            return None, None
        
        if length != 3:
            module_logger.info(
                f"Error estimating standard deviation - length: {len(params)}"
            )
        else:
            #In some cases, the final emission factor is far different than the
            #geometric mean of the individual emission factor. Depending on the 
            #severity, this could be a clear sign of outliers having a large impact
            #on the final emission factor. When the uncertainty is generated for
            #these cases, the results can be nonsensical - hence we skip them. A more
            #agressive approach would be to re-assign the emission factor as well.
            if df["Emission_factor"]>df["uncertaintyLognormParams"][2]:
                return None, None
            else:
                c=np.log(df["uncertaintyLognormParams"][2])-np.log(df["Emission_factor"])
                b=-2**0.5*erfinv(2*0.95-1)
                a=0.5
                sd1=(-b+(b**2-4*a*c)**0.5)/(2*a)
                sd2=(-b-(b**2-4*a*c)**0.5)/(2*a)
                if sd1 is not float("nan") and sd2 is not float("nan"):
                    if sd1<sd2:
                        geostd=np.exp(sd1)
                        geomean=np.exp(np.log(df["Emission_factor"])-0.5*sd1**2)
                    else:
                        geostd=np.exp(sd2)
                        geomean=np.exp(np.log(df["Emission_factor"])-0.5*sd2**2)
                elif sd1 is not float("nan"):
                    geostd=np.exp(sd1)
                    geomean=np.exp(np.log(df["Emission_factor"])-0.5*sd1**2)
                elif sd2 is not float("nan"):
                    geostd=np.exp(sd2)
                    geomean=np.exp(np.log(df["Emission_factor"])-0.5*sd2**2)
                else:
                    return None, None
                if (
                    (geostd is np.inf)
                    or (geostd is np.NINF)
                    or (geostd is np.nan)
                    or (geostd is float("nan"))
                    or str(geostd) == "nan"
                    or (geostd == 0)
                ):
                    return None, None
                return str(geomean), str(geostd)

    region_agg = subregion_col(subregion)
    fuel_agg = ["FuelCategory"]
    if region_agg:
        groupby_cols = (
            region_agg
            + fuel_agg
            + ["stage_code", "FlowName", "Compartment", "FlowUUID","Unit"]
        )
        elec_df_groupby_cols = (
            region_agg + fuel_agg + ["Year", "source_string"]
        )
    else:
        groupby_cols = fuel_agg + [
            "stage_code",
            "FlowName",
            "Compartment",
            "FlowUUID",
            "Unit"
        ]
        elec_df_groupby_cols = fuel_agg + ["Year", "source_string"]
    total_db["FlowUUID"] = total_db["FlowUUID"].fillna(value="dummy-uuid")
    total_db = aggregate_facility_flows(total_db)
    total_db, electricity_df = calculate_electricity_by_source(
        total_db, subregion
    )
    total_db["FlowAmount"].replace(to_replace=0,value=1E-15,inplace=True)
    total_db = add_data_collection_score(total_db, electricity_df, subregion)
    total_db["facility_emission_factor"] = (
        total_db["FlowAmount"] / total_db["Electricity"]
    )
    total_db.dropna(subset=["facility_emission_factor"], inplace=True)

    def wtd_mean(pdser, total_db, cols):
        try:
            wts = total_db.loc[pdser.index, "FlowAmount"]
            result = np.average(pdser, weights=wts)
        except:
            module_logger.debug(
                f"Error calculating weighted mean for {pdser.name}-"
                f"likely from 0 FlowAmounts"
                #f"{total_db.loc[pdser.index[0],cols]}"
            )
            try:
                with np.errstate(all='raise'):
                    result = np.average(pdser)
            except ArithmeticError or ValueError or FloatingPointError:    
                result = float("nan")
        return result

    wm = lambda x: wtd_mean(x, total_db, groupby_cols)
    geo_mean = lambda x: geometric_mean(x, total_db, groupby_cols)
    geo_mean.__name__ = "geo_mean"
    print(
        "Aggregating flow amounts, dqi information, and calculating uncertainty"
    )

    database_f3 = total_db.groupby(
        groupby_cols + ["Year", "source_string"], as_index=False
    ).agg(
        {
            "FlowAmount": ["sum", "count"],
            "TemporalCorrelation": wm,
            "TechnologicalCorrelation": wm,
            "GeographicalCorrelation": wm,
            "DataCollection": wm,
            "ReliabilityScore": wm,
            "facility_emission_factor": ["min", "max", geo_mean],
        }
    )
    database_f3.columns = groupby_cols + [
        "Year",
        "source_string",
        "FlowAmount",
        "FlowAmountCount",
        "TemporalCorrelation",
        "TechnologicalCorrelation",
        "GeographicalCorrelation",
        "DataCollection",
        "ReliabilityScore",
        "uncertaintyMin",
        "uncertaintyMax",
        "uncertaintyLognormParams",
    ]

    criteria = database_f3["Compartment"] == "input"
    database_f3.loc[criteria, "uncertaintyLognormParams"] = None
    database_f3 = database_f3.merge(
        right=electricity_df,
        left_on=elec_df_groupby_cols,
        right_on=elec_df_groupby_cols,
        how="left",
    )

    canadian_criteria = database_f3["FuelCategory"] == "ALL"
    if region_agg:
        canada_db = pd.merge(
            left=database_f3.loc[canadian_criteria, :],
            right=total_db[groupby_cols + ["Electricity"]],
            left_on=groupby_cols,
            right_on=groupby_cols,
            how="left",
        ).drop_duplicates(subset=groupby_cols)
    else:
        total_grouped = total_db.groupby(by=groupby_cols, as_index=False)[
            "Electricity"
        ].sum()
        canada_db = pd.merge(
            left=database_f3.loc[canadian_criteria, :],
            right=total_grouped,
            left_on=groupby_cols,
            right_on=groupby_cols,
            how="left",
        )
    canada_db.index = database_f3.loc[canadian_criteria, :].index
    database_f3.loc[
        database_f3["FlowUUID"] == "dummy-uuid", "FlowUUID"
    ] = float("nan")
    database_f3.loc[canada_db.index, "electricity_sum"] = canada_db[
        "Electricity"
    ]
    database_f3["Emission_factor"] = (
        database_f3["FlowAmount"] / database_f3["electricity_sum"]
    )
    #Infinite values generally coming from places with 0 generation. This happens
    #particularly with the Canadian mixes.
    database_f3["Emission_factor"].replace(to_replace=float("inf"),value=0,inplace=True)
    if region_agg is not None:
        database_f3["GeomMean"], database_f3["GeomSD"] = zip(
            *database_f3[
                [
                    "Emission_factor",
                    "uncertaintyLognormParams",
                    "uncertaintyMin",
                    "uncertaintyMax",
                    "FuelCategory",
                    "FlowName"
                ]+region_agg
            ].apply(calc_geom_std, axis=1)
        )
    else:
        database_f3["GeomMean"], database_f3["GeomSD"] = zip(
            *database_f3[
                [
                    "Emission_factor",
                    "uncertaintyLognormParams",
                    "uncertaintyMin",
                    "uncertaintyMax",
                    "FuelCategory",
                    "FlowName"
                ]
            ].apply(calc_geom_std, axis=1)
        )
    database_f3.sort_values(by=groupby_cols, inplace=True)
    return database_f3


def olcaschema_genprocess(database, upstream_dict={}, subregion="BA"):
    """Turns the give database containing generator facility emissions
    into dictionaries that contain the required data for insertion into
    an openLCA-compatible json-ld. Additionally, default providers
    for fuel inputs are mapped, using the information contained in the dictionary
    containing openLCA-formatted data for the fuels.

    Parameters
    ----------
    database : dataframe
        Dataframe containing aggregated emissions to be turned into openLCA
        unit processes
    upstream_dict : dictionary, optional
        Dictionary as created by upstream_dict.py, containing the openLCA
        formatted data for all of the fuel inputs. This function will use the
        names and UUIDs from the entries to assign them as default providers.
    subregion : str, optional
        The subregion level of the aggregated data, by default "BA". See
        aggregation_selector.py for available subregions.

    Returns
    -------
    dictionary: dictionary contaning openLCA-formatted data
    """
    from electricitylci.process_dictionary_writer import (
        unit,
        flow_table_creation,
        ref_exchange_creator,
        uncertainty_table_creation,
        process_doc_creation,
    )

    from electricitylci.aggregation_selector import subregion_col

    region_agg = subregion_col(subregion)
    fuel_agg = ["FuelCategory"]
    if region_agg:
        base_cols = region_agg + fuel_agg
    else:
        base_cols = fuel_agg
    non_agg_cols = [
        "stage_code",
        "FlowName",
        "FlowUUID",
        "Compartment",
        "Unit",
        "Year",
        "source_string",
        "TemporalCorrelation",
        "TechnologicalCorrelation",
        "GeographicalCorrelation",
        "DataCollection",
        "ReliabilityScore",
        "uncertaintyMin",
        "uncertaintyMax",
        "uncertaintyLognormParams",
        "Emission_factor",
        "GeomMean",
        "GeomSD",
    ]   
    def turn_data_to_dict(data, upstream_dict):

        module_logger.debug(
            f"Turning flows from {data.name} into dictionaries"
        )
        cols_for_exchange_dict = [
            "internalId",
            "@type",
            "avoidedProduct",
            "flow",
            "flowProperty",
            "input",
            "quantitativeReference",
            "baseUncertainty",
            "provider",
            "amount",
            "amountFormula",
            "unit",
            "pedigreeUncertainty",
            "dqEntry",
            "uncertainty",
            "comment",
        ]
        year = ",".join(data["Year"].astype(str).unique())
        datasources = ",".join(data["source_string"].astype(str).unique())
        data["Maximum"] = data["uncertaintyMax"]
        data["Minimum"] = data["uncertaintyMin"]
        data["uncertainty"] = ""
        data["internalId"] = ""
        data["@type"] = "Exchange"
        data["avoidedProduct"] = False
        data["flowProperty"] = ""
        data["input"]=False
        input_filter = (
                (data["Compartment"].str.lower().str.contains("input")) 
                | (data["Compartment"].str.lower().str.contains("resource"))
                | (data["Compartment"].str.lower().str.contains("technosphere"))
        )
        data.loc[input_filter, "input"] = True
        data["baseUncertainty"] = ""
        data["provider"] = ""
        data["unit"] = data["Unit"]
#        data["ElementaryFlowPrimeContext"] = data["Compartment"]
#        default_unit = unit("kg")
#        data["unit"] = [default_unit] * len(data)
        data["FlowType"]="ELEMENTARY_FLOW"
        product_filter=(
                (data["Compartment"].str.lower().str.contains("technosphere"))
                |(data["Compartment"].str.lower().str.contains("valuable"))
        )
        data.loc[product_filter,"FlowType"] = "PRODUCT_FLOW"
        waste_filter=(
                (data["Compartment"].str.lower().str.contains("technosphere"))
        )
        data.loc[waste_filter,"FlowType"] = "WASTE_FLOW"
        data["flow"] = ""
        provider_filter = data["stage_code"].isin(upstream_dict.keys())
        for index, row in data.loc[provider_filter, :].iterrows():
            provider_dict = {
                "name": upstream_dict[getattr(row, "stage_code")]["name"],
                "categoryPath": upstream_dict[getattr(row, "stage_code")][
                    "category"
                ],
                "processType": "UNIT_PROCESS",
                "@id": upstream_dict[getattr(row, "stage_code")]["uuid"],
            }
            data.at[index, "provider"] = provider_dict
            data.at[index, "unit"] = unit(
                upstream_dict[getattr(row, "stage_code")]["q_reference_unit"]
            )
            data.at[index, "FlowType"] = "PRODUCT_FLOW"
        for index, row in data.iterrows():
            data.at[index, "uncertainty"] = uncertainty_table_creation(
                data.loc[index:index, :]
            )
            data.at[index, "flow"] = flow_table_creation(
                data.loc[index:index, :]
            )
        data["amount"] = data["Emission_factor"]
        data["amountFormula"] = ""
        data["quantitativeReference"] = False
        data["dqEntry"] = (
            "("
            + str(round(data["ReliabilityScore"].iloc[0], 1))
            + ";"
            + str(round(data["TemporalCorrelation"].iloc[0], 1))
            + ";"
            + str(round(data["GeographicalCorrelation"].iloc[0], 1))
            + ";"
            + str(round(data["TechnologicalCorrelation"].iloc[0], 1))
            + ";"
            + str(round(data["DataCollection"].iloc[0], 1))
            + ")"
        )
        data["pedigreeUncertainty"] = ""
        data["comment"] = f"{datasources} - {year}"
        data_for_dict = data[cols_for_exchange_dict]
        data_for_dict = data_for_dict.append(
            ref_exchange_creator(), ignore_index=True
        )
        data_dict = data_for_dict.to_dict("records")
        return data_dict

    database_groupby = database.groupby(by=base_cols)
    process_df = pd.DataFrame(
        database_groupby[non_agg_cols].apply(
            turn_data_to_dict, (upstream_dict)
        )
    )
    process_df.columns = ["exchanges"]
    process_df.reset_index(inplace=True)
    process_df["@type"] = "Process"
    process_df["allocationFactors"] = ""
    process_df["defaultAllocationMethod"] = ""
    process_df["location"] = ""
    process_df["parameters"] = ""
#    process_doc_dict = process_doc_creation(process_type)
#    process_df["processDocumentation"] = [process_doc_dict]*len(process_df)
    process_df["processType"] = "UNIT_PROCESS"
    process_df["category"] = (
        "22: Utilities/2211: Electric Power Generation, Transmission and Distribution/"
        + process_df[fuel_agg].values
    )
    if region_agg is None:
        process_df["description"] = (
            "Electricity from "
            + process_df[fuel_agg].values
            + " produced at generating facilities in the US"
        )
        process_df["name"] = (
            "Electricity - " + process_df[fuel_agg].values + " - US"
        )
    else:
        process_df["description"] = (
            "Electricity from "
            + process_df[fuel_agg].values
            + " produced at generating facilities in the "
            + process_df[region_agg].values
            + " region"
        )
        process_df["name"] = (
            "Electricity - "
            + process_df[fuel_agg].values
            + " - "
            + process_df[region_agg].values
        )
    #process_df["processDocumentation"]=map(process_doc_creation,list(process_df["FuelCategory"].str.lower()))
    process_df["processDocumentation"]=[process_doc_creation(x) for x in list(process_df["FuelCategory"].str.lower())]
    process_cols = [
        "@type",
        "allocationFactors",
        "defaultAllocationMethod",
        "exchanges",
        "location",
        "parameters",
        "processDocumentation",
        "processType",
        "name",
        "category",
        "description",
    ]
    result = process_df[process_cols].to_dict("index")
    return result


if __name__ == "__main__":
    plant_emission_df = create_generation_process_df()
    aggregated_emissions_df = aggregate_data(plant_emission_df, subregion="BA")
    datetimestr = datetime.now().strftime("%Y%m%d_%H%M%S")
    aggregated_emissions_df.to_csv(
        f"{output_dir}/aggregated_emissions_{datetimestr}.csv"
    )
    plant_emission_df.to_csv(f"{output_dir}/plant_emissions_{datetimestr}.csv")
