import asyncio
from multiprocessing import Process

from agent import ScienceTestAgent

def run(i):
        print(f'Mars{i+1} run')
        agent = ScienceTestAgent(f'Mars{i+1}', './scenarios/sim_test/')
        asyncio.run(agent.live())

if __name__ == '__main__':
    print('Initializing agents...')

    n_agents = 2
    processes = []
    print('Creating agent run process...')
    for i in range(n_agents):
        processes.append(Process(target=run, args=(i,)))

    print('Starting agent run process...')
    for process in processes:
        process.start()

    for process in processes:
        process.join()
    print('Agent runs complete! Simulation ended.')

    