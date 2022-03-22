from mesa import Model
from mesa.datacollection import DataCollector
from mesa.time import SimultaneousActivation
from pandas import DataFrame

from src.agents.AbstractAgent import AbstractAgent
from src.agents.planners.CentralizedPlanner import CentralizedPlannerGS


class TestModel(Model):
    """A model with some number of agents."""
    def __init__(self, N, start_epoc=0, time_step=1):
        self.num_agents = N
        self.schedule = SimultaneousActivation(self)
        # Create agents
        for i in range(self.num_agents):
            planner = CentralizedPlannerGS('dshield_centralized', start_epoc=start_epoc, time_step=time_step)
            a = AbstractAgent(i, planner, self, component_list=None)
            self.schedule.add(a)

        self.datacollector = DataCollector(
            model_reporters={}, agent_reporters={"x": "x"}
        )

    def step(self):
        """Advance the model by one step."""
        self.datacollector.collect(self)
        self.schedule.step()

testModel = TestModel(1)
for i in range(10):
    testModel.step()

y = testModel.datacollector.get_agent_vars_dataframe()