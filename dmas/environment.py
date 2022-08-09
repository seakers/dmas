import logging
import os
import threading
import zmq

class Environment:
    def __init__(self, name, scenario_dir, agent_name_list, simulation_frequency, duration, environment_port_number='5555', request_port_number='5556') -> None:
        # Constants
        self.name = name                                            # Environment Name
        self.SIMULATION_FREQUENCY = simulation_frequency            # Ratio of simulation-time to real-time
        self.DURATION = duration                                    # Duration of simulation in simulation-time
        self.NUMBER_AGENTS = len(agent_name_list)                   # Number of agents present in the simulation
        self.AGENT_NAME_LIST = []                                   # List of names of agent present in the simulation
        for agent_name in agent_name_list:
            self.AGENT_NAME_LIST.append(agent_name)
        
        # Set up network ports
        self.context = zmq.Context()                                
        
        publisher_socket = self.context.socket(zmq.PUB)             # Socket to send information to agents
        publisher_socket.sndhwm = 1100000                           ## set SNDHWM, so we don't drop messages for slow subscribers
        publisher_socket.bind(f"tcp://*:{environment_port_number}")

        request_socket = self.context.socket(zmq.REP)               # Socket to receive requests from agents
        request_socket.bind(f"tcp://*:{request_port_number}")

        # set up results dir
        self.SCENARIO_RESULTS_DIR, self.ENVIRONMENT_RESULTS_DIR = self.set_up_results_directory(scenario_dir)

        # set up loggers
        self.message_logger, self.request_logger, self.state_logger = self.set_up_loggers()


    def live(self):
        """
        MAIN FUNCTION 
        """
        self.state_logger.debug('Environment Initialized!')

        # Wait for all agents to initialize
        self.state_logger(f"Waiting for {self.NUMBER_AGENTS} to initiate...")
        sync_subscriber = threading.Thread(target=self.sync_agents)
        sync_subscriber.start()
        sync_subscriber.join()

        self.state_logger(f"All subscribers initalized! Starting simulation...")
        timer = threading.Thread(target=self.run_timer)
        timer.start()
        timer.join
        self.state_logger(f"Simulation time completed! Termianting sim...")

    """
    --------------------
    PARALLEL PROCESSES
    --------------------
    """
    def run_timer(self): 
        delay = self.DURATION/self.SIMULATION_FREQUENCY
        self.sleep(delay)

    def sync_agents(self):
        """
        Awaits for all other agents to undergo their initialization routines and become online. Once they become online, 
        they will reach the environment through the 'request_socket' channel and subscribe to future broadcasts from the environment
        """
        subscribers = []
        n_subscribers = 0
        while subscribers < self.NUMBER_AGENTS:
            # wait for synchronization request
            msg = self.request_socket.recv()
            
            # send synchronization reply
            self.request_socket.send('')

            # log subscriber confirmation
            for agent_name in self.AGENT_NAME_LIST:
                if agent_name in msg and not agent_name in subscribers:
                    subscribers.append(agent_name)
                    n_subscribers += 1
                    self.state_logger(f"{agent_name} subscribed to environment! ({n_subscribers}/{self.NUMBER_AGENTS})")
                    continue


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

        enviroment_results_path = scenario_results_path + '/environment'
        if not os.path.exists(enviroment_results_path):
            # if directory does not exists, create it
            os.mkdir(enviroment_results_path)

        return scenario_results_path, enviroment_results_path

    def set_up_loggers(self):
        logger_names = ['messages', 'requests', 'state']

        loggers = []
        for name in logger_names:
            path = self.ENVIRONMENT_RESULTS_DIR + f'/{name}.log'

            if os.path.isdir(path):
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