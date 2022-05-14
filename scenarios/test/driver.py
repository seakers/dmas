import simpy

from src.agents.agent import AbstractAgent
from src.agents.components.components import *
from src.planners.planner import PingPlanner

n = 2
env = simpy.Environment()
agents = []
for i in range(n):
    transceiver = Transceiver(env, 1, 1, 20)
    data_storage = DataStorage(env, 1, 100)
    planner = PingPlanner()
    agent = AbstractAgent(env, i, component_list=[transceiver, data_storage], planner=planner)
    agents.append(agent)

for agent in agents:
    agent.set_other_agents(agents)
    env.process(agent.live())

env.run(50)