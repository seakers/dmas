import asyncio
from curses import def_prog_mode
import json
import os

from environment import EnvironmentServer

import random
import sys
import time
import zmq
import zmq.asyncio
import logging

from messages import AgentAccessEventBroadcastMessage, AgentEndConfirmationMessage, BroadcastMessage, BroadcastMessageTypes, BroadcastTypes, EclipseEventBroadcastMessage, GndPointAccessEventBroadcastMessage, GndStationAccessEventBroadcastMessage, InterNodeMessageTypes, InternalMessage, PrintRequestMessage, SimulationEndBroadcastMessage, SimulationStartBroadcastMessage, SyncRequestMessage, TicEventBroadcast
from utils import SimClocks, Container, SimulationConstants
from messages import RequestTypes

from modules import Module

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

class AgentClient(Module):
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

    async def _shut_down(self):
        """
        Terminate processes 
        """
        self.log(f"Shutting down agent...", level=logging.INFO)
        
        # send a reception confirmation
        # end_msg = dict()
        # end_msg['src'] = self.name
        # end_msg['dst'] = EnvironmentServer.ENVIRONMENT_SERVER_NAME
        # end_msg['@type'] = RequestTypes.AGENT_END_CONFIRMATION.name
        # end_json = json.dumps(end_msg)
        end_msg = AgentEndConfirmationMessage(self.name, SimulationConstants.ENVIRONMENT_SERVER_NAME.value)

        self.log('Awaiting access to environment request socket...')
        await self.environment_request_lock.acquire()
        self.log('Access to environment request socket obtained! Sending agent termination confirmation...')
        # await self.environment_request_socket.send_json(end_json)
        await self.environment_request_socket.send_json(end_msg.to_json())

        self.env_request_logger.info('Agent termination aknowledgement sent. Awaiting environment response...')
        self.log('Agent termination aknowledgement sent. Awaiting environment response...')

        # wait for server reply
        await self.environment_request_socket.recv() 
        self.environment_request_lock.release()
        self.env_request_logger.info('Response received! terminating agent.')
        self.log('Response received! terminating agent.')

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
    async def internal_message_handler(self, msg: InternalMessage):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            if msg.dst_module != self.name:
                await self.put_in_inbox(msg)
            else:
                self.log(f'Received internal message of type {type(msg.content)}.')
                self.log(f'No handler specified, dumping message...')

        except asyncio.CancelledError:
            return

    async def coroutines(self):
        try:
            # create coroutine tasks
            coroutines = []
            
            broadcast_handler = asyncio.create_task(self.broadcast_handler())
            broadcast_handler.set_name (f'{self.name}_broadcast_handler')
            coroutines.append(broadcast_handler)

            reception_handler = asyncio.create_task(self.reception_handler())
            reception_handler.set_name (f'{self.name}_reception_handler')
            coroutines.append(reception_handler)

            _, pending = await asyncio.wait(coroutines, return_when=asyncio.FIRST_COMPLETED)

            done_name = None
            for coroutine in coroutines:
                if coroutine not in pending:
                    done_name = coroutine.get_name()

            # cancell all other coroutine tasks
            self.log(f'{done_name} ended. Terminating all other coroutines...', level=logging.INFO)
            for coroutine in pending:
                coroutine.cancel()
                await coroutine
            return

        except asyncio.CancelledError: 
            self.log('Cancelling all coroutines...')
            for coroutine in coroutines:
                coroutine.cancel()
                await coroutine
            return

    async def broadcast_handler(self):
        """
        Listens for broadcasts from the environment. Stops processes when simulation end-command is received.
        """
        try:
            while True:
                # msg_string = await self.environment_broadcast_socket.recv_json()
                # msg = json.loads(msg_string)

                # src = msg['src']
                # dst = msg['dst']
                # msg_type = msg['@type']
                # t_server = msg['server_clock']

                # self.message_logger.info(f'Received message of type {msg_type} from {src} intended for {dst} with server time of t={t_server}!')
                # self.log(f'Received message of type {msg_type} from {src} intended for {dst} with server time of t={t_server}!')

                # if self.name == dst or 'all' == dst:
                #     # broadcast intended for this or all agents

                #     msg_type = BroadcastTypes[msg_type]
                #     if msg_type is BroadcastTypes.SIM_END_EVENT:
                        # # if simulation end broadcast is received, terminate agent.
                        # self.log('Simulation end broadcast received! Terminating agent...', level=logging.INFO)

                        # return

                #     elif msg_type is BroadcastTypes.TIC_EVENT:
                        # if (self.CLOCK_TYPE == SimClocks.SERVER_EVENTS 
                        #     or self.CLOCK_TYPE == SimClocks.SERVER_TIME
                        #     or self.CLOCK_TYPE == SimClocks.SERVER_TIME_FAST):
                            
                        #     # use server clock broadcasts to update internal clock
                        #     self.message_logger.info(f'Updating internal clock.')
                        #     await self.sim_time.set_level(t_server)
                        #     self.log('Updated internal clock.')

                #     else:
                #         self.handle_broadcast(msg)
                # else:
                    # # broadcast was intended for someone else, discarding
                    # self.log('Broadcast not intended for this agent. Discarding message...')

                broadcast_msg = await self.environment_broadcast_socket.recv_json()

                broadcast_type = BroadcastMessageTypes[[broadcast_msg['@type']]]
                broadcast_src = broadcast_msg['src']
                broadcast_dst = broadcast_msg['dst']

                self.message_logger.info(f'Received broadcast message of type {broadcast_type} from {broadcast_src} intended for {broadcast_dst}!')
                self.log(f'Received broadcast message of type {broadcast_type} from {broadcast_src} intended for {broadcast_dst}!')

                if self.name == broadcast_dst or 'all' == broadcast_dst:                  
                    if broadcast_type is BroadcastMessageTypes.TIC_EVENT:
                        if (self.CLOCK_TYPE == SimClocks.SERVER_EVENTS 
                            or self.CLOCK_TYPE == SimClocks.SERVER_TIME
                            or self.CLOCK_TYPE == SimClocks.SERVER_TIME_FAST):
                            
                            # use server clock broadcasts to update internal clock
                            broadcast = TicEventBroadcast.from_dict(broadcast_msg)

                            self.message_logger.info(f'Updating internal clock to T={broadcast.t}[s].')
                            await self.sim_time.set_level(broadcast.t)
                            self.log('Updated internal clock.')

                            continue
                        
                    elif broadcast_type is BroadcastMessageTypes.SIM_END_EVENT:
                        # if simulation end broadcast is received, terminate agent.

                        broadcast = SimulationEndBroadcastMessage.from_dict(broadcast_msg)
                        self.log('Simulation end broadcast received! Terminating agent...', level=logging.INFO)

                        return

                    # elif broadcast_type is BroadcastMessageTypes.ECLIPSE_EVENT:
                    #     broadcast = EclipseEventBroadcastMessage.from_dict(broadcast_msg)
                    #     pass

                    # elif broadcast_type is BroadcastMessageTypes.GP_ACCESS_EVENT:
                    #     broadcast = GndPointAccessEventBroadcastMessage.from_dict(broadcast_msg)
                    #     pass

                    # elif broadcast_type is BroadcastMessageTypes.GS_ACCESS_EVENT:
                    #     broadcast = GndStationAccessEventBroadcastMessage.from_dict(broadcast_msg)
                    #     pass

                    # elif broadcast_type is BroadcastMessageTypes.AGENT_ACCESS_EVENT:
                    #     broadcast = AgentAccessEventBroadcastMessage.from_dict(broadcast_msg)
                    #     pass

                    else:
                        self.log(content=f'Broadcasts of type {broadcast_type} not yet supported.')
                else:
                    # broadcast was intended for someone else, discarding
                    self.log('Broadcast not intended for this agent. Discarding message...')
                    

        except asyncio.CancelledError:
            return

    async def reception_handler(self):
        """
        Listens for messages from other agents. Stops processes when simulation end-command is received.
        """
        try:            
            self.log('Acquiring access to agent-in port...')
            await self.agent_socket_in_lock.acquire()
            self.log('Access to agent-in port acquired.')

            while True:
                msg_in = None
                worker_task = None

                # listen for requests
                self.log('Waiting for agent requests.')
                msg_in = await self.agent_socket_in.recv_json()
                self.log(f'Request received!')
                
                # handle request
                self.log(f'Handling agent request...')
                worker_task = asyncio.create_task(self.reception_worker(msg_in))
                await worker_task
                self.log(f'Agent request handled')

        except asyncio.CancelledError:
            if msg_in is not None:
                self.log('Sending blank response...')
                await self.agent_socket_in.send_string('')
            elif worker_task is not None:
                self.log('Cancelling response...')
                worker_task.cancel()
                await worker_task
            else:
                poller = zmq.asyncio.Poller()
                poller.register(self.agent_socket_in, zmq.POLLIN)
                poller.register(self.agent_socket_in, zmq.POLLOUT)

                evnt = await poller.poll(1000)
                if len(evnt) > 0:
                    self.log('Agent request message received during shutdown process. Sending blank response..')
                    await self.agent_socket_in.send_string('')

            self.log('Releasing agent-in port...')
            self.agent_socket_in_lock.release()
            return

    async def reception_worker(self, msg_in: dict):
        """
        Handles received message according to its type
        """
        try:            
            msg_type = InterNodeMessageTypes[[msg_in['@type']]]
            msg_src = msg_in['src']
            msg_dst = msg_in['dst']

            #TODO check for format of message being sent?

            self.message_logger.info(f'Received a message of type {msg_type} from {msg_src} intended for {msg_dst}!')
            self.log(f'Received a message of type {msg_type} from {msg_src} intended for {msg_dst}!')

            if self.name == msg_dst:
                if msg_type is InterNodeMessageTypes.PRINT_REQUEST:
                    msg = PrintRequestMessage.from_dict(msg_in)
                    self.log(msg.content)

                    # send reception confirmation to sender agent
                    await self.agent_socket_in.send_string('')
                else:
                    # if request does not match any of the standard request format, dump and continue
                    self.log(f'Agent messages not yet supported. Sending blank response and dumping message...')

                    # send reception confirmation to sender agent
                    await self.agent_socket_in.send_string('')

            else:
                # message was intended for someone else, discard message
                self.log('Inter agent message not intended for this agent. Discarding message...')
        except asyncio.CancelledError:
            await self.agent_socket_in.send_string('')

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
        self.agent_socket_in_lock = asyncio.Lock()

        self.agent_socket_out = self.context.socket(zmq.REQ)
        self.agent_socket_out_lock = asyncio.Lock()

    async def sync_environment(self):
        """
        Cend a synchronization request to environment server
        """
        self.log('Connection to environment established!')
        await self.environment_request_lock.acquire()

        # sync_msg = dict()
        # sync_msg['src'] = self.name
        # sync_msg['dst'] = EnvironmentServer.ENVIRONMENT_SERVER_NAME
        # sync_msg['@type'] = RequestTypes.SYNC_REQUEST.name
        # sync_msg['port'] = self.agent_port_in
        # sync_msg['n_coroutines'] = count_number_of_subroutines(self)
        # sync_json = json.dumps(sync_msg)

        sync_req = SyncRequestMessage(self.name, SimulationConstants.ENVIRONMENT_SERVER_NAME.value, self.agent_port_in, count_number_of_subroutines(self))

        # await self.environment_request_socket.send_json(sync_json)

        await self.environment_request_socket.send_json(sync_req.to_json())
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
        # start_msg = await self.environment_broadcast_socket.recv_json()
        start_msg_dict = await self.environment_broadcast_socket.recv_json()
        start_msg = SimulationStartBroadcastMessage.from_dict(start_msg_dict)

        # log simulation start time
        self.START_TIME = time.perf_counter()

        # register agent-to-port map
        port_ledger = start_msg.port_ledger

        self.AGENT_TO_PORT_MAP = dict()
        for agent in port_ledger:
            self.AGENT_TO_PORT_MAP[agent] = port_ledger[agent]
        self.log(f'Agent to port map received: {self.AGENT_TO_PORT_MAP}')

        # setup clock information
        clock_info = start_msg.clock_info
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
                
    async def environment_message_submitter(self, req):
        try:
            req_type = req['@type']
            self.log(f'Submitting a request of type {req_type}.')

            if RequestTypes[req_type] is RequestTypes.TIC_REQUEST:
                t_end = req['t']
                req_json = json.dumps(req)

                # submit request
                self.log(f'Sending {req_type} for t_end={t_end}. Awaiting access to environment request socket...')
                await self.environment_request_lock.acquire()
                self.log('Access to environment request socket confirmed. Sending request...')
                await self.environment_request_socket.send_json(req_json)
                self.log('Request sent successfully. Awaiting confirmation...')

                # wait for sever reply
                await self.environment_request_socket.recv()  
                self.environment_request_lock.release()
                self.log('Tic request reception confirmation received.')         

                return   

            elif RequestTypes[req_type] is RequestTypes.AGENT_ACCESS_REQUEST:
                target = req['target']
                req_json = json.dumps(req)

                # submit request
                self.log(f'Sending Agent Access Request (from {self.name} to {target})...')
                await self.environment_request_lock.acquire()
                await self.environment_request_socket.send_json(req_json)
                self.log('Agent Access request sent successfully. Awaiting response...')
                
                # wait for server reply
                resp = await self.environment_request_socket.recv_json()
                resp = json.loads(resp)
                self.environment_request_lock.release()
                resp_val = resp.get('result')
                self.log(f'Received Request Response: \'{resp_val}\'')        
                
                return resp

            elif RequestTypes[req_type] is RequestTypes.GS_ACCESS_REQUEST:
                target = req['target']            
                req_json = json.dumps(req)

                # submit request
                self.log(f'Sending Ground Station Access Request (from {self.name} to {target})...')
                await self.environment_request_lock.acquire()
                await self.environment_request_socket.send_json(req_json)
                self.log('Ground Station Access request sent successfully. Awaiting response...')
                
                # wait for server reply
                resp = await self.environment_request_socket.recv_json()
                resp = json.loads(resp)
                self.environment_request_lock.release()
                resp_val = resp.get('result')
                self.log(f'Received Request Response: \'{resp_val}\'')       

                return resp
            
            elif RequestTypes[req_type] is RequestTypes.AGENT_INFO_REQUEST:
                req_json = json.dumps(req)

                # submit request
                self.log(f'Sending Agent Info Request...')
                await self.environment_request_lock.acquire()
                await self.environment_request_socket.send_json(req_json)
                self.log('Agent Info request sent successfully. Awaiting response...')
                
                # wait for server reply
                resp = await self.environment_request_socket.recv_json()
                resp = json.loads(resp)
                self.environment_request_lock.release()
                resp_val = resp.get('result')
                self.log(f'Received Request Response: \'{resp_val}\'')       

                return resp
            
            elif RequestTypes[req_type] is RequestTypes.GP_ACCESS_REQUEST:
                req_json = json.dumps(req)
                lat = req['lat']
                lon = req['lon']

                # submit request
                self.log(f'Sending Groung Point Access Request for ({lat}°,{lon}°)...')
                await self.environment_request_lock.acquire()
                await self.environment_request_socket.send_json(req_json)
                self.log('Groung Point Access request sent successfully. Awaiting response...')
                
                # wait for server reply
                resp = await self.environment_request_socket.recv_json()
                resp = json.loads(resp)
                self.environment_request_lock.release()
                resp_val = resp.get('result')
                self.log(f'Received Request Response: \'{resp_val}\'')       

                return resp

            else:
                raise Exception(f'Request of type {req_type} not supported by request submitter.')
        except asyncio.CancelledError:
            pass

    async def message_transmitter(self, msg: dict):
        # reformat message
        msg['src'] = self.name
        msg_type = msg['@type']
        dst = msg['dst']

        req_json = json.dumps(msg)

        # connect socket to destination 
        port = self.AGENT_TO_PORT_MAP[dst]
        self.log(f'Connecting to agent {dst} through port number {port}...')
        self.agent_socket_out.connect(f"tcp://localhost:{port}")
        self.log(f'Connected to agent {dst}!')

        # submit request
        self.log(f'Transmitting a message of type {msg_type} (from {self.name} to {dst})...')
        await self.agent_socket_out_lock.acquire()
        await self.agent_socket_out.send_json(req_json)
        self.log(f'{msg_type} message sent successfully. Awaiting response...')
        
        # wait for server reply
        await self.agent_socket_out.recv()
        self.agent_socket_out_lock.release()
        self.log(f'Received message reception confirmation!')      

        # disconnect socket from destination
        self.log(f'Disconnecting from agent {dst}...')
        self.agent_socket_out.disconnect(f"tcp://localhost:{port}")
        self.log(f'Disconnected from agent {dst}!')

