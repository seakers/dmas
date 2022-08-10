import os
# os.environ['PYTHONASYNCIODEBUG'] = '0'
import asyncio
import json
import logging
from multiprocessing import Process
import threading
import time
import zmq
import zmq.asyncio

def is_port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

class Environment:
    def __init__(self, name, scenario_dir, agent_name_list: list, simulation_frequency, duration) -> None:
        # Constants
        self.name = name                                                # Environment Name
        self.SIMULATION_FREQUENCY = simulation_frequency                # Ratio of simulation-time to real-time
        self.DURATION = duration                                        # Duration of simulation in simulation-time
        self.NUMBER_AGENTS = len(agent_name_list)                       # Number of agents present in the simulation
        self.AGENT_NAME_LIST = []                                       # List of names of agent present in the simulation
        for agent_name in agent_name_list:
            self.AGENT_NAME_LIST.append(agent_name)
        
        # set up results dir
        self.SCENARIO_RESULTS_DIR, self.ENVIRONMENT_RESULTS_DIR = self.set_up_results_directory(scenario_dir)

        # set up loggers
        [self.message_logger, self.request_logger, self.state_logger] = self.set_up_loggers()
        
        self.state_logger.info('Environment Initialized!')

    def main(self):
        """
        MAIN FUNCTION 
        """
        # Activate 
        self.activate()

        # Run simulation
        self.live()

        # Turn off
        self.shut_down()

    def activate(self):
        """
        Initiates and executes commands that are thread-sensitive but that must be performed before the simulation starts.
        """
        self.state_logger.info('Starting activation routine...')
        
        # activate network ports
        self.state_logger.info('Configuring network ports...')
        self.network_config()
        self.state_logger.info('Network configuration completed!')

        # Wait for agents to initialize their own network ports
        self.state_logger.info(f"Waiting for {self.NUMBER_AGENTS} to initiate...")
        self.sync_agents()
        self.state_logger.info(f"All subscribers initalized! Starting simulation...")

        self.state_logger.info('Environment Activated!')

    def live(self):
        """
        Performs simulation actions 
        """
        self.state_logger.info(f"Starting simulation...")
        
        asyncio.run(self.excute_coroutines())
        
    def shut_down(self):
        """
        Terminate processes 
        """
        self.state_logger.info(f"Shutting down...")

        # broadcast simulation end
        self.broadcast_end()

        # close network ports     
        self.publisher.close()
        self.reqservice.close()
        self.context.term()
        self.state_logger.info(f"Network ports closed.")
        
        self.state_logger.info(f"Good night!")

    """
    --------------------
    CO-ROUTINES AND TASKS
    --------------------
    """
    async def excute_coroutines(self):
        # await asyncio.gather( 
        #     self.sim_wait(self.DURATION)
        # )
        t1 = asyncio.create_task(self.sim_wait(self.DURATION))
        t2 = asyncio.create_task(self.tic_broadcast())

        await t1
        t2.cancel()
        await t2
        self.state_logger.info(f"Simulation time completed!")

    async def sim_wait(self, delay):
        """
        Sleeps for a given amout of time
        delay: simulation time to be waited
        """
        await asyncio.sleep(delay/self.SIMULATION_FREQUENCY)

    async def tic_broadcast(self):
        try:
            while True:
                msg_dict = dict()
                msg_dict['src'] = self.name
                msg_dict['dst'] = 'all'
                msg_dict['@type'] = 'tic'
                msg_dict['server_clock'] = time.perf_counter()
                msg_json = json.dumps(msg_dict)

                t = msg_dict['server_clock']
                self.message_logger.debug(f'Broadcasting server tic at t={t}')
                self.state_logger.debug(f'Broadcasting server tic at t={t}')

                self.publisher.send_json(msg_json)

                await self.sim_wait(1)
        except asyncio.CancelledError:
            return

    def broadcast_end(self):
        # broadcast simulation end to all subscribers
        msg_dict = dict()
        msg_dict['src'] = self.name
        msg_dict['dst'] = 'all'
        msg_dict['@type'] = 'END'
        msg_dict['server_clock'] = time.perf_counter()
        kill_msg = json.dumps(msg_dict)

        t = msg_dict['server_clock']
        self.message_logger.debug(f'Broadcasting simulation end at t={t}')
        # self.state_logger.debug(f'Broadcasting simulation end at t={t}')
        self.publisher.send_json(kill_msg)

        # wait for their confirmation
        subscribers = []
        n_subscribers = 0
        while n_subscribers < self.NUMBER_AGENTS:
            # wait for synchronization request
            msg = self.reqservice.recv_string() # TODO: Change to recv_json() and check if message received is a sync request, else reject or raise an exception
            self.request_logger.info(f'Received simulation end confirmation from {msg}!')

            # send synchronization reply
            self.reqservice.send_string('')
            
            # log subscriber confirmation
            for agent_name in self.AGENT_NAME_LIST:
                if agent_name in msg and not agent_name in subscribers:
                    subscribers.append(agent_name)
                    n_subscribers += 1
                    self.state_logger.info(f"{agent_name} has ended its processes ({n_subscribers}/{self.NUMBER_AGENTS}).")
                    break

    """
    --------------------
    HELPING FUNCTIONS
    --------------------    
    """
    def network_config(self):
        """
        Creates communication ports and binds to them

        publisher: port in charge of broadcasting messages to all agents in the simulation
        reqservice: port in charge of receiving and answering requests from agents. These request can be sync requests or 
        """
        # Activate network ports
        self.context = zmq.Context()
        # self.context = zmq.asyncio.Context()              
    
        ## assign ports to sockets
        self.environment_port_number = '5561'
        if is_port_in_use(int(self.environment_port_number)):
            raise Exception(f"{self.environment_port_number} port already in use")
        
        self.publisher = self.context.socket(zmq.PUB)                   # Socket to send information to agents
        self.publisher.sndhwm = 1100000                                 ## set SNDHWM, so we don't drop messages for slow subscribers
        self.publisher.bind(f"tcp://*:{self.environment_port_number}")

        self.request_port_number = '5562'
        if is_port_in_use(int(self.request_port_number)):
            raise Exception(f"{self.request_port_number} port already in use")

        self.reqservice = self.context.socket(zmq.REP)                 # Socket to receive synchronization and measurement requests from agents
        self.reqservice.bind(f"tcp://*:{self.request_port_number}")

    def sync_agents(self):
        """
        Awaits for all other agents to undergo their initialization routines and become online. Once they become online, 
        they will reach the environment through the 'request_socket' channel and subscribe to future broadcasts from the environment
        """
        subscribers = []
        n_subscribers = 0
        while n_subscribers < self.NUMBER_AGENTS:
            # wait for synchronization request
            msg = self.reqservice.recv_string() # TODO: Change to recv_json() and check if message received is a sync request, else reject or raise an exception
            self.request_logger.info(f'Received sync request from {msg}! Checking if already synchronized...')

            # send synchronization reply
            self.reqservice.send_string('')
            
            # log subscriber confirmation
            for agent_name in self.AGENT_NAME_LIST:
                if agent_name in msg and not agent_name in subscribers:
                    subscribers.append(agent_name)
                    n_subscribers += 1
                    self.state_logger.info(f"{agent_name} is now synchronized to environment ({n_subscribers}/{self.NUMBER_AGENTS}).")
                    break

    def set_up_results_directory(self, scenario_dir):
        scenario_results_path = scenario_dir + '/results'
        if not os.path.exists(scenario_results_path):
            # if directory does not exists, create it
            os.mkdir(scenario_results_path)

        enviroment_results_path = scenario_results_path + f'/{self.name}'
        if os.path.exists(enviroment_results_path):
            # if directory already exists, cleare contents
            for f in os.listdir(enviroment_results_path):
                os.remove(os.path.join(enviroment_results_path, f)) 
        else:
            # if directory does not exist, create a new onw
            os.mkdir(enviroment_results_path)

        return scenario_results_path, enviroment_results_path


    def set_up_loggers(self):
        # set root logger to default settings
        logging.root.setLevel(logging.NOTSET)
        logging.basicConfig(level=logging.NOTSET)

        logger_names = ['messages', 'requests', 'state']

        loggers = []
        for logger_name in logger_names:
            path = self.ENVIRONMENT_RESULTS_DIR + f'/{logger_name}.log'

            if os.path.isdir(path):
                # if file already exists, delete
                os.remove(path)

            # create logger
            logger = logging.getLogger(f'{self.name}_{logger_name}')
            logger.propagate = False

            # create handlers
            c_handler = logging.StreamHandler()
            c_handler.setLevel(logging.INFO)

            f_handler = logging.FileHandler(path)
            f_handler.setLevel(logging.DEBUG)

            # create formatters
            c_format = logging.Formatter(f'{self.name}:\t%(message)s')
            c_handler.setFormatter(c_format)
            f_format = logging.Formatter('%(message)s')
            f_handler.setFormatter(f_format)

            # add handlers to logger
            logger.addHandler(c_handler)
            logger.addHandler(f_handler)

            loggers.append(logger)
        return loggers

"""
--------------------
MAIN
--------------------    
"""
if __name__ == '__main__':
    print('Initializing environment...')
    scenario_dir = './scenarios/sim_test'
    agent_to_port_map = dict()
    agent_to_port_map['AGENT0'] = '5557'
    
    environment = Environment("ENV", scenario_dir, ['AGENT0'], simulation_frequency=1, duration=5)
    
    env_prcs = Process(target=environment.main)
    env_prcs.start()
    env_prcs.join()