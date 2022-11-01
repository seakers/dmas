import asyncio
from multiprocessing import Process

from agent import ScienceTestAgent
from agent import IridiumTestAgent

def suominpp_run():
    print(f'Suomi NPP run')
    agent = ScienceTestAgent(f'Suomi NPP', './scenarios/sim_test/')
    asyncio.run(agent.live())

def jason_run():
    print(f'Jason-3 run')
    agent = ScienceTestAgent(f'Jason-3', './scenarios/sim_test/')
    asyncio.run(agent.live())

def customsat_run():
    print(f'CustomSat run')
    agent = ScienceTestAgent(f'CustomSat', './scenarios/sim_test/')
    asyncio.run(agent.live())

def iridium_run():
    print(f'Iridium run')
    agent = IridiumTestAgent(f'Iridium', './scenarios/sim_test/')
    asyncio.run(agent.live())

if __name__ == '__main__':
    print('Initializing agents...')

    n_agents = 3
    processes = []
    print('Creating agent run processes...')

    processes.append(Process(target=suominpp_run, args=()))
    processes.append(Process(target=jason_run, args=()))
    processes.append(Process(target=customsat_run, args=()))
    processes.append(Process(target=iridium_run, args=()))
    print('Starting agent run process...')
    for process in processes:
        process.start()

    for process in processes:
        process.join()
    print('Agent runs complete! Simulation ended.')

    