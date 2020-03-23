# Data filtered from stewi and Stewi combo is written ina dictionary in this script.
# The dictionary is basaed on the OLCA schema
# This dictionary can be used for writing json files or templates
import math
import time
import pandas as pd
from os.path import join
import electricitylci
from electricitylci.globals import (
    data_dir,
    electricity_flow_name_generation_and_distribution,
    electricity_flow_name_consumption,
)
from electricitylci.model_config import (
        egrid_year,
        regional_aggregation,
        replace_egrid,
        model_specs
)
from electricitylci.egrid_facilities import egrid_subregions
import yaml
import logging

module_logger = logging.getLogger("process_dictionary_writer.py")
year = egrid_year

# Read in general metadata to be used by all processes
with open(join(data_dir, "process_metadata.yml")) as f:
    metadata=yaml.safe_load(f)


#Wanted to be able to reuse sections of the metadata in other subsections.
#in order to do this with yaml, we need to be able to process lists of lists.
#process_metadata makes this happen.
def process_metadata(entry):
    if isinstance(entry,str):
        return entry
    elif isinstance(entry,list):
        try:
            total_string = ""
            for x in entry:
                if isinstance(x,str): 
                    total_string=total_string+x+"\n"
                elif isinstance(x,list):
                    if len(x)==1:
                        total_string+=x[0]
                    else:
                        total_string=total_string+"\n".join([y[0] for y in x])
#            result = '\n'.join([x[0] for x in entry])
            return total_string
        except ValueError:
            pass
        
    elif isinstance(entry,dict):
        for key in entry.keys():
            entry[key] = process_metadata(entry[key])
        return entry

for key in metadata.keys():
    metadata[key]=process_metadata(metadata[key])
#metadata = pd.read_csv(join(data_dir, "metadata.csv"))
# Use only first row of metadata for all processes for now
#metadata = metadata.iloc[0,]

# Read in process location uuids
location_UUID = pd.read_csv(join(data_dir, "location_UUIDs.csv"))


def lookup_location_uuid(location):
    try:
        uuid = location_UUID.loc[location_UUID["NAME"] == location][
            "REF_ID"
        ].iloc[0]
    except IndexError:
        uuid = ""
    return uuid


# Read in process name info
process_name = pd.read_csv(join(data_dir, "processname_1.csv"))
generation_name_parts = process_name[
    process_name["Stage"] == "generation"
].iloc[0]
generation_mix_name_parts = process_name[
    process_name["Stage"] == "generation mix"
].iloc[0]

generation_mix_name = (
    generation_mix_name_parts["Base name"]
    + "; "
    + generation_mix_name_parts["Location type"]
    + "; "
    + generation_mix_name_parts["Mix type"]
)
surplus_pool_name = "Electricity; at grid; surplus pool"
consumption_mix_name = "Electricity; at grid; consumption mix"
distribution_to_end_user_name = "Electricity; at user; consumption mix"

electricity_at_grid_flow = {
    "flowType": "PRODUCT_FLOW",
    "flowProperties": "",
    "name": electricity_flow_name_generation_and_distribution,
    "id": "",
    "category": "Technosphere Flows/22: Utilities/2211: Electric Power Generation, Transmission and Distribution",
}

electricity_at_user_flow = {
    "flowType": "PRODUCT_FLOW",
    "flowProperties": "",
    "name": electricity_flow_name_consumption,
    "id": "",
    "category": "Technosphere Flows/22: Utilities/2211: Electric Power Generation, Transmission and Distribution",
}


def exchange(flw, exchanges_list):
    exchanges_list.append(flw)
    return exchanges_list


def exchange_table_creation_ref(data):
    region = data["Subregion"].iloc[0]
    ar = dict()
    ar["internalId"] = ""
    ar["@type"] = "Exchange"
    ar["avoidedProduct"] = False
    ar["flow"] = electricity_at_grid_flow
    ar["flowProperty"] = ""
    ar["input"] = False
    ar["quantitativeReference"] = True
    ar["baseUncertainty"] = ""
    ar["provider"] = ""
    ar["amount"] = 1.0
    ar["amountFormula"] = ""
    ar["unit"] = unit("MWh")
    return ar

def exchange_table_creation_ref_cons(data):
    ar = dict()
    ar["internalId"] = ""
    ar["@type"] = "Exchange"
    ar["avoidedProduct"] = False
    ar["flow"] = electricity_at_grid_flow
    ar["flowProperty"] = ""
    ar["input"] = False
    ar["quantitativeReference"] = True
    ar["baseUncertainty"] = ""
    ar["provider"] = ""
    ar["amount"] = 1.0
    ar["amountFormula"] = ""
    ar["unit"] = unit("MWh")
    return ar

