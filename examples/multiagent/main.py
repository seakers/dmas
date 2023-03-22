import logging
import zmq
from dmas.clocks import ClockConfig
from dmas.element import SimulationElement
from dmas.messages import *
from dmas.network import NetworkConfig, NetworkElement
from examples.multiagent.agent import AgentNode
from examples.multiagent.environment import EnvironmentNode
from examples.multiagent.manager import SimulationManager
from examples.multiagent.monitor import DummyMonitor
import concurrent.futures

"""
Multi-agent Ping-Pong simulation example.

Agent performs peer-to-peer message with Environment. 
The environment then responds shortly after.
"""

if __name__ == '__main__':
    # set simulation parameters
    level = logging.WARNING
    dt = 3
    f = 2.0
    port = 5555
    n_agents = 2

    # simulation time donfig
    year = 2023
    month = 1
    day = 1
    hh = 12
    mm = 00
    ss = 00
    start_date = datetime(year, month, day, hh, mm, ss)
    end_date = datetime(year, month, day, hh, mm, ss+dt)
    clock_config = AcceleratedRealTimeClockConfig(start_date, end_date, f)

    # initiate simulation monitor
    monitor = DummyMonitor(clock_config, port, level)

    # initiate simulation manager
    sim_element_names = [f'AGENT_{i}' for i in range(n_agents)]
    sim_element_names.append(SimulationElementRoles.ENVIRONMENT.value,)
    manager = SimulationManager(clock_config, 
                                sim_element_names, 
                                port, 
                                logger=monitor.get_logger()
                                )
    
    # initiate simulation environment
    environment = EnvironmentNode(port, logger=monitor.get_logger())
    
    sim_elements = [monitor, manager, environment]
    
    # initiate agent
    network_config = NetworkConfig( 'TEST_NETWORK',
                                    internal_address_map = {},
                                    external_address_map = {
                                                            zmq.REQ: [f'tcp://localhost:{port}'],
                                                            zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                            zmq.PUSH: [f'tcp://localhost:{port+2}']}
                                    )
    for i in range(n_agents):
        agent = AgentNode(f'AGENT_{i}', network_config, logger=monitor.get_logger())
        sim_elements.append(agent)

    # run all simulation elements as separate processes
    with concurrent.futures.ThreadPoolExecutor(len(sim_elements)) as pool:
        for sim_element in sim_elements:
            sim_element : NetworkElement
            pool.submit(sim_element.run, *[])
