import logging
from typing import Any, Callable, Union
from dmas.agents import AgentAction
from dmas.network import NetworkConfig
from nodes.planning.groundstat import GroundStationPlanner
from nodes.science.science import ScienceModule
from nodes.agent import SimulationAgentState, SimulationAgent
import numpy as np
import zmq

class GroundStationAgent(SimulationAgent):
    def __init__(self, 
                    agent_name: str, 
                    scenario_name: str, 
                    port : int,
                    manager_network_config: NetworkConfig, 
                    initial_state: SimulationAgentState, 
                    utility_func: Callable[[], Any],  
                    measurement_reqs : list = [],
                    science_module : ScienceModule = None,
                    level: int = logging.INFO, 
                    logger: logging.Logger = None
                ) -> None:


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

        results_path = f'./results' + scenario_name + '/' + agent_name
        planning_module = GroundStationPlanner( results_path, 
                                                agent_name, 
                                                measurement_reqs, 
                                                agent_network_config, 
                                                utility_func,
                                                level,
                                                logger)

        super().__init__(   agent_name, 
                            scenario_name,
                            manager_network_config, 
                            agent_network_config, 
                            initial_state, 
                            [], 
                            utility_func, 
                            planning_module, 
                            science_module, 
                            level, 
                            logger)

    async def setup(self) -> None:
        # nothing to setup
        return