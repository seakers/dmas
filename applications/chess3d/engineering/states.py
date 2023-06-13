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
                vel : list,
                status : str,
                t : Union[float, int]=0,
                **_
                ) -> None:
        super().__init__()
        self.pos = pos
        self.vel = vel
        self.status = status
        self.t = t
        self.history = []

    # def update_state(self, 
    #                 t : Union[float, int], 
    #                 vel : list=[0.0,0.0], 
    #                 status : str=None):
    #     if t >= self.t:        
    #         # update position with previous state info and new time jump
    #         x, y = self.pos
    #         vx, vy = self.vel

    #         dt = t - self.t
    #         x += vx * dt
    #         y += vy * dt

    #         if x < min(self.x_bounds):
    #             x = min(self.x_bounds)
    #         elif x > max(self.x_bounds):
    #             x = max(self.x_bounds)

    #         if y < min(self.y_bounds):
    #             y = min(self.y_bounds)
    #         elif y > max(self.y_bounds):
    #             y = max(self.y_bounds)

    #         self.pos = [x, y]

    #         # update velocity for future update
    #         if vel is not None:
    #             self.vel = vel  

    #     # update status
    #     if status is not None:
    #         self.status = status

    #     # update last updated time
    #     self.t = t
        
    #     if self.status != self.SENSING:
    #         out = self.to_dict()
    #         self.history.append(out)

    # def propagate_state(
    #                     self, 
    #                     pos : list = None, 
    #                     vel : list = None,  
    #                     t : Union[float, int]=None
    #                     ) -> object:
        
                
    #     future_pos = pos if pos is not None else [v for v in self.pos]
    #     future_vel = vel if vel is not None else [v for v in self.vel]
        
    #     if t is not None:
    #         x_future = self.pos[0] + future_vel[0] * (t - self.t)
    #         y_future = self.pos[1] + future_vel[1] * (t - self.t)
    #         future_pos = [x_future, y_future]

    #     else:
    #         t = self.calc_arrival_time(self.pos, future_pos, self.t)

    #     return SimulationAgentState(future_pos, 
    #                                 self.x_bounds, 
    #                                 self.y_bounds,
    #                                 future_vel,
    #                                 self.v_max,
    #                                 [],
    #                                 self.status,
    #                                 t,
    #                                 self.instruments)              

    # def calc_arrival_time(self, pos_start : list, pos_final : list, t_start : Union[int, float]) -> float:
    #     """
    #     Estimates the quickest arrival time from a starting position to a given final position
    #     """
    #     dpos = np.sqrt( (pos_final[0]-pos_start[0])**2 + (pos_final[1]-pos_start[1])**2 )
    #     return t_start + dpos / self.v_max

    # def is_goal_state(
    #                     self, 
    #                     target_pos : list, 
    #                     dt : Union[float, int] = None,
    #                 ) -> bool:
    #     """
    #     Returns True if a goal state has been reached

    #     ## Arguments:
    #         - target_pos (`list`) : target position at goal state
    #         - target_t (`float` or `int`) : time by which the desired state should be reached by
    #         - clock type (`type`) : Clock type being used to propagation of this state
    #         - target_vel (`list`) : target velocity at goal state
    #         - target_status (`str`) : target status at goal state
    #     """
    #     dx = target_pos[0] - self.pos[0]
    #     dy = target_pos[1] - self.pos[1]

    #     dpos = np.sqrt(dx**2 + dy**2)

    #     if dt is not None:
    #         eps = self.v_max * dt / 2.0
    #     else:
    #         eps = 1e-6        

    #     return dpos < eps

    def __repr__(self) -> str:
        return str(self.to_dict())

    def __str__(self):
        return str(dict(self.__dict__))
    
    def to_dict(self) -> dict:
        out = {
            'pos' : self.pos,
            'vel' : self.vel,
            'status' : self.status,
            't' : self.t
        }

        return out
    
    def is_critial(self) -> bool:
        return False

    def is_failure(self) -> bool:
        return False

    def predict_critical(self) -> float:
        return np.Inf

    def predict_failure(self) -> float:
        return np.Inf