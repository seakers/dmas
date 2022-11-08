import asyncio
from multiprocessing import Process

from agent import ScienceTestAgent
from agent import IridiumTestAgent



def suominpp_run(directory):
    print(f'Suomi NPP run')
    agent = ScienceTestAgent(f'Suomi NPP', directory)
    asyncio.run(agent.live())

def jason_run(directory):
    print(f'Jason-3 run')
    agent = ScienceTestAgent(f'Jason-3', directory)
    asyncio.run(agent.live())

def customsat_run(directory):
    print(f'CustomSat run')
    agent = ScienceTestAgent(f'CustomSat', directory)
    asyncio.run(agent.live())

def iridium_run(directory):
    print(f'Iridium run')
    agent = IridiumTestAgent(f'Iridium', directory)
    asyncio.run(agent.live())

if __name__ == '__main__':
    print('Initializing agents...')
    directory = ["./scenarios/default_mission/"]

    n_agents = 3
    processes = []
    print('Creating agent run processes...')

    processes.append(Process(target=suominpp_run, args=(directory)))
    processes.append(Process(target=jason_run, args=(directory)))
    processes.append(Process(target=customsat_run, args=(directory)))
    processes.append(Process(target=iridium_run, args=(directory)))
    print('Starting agent run process...')
    for process in processes:
        process.start()

    for process in processes:
        process.join()
    print('Agent runs complete! Simulation ended.')

    