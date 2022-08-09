import os
import threading
import time
import zmq
import logging

class AbstractAgent:
    def __init__(self, name, scenario_dir, agent_to_port_map, simulation_frequency, environment_port_number='5555', request_port_number='5556') -> None:
        # constants
        self.name = name
        self.SIMULATION_FREQUENCY = simulation_frequency
        self.START_TIME = -1
        
        # Network information
        self.context = zmq.Context() 
        self.ENVIRONMENT_PORT_NUMBER = environment_port_number
        self.REQUEST_PORT_NUMBER = request_port_number
        self.AGENT_TO_PORT_MAP = dict()
        for port in agent_to_port_map:
            self.AGENT_TO_PORT_MAP[port] = agent_to_port_map

        # set up results dir
        self.SCENARIO_RESULTS_DIR, self.AGENT_RESULTS_DIR = self.set_up_results_directory(scenario_dir)

        # set up loggers
        self.message_logger, self.request_logger, self.measurement_logger, self.scheduler_logger, self.state_logger = self.set_up_loggers()

    def activate(self):
        """
        Initiates agent multiprocessing threads
        """
        self.state_logger.debug('Agent activated!')

    def live(self):
        """
        MAIN FUNCTION 
        """
        self.state_logger.debug('Agent Initialized!')
        
        # confirm online status to server 
        t = threading.Thread(target=self.sync_environment)
        t.start()
        t.join()

        # start simulation
        
        ## activate agent
        self.activate()

        self.state_logger.debug('Good Night!')

    def terminate(self):
        self.environment_broadcast_socket.close()
        self.environment_request_socket.close()

    """
    --------------------
    PARALLEL PROCESSES
    --------------------
    """
    def sync_environment(self):
        ## give environment time to set up
        time.sleep(1)
        self.request_logger.debug('Connecitng to environment server ports...')

        ## subscribe to environment broadcasting port
        self.environment_broadcast_socket = self.context.socket(zmq.SUB)
        self.environment_broadcast_socket.connect(f"tcp://localhost:{self.ENVIRONMENT_PORT_NUMBER}")
        self.environment_broadcast_socket.setsockopt(zmq.SUBSCRIBE, b'')

        ## connect to environment request port
        self.environment_request_socket = self.context.socket(zmq.REQ)
        self.environment_request_socket.connect(f"tcp://localhost:{self.REQUEST_PORT_NUMBER}")

        ## send a synchronization request
        self.request_logger.debug('Connection to environment established! Awaiting environment synchronization...')
        self.environment_request_socket.send(b'')

        # wait for synchronization reply
        self.environment_request_socket.recv()  

        # log simulation start time
        self.START_TIME = time.perf_counter()
        self.request_logger.debug(f'Environment synchronized at time {self.START_TIME}!')

    """
    --------------------
    HELPING FUNCTIONS
    --------------------    
    """
    def set_up_results_directory(self, scenario_dir):
        scenario_results_path = scenario_dir + '/results'
        if not os.path.exists(scenario_results_path):
            # if directory does not exists, create it
            os.mkdir(scenario_results_path)

        agent_results_path = scenario_results_path + f'/{self.name}'
        if not os.path.exists(agent_results_path):
            # if directory does not exists, create it
            os.mkdir(agent_results_path)

        return scenario_results_path, agent_results_path

    def set_up_loggers(self):
        logger_names = ['messages', 'requests', 'measurements', 'scheduler', 'state']

        loggers = []
        for name in logger_names:
            path = self.AGENT_RESULTS_DIR + f'/{name}.log'

            if os.path.exists(path):
                # if file already exists, delete
                os.remove(path)

            # create logger
            logger = logging.getLogger(self.name)

            # create handlers
            c_handler = logging.StreamHandler()
            c_handler.setLevel(logging.WARNING)

            f_handler = logging.FileHandler(path)
            f_handler.setLevel(logging.DEBUG)

            # create formatters
            c_format = logging.Formatter('%(name)s:\t%(message)s')
            c_handler.setFormatter(c_format)
            f_format = logging.Formatter('%(message)s')
            f_handler.setFormatter(f_format)

            # add handlers to logger
            logger.addHandler(c_handler)
            logger.addHandler(f_handler)

            loggers.append(logger)
        return loggers