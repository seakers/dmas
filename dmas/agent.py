import asyncio
import json
from multiprocessing import Process
import os
import random
import sys
import threading
import time
import zmq
import zmq.asyncio
import logging

from modules.modules import Module, TestModule

def is_port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def get_next_available_port():
    port = 5555
    while is_port_in_use(port):
        port += 1
    return port

class AbstractAgent(Module):
    def __init__(self, name, scenario_dir, simulation_frequency, modules=[], env_port_number = '5561', env_request_port_number = '5562') -> None:
        super().__init__(name, None, modules)

        # constants
        self.SIMULATION_FREQUENCY = simulation_frequency

        # set up results dir
        self.SCENARIO_RESULTS_DIR, self.AGENT_RESULTS_DIR = self.set_up_results_directory(scenario_dir)

        # set up loggers
        self.message_logger, self.env_request_logger, self.measurement_logger, self.state_logger, self.actions_logger = self.set_up_loggers()
        
        # Network information
        self.ENVIRONMENT_PORT_NUMBER =  env_port_number
        self.REQUEST_PORT_NUMBER = env_request_port_number
        self.AGENT_TO_PORT_MAP = None

        # self.state_logger.info('Agent Initialized!')

    async def live(self):
        """
        MAIN FUNCTION 
        executes event loop for ayncronous processes within the agent
        """
        # Activate 
        await self.activate()

        # Run simulation
        await self.run()

    async def activate(self):
        """
        Initiates and executes commands that are thread-sensitive but that must be performed before the simulation starts.
        """
        self.log(f'Starting activation routine...', level=logging.INFO)

        # initiate network ports and connect to environment server
        self.log('Configuring network ports...')
        await self.network_config()
        self.log('Network configuration completed!')

        # confirm online status to environment server 
        self.log("Synchronizing with environment...")
        await self.sync_environment()
        self.log(f'Synchronization response received! Synchronized with environment.')

        # await for start-simulation message from environment
        self.log(f'Waiting for simulation start broadcast...')
        await self.wait_sim_start()
        self.log(f'Simulation start broadcast received!')

        self.log(f'Activating agent submodules...')
        await super().activate()
        self.log('Agent activated!', level=logging.INFO)

    async def run(self):        
        """
        Performs simulation actions.

        Runs every module owned by the agent. Stops when one of the modules goes off-line, completes its run() routines, 
        or the environment sends a simulation end broadcast.
        """  
        # begin simulation
        self.log(f"Starting simulation...", level=logging.INFO)
        await super().run()

    async def shut_down(self):
        """
        Terminate processes 
        """
        self.log(f"Shutting down agent...", level=logging.INFO)

        self.log(f"Closing all communications channels...")
        self.context.destroy()

        self.log(f'...Good Night!', level=logging.INFO)

    """
    --------------------
    CO-ROUTINES AND TASKS
    --------------------
    """
    async def routine(self):
        """
        Listens for broadcasts from the environment. Stops processes when simulation end-command is received.
        """
        try:
            self.state_logger.debug('Listening to environment broadcasts...')
            while True:
                msg_string = await self.environment_broadcast_socket.recv_json()
                msg_dict = json.loads(msg_string)

                src = msg_dict['src']
                dst = msg_dict['dst']
                msg_type = msg_dict['@type']
                t_server = msg_dict['server_clock']

                self.message_logger.info(f'Received message of type {msg_type} from {src} intended for {dst} with server time of t={t_server}!')

                if msg_type == 'END':
                    self.state_logger.info(f'Sim has ended.')
                    
                    # send a reception confirmation
                    self.env_request_logger.info('Connection to environment established!')
                    self.environment_request_socket.send_string(self.name)
                    self.env_request_logger.info('Agent termination aknowledgement sent. Awaiting environment response...')

                    # wait for server reply
                    await self.environment_request_socket.recv() 
                    self.env_request_logger.info('Response received! terminating agent.')
                    self.log('Simulation end broadcast received! terminating agent...', level=logging.INFO)
                    return

                elif msg_type == 'tic':
                    self.message_logger.info(f'Updating internal clock.')
                    self.sim_time = t_server
        except asyncio.CancelledError:
            return

    """
    --------------------
    HELPING FUNCTIONS
    --------------------    
    """
    async def network_config(self):
        # self.context = zmq.Context() 
        self.context = zmq.asyncio.Context() 

        # subscribe to environment broadcasting port
        self.environment_broadcast_socket = self.context.socket(zmq.SUB)
        self.environment_broadcast_socket.connect(f"tcp://localhost:{self.ENVIRONMENT_PORT_NUMBER}")
        self.environment_broadcast_socket.setsockopt(zmq.SUBSCRIBE, b'')
        
        # give environment time to set up
        time.sleep(random.random())

        # connect to environment request port
        self.environment_request_socket = self.context.socket(zmq.REQ)
        self.environment_request_socket.connect(f"tcp://localhost:{self.REQUEST_PORT_NUMBER}")
        self.environment_request_lock = asyncio.Lock()

        # create agent communication sockets
        self.agent_socket_in = self.context.socket(zmq.REP)
        self.agent_port_in = get_next_available_port()
        self.agent_socket_in.bind(f"tcp://*:{self.agent_port_in}")

        self.agent_socket_out = self.context.socket(zmq.REQ)

    async def sync_environment(self):
        # send a synchronization request to environment server
        self.log('Connection to environment established!')
        await self.environment_request_lock.acquire()

        sync_msg = dict()
        sync_msg['src'] = self.name
        sync_msg['dst'] = 'ENV'
        sync_msg['@type'] = 'SYNC_REQUEST'
        content = dict()
        content['port'] = self.agent_port_in
        sync_msg['content'] = content
        sync_json = json.dumps(sync_msg)

        self.environment_request_socket.send_json(sync_json)
        self.log('Synchronization request sent. Awaiting environment response...')

        # wait for synchronization reply
        await self.environment_request_socket.recv()  
        self.environment_request_lock.release()

    async def wait_sim_start(self):
        # await list of other agent's port numbers
        port_map_msg = await self.environment_broadcast_socket.recv_json()

        # log simulation start time
        self.START_TIME = time.perf_counter()
        self.sim_time = 0

        # register agent-to-port map
        port_map_dict = json.loads(port_map_msg)
        agent_to_port_map = port_map_dict['content']

        self.AGENT_TO_PORT_MAP = dict()
        for agent in agent_to_port_map:
            self.AGENT_TO_PORT_MAP[agent] = agent_to_port_map[agent]
        self.log(f'Agent to port map received:\n{self.AGENT_TO_PORT_MAP}')

    def set_up_results_directory(self, scenario_dir):
        scenario_results_path = scenario_dir + '/results'
        if not os.path.exists(scenario_results_path):
            # if directory does not exists, create it
            os.mkdir(scenario_results_path)

        agent_results_path = scenario_results_path + f'/{self.name}'
        if os.path.exists(agent_results_path):
            # if directory already exists, clear contents
            for f in os.listdir(agent_results_path):
                os.remove(os.path.join(agent_results_path, f)) 
        else:
            # if directory does not exist, create a new onw
            os.mkdir(agent_results_path)

        return scenario_results_path, agent_results_path

    def set_up_loggers(self):
        # set root logger to default settings
        logging.root.setLevel(logging.NOTSET)
        logging.basicConfig(level=logging.NOTSET)
        
        logger_names = ['agent_messages', 'env_requests', 'measurements', 'state', 'actions']

        loggers = []
        for logger_name in logger_names:
            path = self.AGENT_RESULTS_DIR + f'/{logger_name}.log'

            if os.path.exists(path):
                # if file already exists, delete
                os.remove(path)

            # create logger
            logger = logging.getLogger(f'{self.name}_{logger_name}')
            logger.propagate = False

            # create handlers
            c_handler = logging.StreamHandler(sys.stderr)

            if logger_name == 'actions':
                c_handler.setLevel(logging.DEBUG)
            else:
                c_handler.setLevel(logging.WARNING)

            f_handler = logging.FileHandler(path)
            f_handler.setLevel(logging.DEBUG)

            # create formatters
            f_format = logging.Formatter('%(message)s')
            f_handler.setFormatter(f_format)

            # add handlers to logger
            logger.addHandler(c_handler)
            logger.addHandler(f_handler)

            loggers.append(logger)
        return loggers

class AgentState:
    def __init__(self, agent: AbstractAgent, component_list) -> None:
        pass


"""
--------------------
  TESTING AGENTS
--------------------
"""
class TestAgent(AbstractAgent):
    def __init__(self, name, scenario_dir, simulation_frequency, env_port_number='5561', env_request_port_number='5562') -> None:
        super().__init__(name, scenario_dir, simulation_frequency, [], env_port_number, env_request_port_number)
        self.submodules = [TestModule(self)]
    

"""
--------------------
MAIN
--------------------    
"""
if __name__ == '__main__':
    print('Initializing agent...')
    scenario_dir = './scenarios/sim_test'
    
    agent = TestAgent("AGENT0", scenario_dir, 1)
    
    asyncio.run(agent.live())