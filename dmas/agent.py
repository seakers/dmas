from multiprocessing import Process
import os
import threading
import time
import zmq
import logging

def is_port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

class AbstractAgent:
    def __init__(self, name, scenario_dir, agent_to_port_map, simulation_frequency) -> None:
        # constants
        self.name = name
        self.SIMULATION_FREQUENCY = simulation_frequency
        self.START_TIME = -1

        # set up results dir
        self.SCENARIO_RESULTS_DIR, self.AGENT_RESULTS_DIR = self.set_up_results_directory(scenario_dir)

        # set up loggers
        self.message_logger, self.request_logger, self.measurement_logger, self.scheduler_logger, self.state_logger = self.set_up_loggers()
        
        # Network information
        self.context = zmq.Context() 
        self.ENVIRONMENT_PORT_NUMBER =  '5561'
        self.REQUEST_PORT_NUMBER = '5562'
        self.AGENT_TO_PORT_MAP = dict()
        for port in agent_to_port_map:
            self.AGENT_TO_PORT_MAP[port] = agent_to_port_map

        self.state_logger.info('Agent Initialized!')

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

        # initiate network ports and connect to environment server
        self.state_logger.debug('Configuring network ports...')
        self.network_config()
        self.state_logger.debug('Network configuration completed!')

        # confirm online status to environment server 
        self.state_logger.debug(f"Synchronizing with environment...")
        self.sync_environment()
        self.request_logger.debug(f'Synchronization response received! Environment synchronized at time {self.START_TIME}!')

        self.state_logger.info('Agent activated!')

    def live(self):        
        """
        Performs simulation actions 
        """
        self.state_logger.info(f"Starting simulation...")
        time.sleep(1)        

    def shut_down(self):
        """
        Terminate processes 
        """
        self.state_logger.info(f"Shutting down...")

        # close network ports  
        self.environment_broadcast_socket.close()
        self.environment_request_socket.close()

        self.state_logger.info('Good Night!')

    """
    --------------------
    PARALLEL PROCESSES
    --------------------
    """
    def message_handler(self):
        while True:
            pass

    """
    --------------------
    HELPING FUNCTIONS
    --------------------    
    """
    def network_config(self):
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
        self.poller = zmq.Poller()
        self.poller.register(self.environment_request_socket, zmq.POLLIN)
        self.poller.register(self.environment_broadcast_socket, zmq.POLLIN)

    def sync_environment(self):
        ## send a synchronization request
        self.request_logger.debug('Connection to environment established!')
        self.environment_request_socket.send_string(self.name)
        self.request_logger.debug('Synchronization request sent. Awaiting environment response...')

        # wait for synchronization reply
        self.environment_request_socket.recv()  

        # log simulation start time
        self.START_TIME = time.perf_counter()

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