import numpy as np
from simpy.core import SimTime

from src.agents.agent import AbstractAgent


class OrbitData:
    def __init__(self, agent: AbstractAgent):
        self.parent_agent = agent
        # self.eclipse_intervals = [(4.5, 6.5)]
        self.eclipse_intervals = []
        return

    def get_next_eclipse(self, t: SimTime):
        for interval in self.eclipse_intervals:
            t_start, t_end = interval
            if t_end <= t:
                continue
            elif t < t_start:
                return t_start
            elif t < t_end:
                return t_end
        return np.Infinity

    def is_eclipse(self, t: SimTime):
        for interval in self.eclipse_intervals:
            t_start, t_end = interval
            if t_start <= t <= t_end:
                return True
        return False

    def get_position(self, t: SimTime):
        return [-1, -1, -1]

    def get_velocity(self, t: SimTime):
        return [-1, -1, -1]