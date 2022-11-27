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

def cryosat_run(directory):
    print(f'CryoSat-2 run')
    agent = ScienceTestAgent(f'CryoSat-2', directory)
    asyncio.run(agent.live())

def swot_run(directory):
    print(f'SWOT run')
    agent = ScienceTestAgent(f'SWOT', directory)
    asyncio.run(agent.live())

def sentinel6a_run(directory):
    print(f'Sentinel-6A run')
    agent = ScienceTestAgent(f'Sentinel-6A', directory)
    asyncio.run(agent.live())

def sentinel6b_run(directory):
    print(f'Sentinel-6B run')
    agent = ScienceTestAgent(f'Sentinel-6B', directory)
    asyncio.run(agent.live())

def customsat_run(directory):
    print(f'CustomSat run')
    agent = ScienceTestAgent(f'CustomSat', directory)
    asyncio.run(agent.live())

def landsat_run(directory):
    print(f'Landsat run')
    agent = ScienceTestAgent(f'Landsat 9', directory)
    asyncio.run(agent.live())


def iridium_run(directory):
    print(f'Iridium run')
    agent = IridiumTestAgent(f'Iridium', directory)
    asyncio.run(agent.live())

if __name__ == '__main__':
    print('Initializing agents...')
    directory = ["./scenarios/landsat_altimeters/"]

    n_agents = 3
    processes = []
    print('Creating agent run processes...')

    #processes.append(Process(target=suominpp_run, args=(directory)))
    processes.append(Process(target=jason_run, args=(directory)))
    processes.append(Process(target=swot_run, args=(directory)))
    processes.append(Process(target=sentinel6a_run, args=(directory)))
    processes.append(Process(target=sentinel6b_run, args=(directory)))
    processes.append(Process(target=cryosat_run, args=(directory)))
    processes.append(Process(target=landsat_run, args=(directory)))
    #processes.append(Process(target=customsat_run, args=(directory)))
    processes.append(Process(target=iridium_run, args=(directory)))
    print('Starting agent run process...')
    for process in processes:
        process.start()

    for process in processes:
        process.join()
    print('Agent runs complete! Simulation ended.')

    