# -*- coding: utf-8 -*-
import logging

module_logger = logging.getLogger("aggregation_selector.py")


def subregion_col(subregion="BA"):
    available_options=["all","NERC","BA","US","FERC","EIA"]
    if subregion not in  available_options:
        module_logger.warning("Invalid subregion specified - US selected")
        region_agg = "US"
    if subregion == "all":
        region_agg = ["Subregion"]
    elif subregion == "NERC":
        region_agg = ["NERC"]
    elif subregion == "BA":
        region_agg = ["Balancing Authority Name"]
    elif subregion == "US":
        region_agg = None
    elif subregion == "FERC":
        region_agg = ["FERC_Region"]
    elif subregion == "EIA":
        region_agg = ["EIA_Region"]
    return region_agg

def subregion_name(subregion="BA"):
    available_options=["all","NERC","BA","US","FERC","EIA"]
    if subregion not in  available_options:
        module_logger.warning("Invalid subregion specified - US selected")
        region_name = "US"
    if subregion == "all":
        region_name = "EIA Subregion"
    elif subregion == "NERC":
        region_name = "NERC Region"
    elif subregion == "BA":
        region_name = "Balancing Authority Area"
    elif subregion == "US":
        region_name = "US"
    elif subregion == "FERC":
        region_name = "FERC Region"
    elif subregion == "EIA":
        region_name = "EIA_Region"
    return region_name