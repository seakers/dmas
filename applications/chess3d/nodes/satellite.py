import logging
from typing import Any, Callable
from nodes.planning.planners import PlannerTypes
from nodes.science.science import ScienceModule
from nodes.planning.planners import PlanningModule
from nodes.agent import SimulationAgentState
from dmas.network import NetworkConfig
from nodes.agent import SimulationAgent
import zmq 


class SatelliteAgent(SimulationAgent):
    def __init__(   self, 
                    agent_name: str, 
                    scenario_name: str, 
                    port : int,
                    manager_network_config: NetworkConfig, 
                    agent_network_config: NetworkConfig,
                    initial_state: SimulationAgentState, 
                    planner_type : PlannerTypes,
                    payload: list, 
                    utility_func: Callable[[], Any], 
                    science_module: ScienceModule = None, 
                    level: int = logging.INFO, 
                    logger: logging.Logger = None
                    ) -> None:

        
        super().__init__(agent_name, 
                        scenario_name, 
                        manager_network_config, 
                        agent_network_config, 
                        initial_state, 
                        payload, 
                        utility_func, 
                        planning_module, 
                        science_module, 
                        level, 
                        logger)