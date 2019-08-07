# -*- coding: utf-8 -*-

import pandas as pd

COAL_MINING_CODES=[
    "CA-B-S",
    "CA-B-U",
    "CI-B-S",
    "CI-B-U",
    "GL-B-S",
    "GL-B-U",
    "GL-L-S",
    "IB-B-S",
    "IB-B-U",
    "L-L-S",
    "NA-B-S",
    "NA-B-U",
    "PRB-B-U",
    "PRB-S-S",
    "RM-B-S",
    "RM-B-U",
    "RM-S-S",
    "RM-S-U",
    "SA-B-S",
    "SA-B-U",
    "WNW-L-S",
    "WNW-S-S",
    "CA-B-P",
    "CI-B-P",
    "IB-B-P",
    "IMP-B-S",
    "IMP-B-U",
    "IMP-S-S",
    "NA-B-P",
    "NA-W-",
    "NA-W-P",
    "NA-W-S",
    "NA-W-U",
    "PRB-B-S",
    "RM-B-P",
    "RM-W-S",
]

COAL_TRANSPORT_CODES=[
    'Barge',
    'Lake Vessel',
    'Ocean Vessel',
    'Railroad',
    'Truck'
]

NG_UPSTREAM_CODES=[
       'Anadarko', 'Appalachian', 'Arkla', 'Arkoma',
       'East Texas', 'Fort Worth', 'Green River', 'Gulf', 'Permian',
       'Piceance', 'San Juan', 'South Oklahoma', 'Strawn', 'Uinta'
]

OIL_UPSTREAM_CODES=(
        [f"DFO_{x}" for x in range(1,6)]
        +[f"RFO_{x}" for x in range(1,6)]
)

CONST_CODES=["coal_const","ngcc_const"]


def apply_generic_stage_names(df):
    df["generic_stage_name"]=float("nan")
    df.loc[(df["stage_code"].isin(COAL_MINING_CODES))|(df["stage_code"].isin(COAL_TRANSPORT_CODES)),"generic_stage_name"]="Coal mining/transportation"
    df.loc[df["stage_code"]=="Power plant","generic_stage_name"]="Power plant"
    df.loc[df["stage_code"].isin(CONST_CODES),"generic_stage_name"]="Power plant"
    df.loc[df["stage_code"].isin(NG_UPSTREAM_CODES),"generic_stage_name"]="Natural gas extraction/transport"
    df.loc[df["stage_code"].isin(OIL_UPSTREAM_CODES),"generic_stage_name"]="Oil extraction/refining/transport"
    df.loc[df["stage_code"]=="NUC","generic_stage_name"]="Nuclear fuel"
    return df