import copy
from datetime import datetime
import logging
import random
import zmq
import concurrent.futures
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import pandas

from dmas.clocks import EventDrivenClockConfig, FixedTimesStepClockConfig
from dmas.elements import SimulationElement
from dmas.messages import SimulationElementRoles
from dmas.network import NetworkConfig

from utils import setup_results_directory
from tasks import MeasurementTask
from manager import PlanningSimulationManager
from monitor import ResultsMonitor
from environment import SimulationEnvironment
from agent import SimulationAgent
from planners import PlannerTypes
from states import *

def random_instruments(task_types : list) -> list:
    instruments = []
    n_instruments = random.randint(1, len(task_types))
    for _ in range(n_instruments):
        i_ins = random.randint(0, len(task_types)-1)
        while task_types[i_ins] in instruments:
            i_ins = random.randint(0, len(task_types)-1)
        instruments.append(task_types[i_ins])           
    return instruments

if __name__ == '__main__':
    """
    Wrapper for planner simulation using DMAS
    """    
    # create results directory
    plot_results = True
    scenario_name = 'TEST'
    results_path = setup_results_directory(scenario_name)
    
    # define simulation config
    ## environment bounds
    x_bounds = [0, 5]
    y_bounds = [0, 5]

    ## agents
    n_agents = 1
    comms_range = 20
    v_max = 1

    ## clock configuration
    T = 10
    year = 2023
    month = 1
    day = 1
    hh = 12
    mm = 00
    ss = 00
    start_date = datetime(year, month, day, hh, mm, ss)
    end_date = datetime(year, month, day, hh, mm, ss+T)
    dt = 1.0/2.0
    clock_config = FixedTimesStepClockConfig(start_date, end_date, dt)

    # clock_config = EventDrivenClockConfig(start_date, end_date)

    ## network
    port = random.randint(5555,9999)

    ## loggers
    level = logging.DEBUG

    ### random tasks 
    n_tasks = 1
    task_types = ['VNIR', 'MWR', 'LIDAR']
    
    # create tasks
    tasks = []
    s_max = 1.0
    t_start = 0.0
    t_end = T

    pos = [1.0, 1.0]   
    instruments = [task_types[0]]
    task = MeasurementTask(pos, s_max, instruments, t_start, t_end)
    tasks.append(MeasurementTask(pos, s_max, instruments, t_start, t_end))

    # pos = [1.0, 2.0]   
    # instruments = [task_types[0]]
    # task = MeasurementTask(pos, s_max, instruments, t_start, t_end)
    # tasks.append(MeasurementTask(pos, s_max, instruments, t_start, t_end))

    # pos = [2.0, 1.0]   
    # instruments = [task_types[0]]
    # task = MeasurementTask(pos, s_max, instruments, t_start, t_end)
    # tasks.append(MeasurementTask(pos, s_max, instruments, t_start, t_end))

    # pos = [2.0, 2.0]   
    # instruments = [task_types[0]]
    # task = MeasurementTask(pos, s_max, instruments, t_start, t_end)
    # tasks.append(MeasurementTask(pos, s_max, instruments, t_start, t_end))

    # for i in range(n_tasks):
        # t_start = random.random() * clock_config.get_total_seconds()
        # t_end = random.random() * (clock_config.get_total_seconds() - t_start) + t_start
        # x = x_bounds[0] + (x_bounds[1] - x_bounds[0]) * random.random()
        # y = y_bounds[0] + (y_bounds[1] - y_bounds[0]) * random.random()
        # pos = [x, y]
        # s_max = 1.0
        # instruments = random_instruments(task_types)

        # task = MeasurementTask(pos, s_max, instruments, t_start, t_end)
        # tasks.append(MeasurementTask(pos, s_max, instruments, t_start, t_end))

    # create simulation manager
    network_name = 'PLANNING_NETWORK'
    manager_network_config = NetworkConfig( network_name,
											manager_address_map = {
																	zmq.REP: [f'tcp://*:{port}'],
																	zmq.PUB: [f'tcp://*:{port+1}'],
                                                                    zmq.SUB: [f'tcp://*:{port+2}'],
																	zmq.PUSH: [f'tcp://localhost:{port+3}']
                                                                    }
                                            )
    node_names = [f'AGENT_{i}' for i in range(n_agents)]
    node_names.append(SimulationElementRoles.ENVIRONMENT.value)
    manager = PlanningSimulationManager(node_names, clock_config, manager_network_config, level)
    logger = manager.get_logger()

    # create results monitor
    monitor_network_config = NetworkConfig( network_name,
                                    external_address_map = {zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                            zmq.PULL: [f'tcp://*:{port+3}']}
                                    )
    
    monitor = ResultsMonitor(clock_config, monitor_network_config, logger=logger)

    # create simulation environment
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
    
    environment = SimulationEnvironment(results_path, env_network_config, manager_network_config, x_bounds, y_bounds, comms_range, copy.deepcopy(tasks), logger=logger)

    # create simulation agents
    agents = []
    pos = [1.0, 0.0]
    vel = [0.0, 0.0]
    instruments = task_types
    agent_id = 0
    initial_state = SimulationAgentState(   pos, 
                                            x_bounds, 
                                            y_bounds, 
                                            vel, 
                                            v_max, 
                                            [],  
                                            status=SimulationAgentState.IDLING,
                                            instruments=instruments)
    agent = SimulationAgent(    results_path,
                                network_name,
                                port, 
                                agent_id,
                                manager_network_config,
                                PlannerTypes.ACCBBA,
                                instruments,
                                initial_state,
                                level,
                                logger
                                )
    agents.append(agent)

    # pos = [2.0, 0.0]
    # vel = [0.0, 0.0]
    # instruments = task_types
    # agent_id = 1
    # initial_state = SimulationAgentState(   pos, 
    #                                         x_bounds, 
    #                                         y_bounds, 
    #                                         vel, 
    #                                         v_max, 
    #                                         [],  
    #                                         status=SimulationAgentState.IDLING,
    #                                         instruments=instruments)
    # agent = SimulationAgent(    results_path,
    #                             network_name,
    #                             port, 
    #                             agent_id,
    #                             manager_network_config,
    #                             PlannerTypes.ACCBBA,
    #                             instruments,
    #                             initial_state,
    #                             level,
    #                             logger
    #                             )
    # agents.append(agent)


    # for id in range(n_agents):        
    #     # x = x_bounds[0] + (x_bounds[1] - x_bounds[0]) * random.random()
    #     # y = y_bounds[0] + (y_bounds[1] - y_bounds[0]) * random.random()  
    #     pos = [x, y]
    #     vel = [0.0, 0.0]
    #     instruments = task_types
    #     # instruments = random_instruments(task_types)
    #     initial_state = SimulationAgentState(   pos, 
    #                                             x_bounds, 
    #                                             y_bounds, 
    #                                             vel, 
    #                                             v_max, 
    #                                             [],  
    #                                             status=SimulationAgentState.IDLING,
    #                                             instruments=instruments)
    #     agent = SimulationAgent(    results_path,
    #                                 network_name,
    #                                 port, 
    #                                 id,
    #                                 manager_network_config,
    #                                 PlannerTypes.ACCBBA,
    #                                 instruments,
    #                                 initial_state,
    #                                 level,
    #                                 logger
    #                                 )
    #     agents.append(agent)

    # run simulation
    with concurrent.futures.ThreadPoolExecutor(len(agents) + 3) as pool:
        pool.submit(monitor.run, *[])
        pool.submit(manager.run, *[])
        pool.submit(environment.run, *[])
        for agent in agents:                
            agent : SimulationElement
            pool.submit(agent.run, *[])

    # TODO Compile and compare planner results
    # for id in range(n_agents):
    #     listener_results = {}
    #     listener_df = pandas.read_csv(f"{results_path}/AGENT_{id}/listener_bids.csv")


    #     bundle_builder_results = {}
    

    # # plot results
    if plot_results:
        t = None
        agent_data = {}
        for id in range(n_agents):
            df = pandas.read_csv(f"{results_path}/AGENT_{id}/states.csv")
            agent_data[f'AGENT_{id}'] = df
            if t is None or len(df['t']) < len(t):
                t = df['t']

        fig, ax = plt.subplots()
        plt.grid(True)
        ax.set_xlim(x_bounds[0], x_bounds[1]) 
        ax.set_ylim(y_bounds[0], y_bounds[1]) 
        ax.set_xlabel('x')
        ax.set_ylabel('x')

        # plot original agent position
        x = []
        y = []
        for agent in agent_data:
            agent : str
            _, id = agent.split('_')
            x.append( agent_data[agent]['x_pos'][0] )
            y.append( agent_data[agent]['y_pos'][0] )
        scat = ax.scatter(x, y, color='b')
        
        # plot task location
        x = []
        y = []
        for task in tasks:
            task : MeasurementTask
            x_i, y_i = task.pos
            x.append(x_i)
            y.append(y_i)
        ax.scatter(x, y, color='r', marker='*')

        def update(frame):
            # update agent states
            x = []
            y = []
            for agent in agent_data: 
                x.append( agent_data[agent]['x_pos'][frame] )
                y.append( agent_data[agent]['y_pos'][frame] )

            # TODO update task states

            # update plots
            data = np.stack([x,y]).T
            scat.set_offsets(data)
            ax.set_title(f't={t[frame]}[s]')
            return scat
        
        ani = animation.FuncAnimation(fig=fig, func=update, frames=len(t), interval=30)
        plt.show()
