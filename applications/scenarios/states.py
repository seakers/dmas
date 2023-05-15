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
                pos : list, 
                x_bounds : list,
                y_bounds : list,
                vel : list, 
                v_max : float, 
                actions_performed : list, 
                status : str,
                t : Union[float, int]=0,
                instruments : list = [],
                **_
                ) -> None:
        super().__init__()
        self.pos = pos
        self.x_bounds = x_bounds
        self.y_bounds = y_bounds
        self.vel = vel
        self.v_max = v_max
        self.actions_performed = actions_performed
        self.status = status
        self.t = t
        self.history = []
        self.instruments = instruments

    def update_state(self, 
                    t : Union[float, int], 
                    vel : list=None, 
                    actions_performed : list=[], 
                    status : str=None):
        if t >= self.t:        
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

            self.pos = [x, y]

            # update velocity for future update
            if vel is not None:
                self.vel = vel  

        # update tasks performed
        self.actions_performed.extend(actions_performed)

        # update status
        if status is not None:
            self.status = status

        # update last updated time
        self.t = t
        
        if self.status != self.SENSING:
            out = self.to_dict()
            self.history.append(out)

    def __repr__(self) -> str:
        return str(self.to_dict())

    def __str__(self):
        return str(dict(self.__dict__))
    
    def to_dict(self) -> dict:
        out = super().to_dict().copy()
        out.pop('history')
        return out
    
    def is_critial(self) -> bool:
        return False

    def is_failure(self) -> bool:
        return False

    def predict_critical(self) -> float:
        return np.Inf

    def predict_failure(self) -> float:
        return np.Inf