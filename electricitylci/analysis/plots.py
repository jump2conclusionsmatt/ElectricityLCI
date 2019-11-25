# -*- coding: utf-8 -*-

import matplotlib.pyplot as plt
import seaborn as sns
from electricitylci.aggregation_selector import subregion_col
import electricitylci.analysis.utils as an_util
import pandas as pd
import numpy as np
from itertools import groupby

subregion_names={
    "Subregion":"eGRID",
    "NERC":"NERC",
    "Balancing Authority Name":"BA",
    "FERC_Region":"FERC",
    "EIA_Region":"EIA",
}
def _get_labels(units_str):
    """Internal function to return the name of the impact category given
    the units string provided in the dataframe. Currently only works
    with the strings contained in the impact_ef_unit column.
    
    Parameters
    ----------
    units_str : string
        A string containing the units of the emissions factor (i.e., from
        the impact_ef_unit column).
    
    Returns
    -------
    tuple :
        A tuple containing a string for the impact category, and a string
        suitable for using in an axis label for the units.
    """
    if units_str == "kg N eq/MWh":
        label = ("Eutrophication Potential", r"$\frac{kg N eq}{MWh}$")
    elif units_str == "kg SO2 eq/MWh":
        label = ("Acidification Potential", r"$\frac{kg SO_2 eq}{MWh}$")
    elif units_str == "PM 2.5 eq/MWh":
        label = (
            "Particulate Matter Formation Potential",
            r"$\frac{PM 2.5 eq}{MWh}$",
        )
    elif units_str == "kg O3 eq/MWh":
        label = ("Smog Formation Potential", r"$\frac{O_3 eq}{MWh}$")
    elif units_str == "kg CO2 eq/MWh":
        label = ("Global Warming Potential", r"$\frac{kg CO_2 eq}{MWh}$")
    elif units_str == "kg CFC-11 eq/MWh":
        label = ("Ozone Depletion Potential", r"$\frac{kg CFC-11 eq}{MWh}$")
    return label


