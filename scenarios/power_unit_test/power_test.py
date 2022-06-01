import os

import numpy as np

from src.agents.agent import AbstractAgent
from src.agents.components.components import *
from src.agents.components.instruments import *
from src.planners.planner import *
from src.planners.testPlanners import PowerTracking
import pandas as pd
import matplotlib.pyplot as plt


# SIMULATION SETUP
T = 30
n = 1
scenario = 3
env = simpy.Environment()
agents = []
component_list = None
for i in range(n):
    if scenario == 1:
        transmitter = Transmitter(env, 1, 1, 10, 1)
        receiver = Receiver(env, 1, 1, 10, 1)
        generator = PowerGenerator(env, 10)
        battery = Battery(env, 0, 100, initial_charge=1)
        onboardcomp = OnBoardComputer(env, 1, 100)
        ins = Instrument(env, 'instrument', 8, 1)

    elif scenario == 2:
        transmitter = Transmitter(env, 1, 1, 10, 1)
        receiver = Receiver(env, 1, 1, 10, 1)
        generator = PowerGenerator(env, 0)
        battery = Battery(env, 10, 100, initial_charge=1)
        onboardcomp = OnBoardComputer(env, 1, 100)
        ins = Instrument(env, 'instrument', 8, 1)

    elif scenario == 3:
        transmitter = Transmitter(env, 1, 1, 10, 1)
        receiver = Receiver(env, 1, 1, 10, 1)
        generator = PowerGenerator(env, 10)
        battery = Battery(env, 10, 100, initial_charge=0.5)
        onboardcomp = OnBoardComputer(env, 1, 100)
        ins = Instrument(env, 'instrument', 8, 1)

    else:
        raise Exception("Scenario not yet supported")

    component_list = [transmitter, receiver, generator, battery, onboardcomp, ins]
    planner = PowerTracking(env, i, component_list, scenario=scenario)
    agent = AbstractAgent(env, i, component_list=component_list, planner=planner)
    agents.append(agent)

for agent in agents:
    agent.set_other_agents(agents)
    env.process(agent.live())

# RUN SIMULATION
env.run(until=T)

# PRINT AGENT STATE HISTORY
for agent in agents:
    agent.print_state()

# PLOTS
directory_path = os.getcwd()
results_dir = directory_path + '/results/'
df = pd.read_csv(results_dir + 'A0_state.csv')

# -Power Plot
figure, axis = plt.subplots(5, 1)

axis[0].step(df['t'], df['p_in'])
axis[0].set_title("Power Generated [W]")
axis[0].grid(True)

axis[1].step(df['t'], df['p_out'])
axis[1].set_title("Power Consumed [W]")
axis[1].grid(True)

axis[2].step(df['t'], df['p_tot'])
axis[2].set_title("Total Power ")
axis[2].grid(True)

axis[3].step(df['t'], df['p_in'])
axis[3].step(df['t'], -df['p_out'])
axis[3].step(df['t'], df['p_tot'])
axis[3].set_title("Total Power ")
axis[3].grid(True)

axis[4].plot(df['t'], df['e_str']/df['e_cap'])
axis[4].set_title("Battery Charge")
axis[4].grid(True)

# Combine all the operations and
plt.subplots_adjust(wspace=0.4,
                    hspace=0.9)
# plt.xticks(np.arange(0, T, 1))
plt.show()

# -Component Status
figure, axis = plt.subplots(len(component_list), 1)

for i in range(len(component_list)):
    component = component_list[i]
    axis[i].step(df['t'], df[component.name])
    axis[i].set_title(f'{component.name} Status')
    axis[i].grid(True)
    plt.ylim([0, 1])

# Combine all the operations and
plt.subplots_adjust(wspace=0.4,
                    hspace=0.9)
# plt.xticks(np.arange(0, T, 1))
plt.show()
