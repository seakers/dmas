import logging
from typing import Any, Callable
from nodes.agent import SimulationAgent
from nodes.planning.planners import PlanningModule
from nodes.science.science import ScienceModule
from nodes.states import SimulationAgentState
from dmas.network import NetworkConfig


class UAVAgent(SimulationAgent):
    def __init__(   
                    self, 
                    agent_name: str,    
                    results_path: str, 
                    manager_network_config: NetworkConfig, 
                    agent_network_config: NetworkConfig, 
                    initial_state: SimulationAgentState, 
                    payload: list, 
                    planning_module: PlanningModule = None, 
                    science_module: ScienceModule = None, 
                    level: int = logging.INFO, 
                    logger: logging.Logger = None
                ) -> None:

        super().__init__(
                        agent_name, 
                        results_path, 
                        manager_network_config, 
                        agent_network_config, 
                        initial_state, 
                        payload, 
                        planning_module, 
                        science_module, 
                        level, 
                        logger
                    )

    async def setup(self) -> None:
        # nothing to setup
        return