def gen_process_ref(fuel, reg):
    processref = dict()
    processref["name"] = (
        generation_name_parts["Base name"]
        + "; from "
        + str(fuel)
        + "; "
        + generation_name_parts["Location type"]
        +" - "
        +reg
    )
    processref["location"] = reg
    processref["processType"] = "UNIT_PROCESS"
    processref["categoryPath"] = [
        "22: Utilities",
        "2211: Electric Power Generation, Transmission and Distribution",
        fuel,
    ]
    return processref


def con_process_ref(reg, ref_type="generation"):
    # If ref is to a consunmption mix (for a distribution process), use consumption mix name
    # If not, if the region is an egrid regions, its a generation mix process; otherwise its a surplus pool process
    if ref_type == "consumption":
        name = consumption_mix_name +" - "+reg
    elif reg in egrid_subregions:
        name = generation_mix_name +" - "+reg
    else:
        name = surplus_pool_name + " - "+reg
    processref = dict()
    processref["name"] = name
    processref["location"] = reg
    processref["processType"] = "UNIT_PROCESS"
    processref["categoryPath"] = [
        "22: Utilities",
        "2211: Electric Power Generation, Transmission and Distribution",
    ]
    return processref


def exchange_table_creation_input_genmix(database, fuelname):
    region = database["Subregion"].iloc[0]
    ar = dict()
    ar["internalId"] = ""
    ar["@type"] = "Exchange"
    ar["avoidedProduct"] = False
    ar["flow"] = electricity_at_grid_flow
    ar["flowProperty"] = ""
    ar["input"] = True
    ar["quantitativeReference"] = "True"
    ar["baseUncertainty"] = ""
    ar["provider"] = gen_process_ref(fuelname, region)
    ar["amount"] = database["Generation_Ratio"].iloc[0]
    ar["unit"] = unit("MWh")
    ar["pedigreeUncertainty"] = ""
    # ar['category']='22: Utilities/2211: Electric Power Generation, Transmission and Distribution'+fuelname
    ar["comment"] = "from " + fuelname +" - "+ region
    ar["uncertainty"] = ""
    return ar


def exchange_table_creation_input_con_mix(
    generation, loc, ref_to_consumption=False
):
    ar = dict()
    ar["internalId"] = ""
    ar["@type"] = "Exchange"
    ar["avoidedProduct"] = False
    ar["flow"] = electricity_at_grid_flow
    ar["flowProperty"] = ""
    ar["input"] = True
    ar["baseUncertainty"] = ""
    if ref_to_consumption:
        ar["provider"] = con_process_ref(loc, "consumption")
    else:
        ar["provider"] = con_process_ref(loc)
    ar["amount"] = generation
    ar["unit"] = unit("MWh")
    ar["pedigreeUncertainty"] = ""
    ar["uncertainty"] = ""
    ar["comment"] = "eGRID " + str(year) + ". From " + loc
    # ar['location'] = location(loc)
    return ar

def process_table_creation_gen(fuelname, exchanges_list, region):
    ar = dict()
    ar["@type"] = "Process"
    ar["allocationFactors"] = ""
    ar["defaultAllocationMethod"] = ""
    ar["exchanges"] = exchanges_list
    ar["location"] = location(region)
    ar["parameters"] = ""
    ar["processDocumentation"] = process_doc_creation()
    ar["processType"] = "UNIT_PROCESS"
    ar["name"] = (
        generation_name_parts["Base name"]
        + "; from "
        + str(fuelname)
        + "; "
        + generation_name_parts["Location type"]
    )
    ar["category"] = (
        "22: Utilities/2211: Electric Power Generation, Transmission and Distribution/"
        + fuelname
    )
    ar["description"] = (
        "Electricity from "
        + str(fuelname)
        + " produced at generating facilities in the "
        + str(region)
        + " region"
    )
    return ar


def process_table_creation_genmix(region, exchanges_list):
    ar = dict()
    ar["@type"] = "Process"
    ar["allocationFactors"] = ""
    ar["defaultAllocationMethod"] = ""
    ar["exchanges"] = exchanges_list
    ar["location"] = location(region)
    ar["parameters"] = ""
    ar["processDocumentation"] = process_doc_creation(process_type="generation_mix")
    ar["processType"] = "UNIT_PROCESS"
    ar["name"] = generation_mix_name + " - " + str(region)
    ar[
        "category"
    ] = "22: Utilities/2211: Electric Power Generation, Transmission and Distribution"
    ar["description"] = (
        "Electricity generation mix in the " + str(region) + " region"
    )
    return ar


