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

def random_measurements(measurement_types : list, n_max : int = None, n_min : int = None) -> list:
    n_max = n_max if n_max is not None else len(measurement_types)
    n_min = n_min if n_min is not None else 1
    measurements = []
    n_measurements = random.randint(n_min, n_max)
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
    comms_range = 3
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
    dt = 1.0/8.0
    # dt = 0.12

    clock_config = FixedTimesStepClockConfig(start_date, end_date, dt)
    # clock_config = EventDrivenClockConfig(start_date, end_date)

    ## network
    port = random.randint(5555,9999)

    ## loggers
    level = logging.WARNING

    ### random tasks 
    n_tasks = 6
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
    # measurements = [task_types[0], task_types[1]]
    # # s_max = 100 * len(measurements) / len(task_types)
    # tasks.append(MeasurementTask(pos, s_max, measurements, t_start, t_end))

    # pos = [1.0, 2.0]   
    # measurements = [task_types[0]]
    # # s_max = 100 * len(measurements) / len(task_types)
    # tasks.append(MeasurementTask(pos, s_max/3.0, measurements, t_start, t_end))

    # pos = [1.0, 3.0]   
    # measurements = [task_types[1]]
    # # s_max = 100 * len(measurements) / len(task_types)
    # tasks.append(MeasurementTask(pos, s_max/3.0, measurements, t_start, t_end))

    # pos = [2, 3]   
    # measurements = [task_types[0], task_types[1]]
    # # s_max = 100 * len(measurements) / len(task_types)
    # tasks.append(MeasurementTask(pos, s_max, measurements, t_start, t_end, t_corr))

    pos = [1.6584931928268665, 2.2686453819071453]
    measurements = [task_types[0], task_types[1]]
    s_max = 100 if len(measurements) > 1 else 30.0
    tasks.append(MeasurementTask(pos, s_max, measurements, t_start, t_end, t_corr))

    pos = [3.8193647821146692, 2.46260804354465]
    measurements = [task_types[0], task_types[1]]
    s_max = 100 if len(measurements) > 1 else 30.0
    tasks.append(MeasurementTask(pos, s_max, measurements, t_start, t_end, t_corr))

    pos = [3.0840459880745765, 1.5328625005614467]
    measurements = [task_types[1], task_types[0]]
    s_max = 100 if len(measurements) > 1 else 30.0
    tasks.append(MeasurementTask(pos, s_max, measurements, t_start, t_end, t_corr))

    pos = [1.5, 3.5]
    measurements = [task_types[0], task_types[1]]
    s_max = 100 if len(measurements) > 1 else 30.0
    tasks.append(MeasurementTask(pos, s_max, measurements, t_start, t_end, t_corr))

    pos = [1.117248843260703, 2.563973829177466]
    measurements = [task_types[1], task_types[0]]
    s_max = 100 if len(measurements) > 1 else 30.0
    tasks.append(MeasurementTask(pos, s_max, measurements, t_start, t_end, t_corr))

    pos = [3.83865515189413, 1.6213132637921683]
    measurements = [task_types[1]]
    s_max = 100 if len(measurements) > 1 else 30.0
    tasks.append(MeasurementTask(pos, s_max, measurements, t_start, t_end, t_corr))

    while len(tasks) < n_tasks:
        x = x_bounds[0] + (x_bounds[1] - x_bounds[0]) * random.random()
        y = y_bounds[0] + (y_bounds[1] - y_bounds[0]) * random.random()
        pos = [x, y]
        measurements = random_measurements(task_types, 2)
        # measurements = [task_types[0]]
        # s_max = 100 * len(measurements) / len(task_types)
        s_max = 100 if len(measurements) > 1 else 30.0

        task = MeasurementTask(pos, s_max, measurements, t_start, t_end)
        tasks.append(MeasurementTask(pos, s_max, measurements, t_start, t_end))

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

    pos = [0.0, 5.0]
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
    t = None

    # load agent data
    agent_data = {}
    for id in range(n_agents):
        df = pandas.read_csv(f"{results_path}/AGENT_{id}/states.csv")
        agent_data[f'AGENT_{id}'] = df
        if t is None or len(df['t']) < len(t):
            t = df['t']

    # initialize plot
    fig, ax = plt.subplots()

    # plot original agent position
    agent_scats = {}
    agent_lines = {}
    for agent in agent_data:
        agent : str
        _, id = agent.split('_')
        pos_str : str = agent_data[agent]['pos'][0]
        pos_str = pos_str.replace("[","")
        pos_str = pos_str.replace("]","")
        x_str, y_str = pos_str.split(', ')

        agent_scats[agent] = ax.scatter([float(x_str)], [float(y_str)], label=f'{agent}')
        agent_lines[agent] = ax.plot([float(x_str)], [float(y_str)])


    # load measurement location
    measurement_data = pandas.read_csv(f"{results_path}/ENVIRONMENT/measurements.csv")
    
    # plot task location
    print('TASK POSITION')
    print('id, pos, measurements')
    x_tasks = []
    y_tasks = []
    for task in tasks:
        task : MeasurementTask
        x_i, y_i = task.pos
        x_tasks.append(x_i)
        y_tasks.append(y_i)
        # x, y = [x_i], [y_i]
        task_id = task.id.split('-')[0]
        print(f'{task_id},{task.pos},{task.measurements}')

    task_scat = ax.scatter(x_tasks, y_tasks, color='r', marker='*')

    plt.grid(True)
    ax.set(xlim=x_bounds, ylim=y_bounds, xlabel='x', ylabel='y')
    ax.legend()

    def update(frame):
        # update agent states
        for agent in agent_data: 
            x = []
            y = []
            pos_strs : list = agent_data[agent]['pos'][:frame]
            for pos_str in pos_strs:
                pos_str : str
                pos_str = pos_str.replace("[","")
                pos_str = pos_str.replace("]","")
                x_str, y_str = pos_str.split(', ')
                
                x.append( float(x_str) )
                y.append( float(y_str) )

            agent_lines[agent][0].set_xdata(x)
            agent_lines[agent][0].set_ydata(y)
            # agent_lines[agent].set_offsets(data)

            if len(x) > 0:
                x, y = [x[-1]], [y[-1]]
            data = np.stack([x,y]).T
            agent_scats[agent].set_offsets(data)

        # update task status
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
                x_tasks.append(float(x_str))
                y_tasks.append(float(y_str))

            task_scat = ax.scatter(x_tasks, y_tasks, color='g', marker='*')
        else:
            for task in tasks:
                task : MeasurementTask
                x_i, y_i = task.pos
                x_tasks.append(x_i)
                y_tasks.append(y_i)
            task_scat = ax.scatter(x_tasks, y_tasks, color='r', marker='*')


        ax.set_title(f't={t[frame]}[s]')
        out = [agent_scats[agent] for agent in agent_scats]
        out.extend([agent_lines[agent][0] for agent in agent_lines])
        out.append(task_scat)

        ax.set_title(f't={t[frame]}[s]')
        return (p for p in out)
    
    ani = animation.FuncAnimation(fig=fig, func=update, frames=len(t), interval=50)
    

    if plot_results:
        plt.show()
    
    if save_plot:
        ani.save(f'{results_path}/animation.gif', writer='imagemagick')      
        plt.close() 
        print(f'Animated plot saved at: `{results_path}/animation.gif`')

    print('SIM DONE')