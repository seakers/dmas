from mesa import Model
from mesa.datacollection import DataCollector
from mesa.time import SimultaneousActivation
from pandas import DataFrame

from src.agents.AbstractAgent import AbstractAgent
from src.agents.Agents import SimulationAgent
from src.agents.components.Battery import Battery
from src.agents.components.Comms import Comms
from src.agents.planners.CentralizedPlanner import CentralizedPlannerGS, CentralizedPlannerSat
from src.agents.planners.Planner import TestPlanner
from src.agents.planners.TestPlanner import CommsTestPlanner


class TestModel(Model):
    """A model with some number of agents."""
    def __init__(self, N, start_epoc=0, time_step=1):
        self.num_agents = N
        self.schedule = SimultaneousActivation(self)
        # Create agents
        for i in range(self.num_agents):
            planner = TestPlanner(i, start_epoc)
            battery = Battery('testBattery', 0, 2, 20, 1)
            comms = Comms('testComms', 1, 1, 10)
            # a = AbstractAgent(i, planner, self, component_list=[comms, battery])
            a = SimulationAgent(i, planner, self, component_list=[comms, battery])
            # (self, unique_id, planner, model, start_epoc=0, time_step=1, component_list=None)
            self.schedule.add(a)

        # self.datacollector = DataCollector(
        #     model_reporters={}, agent_reporters={"x": "x"}
        # )

    def step(self):
        """Advance the model by one step."""
        # self.datacollector.collect(self)
        self.schedule.step()

testModel = TestModel(3)
for i in range(20):
    print("TICK: " + str(i))
    testModel.step()

# y = testModel.datacollector.get_agent_vars_dataframe()