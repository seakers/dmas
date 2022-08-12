from dmas.agent import AbstractAgent
from dmas.modules.modules import Module, SubModule
import asyncio

"""
--------------------------------------------------------
 _____            _                      _              
|  ___|          (_)                    (_)             
| |__ _ __   __ _ _ _ __   ___  ___ _ __ _ _ __   __ _  
|  __| '_ \ / _` | | '_ \ / _ \/ _ \ '__| | '_ \ / _` | 
| |__| | | | (_| | | | | |  __/  __/ |  | | | | | (_| | 
\____/_| |_|\__, |_|_| |_|\___|\___|_|  |_|_| |_|\__, | 
             __/ |                                __/ | 
            |___/                                |___/  
___  ___          _       _                             
|  \/  |         | |     | |                            
| .  . | ___   __| |_   _| | ___                        
| |\/| |/ _ \ / _` | | | | |/ _ \                       
| |  | | (_) | (_| | |_| | |  __/                       
\_|  |_/\___/ \__,_|\__,_|_|\___|                                                                                                                                                   
--------------------------------------------------------
"""

class EngineeringModule(Module):
    def __init__(self, parent_agent, component_list: list, 
                    agent_comms_socket_in, agent_comms_socket_out, 
                    environment_broadcast_socket, environment_request_socket, environment_request_lock) -> None:
        # network_simulator = NetworkSimulator(self, parent_agent)
        platform_simulator = PlatformSimulator(self, component_list, environment_broadcast_socket)
        # operations_planner = OperationsPlanner()

        submodules = []
        super().__init__('engineering_mod', parent_agent, submodules)

"""
--------------------
Platform Simulator
--------------------
"""
class PlatformSimulator(Module):
    """
    Simulates and keeps track of the state of the agent.

    """
    def __init__(self, parent_module: Module, component_list, environment_request_socket, environment_request_lock) -> None:
        super().__init__('plaform_simulator', parent_module, submodules=[])
        self.parent_agent = self.parent_module.parent_module
        self.environment_request_socket = environment_request_socket
        self.environment_request_lock = environment_request_lock
        self.component_list = []
        for component in component_list:
            self.component_list.append(component)
        
    async def activate(self):
        await super().activate()
        self.updated = asyncio.Event()
        self.update_state()
        return 

    async def internal_message_handler(self):
        """
        Reads messages from other modules. Only accepts the following message types:
            -STATE_UPDATE_REQUEST: integrates state up to current simulation time. Returns state to sender
            -CRITICAL_STATE:
        """
        try:
            while True:
                # wait for any incoming messages
                msg = await self.inbox.get()
                dst_name = msg['dst']

                if dst_name != self.name:
                    await self.internal_message_router(msg)
                else:
                    if msg['@type'] == 'PRINT':
                        content = msg['content']
                        print(content)    

        except asyncio.CancelledError:
            return
    
    async def wait_for_critical_state(self):
        """
        Sends current state to Predictive model submodule and waits for estimate for the next projected critical state. 

        """
        pass

    async def periodic_state_update(self):

        while True:
            self.update_state()
            await asyncio.sleep(self.parent_agent.SIMULATION_FREQUENCY)

    async def wait_for_environment_event(self):
        pass

    def is_critical(self):
        return False

    def update_state():
        pass
