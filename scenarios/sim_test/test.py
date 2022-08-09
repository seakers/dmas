from multiprocessing import Process
from dmas.environment import Environment
from dmas.agent import AbstractAgent

scenario_dir = './scenarios/sim_test/'
agent_to_port_map = dict()
agent_to_port_map['AGENT0'] = '5557'

if __name__ == '__main__':
    environment = Environment("ENV", scenario_dir, 'AGENT0', 1, 1)
    agent = AbstractAgent("AGENT0", scenario_dir, agent_to_port_map, 1)
    
    env_prcs = Process(target=environment.live)
    agent_prcs = Process(target=agent.live)

    env_prcs.start()
    agent_prcs.start()

    env_prcs.join()
    agent_prcs.join