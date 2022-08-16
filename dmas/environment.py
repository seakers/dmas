import os
# os.environ['PYTHONASYNCIODEBUG'] = '0'
import asyncio
import json
import logging
import time
import zmq.asyncio
from utils import Container, SimClocks

from modules.modules import Module

def is_port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

class EnvironmentServer(Module):
    def __init__(self, name,scenario_dir, agent_name_list: list, duration, clock_type: SimClocks = SimClocks.REAL_TIME, simulation_frequency: float = -1) -> None:
        super().__init__(name, None, [])
        # Constants
        self.name = name                                                # Environment Name
        self.AGENT_NAME_LIST = []                                       # List of names of agent present in the simulation
        self.NUMBER_AGENTS = len(agent_name_list)                       # Number of agents present in the simulation
        self.NUMBER_OF_TIMED_COROUTINES = 0                             # Number of timed co-routines to be performed by the server
        self.NUMBER_OF_TIMED_COROUTINES_AGENTS = 0                      # Number of timed co-routines to be performed by other agents

        for agent_name in agent_name_list:
            self.AGENT_NAME_LIST.append(agent_name)

        # simulation clock constants
        self.CLOCK_TYPE = clock_type                                    # Clock type being used in this simulation
        self.DURATION = duration                                        # Duration of simulation in simulation-time
        if self.SIMULATION_FREQUENCY < 0 and self.CLOCK_TYPE == SimClocks.REAL_TIME_FAST:
            raise Exception('Simulation frequency needed to initiate simulation with a REAL_TIME_FAST clock.')
        if self.CLOCK_TYPE == SimClocks.REAL_TIME:
            self.SIMULATION_FREQUENCY = 1
        elif self.CLOCK_TYPE == SimClocks.REAL_TIME_FAST:
            self.SIMULATION_FREQUENCY = simulation_frequency            # Ratio of simulation-time seconds to real-time seconds
        elif self.CLOCK_TYPE == SimClocks.SERVER_STEP:
            pass
        else:
            raise Exception(f'Simulation clock of type {clock_type.value} not yet supported')
        
        # set up results dir
        self.SCENARIO_RESULTS_DIR, self.ENVIRONMENT_RESULTS_DIR = self.set_up_results_directory(scenario_dir)

        # set up loggers
        [self.message_logger, self.request_logger, self.state_logger, self.actions_logger] = self.set_up_loggers()
        
        print('Environment Initialized!')

    async def live(self):
        """
        MAIN FUNCTION 
        executes event loop for ayncronous processes within the environment
        """
        # Activate 
        await self.activate()

        # Run simulation
        await self.run()

    async def activate(self):
        """
        Initiates and executes commands that are thread-sensitive but that must be performed before the simulation starts.
        """
        self.log('Starting activation routine...', level=logging.INFO)
        
        # activate network ports
        self.log('Configuring network ports...', level=logging.INFO)
        await self.network_config()
        self.log('Network configuration completed!', level=logging.INFO)

        # Wait for agents to initialize their own network ports
        self.log(f"Waiting for {self.NUMBER_AGENTS} to initiate...", level=logging.INFO)
        subscriber_to_port_map =await self.sync_agents()

        self.log(f"All subscribers initalized! Starting simulation...", level=logging.INFO)
        await self.broadcast_sim_start(subscriber_to_port_map)

        self.log(f'Activating environment submodules...')
        await super().activate()
        self.log('Environment Activated!', level=logging.INFO)
    
    async def coroutines(self):
        sim_end_timer = asyncio.create_task(self.sim_wait(self.DURATION))
        agent_req_handler = asyncio.create_task(self.agent_request_handler())
        tic_request_handler = asyncio.create_task(self.tic_request_handler())
        ticker = asyncio.create_task(self.tic_broadcast())

        await sim_end_timer
        ticker.cancel()
        agent_req_handler.cancel()
        tic_request_handler.cancel()
        await ticker
        await agent_req_handler
        await tic_request_handler
        self.log(f"Simulation time completed!", level=logging.INFO)

    async def shut_down(self):
        """
        Terminate processes 
        """
        self.log(f"Shutting down...", level=logging.INFO)

        # broadcast simulation end
        await self.broadcast_end()

        # close network ports     
        self.publisher.close()
        self.reqservice.close()
        self.context.term()
        self.log(f"Network sockets closed.", level=logging.INFO)
        
        self.log(f"Simulation done, good night!", level=logging.INFO)

    """
    --------------------
    CO-ROUTINES AND TASKS
    --------------------
    """

    async def agent_request_handler(self):
        try:
            while True:
                msg_str = await self.reqservice.recv_json() 
                msg_dict = json.loads(msg_str)

                msg_type = msg_dict.get('@type', None)
                await self.reqservice.send_string('')

                if msg_type == 'TIC_REQUEST':
                    t_req = msg_dict.get('t')
                    self.log(f'Received tic request for t_req={t_req}')
                    await self.tic_request_queue.put(t_req)
                else:
                    # dump message
                    continue
        except asyncio.CancelledError:
            return

    async def tic_request_handler(self):
        try:
            while True:
                tic_req = float(await self.tic_request_queue.get())
                self.tic_request_queue_sorted.append(tic_req)

                self.log(f'Tic request queue: {len(self.tic_request_queue_sorted)} / {self.NUMBER_OF_TIMED_COROUTINES_AGENTS}')
                if len(self.tic_request_queue_sorted) == self.NUMBER_OF_TIMED_COROUTINES_AGENTS:
                    self.log('Sorting tic requests...')
                    print(self.tic_request_queue_sorted)
                    self.tic_request_queue_sorted.sort()
                    self.log(f'Tic requests sorted: {self.tic_request_queue_sorted}')

                    t_next = self.tic_request_queue_sorted.pop(0)

                    await self.sim_time.set_level(t_next)

                    if self.CLOCK_TYPE == SimClocks.SERVER_STEP:                    
                        msg_dict = dict()
                        msg_dict['src'] = self.name
                        msg_dict['dst'] = 'all'
                        msg_dict['@type'] = 'tic'
                        msg_dict['server_clock'] = t_next
                        msg_json = json.dumps(msg_dict) 

                        t = msg_dict['server_clock']
                        self.message_logger.debug(f'Broadcasting server tic at t={t}')
                        self.state_logger.debug(f'Broadcasting server tic at t={t}')

                        await self.publisher.send_json(msg_json)

        except asyncio.CancelledError:
            return

    async def tic_broadcast(self):
        try:
            while True:
                # TODO: Create different cases for each different synchronous clock types
                if self.CLOCK_TYPE == SimClocks.SERVER_TIME or self.CLOCK_TYPE == SimClocks.SERVER_TIME_FAST:
                    pass
                else:
                    await self.sim_wait(10000000)
        except asyncio.CancelledError:
            return

    async def broadcast_end(self):
        # broadcast simulation end to all subscribers
        msg_dict = dict()
        msg_dict['src'] = self.name
        msg_dict['dst'] = 'all'
        msg_dict['@type'] = 'END'
        msg_dict['server_clock'] = time.perf_counter() - self.START_TIME
        kill_msg = json.dumps(msg_dict)

        t = msg_dict['server_clock']
        self.message_logger.debug(f'Broadcasting simulation end at t={t}[s]')
        self.log(f'Broadcasting simulation end at t={t}[s]')
        await self.publisher.send_json(kill_msg)

        # wait for their confirmation
        subscribers = []
        n_subscribers = 0
        while n_subscribers < self.NUMBER_AGENTS:
            # wait for synchronization request
            msg = await self.reqservice.recv_string() 
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
    async def network_config(self):
        """
        Creates communication ports and binds to them

        publisher: port in charge of broadcasting messages to all agents in the simulation
        reqservice: port in charge of receiving and answering requests from agents. These request can be sync requests or 
        """
        # Activate network ports
        self.context = zmq.asyncio.Context()
    
        ## assign ports to sockets
        self.environment_port_number = '5561'
        if is_port_in_use(int(self.environment_port_number)):
            raise Exception(f"{self.environment_port_number} port already in use")
        
        self.publisher = self.context.socket(zmq.PUB)                   # Socket to broadcast information to agents
        self.publisher.sndhwm = 1100000                                 ## set SNDHWM, so we don't drop messages for slow subscribers
        self.publisher.bind(f"tcp://*:{self.environment_port_number}")

        self.request_port_number = '5562'
        if is_port_in_use(int(self.request_port_number)):
            raise Exception(f"{self.request_port_number} port already in use")

        self.reqservice = self.context.socket(zmq.REP)                 # Socket to receive synchronization and measurement requests from agents
        self.reqservice.bind(f"tcp://*:{self.request_port_number}")

    async def sync_agents(self):
        """
        Awaits for all other agents to undergo their initialization routines and become online. Once they become online, 
        they will reach out to the environment through the 'reqservice' channel and subscribe to future broadcasts from the environment.

        The environment will then broadcast a list of agent-to-port assignments to all agents so they are able to communicate directly 
        with one and other as needed 
        """

        # wait for agents to synchronize
        subscribers = []
        subscriber_to_port_map = dict()
        n_subscribers = 0
        while n_subscribers < self.NUMBER_AGENTS:
            # wait for synchronization request
            msg_str = await self.reqservice.recv_json() 
            msg = json.loads(msg_str)
            if msg['@type'] != 'SYNC_REQUEST' or msg.get('port') is None:
                continue
            
            msg_src = msg.get('src', None)
            src_port = msg.get('port')
            self.NUMBER_OF_TIMED_COROUTINES_AGENTS += msg.get('n_coroutines')

            self.log(f'Received sync request from {msg_src}! Checking if already synchronized...', level=logging.INFO) 

            # log subscriber confirmation
            for agent_name in self.AGENT_NAME_LIST:
                if (agent_name in msg_src) and (agent_name not in subscribers):
                    subscribers.append(agent_name)
                    n_subscribers += 1
                    self.log(f"{agent_name} is now synchronized to environment ({n_subscribers}/{self.NUMBER_AGENTS}).")
                    
                    subscriber_to_port_map[msg_src] = src_port
                    break
            # send synchronization reply
            await self.reqservice.send_string('')
        return subscriber_to_port_map
                    
    async def broadcast_sim_start(self, subscriber_to_port_map):
        # boradcast simulation start with agent-to-port map
        msg_dict = dict()
        msg_dict['src'] = self.name
        msg_dict['dst'] = 'ALL'
        msg_dict['@type'] = 'START'
        msg_dict['port_map'] = subscriber_to_port_map
        
        clock_info = dict()
        clock_info['@type'] = self.CLOCK_TYPE.value
        if self.CLOCK_TYPE == SimClocks.REAL_TIME or self.CLOCK_TYPE == SimClocks.REAL_TIME_FAST:
            clock_info['frequency'] = self.SIMULATION_FREQUENCY
            self.sim_time = 0
        else:
            self.sim_time = Container()
        msg_dict['clock_info'] = clock_info

        msg_json = json.dumps(msg_dict)
        await self.publisher.send_json(msg_json)

        # log simulation start time
        self.START_TIME = time.perf_counter()

        # initiate tic request queue
        self.tic_request_queue = asyncio.Queue()
        self.tic_request_queue_sorted = []

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

        logger_names = ['messages', 'requests', 'state', 'actions']

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
            if logger_name == 'actions':
                c_handler.setLevel(logging.DEBUG)
            else:
                c_handler.setLevel(logging.WARNING)

            f_handler = logging.FileHandler(path)
            f_handler.setLevel(logging.DEBUG)

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
    
    # environment = EnvironmentServer("ENV", scenario_dir, ['AGENT0'], simulation_frequency=1, duration=5)
    environment = EnvironmentServer('ENV', scenario_dir, ['AGENT0'], 5, clock_type=SimClocks.SERVER_STEP)
    
    asyncio.run(environment.live())