class AgentState:
    def __init__(self, agent: AgentClient, component_list) -> None:
        pass

"""
--------------------
  TESTING AGENTS
--------------------
"""
class TestAgent(AgentClient):    
    def __init__(self, name, scenario_dir) -> None:
        super().__init__(name, scenario_dir)
        self.submodules = [TestModule(self)]  

"""
--------------------
  TESTING MODULES
--------------------
"""
class TestModule(Module):
    def __init__(self, parent_agent) -> None:
        super().__init__('test', parent_agent, [SubModule('sub_test', self)])

class SubModule(Module):
    def __init__(self, name, parent_module) -> None:
        super().__init__(name, parent_module, submodules=[])

    async def coroutines(self):
        try:
            sent_requests = False
            messages_sent = 0
            n_messages = 1
            self.log('Starting periodic print routine...')
            while True:
                if not sent_requests:
                    # test message to parent module
                    msg = dict()
                    msg['src'] = self.name
                    msg['dst'] = self.parent_module.name
                    msg['@type'] = 'PRINT'
                    msg['content'] = 'TEST_PRINT'

                    await self.parent_module.send_internal_message(msg)

                    await self.sim_wait_to(int(self.get_current_time()) + 1)

                    # # agent access req
                    target = 'Mars2'
                    msg = RequestTypes.create_agent_access_request(self.name, 
                                                                    EnvironmentServer.ENVIRONMENT_SERVER_NAME, 
                                                                    target)
                    _ = await self.submit_environment_message(msg)
                    # result = response['result']
                    # self.log(f'Access to {target}: {result}')
                    await self.sim_wait(random.random())

                    # gs access req
                    gs_name = 'NEN2'
                    msg = RequestTypes.create_ground_station_access_request(self.name, 
                                                                            EnvironmentServer.ENVIRONMENT_SERVER_NAME,
                                                                            gs_name)
                    _ = await self.submit_environment_message(msg)
                    # result = response['result']
                    # self.log(f'Access to GS({gs_name}): {result}')
                    await self.sim_wait(random.random())

                    # gp access req
                    lat = 1.0
                    lon = 158.0
                    msg = RequestTypes.create_ground_point_access_request(self.name, 
                                                                        EnvironmentServer.ENVIRONMENT_SERVER_NAME,
                                                                        lat, lon)
                    _ = await self.submit_environment_message(msg)
                    # result = response['result']
                    # self.log(f'Access to GP({lat}°,{lon}°): {result}')
                    await self.sim_wait(random.random())

                    # agent info req 
                    msg = RequestTypes.create_agent_info_request(self.name, EnvironmentServer.ENVIRONMENT_SERVER_NAME)
                    
                    _ = await self.submit_environment_message(msg)
                    # result = response['result']
                    # self.log(f'Agent external state: {result}')

                    await self.sim_wait(4.6656879355937875 * random.random())
                    sent_requests = True
                else:
                    await self.sim_wait( 1e6 )

                if messages_sent < n_messages and '1' in self.parent_module.parent_module.name:
                    msg = dict()
                    msg['src'] = self.name
                    msg['dst'] = 'Mars2'
                    msg['content'] = 'Howdy'
                    msg['@type'] = 'HELLO_WORLD'

                    await self.transmit_message(msg)

                    messages_sent += 1

                # await self.sim_wait(20)
                
        except asyncio.CancelledError:
            self.log('Periodic print routine cancelled')
            return

"""
--------------------
MAIN
--------------------    
"""
if __name__ == '__main__':
    print('Initializing agent...')
    
    agent = TestAgent('Mars1', './scenarios/sim_test')
    
    asyncio.run(agent.live())