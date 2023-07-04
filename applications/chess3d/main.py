from datetime import datetime, timedelta
import json
import logging
from instrupy.base import Instrument
import orbitpy.util
import pandas as pd
import random
import sys
import zmq
import concurrent.futures
from nodes.planning.greedy import GreedyPlanner
from nodes.science.reqs import GroundPointMeasurementRequest
from nodes.actions import TravelAction
from nodes.satellite import SatelliteAgent
from nodes.states import SatelliteAgentState
from nodes.planning.fixed import FixedPlanner
from nodes.planning.planners import PlannerTypes
from nodes.states import GroundStationAgentState
from nodes.groundstat import GroundStationAgent
from nodes.utility import linear_utility
from nodes.agent import SimulationAgent
from utils import *
from dmas.messages import SimulationElementRoles
from dmas.network import NetworkConfig
from dmas.clocks import FixedTimesStepClockConfig, EventDrivenClockConfig
from manager import SimulationManager
from monitor import ResultsMonitor
from nodes.environment import SimulationEnvironment

"""
======================================================
   _____ ____  ________  __________________
  |__  // __ \/ ____/ / / / ____/ ___/ ___/
   /_ </ / / / /   / /_/ / __/  \__ \\__ \ 
 ___/ / /_/ / /___/ __  / /___ ___/ /__/ / 
/____/_____/\____/_/ /_/_____//____/____/       (v1.0)
======================================================
                Texas A&M - SEAK Lab
======================================================

Preliminary wrapper used for debugging purposes
"""
if __name__ == "__main__":
    
    # read system arguments
    scenario_name = sys.argv[1]
    plot_results = True
    save_plot = False
    level = logging.WARNING

    # terminal welcome message
    print_welcome(scenario_name)

    # create results directory
    results_path = setup_results_directory(scenario_name)

    # select unsused port
    port = random.randint(5555, 9999)
    
    # load scenario json file
    scenario_path = f"{scenario_name}" if "./scenarios/" in scenario_name else f'./scenarios/{scenario_name}/'
    scenario_file = open(scenario_path + '/MissionSpecs.json', 'r')
    scenario_dict : dict = json.load(scenario_file)
    scenario_file.close()

    # read agent names
    spacecraft_dict = scenario_dict.get('spacecraft', None)
    uav_dict = scenario_dict.get('uav', None)
    gstation_dict = scenario_dict.get('groundStation', None)

    agent_names = [SimulationElementRoles.ENVIRONMENT.value]
    if spacecraft_dict:
        for spacecraft in spacecraft_dict:
            agent_names.append(spacecraft['name'])
    if uav_dict:
        for uav in uav_dict:
            agent_names.append(uav['name'])
    if gstation_dict:
        for gstation in gstation_dict:
            agent_names.append(gstation['name'])

    # precompute orbit data
    orbitdata_dir = precompute_orbitdata(scenario_name)

    # read clock configuration
    epoch_dict : dict = scenario_dict.get("epoch")
    year = epoch_dict.get('year', None)
    month = epoch_dict.get('month', None)
    day = epoch_dict.get('day', None)
    hh = epoch_dict.get('hour', None)
    mm = epoch_dict.get('minute', None)
    ss = epoch_dict.get('second', None)
    duration = scenario_dict.get("duration")
    start_date = datetime(year, month, day, hh, mm, ss)
    delta = timedelta(days=duration)
    end_date = start_date + delta

    if spacecraft_dict:
        for spacecraft in spacecraft_dict:
            spacecraft_dict : list
            spacecraft : dict
            index = spacecraft_dict.index(spacecraft)
            agent_folder = "sat" + str(index) + '/'

            position_file = orbitdata_dir + agent_folder + 'state_cartesian.csv'
            time_data =  pd.read_csv(position_file, nrows=3)
            l : str = time_data.at[1,time_data.axes[1][0]]
            _, _, _, _, dt = l.split(' ')
            dt = float(dt)
    else:
        dt = delta.total_seconds()/100

    # clock_config = FixedTimesStepClockConfig(start_date, end_date, dt)
    clock_config = EventDrivenClockConfig(start_date, end_date)

    # initialize manager
    manager_network_config = NetworkConfig( scenario_name,
											manager_address_map = {
																	zmq.REP: [f'tcp://*:{port}'],
																	zmq.PUB: [f'tcp://*:{port+1}'],
                                                                    zmq.SUB: [f'tcp://*:{port+2}'],
																	zmq.PUSH: [f'tcp://localhost:{port+3}']
                                                                    }
                                            )


    manager = SimulationManager(agent_names, clock_config, manager_network_config, level)
    logger = manager.get_logger()

    # create results monitor
    monitor_network_config = NetworkConfig( scenario_name,
                                    external_address_map = {zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                            zmq.PULL: [f'tcp://*:{port+3}']}
                                    )
    
    monitor = ResultsMonitor(clock_config, monitor_network_config, logger=logger)

    # create environment
    env_network_config = NetworkConfig( manager.get_network_config().network_name,
											manager_address_map = {
													zmq.REQ: [f'tcp://localhost:{port}'],
													zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                    zmq.PUB: [f'tcp://localhost:{port+2}'],
													zmq.PUSH: [f'tcp://localhost:{port+3}']},
											external_address_map = {
													zmq.REP: [f'tcp://*:{port+4}'],
													zmq.PUB: [f'tcp://*:{port+5}']
											})
    environment = SimulationEnvironment(scenario_path, 
                                        results_path, 
                                        env_network_config, 
                                        manager_network_config,
                                        linear_utility, 
                                        logger=logger)
    port += 6
    
    # Create agents 
    agents = []
    if spacecraft_dict is not None:
        for d in spacecraft_dict:
            # Create spacecraft agents
            
            ## unpack mission specs
            agent_name = d['name']
            planner_dict = d.get('planner', None)
            science_dict = d.get('science', None)
            instruments_dict = d.get('instrument', None)
            orbit_state_dict = d.get('orbitState', None)

            ## create agent network config
            manager_addresses : dict = manager_network_config.get_manager_addresses()
            req_address : str = manager_addresses.get(zmq.REP)[0]
            req_address = req_address.replace('*', 'localhost')

            sub_address : str = manager_addresses.get(zmq.PUB)[0]
            sub_address = sub_address.replace('*', 'localhost')

            pub_address : str = manager_addresses.get(zmq.SUB)[0]
            pub_address = pub_address.replace('*', 'localhost')

            push_address : str = manager_addresses.get(zmq.PUSH)[0]

            agent_network_config = NetworkConfig( 	scenario_name,
                                                    manager_address_map = {
                                                            zmq.REQ: [req_address],
                                                            zmq.SUB: [sub_address],
                                                            zmq.PUB: [pub_address],
                                                            zmq.PUSH: [push_address]},
                                                    external_address_map = {
                                                            zmq.REQ: [],
                                                            zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                            zmq.PUB: [f'tcp://*:{port+2}']},
                                                    internal_address_map = {
                                                            zmq.REP: [f'tcp://*:{port+3}'],
                                                            zmq.PUB: [f'tcp://*:{port+4}'],
                                                            zmq.SUB: [f'tcp://localhost:{port+5}']
                                                })

            ## load payload
            if instruments_dict:
                payload = orbitpy.util.dictionary_list_to_object_list(instruments_dict, Instrument) # list of instruments
            else:
                payload = []

            ## load planner module
            if planner_dict is not None:
                planner_type = planner_dict['@type']
                if planner_type == PlannerTypes.FIXED.value:
                    #--- DEBUG PURPOSES ONLY ----
                    final_pos = [
                                6869.7866357588455,
                                100.55337377743358,
                                100.69348801752179
                                ]
                    plan = [ TravelAction(final_pos, 0.0) ]
                    #----------------------------

                    planner = FixedPlanner(results_path, 
                                           agent_name,
                                           plan, 
                                           agent_network_config,
                                           linear_utility, 
                                           logger=logger)
                elif planner_type == PlannerTypes.GREEDY.value:
                    planner = GreedyPlanner(results_path,
                                            agent_name,
                                            agent_network_config,
                                            linear_utility,
                                            payload,
                                            logger=logger)
                else:
                    raise NotImplementedError(f"Planner of type {planner_type} not yet implemented.")
            else:
                # add default planner if no planner was specified
                # TODO create a dummy default planner that  only listens for plans from the ground and executes them
                
                # DEBUG PURPOSES ONLY:
                final_pos = [
                            6869.7866357588455,
                            100.55337377743358,
                            100.69348801752179
                            ]
                plan = [ TravelAction(final_pos, 0.0) ]

                planner = FixedPlanner(results_path, 
                                           agent_name,
                                           plan, 
                                           agent_network_config,
                                           linear_utility, 
                                           logger=logger)

            ## load science module
            if science_dict is not None:
                raise NotImplementedError(f"Science module not yet implemented.")
            else:
                science = None

            ## load initial state 
            initial_state = SatelliteAgentState(orbit_state_dict, time_step=dt) 

            ## create agent
            agent = SatelliteAgent(agent_name,
                                    scenario_name,
                                    manager_network_config,
                                    agent_network_config,
                                    initial_state, 
                                    planner,
                                    payload,
                                    linear_utility,
                                    science,
                                    logger=logger)
            agents.append(agent)
            port += 6
            
    if uav_dict is not None:
        for d in uav_dict:
            # TODO Create UAV agents
            pass
            agent = None 
            agents.append(agent)

            port += 6

    if gstation_dict is not None:
        # load initial measurement request
        measurement_reqs = []
        df = pd.read_csv(scenario_path + '/gpRequests.csv')
            
        for index, row in df.iterrows():
            pos = [row['lat'], row['lon'], row['alt']]
            s_max = row['s_max']
            
            measurements_str : str = row['measurements']
            measurements_str = measurements_str.replace('[','')
            measurements_str = measurements_str.replace(']','')
            measurements_str = measurements_str.replace(' ','')
            measurements = measurements_str.split(',')

            t_start = row['t_start']
            t_end = row['t_end']
            t_corr = row['t_corr']

            req = GroundPointMeasurementRequest(pos, s_max, measurements, t_start, t_end, t_corr)
            measurement_reqs.append(req)

        for d in gstation_dict:
            # Create ground station agents
            d : dict
            agent_name = d['name']
            lat = d['latitude']
            lon = d['longitude']
            alt = d['altitude']
            initial_state = GroundStationAgentState(lat,
                                                    lon,
                                                    alt)

            agent = GroundStationAgent(agent_name, 
                                        scenario_name,
                                        port,
                                        manager_network_config,
                                        initial_state,
                                        linear_utility,
                                        measurement_reqs=measurement_reqs,
                                        logger=logger)
            agents.append(agent)
            port += 6
            

    # run simulation
    with concurrent.futures.ThreadPoolExecutor(len(agents) + 3) as pool:
        pool.submit(monitor.run, *[])
        pool.submit(manager.run, *[])
        pool.submit(environment.run, *[])
        for agent in agents:                
            agent : SimulationAgent
            pool.submit(agent.run, *[])    
    
    print('\nSIMULATION DONE')
    x = 1