import os

from dmas.agents.agent import AbstractAgent
from dmas.agents.components.components import *
from dmas.agents.components.instruments import Instrument
from dmas.environment import SimulationEnvironment
from dmas.planners.planner import Planner
from dmas.planners.testPlanners import PowerTracking
import subprocess


#RUN ORBITPY
print('Starting OrbitPy\n')
subprocess.run(['python', 'scenarios/orbit_data_test/input/run_mission.py', 'scenarios/orbit_data_test/input/'])
print('\nOrbitPy Complete\n\n\n\n')


# SET-UP SIMULATION
from dmas.utils.state_plots import *

env = SimulationEnvironment()
agents = []
component_list = None
n = 1
T = 60*24

for i in range(n):
    transmitter = Transmitter(env, 1, 1, 10, 1)
    receiver = Receiver(env, 1, 1, 10, 1)
    generator = PowerGenerator(env, 10)
    battery = Battery(env, 0, 100)
    onboardcomp = OnBoardComputer(env, 1, 100)
    ins = Instrument(env, 'instrument', 8, 1)

    component_list = [transmitter, receiver, generator, battery, onboardcomp, ins]
    planner = PowerTracking(env, i, component_list, scenario=1)
    agent = AbstractAgent(env, i, component_list, planner)
    agents.append(agent)

for agent in agents:
    agent.set_other_agents(agents)

env.add_agents(agents)



# RUN SIMULATION
env.simulate(T)

# PLOTS
directory_path = os.getcwd()
results_dir = directory_path + '/results/'

# -Power Plot
# plot_power_state(results_dir, n)
#
# # -Data-rate Plot
# plot_data_rate_state(results_dir, n)

# -Data Plot
plot_data_state(results_dir, n)