# Will be used later
# def category():
#
#     global fuelname;
#     ar = {'':''}
#     ar['@id'] = ''
#     ar['@type'] = 'Category'
#     ar['name'] = '22: Utilities/2211: Electric Power Generation, Transmission and Distribution'+str(fuelname)
#     del ar['']
#     return ar


# Will be used later
def location(region):
    ar = dict()
    ar["id"] = lookup_location_uuid(region)
    ar["type"] = "Location"
    ar["name"] = region
    return ar

OLCA_TO_METADATA={
        "timeDescription":None,
        "validUntil":None,
        "validFrom":None,
        "technologyDescription":"TechnologyDescription",
        "dataCollectionDescription":"DataCollectionPeriod",
        "completenessDescription":"DataCompleteness",
        "dataSelectionDescription":"DataSelection",
        "reviewDetails":"DatasetOtherEvaluation",
        "dataTreatmentDescription":"DataTreatment",
        "inventoryMethodDescription":"LCIMethod",
        "modelingConstantsDescription":"ModelingConstants",
        "reviewer":"Reviewer",
        "samplingDescription":"SamplingProcedure",
        "sources":None,
        "restrictionsDescription":"AccessUseRestrictions",
        "copyright":None,
        "sources":None,
        "copyright":None,
        "creationDate":None,
        "dataDocumentor":"DataDocumentor",
        "dataGenerator":"DataGenerator",
        "dataSetOwner":"DatasetOwner",
        "intendedApplication":"IntendedApplication",
        "projectDescription":"ProjectDescription",
        "publication":None,
        "geographyDescription":None,
        "exchangeDqSystem":None,
        "dqSystem":None,
        "dqEntry":None
}
VALID_FUEL_CATS=[
        "default",
        "nuclear_upstream",
        "geothermal",
        "solar",
        "solarthermal",
        "wind",
        "consumption_mix",
        "generation_mix",
        "coal_upstream",
        "gas_upstream",
        "oil_upstream",
        "coal_transport_upstream",
        "construction_upstream"
]
def process_doc_creation(process_type="default"):
    try:
        assert process_type in VALID_FUEL_CATS, f"Invalid process_type ({process_type}), using default"
    except AssertionError:
        process_type="default"
    if model_specs["replace_egrid"] is True:
        subkey = "replace_egrid"
    else:
        subkey= "use_egrid"
    global year
    ar = dict()
    for key in OLCA_TO_METADATA.keys():
        if OLCA_TO_METADATA[key] is not None:
            try:
                ar[key]=metadata[process_type][OLCA_TO_METADATA[key]]
            except KeyError:
                module_logger.debug(f"Failed first key ({key}), trying subkey: {subkey}")
                try:
                    ar[key]=metadata[process_type][subkey][OLCA_TO_METADATA[key]]
                    module_logger.debug(f"Failed subkey, likely no entry in metadata for {process_type}:{key}")
                except KeyError:
                    ar[key]=metadata["default"][OLCA_TO_METADATA[key]]
            except TypeError:
                module_logger.debug(f"Failed first key, likely no metadata defined for {process_type}")
                process_type="default"
                ar[key]=metadata[process_type][OLCA_TO_METADATA[key]]
    ar["timeDescription"] = ""
    ar["validUntil"] = "12/31/2018"
    ar["validFrom"] = "1/1/2018"
    ar["sources"] = ""
    ar["copyright"] = False
    ar["creationDate"] = time.time()
    ar["publication"] = ""
    ar["geographyDescription"] = ""
    ar["exchangeDqSystem"] = exchangeDqsystem()
    ar["dqSystem"] = processDqsystem()
    # Temp place holder for process DQ scores
    ar["dqEntry"] = "(5;5)"
    return ar

def process_description_creation(process_type="fossil"):
    try:
        assert process_type in VALID_FUEL_CATS, f"Invalid process_type ({process_type}), using default"
    except AssertionError:
        process_type="default"
    if model_specs["replace_egrid"] is True:
        subkey = "replace_egrid"
    else:
        subkey= "use_egrid"
    global year
    key = "Description"
    try:
        desc_string=metadata[process_type][key]
    except KeyError:
        module_logger.debug(f"Failed first key ({key}), trying subkey: {subkey}")
        try:
            desc_string=metadata[process_type][subkey][key]
            module_logger.debug("Failed subkey, likely no entry in metadata for {process_type}:{key}")
        except KeyError:
            desc_string=metadata["default"][key]
    except TypeError:
        module_logger.debug(f"Failed first key, likely no metadata defined for {process_type}")
        process_type="default"
        desc_string=metadata[process_type][key]
    return desc_string
    