def impact_plot_comparison(
    df, fuelcat="ALL", subregion="BA", sort=False, **kwargs
):
    """Generates a horizontal stacked bar plot showing a comparison of the life cycle
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
    cat_label=subregion_names[cat_column[0]]
    if fuelcat != "ALL":
        df_red = df.loc[df["FuelCategory"] == fuelcat.upper(), :].copy()
        df_generic = an_util.apply_generic_stage_names(
            df_red
        )  # Assign stage_code to
        df_generic_grouped = df_generic.groupby(
            by=cat_column + ["FuelCategory", "generic_stage_name"],
            as_index=False,
        )["impact_emission_factor"].sum()
    else:
        df_red = df.copy()
        df_generic = an_util.apply_generic_stage_names(df_red)
        df_generic_grouped = df_generic.groupby(
            by=cat_column + ["generic_stage_name"], as_index=False
        ).agg({"impact_emission_factor": "sum"})

    df_generic_grouped.set_index(cat_column, inplace=True)
    try:
        df_generic_grouped.drop("FuelCategory", axis=1, inplace=True)
    except:
        pass

    df_generic_grouped = df_generic_grouped.pivot(columns="generic_stage_name")
    df_generic_grouped.columns = df_generic_grouped.columns.droplevel(level=0)

    col_names = list(df_generic_grouped.columns)
    col_names.sort()

    # Generate color palette for fuel-use categories (i.e. {'Power plant': '#ffffff'})
    # Pandas.plot(kind='bar', stacked = True) lacks the ability to assign color
    # to bar pieces using an integrated parameter. The code below interprets
    # the columns in df_generic_grouped and produces a color palette with the
    # appropriately matched colors.
    labs = [
        "Oil extraction/refining/transport",
        "Power plant",
        "Construction",
        "Natural gas extraction/transport",
        "Transmission and Distribution",
        "Coal mining/transportation",
        "Nuclear fuel",
    ]

    palette = [
        "#4C72B0",
        "#DD8452",
        "#55A868",
        "#C44E52",
        "#B172B3",
        "#937860",
        "#DA8BC3",
    ]

    palette_dict = dict(zip(labs, palette))
    plot_palette = []
    for col in col_names:
        plot_palette.extend([palette_dict[col]])

    # Plotting
    df_generic_grouped[col_names].plot(
        kind="barh",
        stacked=True,
        color=plot_palette,
        figsize=(8, max(len(df_generic_grouped)*0.5,5)),
        width=0.75,
        edgecolor="black",
        linewidth=0.5,
        zorder=3,
    )

    ax = plt.gca()
    ax.set_ylabel(cat_label, fontsize=10, weight="bold")
    xlabel_tuple = _get_labels(df.at[min(df.index), "impact_ef_unit"])
    xlabel = f"{xlabel_tuple[0]} {xlabel_tuple[1]}"
    ax.set_xlabel(
        xlabel,
        fontsize=10,
        weight="bold",
    )
    ax.yaxis.grid(False)
    ax.xaxis.grid(color="#7E7D7D", zorder=0)
    ax.set_facecolor("white")
    ax.patch.set_edgecolor("black")
    ax.patch.set_linewidth("2")
    ax.legend(facecolor="#C5BAA3", frameon=True)
#    ax.set_title(cat_label, fontsize=16, weight="bold")
    return ax


# `add_line()`, `label_len()`, and `label_group_bar_table()` based on the
# implementation described by user 'Stein': 
# https://stackoverflow.com/questions/19184484/how-to-add-group-labels-for-bar-charts-in-matplotlib/39502106#39502106


def add_line(ax, xpos, ypos):
    line = plt.Line2D(
        [xpos, xpos],
        [0, ypos],
        transform=ax.transAxes,
        color="black",
        linewidth=1,
    )
    line.set_clip_on(False)
    ax.add_line(line)


def label_len(my_index, level):
    labels = my_index.get_level_values(level)
    return [(k, sum(1 for i in g)) for k, g in groupby(labels)]


def label_group_bar_table(ax, df):
    scale = 1.0 / df.index.size
    for level in range(df.index.nlevels)[::-1]:
        #        print(level)
        pos = 0
        for label, rpos in label_len(df.index, level):
            if level == 0:
                rot = 0
                ypos = -0.2
            else:
                rot = 90
                ypos = -0.15
            lxpos = (pos + 0.5 * rpos) * scale
            ax.text(
                lxpos,
                ypos,
                label.title(),
                ha="center",
                transform=ax.transAxes,
                fontsize=8,
                rotation=rot,
                verticalalignment="bottom",
            )
            add_line(ax, pos * scale, ypos)
            pos += rpos
        add_line(ax, pos * scale, ypos)
        ypos -= 0.1


def plot_grouped_fuels(df, subregion="BA"):
    """Generates a vertical stacked bar plot showing a comparison of the life cycle
    impact analysis contained in the passed dataframe (e.g., a comparison of
    global warming potential). Impacts are separated by techonology and the 
    area of aggregation (e.g., coal, gas, and oil from the different balancing 
    authority areas)
    
    Parameters
    ----------
    df : dataframe
        A dataframe containing the impact emission factors for various stages
        of the electricity life cycle.
    subregion : str, optional
        The regions contained in the passed df, by default "BA".

    Returns
    -------
    matplotlib.axes
        A figure containing a stacked bar comparison of the life cycle
        impact analysis contained in the passed dataframe. 
    """
    cat_column = subregion_col(subregion)
    sub_name = subregion_name(subregion)
    df_generic = an_util.apply_generic_stage_names(df.copy())
    df_generic_grouped = df_generic.groupby(
        cat_column + ["FuelCategory", "generic_stage_name"]
    ).agg({"impact_emission_factor": "sum"})
    df_generic_grouped.reset_index(inplace=True)
    df_generic_grouped.set_index(cat_column + ["FuelCategory"], inplace=True)
    df_generic_grouped = df_generic_grouped.pivot(columns="generic_stage_name")
    df_generic_grouped.columns = df_generic_grouped.columns.droplevel(level=0)
    # Remove following line to run on all BAs
    #    df_sample = df_generic_grouped.iloc[:BA_count]
    df_sample = df_generic_grouped
    #    print(df_sample.columns)
    # Generating Color Palette
    labs = [
        "Oil extraction/refining/transport",
        "Power plant",
        "Construction",
        "Natural gas extraction/transport",
        "Transmission and Distribution",
        "Coal mining/transportation",
        "Nuclear fuel",
    ]
    palette = [
        "#4C72B0",
        "#DD8452",
        "#55A868",
        "#C44E52",
        "#B172B3",
        "#937860",
        "#DA8BC3",
    ]
    col_names = list(df_generic_grouped.columns)
    col_names.sort()

    palette_dict = dict(zip(labs, palette))
    plot_palette = []
    # Plot_palette is a list of colors sorted by the alphabetical order of the mapped subcategory labels
    for col in col_names:
        plot_palette.extend([palette_dict[col]])
    # df_sample[col_names] ensures that the stacked bars are ordered in the proper color order.
    fig = plt.figure(figsize=(max(len(df_generic_grouped) * 0.25, 6), 6))
    ax = fig.add_subplot(111)
    #    df_sample.to_csv('../Output/All Subregions.csv')
    df_sample[col_names].plot(
        kind="bar",
        stacked=True,
        ax=fig.gca(),
        color=plot_palette,
        edgecolor="black",
        linewidth=0.5,
        zorder=3,
    )

    # Adding Grouping Visualization
    labels = ["" for item in ax.get_xticklabels()]
    ax.set_xticklabels(labels)
    ax.set_xlabel("")
    ax.patch.set_linewidth("1")
    label_group_bar_table(ax, df_sample)
    fig.subplots_adjust(bottom=0.02 * df_sample.index.nlevels)

    # General Aesthetics
    ax.set_xlabel(sub_name, fontsize=10, weight="bold", labelpad=100)
    #    print(df.at[min(df.index),"impact_ef_unit"])
    ylabel_tuple = _get_labels(df.at[min(df.index), "impact_ef_unit"])
    ylabel = f"{ylabel_tuple[0]} {ylabel_tuple[1]}"
    #    print(ylabel)
    if abs(max(ax.get_ylim())) < 0.1:
        scientific_notation = True
    else:
        scientific_notation = False
    for xy in zip(ax.get_xticks(), df_sample.sum(axis=1)):
        if scientific_notation:
            datalabel = f"{xy[1]:.2e}"
        else:
            datalabel = f"{xy[1]:.2f}"
        ax.annotate(
            s=datalabel,
            xy=(xy[0] + 0.1, xy[1] + ax.get_ylim()[1] / 100),
            xycoords="data",
            rotation=90,
            fontsize=8,
            ha="center",
        )
    ax.set_ylabel(ylabel, fontsize=10, weight="bold")
    ax.yaxis.grid(color="#7E7D7D", zorder=0)
    ax.xaxis.grid(False)
    ax.set_facecolor("white")
    ax.patch.set_edgecolor("black")

    ax.legend(facecolor="#C5BAA3", frameon=True)
    emission_sum = df["impact_emission_factor"].sum()
    #    emission_sum=0
    #    print(emission_sum)
    graph_title = (
        f"{ylabel_tuple[0]} - Total: {emission_sum:.2e}{ylabel_tuple[1]}"
    )
    ax.set_title(graph_title, fontsize=11, weight="bold", pad=10)
    ax.margins(y=0.15)
    return ax

