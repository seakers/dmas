import asyncio
from curses import def_prog_mode
import json
import os
import random
import sys
import time
import zmq
import zmq.asyncio
import logging
from messages import BroadcastTypes
from utils import SimClocks, Container
from messages import RequestTypes

from modules.module import Module

"""    
--------------------------------------------------------
 ______                         __        ____    ___                       __      
/\  _  \                       /\ \__    /\  _`\ /\_ \    __               /\ \__   
\ \ \L\ \     __      __    ___\ \ ,_\   \ \ \/\_\//\ \  /\_\     __    ___\ \ ,_\  
 \ \  __ \  /'_ `\  /'__`\/' _ `\ \ \/    \ \ \/_/_\ \ \ \/\ \  /'__`\/' _ `\ \ \/  
  \ \ \/\ \/\ \L\ \/\  __//\ \/\ \ \ \_    \ \ \L\ \\_\ \_\ \ \/\  __//\ \/\ \ \ \_ 
   \ \_\ \_\ \____ \ \____\ \_\ \_\ \__\    \ \____//\____\\ \_\ \____\ \_\ \_\ \__\
    \/_/\/_/\/___L\ \/____/\/_/\/_/\/__/     \/___/ \/____/ \/_/\/____/\/_/\/_/\/__/
              /\____/                                                               
              \_/__/
 __  __              __            
/\ \/\ \            /\ \           
\ \ `\\ \    ___    \_\ \     __   
 \ \ , ` \  / __`\  /'_` \  /'__`\ 
  \ \ \`\ \/\ \L\ \/\ \L\ \/\  __/ 
   \ \_\ \_\ \____/\ \___,_\ \____\
    \/_/\/_/\/___/  \/__,_ /\/____/                                                                                                                                                 
--------------------------------------------------------
"""

def is_port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def get_next_available_port():
    port = 5555
    while is_port_in_use(port):
        port += 1
    return port

def count_number_of_subroutines(module: Module):
        count = module.NUMBER_OF_TIMED_COROUTINES
        for submodule in module.submodules:
            count += count_number_of_subroutines(submodule)
        return count

