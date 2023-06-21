from typing import Union
from nodes.engineering.engineering import EngineeringModule
from nodes.agent import SimulationAgentState


class SatelliteAgentState(SimulationAgentState):
    def __init__(self, 
                    pos: list, 
                    vel: list, 
                    eclise: bool,
                    engineering_module: EngineeringModule = None, 
                    status: str = ..., 
                    t: Union[float, int] = 0, 
                    **_
                ) -> None:
        super().__init__(pos, vel, engineering_module, status, t, **_)
        self.eclipse = eclise