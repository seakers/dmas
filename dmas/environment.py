import os
# os.environ['PYTHONASYNCIODEBUG'] = '0'
import asyncio
import json
import logging
import random
import time
import zmq.asyncio

from messages import BroadcastTypes
from modules.module import  Module, EnvironmentModuleTypes, TicRequestModule
from utils import Container, SimClocks
from messages import RequestTypes

def is_port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

class EnvironmentServer(Module):
    def __init__(self, name,scenario_dir, agent_name_list: list, duration, clock_type: SimClocks = SimClocks.REAL_TIME, simulation_frequency: float = -1) -> None:
        super().__init__(name)
        # Constants
        self.AGENT_NAME_LIST = []                                       # List of names of agent present in the simulation
        self.NUMBER_AGENTS = len(agent_name_list)                       # Number of agents present in the simulation
        self.NUMBER_OF_TIMED_COROUTINES = 0                             # Number of timed co-routines to be performed by the server
        self.NUMBER_OF_TIMED_COROUTINES_AGENTS = 0                      # Number of timed co-routines to be performed by other agents

        for agent_name in agent_name_list:
            self.AGENT_NAME_LIST.append(agent_name)

        # simulation clock constants
        self.CLOCK_TYPE = clock_type                                    # Clock type being used in this simulation
        self.DURATION = duration                                        # Duration of simulation in simulation-time

        self.SIMULATION_FREQUENCY = None
        if self.CLOCK_TYPE == SimClocks.REAL_TIME:
            self.SIMULATION_FREQUENCY = 1
        elif self.CLOCK_TYPE == SimClocks.REAL_TIME_FAST:
            self.SIMULATION_FREQUENCY = simulation_frequency            # Ratio of simulation-time seconds to real-time seconds
        elif self.CLOCK_TYPE != SimClocks.SERVER_STEP:
            raise Exception(f'Simulation clock of type {clock_type.value} not yet supported')
        
        if simulation_frequency < 0 and self.CLOCK_TYPE == SimClocks.REAL_TIME_FAST:
            raise Exception('Simulation frequency needed to initiate simulation with a REAL_TIME_FAST clock.')

        # set up submodules
        self.submodules = [TicRequestModule(self)]
        
        # set up results dir
        self.SCENARIO_RESULTS_DIR, self.ENVIRONMENT_RESULTS_DIR = self.set_up_results_directory(scenario_dir)

        # set up loggers
        [self.message_logger, self.request_logger, self.state_logger, self.actions_logger] = self.set_up_loggers()

        # propagate orbit and coverage information
        # self.orbit_data = None
        
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
        self.log(f"Shutting down...", level=logging.INFO)

        # broadcast simulation end
        # await asyncio.sleep(random.random())
        await self.broadcast_sim_end()

        # close network ports  
        self.log(f"Closing all network sockets...") 
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
    async def coroutines(self):
        """
        Executes list of coroutine tasks to be excuted by the environment. These coroutine task incluide:
            1- 'sim_end_timer': counts down to the end of the simulation
            2- 'request_handler': listens to 'reqservice' port and handles agent requests being sent
            3- 'broadcast_handler': receives broadcast requests and publishes them to all agents
        """
        sim_end_timer = asyncio.create_task(self.sim_wait(self.DURATION))
        request_handler = asyncio.create_task(self.request_handler())
        broadcast_handler = asyncio.create_task(self.broadcast_handler())

        await sim_end_timer
        request_handler.cancel()
        broadcast_handler.cancel()
        await request_handler
        await broadcast_handler
        self.log(f"Simulation time completed!", level=logging.INFO)

    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            dst_name = msg['dst']
            if dst_name != self.name:
                await self.put_message(msg)
            else:
                # if the message is of type broadcast, send to broadcast handler
                msg_type = msg['@type']
                if (BroadcastTypes[msg_type] is BroadcastTypes.TIC
                    or BroadcastTypes[msg_type] is BroadcastTypes.ECLIPSE_EVENT
                    or BroadcastTypes[msg_type] is BroadcastTypes.ACCESS_EVENT):
                    
                    if not BroadcastTypes.format_check(msg):
                        # if broadcast task does not meet the desired format, reject and dump
                        self.log('Broadcast task did not meet format specifications. Task dumped.')
                        return
                    if BroadcastTypes[msg_type] is BroadcastTypes.TIC:
                        t_next = msg['server_clock']
                        self.log(f'Updating internal clock to t={t_next}')
                        await self.sim_time.set_level(t_next)

                    await self.publisher_queue.put(msg)

                # else, dump
                return
        except asyncio.CancelledError:
            return

    async def request_handler(self):
        """
        Listens to 'reqservice' socket and handles agent requests accordingly. List of supported requests:
            1- tic_requests: agents ask to be notified when a certain time has passed in the environment's clock
            2- access_request: agent asks to be notified when a ground point or an agent is going to be accessible by said agent
            3- agent_information_request: agent asks for information regarding its current position, velocity, and eclipse
            4- observation_request: agent requests environment information regarding a the state of a ground point
            
        Only request types 3 and 4 require an immediate response from the environment. The rest create future broadcast tasks.
        """
        try:
            while True:
                self.log('Waiting for agent requests...')
                req_str = await self.reqservice.recv_json()
                self.log(f'Request received!')
                req_dict = json.loads(req_str)
               
                if not RequestTypes.format_check(req_dict):
                    # if request does not match any of the standard request format, dump and continue
                    self.log(f'Request does not match the standard format for a request message. Dumping request...')
                    await self.reqservice.send_string('')
                    continue
        
                req_type = req_dict.get('@type')
                req_type = RequestTypes[req_type]

                if req_type is RequestTypes.TIC_REQUEST:
                    # send agent acknowledgement of reception
                    await self.reqservice.send_string('')

                    # schedule tic request
                    t_req = req_dict.get('t')
                    self.log(f'Received tic request for t_req={t_req}')

                    # change source and destination to internal modules
                    req_dict['src'] = self.name
                    req_dict['dst'] = EnvironmentModuleTypes.TIC_REQUEST_MODULE.value

                    # send to internal message router for forwarding
                    await self.put_message(req_dict)

                # elif req_type is RequestTypes.ACCESS_REQ:
                #     # send agent acknowledgement of reception
                #     await self.reqservice.send_string('')

                #     # schedule acess request
                #     pass
                # elif req_type is RequestTypes.AGENT_INFO_REQ:
                #     await self.reqservice.send_string('')
                #     pass

                # elif req_type is RequestTypes.OBSERVATION_REQ:
                #     await self.reqservice.send_string('')
                #     pass

                else:
                    # if 
                    self.log(f'Request of type {req_type.value} not yet supported. Dumping request.')
                    await self.reqservice.send_string('')
                    continue

        except asyncio.CancelledError:
            return

    async def broadcast_handler(self):
        """
        Listens to internal message inbox to see if any submodule wishes to broadcast information to all agents.
        Broadcast types supported:
            1- 'tic': communicates the current environment clock
            2- 'eclipse_event': communicates which agents just entered or exited eclipse
            3- 'access_event': communicates when an agent just started or stopped accessing a ground point or another agent

            TODO: Add measurement requests from the ground?
        """
        try:
            while True:
                msg = await self.publisher_queue.get()

                msg['src'] = self.name
                msg['dst'] = 'all'
                msg_json = json.dumps(msg)

                msg_type = msg['@type']
                self.log(f'Broadcast task of type {msg_type} received! Publishing to all agents...')

                self.log('Awaiting access to publisher socket...')
                await self.publisher_lock.acquire()
                self.log('Access to publisher socket acquired.')
                await self.publisher.send_json(msg_json)
                self.log('Broadcast sent')
                self.publisher_lock.release()
        except asyncio.CancelledError:
            return
        finally:
            if self.publisher_lock.locked():
                self.publisher_lock.release()

    async def tic_broadcast(self):
        try:
            while True:
                # TODO: Create different cases for each different synchronous clock types
                if self.CLOCK_TYPE == SimClocks.SERVER_TIME or self.CLOCK_TYPE == SimClocks.SERVER_TIME_FAST:
                    await self.sim_wait()
                else:
                    await self.sim_wait(10000000)
        except asyncio.CancelledError:
            return

    """
    --------------------
    HELPING FUNCTIONS
    --------------------    
    """
    async def network_config(self):
        """
        Creates communication sockets and binds this environment to them.

        'publisher': socket in charge of broadcasting messages to all agents in the simulation
        'reqservice': socket in charge of receiving and answering requests from agents. These request can range from:
            1- sync_requests: agents confirm their activation and await a synchronized simulation start message
            2- tic_requests: agents ask to be notified when a certain time has passed in the environment's clock
            3- agent_information_request: agent asks for information regarding its current position, velocity, and eclipse
            4- observation_request: agent requests environment information regarding a the state of a ground point
        """
        # Activate network ports
        self.context = zmq.asyncio.Context()
    
        # Assign ports to sockets
        ## Set up socket to broadcast information to agents
        self.environment_port_number = '5561'
        if is_port_in_use(int(self.environment_port_number)):
            raise Exception(f"{self.environment_port_number} port already in use")
        self.publisher = self.context.socket(zmq.PUB)                   
        self.publisher.sndhwm = 1100000                                 ## set SNDHWM, so we don't drop messages for slow subscribers
        self.publisher.bind(f"tcp://*:{self.environment_port_number}")
        self.publisher_lock = asyncio.Lock()
        self.publisher_queue = asyncio.Queue()

        ## Set up socket to receive synchronization and measurement requests from agents
        self.request_port_number = '5562'
        if is_port_in_use(int(self.request_port_number)):
            raise Exception(f"{self.request_port_number} port already in use")
        self.reqservice = self.context.socket(zmq.REP)
        self.reqservice.bind(f"tcp://*:{self.request_port_number}")

    async def sync_agents(self):
        """
        Awaits for all other agents to undergo their initialization and activation routines and to become online. Once they do, 
        they will reach out to the environment through its 'reqservice' socket and subscribe to future broadcasts from the 
        environment's 'publisher' socket.

        The environment will then create a ledger mapping which agents are assigned to which ports. This ledger will later be 
        broadcasted to all agents.
        """

        # wait for agents to synchronize
        subscribers = []
        subscriber_to_port_map = dict()
        n_subscribers = 0
        while n_subscribers < self.NUMBER_AGENTS:
            # wait for synchronization request
            msg_str = await self.reqservice.recv_json() 
            msg = json.loads(msg_str)
            msg_type = msg['@type']
            if RequestTypes[msg_type] != RequestTypes.SYNC_REQUEST or msg.get('port') is None:
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
        """
        Broadcasts simulation start to all agents subscribed to this environment.
        Simulation start message also contains a ledger that maps agent names to ports to be connected to for inter-agent
        communications. This message also contains information about the clock-type being used in this simulation.
        """
        # create message
        msg_dict = dict()
        msg_dict['src'] = self.name
        msg_dict['dst'] = 'ALL'
        msg_dict['@type'] = BroadcastTypes.SIM_START.name
        
        # include subscriber-to-port map to message
        msg_dict['port_map'] = subscriber_to_port_map
        
        # include clock information to message
        clock_info = dict()
        clock_info['@type'] = self.CLOCK_TYPE.name
        if self.CLOCK_TYPE == SimClocks.REAL_TIME or self.CLOCK_TYPE == SimClocks.REAL_TIME_FAST:
            clock_info['freq'] = self.SIMULATION_FREQUENCY
            self.sim_time = 0
        else:
            self.sim_time = Container()
        msg_dict['clock_info'] = clock_info

        # package message and broadcast
        msg_json = json.dumps(msg_dict)
        await self.publisher.send_json(msg_json)

        # log simulation start time
        self.START_TIME = time.perf_counter()

        # initiate tic request queue if simulation uses a synchronized server clock
        if self.CLOCK_TYPE == SimClocks.SERVER_STEP:
            self.tic_request_queue = asyncio.Queue()
            self.tic_request_queue_sorted = []
            
    async def broadcast_sim_end(self):
        """
        Broadcasts a message announcing the end of the simulation to all agents subscribed to this environment. 
        All agents must aknowledge that they have received and processed this message for the simulation to end.
        """
        # broadcast simulation end to all subscribers
        msg_dict = dict()
        msg_dict['src'] = self.name
        msg_dict['dst'] = 'all'
        msg_dict['@type'] =  BroadcastTypes.SIM_END.name
        msg_dict['server_clock'] = time.perf_counter() - self.START_TIME
        kill_msg = json.dumps(msg_dict)

        t = msg_dict['server_clock']
        self.message_logger.debug(f'Broadcasting simulation end at t={t}[s]')
        self.log(f'Broadcasting simulation end at t={t}[s]')
        
        await self.publisher.send_json(kill_msg)

        # wait for all agents to send their confirmation
        subscribers = []
        n_subscribers = 0
        self.request_logger.info(f'Waiting for simulation end confirmation from {n_subscribers} agents...')
        self.log(f'Waiting for simulation end confirmation from {n_subscribers} agents...', level=logging.INFO)
        while n_subscribers < self.NUMBER_AGENTS:
            # wait for synchronization request
            msg_str = await self.reqservice.recv_json() 
            msg_dict = json.loads(msg_str)
            
            msg_src = msg_dict['src']
            msg_type = msg_dict['@type']
            if RequestTypes[msg_type] is not RequestTypes.END_CONFIRMATION:
                self.reqservice.send_string('')
                continue
            
            self.request_logger.info(f'Received simulation end confirmation from {msg_src}!')
            self.log(f'Received simulation end confirmation from {msg_src}!', level=logging.INFO)

            # send synchronization reply
            self.reqservice.send_string('')
            
            # log subscriber confirmation
            for agent_name in self.AGENT_NAME_LIST:
                if agent_name in msg_src and not agent_name in subscribers:
                    subscribers.append(agent_name)
                    n_subscribers += 1
                    self.log(f"{agent_name} has ended its processes ({n_subscribers}/{self.NUMBER_AGENTS}).", level=logging.INFO)
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
    
    # environment = EnvironmentServer('ENV', scenario_dir, ['AGENT0'], 5, clock_type=SimClocks.REAL_TIME)
    environment = EnvironmentServer('ENV', scenario_dir, ['AGENT0'], 5, clock_type=SimClocks.SERVER_STEP)
    
    asyncio.run(environment.live())