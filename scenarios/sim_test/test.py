from psutil import process_iter
from signal import SIGKILL
from multiprocessing import Process
from dmas.environment import EnvironmentServer
from agent import AgentNode

def is_port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def get_next_available_port(port: int):
    while is_port_in_use(port):
        port += 1
    return port

def terminate_ports():
    for proc in process_iter():
        proc.kill()
        # for conns in proc.get_connections(kind='inet'):
        #     if conns.laddr[1] == 1300:
        #         proc.send_signal(SIGKILL) 
        #         continue

if __name__ == '__main__':
    print('STARTING SIMULATION')
    scenario_dir = './scenarios/sim_test'
    agent_to_port_map = dict()
    agent_to_port_map['AGENT0'] = '5557'
    
    environment = EnvironmentServer("ENV", scenario_dir, ['AGENT0'], simulation_frequency=1, duration=10)   
    agent = AgentNode("AGENT0", scenario_dir, agent_to_port_map, 1)
    
    env_prcs = Process(target=environment.live)
    agent_prcs = Process(target=agent.live)

    agent_prcs.start()
    env_prcs.start()

    env_prcs.join()
    agent_prcs.join