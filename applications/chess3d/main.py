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
from nodes.planning.maccbba import MACCBBA
# from applications.chess3d.nodes.planning.mccbba import MCCBBA
from nodes.states import UAVAgentState
from nodes.uav import UAVAgent
from nodes.planning.greedy import GreedyPlanner
from nodes.science.reqs import GroundPointMeasurementRequest
from nodes.groundstat import GroundStationAgent
from nodes.satellite import SatelliteAgent
from nodes.states import *
from nodes.planning.fixed import FixedPlanner
from nodes.planning.planners import PlannerTypes
from nodes.science.utility import utility_function
from nodes.agent import SimulationAgent
from nodes.states import SimulationAgentTypes
from utils import *
from dmas.messages import SimulationElementRoles
from dmas.network import NetworkConfig
from dmas.clocks import FixedTimesStepClockConfig, EventDrivenClockConfig
from manager import SimulationManager
from monitor import ResultsMonitor
from nodes.environment import SimulationEnvironment
from nodes.science.science import ScienceModule

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
def agent_factory(  scenario_name : str, 
                    scenario_path : str,
                    results_path : str,
                    orbitdata_dir : str,
                    agent_dict : dict, 
                    manager_network_config : NetworkConfig, 
                    port : int, 
                    agent_type : SimulationAgentTypes,
                    clock_config : float,
                    logger : logging.Logger
                ) -> SimulationAgent:
    ## unpack mission specs
    agent_name = agent_dict['name']
    planner_dict = agent_dict.get('planner', None)
    science_dict = agent_dict.get('science', None)
    instruments_dict = agent_dict.get('instrument', None)
    orbit_state_dict = agent_dict.get('orbitState', None)

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
                                                    zmq.SUB: [  
                                                                f'tcp://localhost:{port+5}',
                                                                f'tcp://localhost:{port+6}'
                                                            ]
                                        })

    ## load payload
    if instruments_dict:
        payload = orbitpy.util.dictionary_list_to_object_list(instruments_dict, Instrument) # list of instruments
    else:
        payload = []

    ## load planner module
    if planner_dict is not None:
        planner_type = planner_dict['@type']
        planner_util = planner_dict['utility']
        if planner_type == PlannerTypes.FIXED.value:
            plan = [ ]

            planner = FixedPlanner(results_path, 
                                    agent_name,
                                    plan, 
                                    agent_network_config,
                                    utility_function[planner_util], 
                                    logger=logger)
        elif planner_type == PlannerTypes.GREEDY.value:
            planner = GreedyPlanner(results_path,
                                    agent_name,
                                    agent_network_config,
                                    utility_function[planner_util],
                                    payload,
                                    logger=logger)
        # elif planner_type == PlannerTypes.MCCBBA.value:
        #     planner = MCCBBA(results_path,
        #                         agent_name, 
        #                         agent_network_config,
        #                         utility_function[planner_util],
        #                         payload,
        #                         logger=logger)

        elif planner_type == PlannerTypes.MACCBBA.value:
            planner = MACCBBA(results_path,
                                agent_name, 
                                agent_network_config,
                                utility_function[planner_util],
                                payload,
                                logger=logger)
        else:
            raise NotImplementedError(f"Planner of type {planner_type} not yet implemented.")
    else:
        # add default planner if no planner was specified
        # TODO create a dummy default planner that  only listens for plans from the ground and executes them
        planner = FixedPlanner(results_path, 
                                    agent_name,
                                    [], 
                                    agent_network_config,
                                    utility_function['FIXED'], 
                                    logger=logger)

    ## load science module
    if science_dict is not None:
        science = ScienceModule(results_path,scenario_path,agent_name,agent_network_config,logger=logger)
    else:
        science = None
        # raise NotImplementedError(f"Science module not yet implemented.")
        
    ## create agent
    if agent_type == SimulationAgentTypes.UAV:
        ## load initial state 
            pos = agent_dict['pos']
            max_speed = agent_dict['max_speed']
            if isinstance(clock_config, FixedTimesStepClockConfig):
                eps = max_speed * clock_config.dt / 2.0
            else:
                eps = 1e-6

            initial_state = UAVAgentState( pos, max_speed, eps=eps )

            ## create agent
            return UAVAgent(   agent_name, 
                                results_path,
                                manager_network_config,
                                agent_network_config,
                                initial_state,
                                payload,
                                planner,
                                science,
                                logger=logger
                            )

    elif agent_type == SimulationAgentTypes.SATELLITE:
        agent_folder = "sat" + str(0) + '/'

        position_file = orbitdata_dir + agent_folder + 'state_cartesian.csv'
        time_data =  pd.read_csv(position_file, nrows=3)
        l : str = time_data.at[1,time_data.axes[1][0]]
        _, _, _, _, dt = l.split(' ')
        dt = float(dt)

        initial_state = SatelliteAgentState(orbit_state_dict, time_step=dt) 
        return SatelliteAgent(
                                agent_name,
                                results_path,
                                manager_network_config,
                                agent_network_config,
                                initial_state, 
                                planner,
                                payload,
                                science,
                                logger=logger
                            )
    else:
        raise NotImplementedError(f"agents of type `{agent_type}` not yet supported by agent factory.")


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
    orbitdata_dir = precompute_orbitdata(scenario_name) if spacecraft_dict is not None else None

    # read clock configuration
    epoch_dict : dict = scenario_dict.get("epoch")
    year = epoch_dict.get('year', None)
    month = epoch_dict.get('month', None)
    day = epoch_dict.get('day', None)
    hh = epoch_dict.get('hour', None)
    mm = epoch_dict.get('minute', None)
    ss = epoch_dict.get('second', None)
    start_date = datetime(year, month, day, hh, mm, ss)
    delta = timedelta(days=scenario_dict.get("duration"))
    end_date = start_date + delta

    ## define simulation clock
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

    ## load initial measurement request
    measurement_reqs = []
    df = pd.read_csv(scenario_path + '/gpRequests.csv')
        
    for _, row in df.iterrows():
        s_max = row['s_max']
        
        measurements_str : str = row['measurements']
        measurements_str = measurements_str.replace('[','')
        measurements_str = measurements_str.replace(']','')
        measurements_str = measurements_str.replace(' ','')
        measurements = measurements_str.split(',')

        t_start = row['t_start']
        t_end = row['t_end']
        t_corr = row['t_corr']

        lat, lon, alt = row.get('lat', None), row.get('lon', None), row.get('alt', None)
        if lat is None and lon is None and alt is None: 
            x_pos, y_pos, z_pos = row.get('x_pos', None), row.get('y_pos', None), row.get('z_pos', None)
            if x_pos is not None and y_pos is not None and z_pos is not None:
                pos = [x_pos, y_pos, z_pos]
                lat, lon, alt = 0.0, 0.0, 0.0
            else:
                raise ValueError('GP Measurement Requests in `gpRequest.csv` must specify a ground position as lat-lon-alt or cartesian coordinates.')
        else:
            pos = None

        lan_lon_pos = [lat, lon, alt]
        req = GroundPointMeasurementRequest(lan_lon_pos, s_max, measurements, t_start, t_end, t_corr, pos=pos)
        measurement_reqs.append(req)

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
    scenario_config_dict : dict = scenario_dict['scenario']
    env_utility_function = scenario_config_dict.get('utility', 'LINEAR')
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
                                        utility_function[env_utility_function],
                                        measurement_reqs, 
                                        logger=logger)
    port += 6
    
    # Create agents 
    agents = []
    if spacecraft_dict is not None:
        for d in spacecraft_dict:
            # Create spacecraft agents
            agent = agent_factory(  scenario_name, 
                                    scenario_path, 
                                    results_path, 
                                    orbitdata_dir, 
                                    d, 
                                    manager_network_config, 
                                    port, 
                                    SimulationAgentTypes.SATELLITE, 
                                    clock_config, 
                                    logger
                                )
            agents.append(agent)
            port += 6

    agents = []
    if uav_dict is not None:
        # Create uav agents
        for d in uav_dict:
            agent = agent_factory(  scenario_name, 
                                    scenario_path, 
                                    results_path, 
                                    orbitdata_dir, 
                                    d, 
                                    manager_network_config, 
                                    port, 
                                    SimulationAgentTypes.UAV, 
                                    clock_config, 
                                    logger
                                )
            agents.append(agent)
            port += 6

    if gstation_dict is not None:
        # Create ground station agents
        for d in gstation_dict:
            d : dict
            agent_name = d['name']
            lat = d['latitude']
            lon = d['longitude']
            alt = d['altitude']
            initial_state = GroundStationAgentState(lat,
                                                    lon,
                                                    alt)

            agent = GroundStationAgent( agent_name, 
                                        results_path,
                                        scenario_name,
                                        port,
                                        manager_network_config,
                                        initial_state,
                                        utility_function[env_utility_function],
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