if __name__=="__main__":
    test=process_doc_creation(process_type="oil_upstream")
    print(test)

def exchangeDqsystem():
    ar = dict()
    ar["@type"] = "DQSystem"
    ar["@id"] = "d13b2bc4-5e84-4cc8-a6be-9101ebb252ff"
    ar["name"] = "US EPA - Flow Pedigree Matrix"
    return ar


def processDqsystem():
    ar = dict()
    ar["@type"] = "DQSystem"
    ar["@id"] = "70bf370f-9912-4ec1-baa3-fbd4eaf85a10"
    ar["name"] = "US EPA - Process Pedigree Matrix"
    return ar


def exchange_table_creation_input(data):
    year = data["Year"].iloc[0]
    ar = dict()
    ar["internalId"] = ""
    ar["@type"] = "Exchange"
    ar["avoidedProduct"] = False
    ar["flow"] = flow_table_creation(data)
    ar["flowProperty"] = ""
    ar["input"] = True
    ar["baseUncertainty"] = ""
    ar["provider"] = ""
    ar["amount"] = data["Emission_factor"].iloc[0]
    ar["amountFormula"] = "  "
    ar["unit"] = unit(data["Unit"].iloc[0])
    ar["dqEntry"] = ""
    ar["pedigreeUncertainty"] = ""
    ar["uncertainty"] = uncertainty_table_creation(data)
    ar["comment"] = "eGRID " + str(year)
    # if data['FlowType'].iloc[0] == 'ELEMENTARY_FLOW':
    #   ar['category'] = 'Elementary flows/'+str(data['ElementaryFlowPrimeContext'].iloc[0])+'/'+str(data['Compartment'].iloc[0])
    # elif data['FlowType'].iloc[0] == 'WASTE_FLOW':
    #   ar['category'] = 'Waste flows/'
    # else:
    #   ar['category'] = '22: Utilities/2211: Electric Power Generation, Transmission and Distribution/'+fuelname
    return ar


def unit(unt):
    ar = dict()
    ar["internalId"] = ""
    ar["@type"] = "Unit"
    ar["name"] = unt
    return ar


