from electricitylci.process_dictionary_writer import exchange, ref_exchange_creator, exchange_table_creation_input_con_mix, process_table_creation_distribution, electricity_at_user_flow
from electricitylci.egrid_facilities import egrid_subregions
from electricitylci.model_config import model_specs


def distribution_mix_dictionary():
    distribution_dict = dict()
    for reg in egrid_subregions:
        exchanges_list =[]
        exchange(ref_exchange_creator(electricity_at_user_flow), exchanges_list)
        exchange(exchange_table_creation_input_con_mix(1/model_specs.efficiency_of_distribution_grid, reg, ref_to_consumption=True), exchanges_list)
        final = process_table_creation_distribution(reg, exchanges_list)
        distribution_dict['Distribution'+reg] = final;
    return distribution_dict
