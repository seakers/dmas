from enum import Enum
from dmas.agents import AgentState

class AgentStatus(Enum):
    IDLING = 'IDLING'
    TRAVELING = 'TRAVELING'
    MEASURING = 'MEASURING'

class SimulationAgentState(AgentState):
    def __init__(self, 
                pos : list, 
                x_bounds : list,
                y_bounds : list,
                vel : list, 
                tasks_performed : list, 
                status : str,
                **_
                ) -> None:
        super().__init__()
        self.pos = pos
        self.x_bounds = x_bounds
        self.y_bounds = y_bounds
        self.vel = vel
        self.tasks_performed = tasks_performed
        self.status = status

    def update_state(self, dt, vel : list=None, tasks_performed : list=[], status : AgentStatus=None):
        # update position
        x, y = self.pos
        vx, vy = self.vel

        x += vx * dt
        y += vy * dt

        if x < min(self.x_bounds):
            x = min(self.x_bounds)
        elif x > max(self.x_bounds):
            x = max(self.x_bounds)

        if y < min(self.y_bounds):
            y = min(self.y_bounds)
        elif y > max(self.y_bounds):
            y = max(self.y_bounds)

        # update velocity
        if vel is not None:
            self.vel = vel

        # update tasks performed
        self.tasks_performed.extend(tasks_performed)

        # update status
        if status is not None:
            self.status = status.value

    def __str__(self):
        return str(self.to_dict())