import asyncio
import json

class Module:
    def __init__(self, name, parent_agent, submodules = []) -> None:
        self.name = name
        self.parent_agent = parent_agent

        self.inbox = None       
        self.submodules = submodules

    async def activate(self):
        self.inbox = asyncio.Queue()   
        for submodule in self.submodules:
            await submodule.activate()

    async def run(self):
        subroutines = [submodule.run() for submodule in self.submodules]
        subroutines.append(self.message_handler())

        _, pending = await asyncio.wait(subroutines, return_when=asyncio.FIRST_COMPLETED)

        for subroutine in pending:
            subroutine.cancel()

    async def message_handler(self):
        while True:
            # wait for any incoming requests
            msg = await self.inbox.get()

            # hangle request
            dst_name = msg['dst']

            if dst_name == self.name:
                if msg['@type'] == 'PRINT':
                    content = msg['content']
                    print(content)
            else:
                dst = None
                for submodule in self.submodules:
                    if submodule.name == dst_name:
                        dst = submodule
                        break
                
                if dst is None:
                    dst = self.parent_agent

                await dst.put_message(msg)
                
    async def put_message(self, msg):
        await self.inbox.put(msg)

class SubModule:
    def __init__(self, name, parent_module: Module) -> None:
        self.name = name
        self.parent_module = parent_module
        self.inbox = None

    async def activate(self):
        self.inbox = asyncio.Queue()  

    async def run(self):
        try:
            processes = [self.message_handler(), self.routine()]
            await asyncio.wait(processes, return_when=asyncio.FIRST_COMPLETED)

        except asyncio.CancelledError:
            return

    async def message_handler(self):
        try:
            while True:
                # wait for any incoming messages
                _ = await self.inbox.get()

                # hangle request
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            return

    async def routine(self):
        try:
            while True:
                msg = dict()
                msg['src'] = self.name
                msg['dst'] = self.parent_module.name
                msg['@type'] = 'PRINT'
                msg['content'] = 'TEST_PRINT'

                await self.parent_module.put_message(msg)

                await asyncio.sleep(1)
        except asyncio.CancelledError:
            return

    async def put_message(self, msg):
        await self.inbox.put(msg)

"""
--------------------
--------------------
ENGINEERING MODULES
--------------------
--------------------
"""
class EngineeringModule(Module):
    def __init__(self, parent_agent, component_list: list, agent_comms_socket, environment_request_socket) -> None:
        network_simulator = NetworkSimulator(agent)
        platform_simulator = PlatformSimulator()
        operations_planner = OperationsPlanner()

        submodules = []
        super().__init__('engineering_mod', parent_agent, submodules)

"""
--------------------
Network Simulator
--------------------
"""
class NetworkSimulator(SubModule):
    def __init__(self, parent_module: Module, component_list, agent_comms_socket_in, agent_comms_socket_out, environment_request_socket) -> None:
        super().__init__('network_sim', parent_module)
        self.agent_comms_socket_in = agent_comms_socket_in
        self.agent_comms_socket_out = agent_comms_socket_out
        self.environment_request_socket = environment_request_socket

    async def message_handler(self):
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


"""
--------------------
--------------------
  TESTING MODULES
--------------------
--------------------
"""
class TestModule(Module):
    def __init__(self, parent_agent) -> None:
        submodules = [SubModule('sub_test', self)]
        super().__init__('test', parent_agent, submodules)

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