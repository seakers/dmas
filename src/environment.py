from simpy import Environment
from simpy.core import SimTime

from src.agents.agent import AbstractAgent


class SimulationEnvironment(Environment):
    def __init__(self, agent_list, initial_time: SimTime = 0):
        super().__init__(initial_time=initial_time)
        self.orbit_data = dict.fromkeys(agent_list, None)

    def is_eclipse(self, agent: AbstractAgent, t: SimTime):
        return self.orbit_data[agent].is_eclipse(t)