"""
--------------------
Network Simulator
--------------------
"""
class NetworkSimulator(SubModule):
    def __init__(self, parent_module: Module, agent_comms_socket_in, agent_comms_socket_out, environment_request_socket) -> None:
        super().__init__('network_sim', parent_module)
        self.agent_comms_socket_in = agent_comms_socket_in
        self.agent_comms_socket_out = agent_comms_socket_out
        self.environment_request_socket = environment_request_socket

    async def internal_message_handler(self):
        """
        Reads messages from other modules. Only accepts transmission request messages with contents meant to be sent to other agents. 
        All other messages are ignored.
        """
        try:
            while True:
                # wait for any incoming transmission requests
                msg = await self.inbox.get()

                # hangle request
                if msg['dst'] == self.name and msg['@type'] == 'MESSAGE_TRANSMISSION':
                    transmission = msg['content']

                    src_name = transmission.get('src', None)
                    dst_name = transmission.get('dst', None)
                    t_curr = self.parent_module.parent_agent.get_current_simulation_time()

                    routing_plan = transmission.get('routing', None)
                    if routing_plan is None:
                        # if transmission does not have a routing plan, create one
                        routing_plan = await self.create_routing_plan(src_name, dst_name, t_curr)
                        transmission['routing'] = routing_plan

                    routing_plan_index = routing_plan.index(self.parent_module.parent_agent.name)
                    if routing_plan[routing_plan_index] == routing_plan[-1]:
                        # if being asked to transmit a message to this submodule's own parent agent, then discard message
                        continue

                    transmission_json = json.dumps(transmission)
                    next_dst = routing_plan[routing_plan_index + 1]

                    while True:
                        t_curr = self.parent_module.parent_agent.get_current_simulation_time()
                        t_start, t_end = await self.get_next_access(next_dst, t_curr)
                        
                        if t_curr < t_start:
                            # access starts at a later time, wait until access is achieved
                            break
                        elif t_start <= t_curr <= t_end:
                            # currently accessing message destination, transmit message
                            await self.transmit_message(transmission_json)
                            break
                        else:
                            # previously acquired access times have passed, calculate new access and try again.
                            continue
                    

        except asyncio.CancelledError:
            return

    async def routine(self):
        """
        In charge of listening to transmission port for any requests 
        1-await reception request
        2-check if buffer contains enough space 
        3-Send confirmation once space has been allocated
        4-await message
        5-respond with aknowledgement
        6-compare predicted transmission duration vs real duration
        7-sleep to compensate missing transmission time if needed
        8-if data message, forward message to science module
        9-else if measurement request message, forward to scheduler module
        10-else if forwading message, forward to send message process
        11-if sent to another module, delete message from buffer
        ___________

        msg_string = self.environment_broadcast_socket.recv_json()
        msg_dict = json.loads(msg_string)

        src = msg_dict['src']
        dst = msg_dict['dst']
        msg_type = msg_dict['@type']
        t_server = msg_dict['server_clock']

        # self.message_logger.info(f'Received message of type {msg_type} from {src} intended for {dst} with server time of t={t_server}!')

        if msg_type == 'END':
            self.state_logger.info(f'Sim has ended.')
            
            # send a reception confirmation
            # self.request_logger.info('Connection to environment established!')
            self.environment_request_socket.send_string(self.name)
            # self.request_logger.info('Agent termination aknowledgement sent. Awaiting environment response...')

            # wait for server reply
            self.environment_request_socket.recv() 
            # self.request_logger.info('Response received! terminating agent.')
            return

        """
        
        pass

    async def transmit_message(self, transmission_json):
        """
        1-await transmission request
        2-create routing plan
        3-insert routing plan into message
        4-wait for next access to next agent in routing plan
        5-Send access confirmation request to env
        6-await access confirmation from env
        7-send buffer allocation request to destination agent
        8-await buffer allocation confirmation
        9-begin transmission
        10-compare predicted transmission duration vs real duration
        11-sleep to compensate missing transmission time if needed
        12-delete message from buffer
        """       
        pass

    async def create_routing_plan(self, src_name, dst_name, t_curr):
        pass

    # class CommunicationsModule(Module):
#     def __init__(self, parent_agent: AbstractAgent, results_dir, environment_broadcast_socket) -> None:
#         super().__init__('comms_module', parent_agent, results_dir, submodules=[])
    
#     async def message_handler(self):
#         while True:
#             socks = dict(self.poller.poll())                

#             if self.environment_broadcast_socket in socks:
                # msg_string = self.environment_broadcast_socket.recv_json()
                # msg_dict = json.loads(msg_string)

                # src = msg_dict['src']
                # dst = msg_dict['dst']
                # msg_type = msg_dict['@type']
                # t_server = msg_dict['server_clock']

                # # self.message_logger.info(f'Received message of type {msg_type} from {src} intended for {dst} with server time of t={t_server}!')

                # if msg_type == 'END':
                #     self.state_logger.info(f'Sim has ended.')
                    
                #     # send a reception confirmation
                #     # self.request_logger.info('Connection to environment established!')
                #     self.environment_request_socket.send_string(self.name)
                #     # self.request_logger.info('Agent termination aknowledgement sent. Awaiting environment response...')

                #     # wait for server reply
                #     self.environment_request_socket.recv() 
                #     # self.request_logger.info('Response received! terminating agent.')
                #     return

                # elif msg_type == 'tic':
                #     # self.message_logger.info(f'Updating internal clock.')
                #     _ = 1