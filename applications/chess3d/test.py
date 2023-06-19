import json
import os
import random
import sys
import zmq
import concurrent.futures
from manager import SimulationManager
from dmas.network import NetworkConfig
from utils import *

"""
# TEST WRAPPER

Preliminary wrapper used for debugging purposes
"""
if __name__ == "__main__":
    
    # read system arguments
    scenario_name = sys.argv[1]
    plot_results = True
    save_plot = False

    # terminal welcome message
    print_welcome(scenario_name)

    # create results directory
    results_path = setup_results_directory(scenario_name)

    # select unsused port
    port = random.randint(5555, 9999)
    
    # load scenario json file
    scenario_path = f"{scenario_name}/MissionSpecs.json" if "./scenarios/" in scenario_name else f'./scenarios/{scenario_name}/MissionSpecs.json'
    scenario_file = open(scenario_path, 'r')
    scenario_dict : dict = json.load(scenario_file)
    scenario_file.close()

    # read agent names
    spacecraft_dict = scenario_dict.get('spacecraft', None)
    uav_dict = scenario_dict.get('uav', None)
    gstation_dict = scenario_dict.get('groundStation', None)

    agent_names = []
    if spacecraft_dict:
        for spacecraft in spacecraft_dict:
            agent_names.append(spacecraft['name'])
    if uav_dict:
        for uav in uav_dict:
            agent_names.append(uav['name'])
    if gstation_dict:
        for gstation in gstation_dict:
            agent_names.append(gstation['name'])

    # read clock configuration
    # clock_config = 

    # initialize manager
    manager_network_config = NetworkConfig( scenario_name,
											manager_address_map = {
																	zmq.REP: [f'tcp://*:{port}'],
																	zmq.PUB: [f'tcp://*:{port+1}'],
                                                                    zmq.SUB: [f'tcp://*:{port+2}'],
																	zmq.PUSH: [f'tcp://localhost:{port+3}']
                                                                    }
                                            )


    # manager = SimulationManager(agent_names, clock_config, manager_network_config, level)
    # logger = manager.get_logger()
    
    # node_names = [f'AGENT_{i}' for i in range(n_agents)]
    # node_names.append(SimulationElementRoles.ENVIRONMENT.value)
    # manager = PlanningSimulationManager(node_names, clock_config, manager_network_config, level)
    # logger = manager.get_logger()

    # # create results monitor
    # monitor_network_config = NetworkConfig( network_name,
    #                                 external_address_map = {zmq.SUB: [f'tcp://localhost:{port+1}'],
    #                                                         zmq.PULL: [f'tcp://*:{port+3}']}
    #                                 )
    
    # monitor = ResultsMonitor(clock_config, monitor_network_config, logger=logger)

    # # create environment

    # # create agents
    orbitdata_dir = setup_orbitdata_directory(scenario_name)
    # agents = []

    # # run simulation
    # with concurrent.futures.ThreadPoolExecutor(len(agents) + 3) as pool:
    #     pool.submit(monitor.run, *[])
    #     pool.submit(manager.run, *[])
    #     pool.submit(environment.run, *[])
    #     for agent in agents:                
    #         agent : SimulationAgent
    #         pool.submit(agent.run, *[])    
    
    x = 1