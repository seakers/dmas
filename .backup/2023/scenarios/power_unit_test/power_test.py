import os

from agent import AbstractAgent
from dmas.agents.components.components import *
from dmas.agents.components.instruments import *
from dmas.environment import SimulationEnvironment
from dmas.planners.planner import *
from dmas.planners.testPlanners import PowerTracking

# SIMULATION SETUP
from dmas.utils.state_plots import *

T = 30

scenario = 7

dir_path = os.path.dirname(__file__)
env = SimulationEnvironment(dir_path)
agents = []
component_list = None

n = None
if scenario <= 3 or scenario > 7:
    n = 1
elif scenario <= 4:
    n = 2
elif scenario <= 7:
    n = 3

for i in range(n):
    if scenario <= 1:
        # instrument on and off using power generator
        transmitter = Transmitter(env, 1, 1, 10, 1)
        receiver = Receiver(env, 1, 1, 10, 1)
        generator = PowerGenerator(env, 10)
        battery = Battery(env, 0, 100)
        onboardcomp = OnBoardComputer(env, 1, 100)
        ins = Instrument(env, 'instrument', 8, 1)

    elif scenario <= 2:
        # instrument on and off using battery
        transmitter = Transmitter(env, 1, 1, 10, 1)
        receiver = Receiver(env, 1, 1, 10, 1)
        generator = PowerGenerator(env, 0)
        battery = Battery(env, 10, 50)
        onboardcomp = OnBoardComputer(env, 1, 100)
        ins = Instrument(env, 'instrument', 8, 1)

    elif scenario <= 3:
        # battery charges then gets drained and recharged again
        transmitter = Transmitter(env, 1, 1, 10, 1)
        receiver = Receiver(env, 1, 1, 10, 1)
        generator = PowerGenerator(env, 10)
        battery = Battery(env, 10, 100, initial_charge=0.5)
        onboardcomp = OnBoardComputer(env, 1, 100)
        ins = Instrument(env, 'instrument', 18, 1)

    elif scenario <= 4:
        # agent sends message to other agent (Ping)
        transmitter = Transmitter(env, 1, 1, 10, 1)
        receiver = Receiver(env, 1, 1, 10, 1)
        generator = PowerGenerator(env, 10)
        battery = Battery(env, 0, 100)
        onboardcomp = OnBoardComputer(env, 1, 10)
        ins = Instrument(env, 'instrument', 8, 1)

    elif scenario <= 5.5:
        # two agents send a message to the same agent and wait for a channel to open up
        transmitter = Transmitter(env, 1, 1, 10, 1)
        receiver = Receiver(env, 1, 1, 10, 1)
        generator = PowerGenerator(env, 10)
        battery = Battery(env, 0, 100)
        onboardcomp = OnBoardComputer(env, 1, 10)
        ins = Instrument(env, 'instrument', 8, 1)
    elif scenario <= 6.5:
        # two agents send a message to the same agent and wait for memory to be allocated in the buffer.
        transmitter = Transmitter(env, 1, 1, 10, 1)
        receiver = Receiver(env, 1, 1, 5, 1)
        generator = PowerGenerator(env, 10)
        battery = Battery(env, 0, 100)
        onboardcomp = OnBoardComputer(env, 1, 10)
        ins = Instrument(env, 'instrument', 8, 1)
    elif scenario == 7:
        # two agents send a message to the same agent and wait for memory to be allocated in the receiver's
        # on board computer.
        transmitter = Transmitter(env, 1, 1, 10, 1)
        receiver = Receiver(env, 1, 1, 10, 1)
        generator = PowerGenerator(env, 10)
        battery = Battery(env, 0, 100)
        onboardcomp = OnBoardComputer(env, 1, 5)
        ins = Instrument(env, 'instrument', 8, 1)
    elif scenario == 8:
        # agent uses solar panels to generate power, enters eclipse and switches to battery power, and charges
        # batteries when exiting eclipse
        transmitter = Transmitter(env, 1, 1, 10, 1)
        receiver = Receiver(env, 1, 1, 10, 1)
        generator = SolarPanelArray(env, 10)
        battery = Battery(env, 10, 100)
        onboardcomp = OnBoardComputer(env, 1, 5)
        ins = Instrument(env, 'instrument', 8, 1)
    # elif scenario == 9:
    #     # agent 0 sends a message to agent 1, which responds with the same message as soon as it is received (Ping Pong)
    #     pass
    else:
        raise Exception("Scenario not yet supported")

    component_list = [transmitter, receiver, generator, battery, onboardcomp, ins]
    planner = PowerTracking(env, i, component_list, scenario=scenario)
    agent = AbstractAgent(env, i, results_dir=env.results_dir, component_list=component_list, planner=planner)
    agents.append(agent)

for agent in agents:
    agent.set_other_agents(agents)

env.add_agents(agents)

# RUN SIMULATION
env.simulate(T)

# PLOTS
directory_path = os.path.dirname(__file__)
results_dir = directory_path + '/results/'

# -Power Plot
plot_power_state(results_dir, n)

# -Data-rate Plot
plot_data_rate_state(results_dir, n)

# -Data Plot
plot_data_state(results_dir, n)

