from thermal_simulators.factory import SimulatorFactory
# from rearrange import *
# from therm_xml_parser import *
# from bonding_xml_parser import *
# from heatsink_xml_parser import *
import pickle

if __name__ == "__main__":
    simtype = "Anemoi"
    simulator = SimulatorFactory.get_simulator(simtype)
    # pkl_file = "/app/nanocad/projects/deepflow_thermal/DeepFlow/data_dray1_021825.pkl"
    pkl_file = "/app/nanocad/projects/deepflow_thermal/DeepFlow/data_dray1_051425.pkl"

    with open(pkl_file, 'rb') as f:
        loaded_data = pickle.load(f)

    loaded_values = []
    for key in loaded_data.keys():
        loaded_values.append(loaded_data[key])

    # results = simulator.simulate(*loaded_values)

    print(loaded_data["boxes"])