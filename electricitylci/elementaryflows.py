import pandas as pd
import fedelemflowlist

# flowlist = fedelemflowlist.get_flowlist()
mapping_to_fedelemflows = fedelemflowlist.get_flowmapping()
mapping_to_fedelemflows = mapping_to_fedelemflows[
    [
        "SourceListName",
        "SourceFlowName",
        "SourceFlowContext",
        "SourceUnit",
        "TargetFlowName",
        "TargetFlowUUID",
        "TargetFlowContext",
        "TargetUnit",
    ]
]


def map_emissions_to_fedelemflows(df_with_flows_compartments):

    mapped_df = pd.merge(
        df_with_flows_compartments,
        mapping_to_fedelemflows.drop_duplicates(
            subset=["SourceFlowName", "SourceFlowContext"]
        ),
        left_on=["FlowName", "Compartment"],
        right_on=["SourceFlowName", "SourceFlowContext"],
        how="left",
    )
    # If a NewName is present there was a match, replace FlowName and Compartment with new names
    mapped_df.loc[
        mapped_df["TargetFlowName"].notnull(), "FlowName"
    ] = mapped_df["TargetFlowName"]
    mapped_df.loc[
        mapped_df["TargetFlowName"].notnull(), "Compartment"
    ] = mapped_df["TargetFlowContext"]
    mapped_df.loc[mapped_df["TargetFlowName"].notnull(), "Unit"] = mapped_df[
        "TargetUnit"
    ]

    mapped_df = mapped_df.rename(columns={"TargetFlowUUID": "FlowUUID"})

    # If air, soil, or water assigned it directionality of emission. Others will get assigned later as needed
    emission_compartments = ["emission/air", "emission/ground", "emission/water"]
    mapped_df.loc[
        mapped_df["Compartment"].isin(emission_compartments),
        "ElementaryFlowPrimeContext",
    ] = "emission"

    # Drop all unneeded cols
    mapped_df = mapped_df.drop(
        columns=[
            "SourceFlowName",
            "SourceFlowContext",
            "SourceUnit",
            "TargetFlowName",
            "TargetFlowContext",
            "TargetFlowContext",
            "TargetUnit",
        ]
    )
    return mapped_df


# Manually mapping of input 'Heat' to energy types for renewables
# !Still need to consider amount conversion
def map_renewable_heat_flows_to_fedelemflows(df_with_flows_compart_direction):

    # For all other fuel sources assume techonosphere flows and set to null
    df_with_flows_compart_direction.loc[
        (df_with_flows_compart_direction["FlowName"] == "Heat"),
        "ElementaryFlowPrimeContext",
    ] = None

    df_with_flows_compart_direction.loc[
        (df_with_flows_compart_direction["FlowName"] == "Heat")
        & (
            (df_with_flows_compart_direction["FuelCategory"] == "SOLAR")
            | (df_with_flows_compart_direction["FuelCategory"] == "GEOTHERMAL")
            | (df_with_flows_compart_direction["FuelCategory"] == "WIND")
            | (df_with_flows_compart_direction["FuelCategory"] == "HYDRO")
        ),
        "ElementaryFlowPrimeContext",
    ] = "resource"

    df_with_flows_compart_direction.loc[
        (df_with_flows_compart_direction["FlowName"] == "Heat")
        & (df_with_flows_compart_direction["FuelCategory"] == "SOLAR"),
        "Compartment",
    ] = "air"
    df_with_flows_compart_direction.loc[
        (df_with_flows_compart_direction["FlowName"] == "Heat")
        & (df_with_flows_compart_direction["FuelCategory"] == "SOLAR"),
        "FlowName",
    ] = "Energy, solar"

    df_with_flows_compart_direction.loc[
        (df_with_flows_compart_direction["FlowName"] == "Heat")
        & (df_with_flows_compart_direction["FuelCategory"] == "GEOTHERMAL"),
        "Compartment",
    ] = "ground"
    df_with_flows_compart_direction.loc[
        (df_with_flows_compart_direction["FlowName"] == "Heat")
        & (df_with_flows_compart_direction["FuelCategory"] == "GEOTHERMAL"),
        "FlowName",
    ] = "Energy, geothermal"

    df_with_flows_compart_direction.loc[
        (df_with_flows_compart_direction["FlowName"] == "Heat")
        & (df_with_flows_compart_direction["FuelCategory"] == "WIND"),
        "Compartment",
    ] = "air"
    df_with_flows_compart_direction.loc[
        (df_with_flows_compart_direction["FlowName"] == "Heat")
        & (df_with_flows_compart_direction["FuelCategory"] == "WIND"),
        "FlowName",
    ] = "Energy, wind"

    df_with_flows_compart_direction.loc[
        (df_with_flows_compart_direction["FlowName"] == "Heat")
        & (df_with_flows_compart_direction["FuelCategory"] == "HYDRO"),
        "Compartment",
    ] = "water"
    df_with_flows_compart_direction.loc[
        (df_with_flows_compart_direction["FlowName"] == "Heat")
        & (df_with_flows_compart_direction["FuelCategory"] == "HYDRO"),
        "FlowName",
    ] = "Energy, hydro"

    # Need to handle steam separately
    #    df_with_flows_compart_direction.loc[(df_with_flows_compart_direction['FlowName']=='Steam'),
    #                                   'ElementaryFlowPrimeContext'] = 'coproduct'

    return df_with_flows_compart_direction


# Compartment to flow type mapping
# Use valid flow types in json_ld http://greendelta.github.io/olca-schema/html/FlowType.html
compartment_to_flowtype = pd.DataFrame(
    columns=["Compartment", "FlowType"],
    data=[
        ["air", "ELEMENTARY_FLOW"],
        ["water", "ELEMENTARY_FLOW"],
        ["ground", "ELEMENTARY_FLOW"],
        ["input", "PRODUCT_FLOW"],
        ["output", "PRODUCT_FLOW"],
        ["waste", "WASTE_FLOW"],
        ["emission/air","ELEMENTARY_FLOW"],
        ["emission/water","ELEMENTARY_FLOW"],
        ["emission/ground","ELEMENTARY_FLOW"],
        ["soil","ELEMENTARY_FLOW"]
    ],
)


def map_compartment_to_flow_type(df_with_compartments):
    df_with_flowtypes = pd.merge(
        df_with_compartments,
        compartment_to_flowtype,
        on=["Compartment"],
        how="left",
    )
    return df_with_flowtypes


def add_flow_direction(df_with_flowtypes):
    df_with_flowtypes["FlowDirection"] = "output"
    df_with_flowtypes.loc[
        (df_with_flowtypes["Compartment"] == "input")
        | (df_with_flowtypes["ElementaryFlowPrimeContext"] == "resource"),
        "FlowDirection",
    ] = "input"
    return df_with_flowtypes
