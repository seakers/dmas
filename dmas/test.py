import asyncio
from multiprocessing import Process

from agent import TestAgent


if __name__ == '__main__':
    print('Initializing agent...')
    
    
    def run(i):
        agent = TestAgent(f'Mars{i+1}', './scenarios/sim_test')
        asyncio.run(agent.live())

    n_agents = 2

    processes = []
    for i in range(n_agents):
        processes.append(Process(target=run, args=(i,)))

    for process in processes:
        process.start()

    for process in processes:
        process.join()

    