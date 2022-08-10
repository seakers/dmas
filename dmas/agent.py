import asyncio
import json
from multiprocessing import Process
import os
import threading
import time
import zmq
import zmq.asyncio
import logging

from dmas.modules import TestModule

class AbstractAgent:
    def __init__(self, name, scenario_dir, agent_to_port_map, simulation_frequency, modules=[]) -> None:
        # constants
        self.name = name
        self.SIMULATION_FREQUENCY = simulation_frequency
        self.START_TIME = -1

        # set up results dir
        self.SCENARIO_RESULTS_DIR, self.AGENT_RESULTS_DIR = self.set_up_results_directory(scenario_dir)

        # set up loggers
        self.message_logger, self.request_logger, self.measurement_logger, self.scheduler_logger, self.state_logger = self.set_up_loggers()
        
        # Network information
        self.ENVIRONMENT_PORT_NUMBER =  '5561'
        self.REQUEST_PORT_NUMBER = '5562'
        self.AGENT_TO_PORT_MAP = dict()
        for port in agent_to_port_map:
            self.AGENT_TO_PORT_MAP[port] = agent_to_port_map

        # saves list of modules. They must already be initiated beforehand
        self.queue = None
        if len(modules) == 0:
            modules = [TestModule(self)]
        self.modules = modules

        self.state_logger.info('Agent Initialized!')

    def main(self):
        """
        MAIN FUNCTION 
        """           
        asyncio.run(self.run())

    async def run(self):
        # Activate 
        await self.activate()

        # Run simulation
        await self.live()

        # Turn off
        await self.shut_down()


    async def activate(self):
        """
        Initiates and executes commands that are thread-sensitive but that must be performed before the simulation starts.
        """
        self.state_logger.info('Starting activation routine...')

        # initiate network ports and connect to environment server
        self.state_logger.debug('Configuring network ports...')
        await self.network_config()
        self.state_logger.debug('Network configuration completed!')

        # confirm online status to environment server 
        self.state_logger.debug(f"Synchronizing with environment...")
        await self.sync_environment()
        self.request_logger.debug(f'Synchronization response received! Environment synchronized at time {self.START_TIME}!')

        self.state_logger.info('Agent activated!')

    async def live(self):        
        """
        Performs simulation actions 
        """
        self.state_logger.info(f"Starting simulation...")
        await self.execute_modules()

    async def shut_down(self):
        """
        Terminate processes 
        """
        self.state_logger.info(f"Shutting down...")

        # close network ports  
        self.environment_broadcast_socket.close()
        self.environment_request_socket.close()
        self.context.term()

        self.state_logger.info('Good Night!')

    """
    --------------------
    CO-ROUTINES AND TASKS
    --------------------
    """
    async def put_message(self, msg):
        await self.inbox.put(msg)

    async def execute_modules(self):       
        self.inbox = asyncio.Queue()

        for module in self.modules:
            await module.activate()

        subroutines = []
        subroutines = [module.run() for module in self.modules]
        subroutines.append(self.message_handler())

        _, pending = await asyncio.wait(subroutines, return_when=asyncio.FIRST_COMPLETED)

        for routine in pending:
            routine.cancel()

    async def message_handler(self):
        self.state_logger.debug('Awaiting simulation termination...')
        while True:
            socks = dict(await self.poller.poll())                

            if self.environment_broadcast_socket in socks:
                msg_string = await self.environment_broadcast_socket.recv_json()
                msg_dict = json.loads(msg_string)

                src = msg_dict['src']
                dst = msg_dict['dst']
                msg_type = msg_dict['@type']
                t_server = msg_dict['server_clock']

                self.message_logger.info(f'Received message of type {msg_type} from {src} intended for {dst} with server time of t={t_server}!')
                # self.state_logger.info(f'Received message of type {msg_type} from {src} intended for {dst} with server time of t={t_server}!')

                if msg_type == 'END':
                    self.state_logger.info(f'Sim has ended.')
                    
                    # send a reception confirmation
                    self.request_logger.info('Connection to environment established!')
                    self.environment_request_socket.send_string(self.name)
                    self.request_logger.info('Agent termination aknowledgement sent. Awaiting environment response...')

                    # wait for server reply
                    await self.environment_request_socket.recv() 
                    self.request_logger.info('Response received! terminating agent.')
                    return

                elif msg_type == 'tic':
                    self.message_logger.info(f'Updating internal clock.')
                    self.sim_time = t_server

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
        time.sleep(1)

        # connect to environment request port
        self.environment_request_socket = self.context.socket(zmq.REQ)
        self.environment_request_socket.connect(f"tcp://localhost:{self.REQUEST_PORT_NUMBER}")

        # create poller to be used for parsing through incoming message
        self.poller = zmq.asyncio.Poller()
        self.poller.register(self.environment_request_socket, zmq.POLLIN)
        self.poller.register(self.environment_broadcast_socket, zmq.POLLIN)

    async def sync_environment(self):
        # send a synchronization request
        self.request_logger.debug('Connection to environment established!')
        self.environment_request_socket.send_string(self.name)
        self.request_logger.debug('Synchronization request sent. Awaiting environment response...')

        # wait for synchronization reply
        await self.environment_request_socket.recv()  

        # log simulation start time
        self.START_TIME = time.perf_counter()
        self.sim_time = 0

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
        
        logger_names = ['messages', 'requests', 'measurements', 'scheduler', 'state']

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
    print('Initializing agent...')
    scenario_dir = './scenarios/sim_test'
    agent_to_port_map = dict()
    agent_to_port_map['AGENT0'] = '5557'
    
    agent = AbstractAgent("AGENT0", scenario_dir, agent_to_port_map, 1)
    
    agent_prcs = Process(target=agent.main)    
    agent_prcs.start()
    agent_prcs.join