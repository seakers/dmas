from enum import Enum
from dmas.agents import AgentState

class AgentStatus(Enum):
    IDLING = 'IDLING'
    TRAVELING = 'TRAVELING'
    MEASURING = 'MEASURING'

class SimulationAgentState(AgentState):
    def __init__(self, 
                pos : list, 
                vel : list, 
                tasks_performed : list, 
                status : str,
                **_
                ) -> None:
        super().__init__()
        self.pos = pos
        self.vel = vel
        self.tasks_performed = tasks_performed
        self.status = status

    def __str__(self):
        return str(self.to_dict())

if __name__ == '__main__':
    state = SimulationAgentState()