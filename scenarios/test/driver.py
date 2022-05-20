import os

import simpy

from src.agents.agent import AbstractAgent
from src.agents.components.components import *
from src.agents.components.instruments import *
from src.planners.planner import *



n = 2
env = simpy.Environment()
agents = []
for i in range(n):
    transmitter = Transmitter(env, 1, 1, 10, 1)
    receiver = Receiver(env, 1, 1, 10, 1)
    generator = PowerGenerator(env, 10)
    battery = Battery(env, 10, 100, 1)
    onboardcomp = OnBoardComputer(env, 1, 100)
    ins = Instrument(env, 'testIns', 1, 1)
    component_list = [transmitter, receiver, generator, battery, onboardcomp, ins]

    planner = Planner()
    agent = AbstractAgent(env, i, component_list=component_list, planner=planner)
    agents.append(agent)

for agent in agents:
    agent.set_other_agents(agents)
    env.process(agent.live())

env.run()