class AgentNode(Module):
    def __init__(self, name, scenario_dir, modules=[], env_port_number = '5561', env_request_port_number = '5562') -> None:
        super().__init__(name, submodules=modules, n_timed_coroutines=0)
        
        # set up results dir
        self.SCENARIO_RESULTS_DIR, self.AGENT_RESULTS_DIR = self.set_up_results_directory(scenario_dir)

        # set up loggers
        self.message_logger, self.env_request_logger, self.measurement_logger, self.state_logger, self.actions_logger = self.set_up_loggers()
        
        # Network information
        self.ENVIRONMENT_PORT_NUMBER =  env_port_number
        self.REQUEST_PORT_NUMBER = env_request_port_number
        self.AGENT_TO_PORT_MAP = None
        
        self.log('Agent Initialized!', level=logging.INFO)

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
        
        # send a reception confirmation
        self.env_request_logger.info('Connection to environment established!')
        end_msg = dict()
        end_msg['src'] = self.name
        end_msg['dst'] = 'ENV'
        end_msg['@type'] = RequestTypes.END_CONFIRMATION.name
        end_json = json.dumps(end_msg)

        await self.environment_request_socket.send_json(end_json)
        self.env_request_logger.info('Agent termination aknowledgement sent. Awaiting environment response...')

        # wait for server reply
        await self.environment_request_socket.recv() 
        self.env_request_logger.info('Response received! terminating agent.')

        self.log(f"Closing all network sockets...")
        self.agent_socket_in.close()
        self.context.destroy()
        self.log(f"Network sockets closed.", level=logging.INFO)

        self.log(f'...Good Night!', level=logging.INFO)

    """
    --------------------
    CO-ROUTINES AND TASKS
    --------------------
    """
    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            dst_name = msg['dst']
            if dst_name != self.name:
                await self.put_message(msg)
            else:
                if msg['@type'] == 'PRINT':
                    content = msg['content']
                    self.log(content)                
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        try:
            broadcast_reception_handler = asyncio.create_task(self.broadcast_reception_handler())
            await broadcast_reception_handler   
        except asyncio.CancelledError:
            broadcast_reception_handler.cancel()
            await broadcast_reception_handler
            return
    
    async def broadcast_reception_handler(self):
        """
        Listens for broadcasts from the environment. Stops processes when simulation end-command is received.
        """
        try:
            while True:
                msg_string = await self.environment_broadcast_socket.recv_json()
                msg_dict = json.loads(msg_string)

                src = msg_dict['src']
                dst = msg_dict['dst']
                msg_type = msg_dict['@type']
                t_server = msg_dict['server_clock']

                self.message_logger.info(f'Received message of type {msg_type} from {src} intended for {dst} with server time of t={t_server}!')

                msg_type = BroadcastTypes[msg_type]

                if msg_type is BroadcastTypes.SIM_END_EVENT:
                    self.log('Simulation end broadcast received! Terminating agent...', level=logging.INFO)
                    return

                elif msg_type is BroadcastTypes.TIC_EVENT:
                    if (self.CLOCK_TYPE == SimClocks.SERVER_STEP 
                        or self.CLOCK_TYPE == SimClocks.SERVER_TIME
                        or self.CLOCK_TYPE == SimClocks.SERVER_TIME_FAST):
                        
                        # use server clock broadcasts to update internal clock
                        self.message_logger.info(f'Updating internal clock.')
                        await self.sim_time.set_level(t_server)
                        self.log('Updated internal clock.')
                else:
                    self.log(f'Broadcasts of type {msg_type.name} not yet supported.')
        except asyncio.CancelledError:
            return

    """
    --------------------
    HELPING FUNCTIONS
    --------------------    
    """
    async def network_config(self):
        """
        Creates communication sockets and connects this agent to them.

        'environment_broadcast_socket': listens for broadcasts coming from the environment
        'environment_request_socket': used to request and receive information directly from the environment
        'agent_socket_in': conects to other agents. Receives requests for information from others
        'agent_socket_out': connects to other agents. Sends information to others
        """ 
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
        """
        Cend a synchronization request to environment server
        """
        self.log('Connection to environment established!')
        await self.environment_request_lock.acquire()

        sync_msg = dict()
        sync_msg['src'] = self.name
        sync_msg['dst'] = 'ENV'
        sync_msg['@type'] = RequestTypes.SYNC_REQUEST.name
        sync_msg['port'] = self.agent_port_in
        sync_msg['n_coroutines'] = count_number_of_subroutines(self)
        sync_json = json.dumps(sync_msg)

        await self.environment_request_socket.send_json(sync_json)
        self.log('Synchronization request sent. Awaiting environment response...')

        # wait for synchronization reply
        await self.environment_request_socket.recv()  
        self.environment_request_lock.release()

    async def wait_sim_start(self):
        """
        Awaits for simulation start message from the environment. 
        This message contains a ledger that maps agent names to ports to be connected to for inter-agent communications. 
        The message also contains information about the clock-type being used in this simulation.
        """
        # await for start message 
        start_msg = await self.environment_broadcast_socket.recv_json()

        # log simulation start time
        self.START_TIME = time.perf_counter()

        # register agent-to-port map
        start_dict = json.loads(start_msg)
        agent_to_port_map = start_dict['port_map']
        self.AGENT_TO_PORT_MAP = dict()
        for agent in agent_to_port_map:
            self.AGENT_TO_PORT_MAP[agent] = agent_to_port_map[agent]
        self.log(f'Agent to port map received: {self.AGENT_TO_PORT_MAP}')

        # setup clock information
        clock_info = start_dict['clock_info']
        self.CLOCK_TYPE = SimClocks[clock_info['@type']]

        if self.CLOCK_TYPE == SimClocks.REAL_TIME or self.CLOCK_TYPE == SimClocks.REAL_TIME_FAST:
            self.SIMULATION_FREQUENCY = clock_info['freq']
            self.sim_time = 0
        else:
            self.SIMULATION_FREQUENCY = None
            self.sim_time = Container()

    def set_up_results_directory(self, scenario_dir):
        """
        Creates directories for agent results and clears them if they already exist
        """

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
        """
        set root logger to default settings
        """

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
        
    async def submit_tic_request(self, delay, module_name):
        t_end = self.sim_time.level + delay
        
        self.log(f'Sending tic request for t_end={t_end}. Awaiting access to environment request port...', module_name=module_name)
        await self.environment_request_lock.acquire()

        tic_msg = RequestTypes.create_tic_event_message(self.name, 'ENV', t_end)
        tic_json = json.dumps(tic_msg)

        await self.environment_request_socket.send_json(tic_json)
        self.log('Tic request sent successfully. Awaiting confirmation...', module_name=module_name)

        # wait for synchronization reply
        await self.environment_request_socket.recv()  
        self.environment_request_lock.release()
        self.log('Tic request reception confirmation received.', module_name=module_name)

class AgentState:
    def __init__(self, agent: AgentNode, component_list) -> None:
        pass

"""
--------------------
  TESTING AGENTS
--------------------
"""
class TestAgent(AgentNode):    
    def __init__(self, name, scenario_dir) -> None:
        super().__init__(name, scenario_dir)
        self.submodules = [TestModule(self)]  

"""
--------------------
  TESTING MODULES
--------------------
"""
class SubModule(Module):
    def __init__(self, name, parent_module) -> None:
        super().__init__(name, parent_module, submodules=[])

    async def coroutines(self):
        try:
            self.log('Starting periodic print routine...')
            while True:
                msg = dict()
                msg['src'] = self.name
                msg['dst'] = self.parent_module.name
                msg['@type'] = 'PRINT'
                msg['content'] = 'TEST_PRINT'

                await self.parent_module.put_message(msg)

                await self.sim_wait(20)
                
        except asyncio.CancelledError:
            self.log('Periodic print routine cancelled')
            return

class TestModule(Module):
    def __init__(self, parent_agent) -> None:
        super().__init__('test', parent_agent, [SubModule('sub_test', self)])

"""
--------------------
MAIN
--------------------    
"""
if __name__ == '__main__':
    print('Initializing agent...')
    scenario_dir = './scenarios/sim_test'
    
    agent = TestAgent("AGENT0", scenario_dir)
    
    asyncio.run(agent.live())