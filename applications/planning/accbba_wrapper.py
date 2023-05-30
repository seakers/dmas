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
from actions import MeasurementTask
from manager import PlanningSimulationManager
from monitor import ResultsMonitor
from environment import SimulationEnvironment
from agent import SimulationAgent
from planners.planners import PlannerTypes
from states import *

def random_measurements(measurement_types : list, n_max : int = None) -> list:
    n_max = n_max if n_max is not None else len(measurement_types)
    measurements = []
    n_measurements = random.randint(1, n_max)
    for _ in range(n_measurements):
        i_ins = random.randint(0, len(measurement_types)-1)
        while measurement_types[i_ins] in measurements:
            i_ins = random.randint(0, len(measurement_types)-1)
        measurements.append(measurement_types[i_ins])           
    return measurements


if __name__ == '__main__':
    """
    Wrapper for planner simulation using DMAS
    """    

    # create results directory
    plot_results = True
    save_plot = False
    scenario_name = 'ACCBBA_TEST'
    results_path = setup_results_directory(scenario_name)
    
    # define simulation config
    ## environment bounds
    x_bounds = [0, 5]
    y_bounds = [0, 5]

    ## agents
    n_agents = 2
    comms_range = 20
    v_max = 1

    ## clock configuration
    T = 20
    year = 2023
    month = 1
    day = 1
    hh = 12
    mm = 00
    ss = 00
    start_date = datetime(year, month, day, hh, mm, ss)
    end_date = datetime(year, month, day, hh, mm, ss+T)
    dt = 1.0/4.0
    clock_config = FixedTimesStepClockConfig(start_date, end_date, dt)

    # clock_config = EventDrivenClockConfig(start_date, end_date)

    ## network
    port = random.randint(5555,9999)

    ## loggers
    level = logging.WARNING

    ### random tasks 
    n_tasks = 4
    # task_types = ['MWR', 'IR', 'VNIR']
    task_types = ['MWR', 'IR']
    
    # create tasks
    tasks = []
    s_max = 100.0
    t_start = 0.0
    # t_end = np.Inf
    t_end = T
    t_corr = 1.0

    # pos = [0.0, 2.0]   
    # measurements = [task_types[0]]
    # tasks.append(MeasurementTask(pos, s_max, measurements, t_start, t_end))

    # pos = [1.0, 2.0]   
    # measurements = [task_types[0]]
    # tasks.append(MeasurementTask(pos, s_max, measurements, t_start, t_end))

    # pos = [1.0, 3.0]   
    # measurements = [task_types[0]]
    # tasks.append(MeasurementTask(pos, s_max, measurements, t_start, t_end))

    # pos = [2, 3]   
    # measurements = [task_types[0]]
    # s_max = 100 * len(measurements) / len(task_types)
    # tasks.append(MeasurementTask(pos, s_max, measurements, t_start, t_end, t_corr))

    # pos = [0.582485975658269, 3.176375584717473]
    # measurements = [task_types[1], task_types[0]]
    # s_max = 100 * len(measurements) / len(task_types)
    # tasks.append(MeasurementTask(pos, s_max, measurements, t_start, t_end, t_corr))

    # pos = [4.42695251546435, 1.6151251855783162] 
    # measurements = [task_types[0]]
    # s_max = 100 * len(measurements) / len(task_types)
    # tasks.append(MeasurementTask(pos, s_max, measurements, t_start, t_end, t_corr))

    # while len(tasks) < n_tasks:
    #     x = x_bounds[0] + (x_bounds[1] - x_bounds[0]) * random.random()
    #     y = y_bounds[0] + (y_bounds[1] - y_bounds[0]) * random.random()
    #     pos = [x, y]
    #     measurements = random_measurements(task_types)
    #     # measurements = [task_types[0]]
    #     s_max = 100 * len(measurements) / len(task_types)

    #     task = MeasurementTask(pos, s_max, measurements, t_start, t_end)
    #     tasks.append(MeasurementTask(pos, s_max, measurements, t_start, t_end))

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
    pos = [0.0, 0.0]
    vel = [0.0, 0.0]
    task_types = ['MWR', 'IR', 'VNIR']
    instruments = [task_types[0]]
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

    pos = [1.0, 0.0]
    vel = [0.0, 0.0]
    instruments = [task_types[1]]
    agent_id = 1
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

    # for id in range(n_agents):        
    #     x = x_bounds[0] + (x_bounds[1] - x_bounds[0]) * random.random()
    #     y = y_bounds[0] + (y_bounds[1] - y_bounds[0]) * random.random()  
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
    #                                 PlannerTypes.ACBBA,
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

    # # plot results
    if plot_results:
        t = None

        # load agent data
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
            pos_str : str = agent_data[agent]['pos'][0]
            pos_str = pos_str.replace("[","")
            pos_str = pos_str.replace("]","")
            x_str, y_str = pos_str.split(', ')

            x.append( float(x_str) )
            y.append( float(y_str) )
        agent_scat = ax.scatter(x, y, color='b')
        
        # load measurement location
        measurement_data = pandas.read_csv(f"{results_path}/ENVIRONMENT/measurements.csv")

        # plot task location
        x = []
        y = []
        print('TASK POSITION')
        print('id, pos, measurements')
        for task in tasks:
            task : MeasurementTask
            x_i, y_i = task.pos
            x.append(x_i)
            y.append(y_i)
            task_id = task.id.split('-')[0]
            print(f'{task_id},{task.pos},{task.measurements}')

        task_scat = ax.scatter(x, y, color='r', marker='*')

        def update(frame):
            # update agent states
            x = []
            y = []
            for agent in agent_data: 
                pos_str : str = agent_data[agent]['pos'][frame]
                pos_str = pos_str.replace("[","")
                pos_str = pos_str.replace("]","")
                x_str, y_str = pos_str.split(', ')
                
                x.append( float(x_str) )
                y.append( float(y_str) )
            
            data = np.stack([x,y]).T
            agent_scat.set_offsets(data)

            # TODO update task states
            x_tasks = []
            y_tasks = []
            if frame > 0:
                t_curr = t[frame]
                t_prev = t[frame-1]
                updated_measurements : pandas.DataFrame = measurement_data[measurement_data['t_img'] <= t_curr]
                updated_measurements : pandas.DataFrame = updated_measurements[updated_measurements['t_img'] >= t_prev]
                for _, row in updated_measurements.iterrows():
                    pos_str = row['pos']
                    pos_str = pos_str.replace("[","")
                    pos_str = pos_str.replace("]","")
                    x_str, y_str = pos_str.split(', ')
                    task_scat = ax.scatter(float(x_str), float(y_str), color='g', marker='*')
            else:
                for task in tasks:
                    task : MeasurementTask
                    x_i, y_i = task.pos
                    x_tasks.append(x_i)
                    y_tasks.append(y_i)
                task_scat = ax.scatter(x_tasks, y_tasks, color='r', marker='*')

            ax.set_title(f't={t[frame]}[s]')
            return agent_scat
        
        ani = animation.FuncAnimation(fig=fig, func=update, frames=len(t), interval=50)
        plt.show()
        
        if save_plot:
            ani.save(f'{results_path}/animation.gif', writer='imagemagick')      
            plt.close() 
