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

scenario = 4

env = simpy.Environment()
agents = []
component_list = None

if scenario <= 3:
    n = 1
else:
    n = 2

for i in range(n):
    if scenario == 1:
        # instrument on and off using power generator
        transmitter = Transmitter(env, 1, 1, 10, 1)
        receiver = Receiver(env, 1, 1, 10, 1)
        generator = PowerGenerator(env, 10)
        battery = Battery(env, 0, 100)
        onboardcomp = OnBoardComputer(env, 1, 100)
        ins = Instrument(env, 'instrument', 8, 1)

    elif scenario == 2:
        # instrument on and off using battery
        transmitter = Transmitter(env, 1, 1, 10, 1)
        receiver = Receiver(env, 1, 1, 10, 1)
        generator = PowerGenerator(env, 0)
        battery = Battery(env, 10, 100)
        onboardcomp = OnBoardComputer(env, 1, 100)
        ins = Instrument(env, 'instrument', 8, 1)

    elif scenario == 3:
        # battery charges then gets drained and recharged again
        transmitter = Transmitter(env, 1, 1, 10, 1)
        receiver = Receiver(env, 1, 1, 10, 1)
        generator = PowerGenerator(env, 10)
        battery = Battery(env, 10, 100, initial_charge=0.5)
        onboardcomp = OnBoardComputer(env, 1, 100)
        ins = Instrument(env, 'instrument', 18, 1)

    elif scenario == 4:
        # agent sends message to other agent (Ping)
        transmitter = Transmitter(env, 1, 1, 10, 1)
        receiver = Receiver(env, 1, 1, 10, 1)
        generator = PowerGenerator(env, 10)
        battery = Battery(env, 0, 100)
        onboardcomp = OnBoardComputer(env, 1, 100)
        ins = Instrument(env, 'instrument', 8, 1)

        pass
    elif scenario == 5:
        # agent sends message to other agent and responds (Ping pong)
        pass
    elif scenario == 6:
        # agent makes a measurement, sends results to other agent, other agent performs measurement and responds
        pass

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

# -Power Plot
figure, axis = plt.subplots(5, n)

for i in range(n):
    df = pd.read_csv(results_dir + f'A{i}_state.csv')

    axis[0][i].step(df['t'], df['p_in'])
    axis[0][i].set_title("Power Generated [W]")
    axis[0][i].grid(True)

    axis[1][i].step(df['t'], df['p_out'])
    axis[1][i].set_title("Power Consumed [W]")
    axis[1][i].grid(True)

    axis[2][i].step(df['t'], df['p_tot'])
    axis[2][i].set_title("Total Power ")
    axis[2][i].grid(True)

    axis[3][i].step(df['t'], df['p_in'])
    axis[3][i].step(df['t'], -df['p_out'])
    axis[3][i].step(df['t'], df['p_tot'])
    axis[3][i].set_title("Total Power ")
    axis[3][i].grid(True)

    axis[4][i].plot(df['t'], df['e_str']/df['e_cap'])
    axis[4][i].set_title("Battery Charge")
    axis[4][i].grid(True)

plt.subplots_adjust(wspace=0.4,
                    hspace=0.9)
# plt.xticks(np.arange(0, T, 1))
plt.show()

# -Data-rate Plot
figure, axis = plt.subplots(4, n)

for i in range(n):
    df = pd.read_csv(results_dir + f'A{i}_state.csv')

    axis[0][i].step(df['t'], df['r_in'])
    axis[0][i].set_title("Data-rate In [Mbps]")
    axis[0][i].grid(True)

    axis[1][i].step(df['t'], df['r_out'])
    axis[1][i].set_title("Data-rate Out [Mbps]")
    axis[1][i].grid(True)

    axis[2][i].step(df['t'], df['r_tot'])
    axis[2][i].set_title("Data-rate Total [Mbps]")
    axis[2][i].grid(True)

    axis[3][i].step(df['t'], df['r_in'])
    axis[3][i].step(df['t'], -df['r_out'])
    axis[3][i].step(df['t'], df['r_tot'])
    axis[3][i].set_title("Data-rate")
    axis[3][i].grid(True)

plt.subplots_adjust(wspace=0.4,
                    hspace=0.9)
plt.show()

# -Data Plot
figure, axis = plt.subplots(3, n)

for i in range(n):
    df = pd.read_csv(results_dir + f'A{i}_state.csv')

    axis[0][i].plot(df['t'], df['d_in']/df['d_in_cap'])
    axis[0][i].set_title("Incoming Buffer State [%]")
    axis[0][i].grid(True)

    axis[1][i].plot(df['t'], df['d_out']/df['d_out_cap'])
    axis[1][i].set_title("Outgoing Buffer State [%]")
    axis[1][i].grid(True)

    axis[2][i].plot(df['t'], df['d_mem']/df['d_mem_cap'])
    axis[2][i].set_title("Internal Memory State [%]")
    axis[2][i].grid(True)

plt.subplots_adjust(wspace=0.4,
                    hspace=0.9)
plt.show()

# # -Component Status
# figure, axis = plt.subplots(len(component_list), 1)
#
# for i in range(len(component_list)):
#     component = component_list[i]
#     axis[i].step(df['t'], df[component.name])
#     axis[i].set_title(f'{component.name} Status')
#     axis[i].grid(True)
#     plt.ylim([0, 1])
#
# # Combine all the operations and
# plt.subplots_adjust(wspace=0.4,
#                     hspace=0.9)
# # plt.xticks(np.arange(0, T, 1))
# plt.show()
