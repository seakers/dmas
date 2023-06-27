
import numpy as np
from typing import Union
from nodes.agent import SimulationAgentState, SimulationAgentTypes
from nodes.engineering.engineering import EngineeringModule
from dmas.agents import AgentAction

class GroundStationAgentState(SimulationAgentState):
    """
    Describes the state of a Ground Station Agent
    """
    def __init__(self, 
                lat: float, 
                lon: float,
                alt: float, 
                status: str = SimulationAgentState.IDLING, 
                pos : list = None,
                vel : list = None,
                t: Union[float, int] = 0, **_) -> None:
        
        self.lat = lat
        self.lon = lon
        self.alt = alt 

        R = 6.3781363e+003 + alt
        pos = [
                R * np.cos( lat * np.pi / 180.0) * np.cos( lon * np.pi / 180.0),
                R * np.cos( lat * np.pi / 180.0) * np.sin( lon * np.pi / 180.0),
                R * np.sin( lat * np.pi / 180.0)
        ]
        vel = [0, 0, 0]
        
        super().__init__(SimulationAgentTypes.GROUND_STATION.value, 
                        pos, 
                        vel, 
                        None, 
                        status, 
                        t)

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


class SatelliteAgentState(SimulationAgentState):
    """
    Describes the state of a Satellite Agent
    """
    def __init__( self, 
                    # data_dir : str, 
                    t: Union[float, int], 
                    pos: list = None, 
                    vel: list = None, 
                    attitude : float = 0.0,
                    
                    eclipse: bool = None,
                    engineering_module: EngineeringModule = None, 
                    status: str = ..., 
                    **_
                ) -> None:
        # self.data_dir = data_dir
        super().__init__(pos, vel, engineering_module, status, t, **_)
        self.eclipse = eclipse
        self.attitude = attitude

    def propagate(self, _: Union[int, float]) -> tuple:
        # uses pre-computed data from 
        return self.pos, self.vel

    def is_failure(self) -> None:
        if self.engineering_module:
            # agent only fails if internal components fail
            return self.engineering_module.is_failure()
        return False

    def perform_travel(action: AgentAction, t: Union[int, float]) -> tuple:
        # agent cannot travel
        return action.ABORTED, 0.0

    def perform_maneuver(action: AgentAction, t: Union[int, float]) -> tuple:
        # agent cannot maneuver
        return action.ABORTED, 0.0

class UAVAgentState(SimulationAgentState):
    """
    Describes the state of a UAV Agent
    """
    def __init__(self, 
                    pos: list, 
                    vel: list, 
                    engineering_module: EngineeringModule = None, 
                    status: str = ..., 
                    t: Union[float, int] = 0, 
                    **_
                ) -> None:
        super().__init__(pos, vel, engineering_module, status, t, **_)