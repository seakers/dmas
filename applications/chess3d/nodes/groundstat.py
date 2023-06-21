import logging
from typing import Union
from dmas.agents import AgentAction
from dmas.network import NetworkConfig
from nodes.agent import SimulationAgentState, SimulationAgent
import numpy as np

class GroundStationAgentState(SimulationAgentState):
    """
    Descibes the state of a Ground Station Agent
    """
    def __init__(self, 
                lat: float, 
                lon: float,
                alt: float, 
                status: str = SimulationAgentState.IDLING, 
                t: Union[float, int] = 0, **_) -> None:
        
        R = 6.3781363e+003 + alt
        pos = [
                R * np.cos( lat * np.pi / 180.0) * np.cos( lon * np.pi / 180.0),
                R * np.cos( lat * np.pi / 180.0) * np.sin( lon * np.pi / 180.0),
                R * np.sin( lat * np.pi / 180.0)
        ]
        vel = [0, 0, 0]
        
        super().__init__(pos, vel, None, status, t, **_)

    def propagate(self, _: Union[int, float]) -> tuple:
        # agent does not move
        return self.pos, self.vel

    def is_failure(self) -> None:
        # agent never fails
        return False

    def perform_travel(action: AgentAction, t: Union[int, float]) -> tuple:
        # agent cannot travel
        return action.ABORTED, 0.0

    def perform_maneuver(action: AgentAction, t: Union[int, float]) -> tuple:
        # agent cannot maneuver
        return action.ABORTED, 0.0

class GroundStationAgent(SimulationAgent):
    def __init__(self, 
                    agent_name: str, 
                    scenario_name: str, 
                    manager_network_config: NetworkConfig, 
                    agent_network_config: NetworkConfig,
                    initial_state: SimulationAgentState, 
                    payload: list, 
                    utility_func: function,  
                    level: int = logging.INFO, 
                    logger: logging.Logger = None
                ) -> None:
        super().__init__(agent_name, scenario_name, manager_network_config, agent_network_config, initial_state, payload, utility_func, planning_module, science_module, level, logger)