def exchange_table_creation_output(data):
    year = data["Year"].iloc[0]
    source = data["Source"].iloc[0]
    ar = dict()
    ar["internalId"] = ""
    ar["@type"] = "Exchange"
    ar["avoidedProduct"] = False
    ar["flow"] = flow_table_creation(data)
    ar["flowProperty"] = ""
    ar["input"] = False
    ar["quantitativeReference"] = False
    ar["baseUncertainty"] = ""
    ar["provider"] = ""
    ar["amount"] = data["Emission_factor"].iloc[0]
    ar["amountFormula"] = ""
    ar["unit"] = unit(data["Unit"].iloc[0])
    ar["pedigreeUncertainty"] = ""
    ar["dqEntry"] = (
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
    ar["uncertainty"] = uncertainty_table_creation(data)
    ar["comment"] = str(source) + " " + str(year)
    # if data['FlowType'].iloc[0] == 'ELEMENTARY_FLOW':
    #  ar['category'] = 'Elementary flows/'+str(data['ElementaryFlowPrimeContext'].iloc[0])+'/'+str(data['Compartment'].iloc[0])
    # elif data['FlowType'].iloc[0] == 'WASTE_FLOW':
    #  ar['category'] = 'Waste flows/'
    # else:
    #  ar['category'] = '22: Utilities/2211: Electric Power Generation, Transmission and Distribution'+data['FlowName'].iloc[0]

    return ar


def uncertainty_table_creation(data):

    ar = dict()
    #    print(data["GeomMean"].iloc[0] + ' - ' +data["GeomSD"].iloc[0])
    if data["GeomMean"].iloc[0] is not None:
        ar["geomMean"] = str(float(data["GeomMean"].iloc[0]))
    if data["GeomSD"].iloc[0] is not None:
        ar["geomSd"] = str(float(data["GeomSD"].iloc[0]))
    ar["distributionType"] = "Logarithmic Normal Distribution"
    ar["mean"] = ""
    ar["meanFormula"] = ""
    ar["geomMeanFormula"] = ""
    ar["maximum"] = data["Maximum"].iloc[0]
    ar["minimum"] = data["Minimum"].iloc[0]
    ar["minimumFormula"] = ""
    ar["sd"] = ""
    ar["sdFormula"] = ""
    ar["geomSdFormula"] = ""
    ar["mode"] = ""
    ar["modeFormula"] = ""
    ar["maximumFormula"] = ""
    return ar


def flow_table_creation(data):
    ar = dict()
    flowtype = data["FlowType"].iloc[0]
    ar["flowType"] = flowtype
    ar["flowProperties"] = ""
    ar["name"] = data["FlowName"].iloc[0][
        0:255
    ]  # cutoff name at length 255 if greater than that
    ar["id"] = data["FlowUUID"].iloc[0]
    comp = str(data["Compartment"].iloc[0])
    if (flowtype == "ELEMENTARY_FLOW") & (comp != ""):
        if "emission" in comp or "resource" in comp:
            ar["category"] = (
                "Elementary Flows/"
                + comp
            )
        elif "input" in comp:
            ar["category"] = (
                "Elementary Flows/resource"
        )
        else:
            ar["category"] = (
                "Elementary Flows/"
                "emission/"
                + comp.lstrip("/")
            )
    elif (flowtype == "PRODUCT_FLOW") & (comp != ""):
        ar["category"] = comp
    elif flowtype == "WASTE_FLOW":
        ar["category"] = comp
    else:
        # Assume this is electricity or a byproduct
        ar[
            "category"
        ] = "Technosphere Flows/22: Utilities/2211: Electric Power Generation, Transmission and Distribution"
    return ar


def ref_exchange_creator(electricity_flow=electricity_at_grid_flow):
    ar = dict()
    ar["internalId"] = ""
    ar["@type"] = "Exchange"
    ar["avoidedProduct"] = False
    ar["flow"] = electricity_flow
    ar["flowProperty"] = ""
    ar["input"] = False
    ar["quantitativeReference"] = True
    ar["baseUncertainty"] = ""
    ar["provider"] = ""
    ar["amount"] = 1.0
    ar["amountFormula"] = ""
    ar["unit"] = unit("MWh")
    ar["location"] = ""
    return ar


def process_table_creation_con_mix(region, exchanges_list):
    ar = dict()
    ar["@type"] = "Process"
    ar["allocationFactors"] = ""
    ar["defaultAllocationMethod"] = ""
    ar["exchanges"] = exchanges_list
    ar["location"] = location(region)
    ar["parameters"] = ""
    ar["processDocumentation"] = process_doc_creation(process_type="consumption_mix")
    ar["processType"] = "UNIT_PROCESS"
    ar["name"] = consumption_mix_name + " - " + region
    ar[
        "category"
    ] = "22: Utilities/2211: Electric Power Generation, Transmission and Distribution"
    ar["description"] = (
        "Electricity consumption mix using power plants in the "
        + str(region)
        + " region"
    )
    return ar


def process_table_creation_surplus(region, exchanges_list):
    ar = dict()
    ar["@type"] = "Process"
    ar["allocationFactors"] = ""
    ar["defaultAllocationMethod"] = ""
    ar["exchanges"] = exchanges_list
    ar["location"] = location(region)
    ar["parameters"] = ""
    ar["processDocumentation"] = process_doc_creation()
    ar["processType"] = "UNIT_PROCESS"
    ar["name"] = surplus_pool_name + " - " + region
    ar[
        "category"
    ] = "22: Utilities/2211: Electric Power Generation, Transmission and Distribution"
    ar["description"] = "Electricity surplus in the " + str(region) + " region"
    return ar


def process_table_creation_distribution(region, exchanges_list):
    ar = dict()
    ar["@type"] = "Process"
    ar["allocationFactors"] = ""
    ar["defaultAllocationMethod"] = ""
    ar["exchanges"] = exchanges_list
    ar["location"] = location(region)
    ar["parameters"] = ""
    ar["processDocumentation"] = process_doc_creation()
    ar["processType"] = "UNIT_PROCESS"
    ar["name"] = distribution_to_end_user_name + " - " + region
    ar[
        "category"
    ] = "22: Utilities/2211: Electric Power Generation, Transmission and Distribution"
    ar["description"] = (
        "Electricity distribution to end user in the "
        + str(region)
        + " region"
    )
    return ar


# def process_table_creation_trade_mix(region,exchanges_list):
#     ar = dict()
#     ar['@type'] = 'Process'
#     ar['allocationFactors']=''
#     ar['defaultAllocationMethod']=''
#     ar['exchanges']=exchanges_list;
#     ar['location']=region
#     ar['parameters']=''
#     ar['processDocumentation']=process_doc_creation();
#     ar['processType']=''
#     ar['name'] = 'Electricity; at region '+str(region)+'; Trade Mix'
#     ar['category'] = '22: Utilities/2211: Electric Power Generation, Transmission and Distribution'
#     ar['description'] = 'Electricity trade mix using power plants in the '+str(region)+' region'
#     return ar;
