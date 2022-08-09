from psutil import process_iter
from signal import SIGKILL
from multiprocessing import Process
from dmas.environment import Environment
from dmas.agent import AbstractAgent

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

    environment_port_number='5555'
    request_port_number='5556'

    print('Initializing...')
    environment_port_number = str(get_next_available_port(int(environment_port_number)))
    request_port_number = str(get_next_available_port(int(request_port_number)) + 1)
    environment = Environment("ENV", scenario_dir, ['AGENT0'], 1, 1,
                                environment_port_number=environment_port_number,
                                request_port_number=request_port_number)

    agent_to_port_map = dict()
    agent_to_port_map['AGENT0'] = '5557'

    agent_to_port_map_new = dict()
    for agent_name in agent_to_port_map:
        port = agent_to_port_map[agent_name]
        port_new = get_next_available_port(int(port))
        agent_to_port_map_new[agent_name] = str(port_new)

    agent = AbstractAgent("AGENT0", scenario_dir, agent_to_port_map_new, 1, 
                                    environment_port_number=environment.environment_port_number,
                                    request_port_number=environment.request_port_number)
    
    env_prcs = Process(target=environment.live)
    agent_prcs = Process(target=agent.live)

    agent_prcs.start()
    env_prcs.start()

    env_prcs.join()
    agent_prcs.join