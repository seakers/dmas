from typing import Union
from dmas.agents import AgentState

class SimulationAgentState(AgentState):
    IDLING = 'IDLING'
    TRAVELING = 'TRAVELING'
    MEASURING = 'MEASURING'
    MESSAGING = 'MESSAGING'
    SENSING = 'SENSING'
    THINKING = 'THINKING'

    def __init__(self, 
                pos : list, 
                x_bounds : list,
                y_bounds : list,
                vel : list, 
                v_max : float, 
                tasks_performed : list, 
                status : str,
                t : Union[float, int]=0,
                **_
                ) -> None:
        super().__init__()
        self.pos = pos
        self.x_bounds = x_bounds
        self.y_bounds = y_bounds
        self.vel = vel
        self.v_max = v_max
        self.tasks_performed = tasks_performed
        self.status = status
        self.t = t

        self.history = []

    def update_state(self, t : Union[float, int], vel : list=None, tasks_performed : list=[], status : str=None):
        if t > self.t:        
            # update position with previous state info and new time jump
            x, y = self.pos
            vx, vy = self.vel

            dt = t - self.t
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

            # update velocity for future update
            if vel is not None:
                self.vel = vel

        # update tasks performed
        self.tasks_performed.extend(tasks_performed)

        # update status
        if status is not None:
            self.status = status

        # update last updated time
        self.t = t
        
        out = self.to_dict()
        self.history.append(out)

    def __str__(self):
        return str(self.to_dict())
    
    def to_dict(self) -> dict:
        out = super().to_dict().copy()
        out.pop('history')
        return out
    
    def is_critial(self) -> bool:
        False

    def is_failure(self) -> bool:
        return False