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
        # print('MODULE: awaiting messages')
        while True:
            # wait for any incoming requests
            msg = await self.inbox.get()
            # print('MODULE: received message!')

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
            # for process in processes:
            #     process.cancel()
            return

    async def message_handler(self):
        try:
            while True:
                # wait for any incoming requests
                _ = await self.inbox.get()

                # hangle request
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            return

    async def routine(self):
        try:
            while True:
                # print('SUBMODULE: Preparing to send message to parent module')
                msg = dict()
                msg['src'] = self.name
                msg['dst'] = self.parent_module.name
                msg['@type'] = 'PRINT'
                msg['content'] = 'TEST_PRINT'

                await self.parent_module.put_message(msg)

                # print('SUBMODULE: Message sent!')
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            return

    async def put_message(self, msg):
        await self.inbox.put(msg)
"""
--------------------
TESTING MODULES
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
#                 msg_string = self.environment_broadcast_socket.recv_json()
#                 msg_dict = json.loads(msg_string)

#                 src = msg_dict['src']
#                 dst = msg_dict['dst']
#                 msg_type = msg_dict['@type']
#                 t_server = msg_dict['server_clock']

#                 # self.message_logger.info(f'Received message of type {msg_type} from {src} intended for {dst} with server time of t={t_server}!')

#                 if msg_type == 'END':
#                     self.state_logger.info(f'Sim has ended.')
                    
#                     # send a reception confirmation
#                     # self.request_logger.info('Connection to environment established!')
#                     self.environment_request_socket.send_string(self.name)
#                     # self.request_logger.info('Agent termination aknowledgement sent. Awaiting environment response...')

#                     # wait for server reply
#                     self.environment_request_socket.recv() 
#                     # self.request_logger.info('Response received! terminating agent.')
#                     return

#                 elif msg_type == 'tic':
#                     # self.message_logger.info(f'Updating internal clock.')
#                     _ = 1