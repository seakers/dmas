from typing import Union
import numpy as np
from dmas.agents import AgentState

class SimulationAgentState(AgentState):
    IDLING = 'IDLING'
    TRAVELING = 'TRAVELING'
    MEASURING = 'MEASURING'
    MESSAGING = 'MESSAGING'
    SENSING = 'SENSING'
    THINKING = 'THINKING'
    LISTENING = 'LISTENING'

    def __init__(self, 
                status : str,
                t : Union[float, int]=0,
                **_
                ) -> None:
        super().__init__()
        self.status = status
        self.t = t
    
    def __repr__(self) -> str:
        return str(self.to_dict())

    def __str__(self):
        return str(dict(self.__dict__))
    
    def to_dict(self) -> dict:
        return self.__dict__


