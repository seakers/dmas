import asyncio
import json
from multiprocessing import parent_process
"""
MODULE
"""
class Module:
    """
    Generic module class. Can house multiple submodules 
    """
    def __init__(self, name, parent_module, submodules = []) -> None:
        self.name = name
        self.parent_module = parent_module

        self.inbox = None       
        self.submodules = submodules

    async def activate(self):
        """
        Initiates any thread-sensitive or envent-loop-sensitive variables
        """
        self.inbox = asyncio.Queue()   
        for submodule in self.submodules:
            await submodule.activate()

    async def run(self):
        """
        Executes any internal routines along with any submodules' routines. 
        If class is modified to perform implementation-specific routines, this function must be overwritten to execute
        said routines. Must include catch for CancelledError exception.
        """
        try:
            subroutines = [asyncio.Task(submodule.run()) for submodule in self.submodules]
            subroutines.append(asyncio.Task(self.routine()))
            subroutines.append(asyncio.Task(self.internal_message_router()))

            await asyncio.wait(subroutines, return_when=asyncio.ALL_COMPLETED)
        except asyncio.CancelledError: 
            print('cancelling submodule routines...')
            for subroutine in subroutines:
                subroutine.cancel()
            return

    async def internal_message_router(self):
        """
        Listens for internal messages being sent between modules and routes them to their respective destinations.
        If this module is the intended destination for this message, then handle the message.
        """
        try:
            while True:
                # wait for any incoming messages
                msg = await self.inbox.get()
                dst_name = msg['dst']

                # if this module is the intended receiver, handle message
                if dst_name == self.name:
                    await self.handle_message(msg)
                else:
                    # else, search if any of this module's submodule is the intended destination
                    dst = None
                    for submodule in self.submodules:
                        if submodule.name == dst_name:
                            dst = submodule
                            break
                    
                    # if no module is found, forward to parent agent
                    if dst is None:
                        dst = self.parent_module

                    await dst.put_message(msg)
        except asyncio.CancelledError:
            return

    async def handle_message(self, msg):
        """
        Handles message intended for this module.
        """
        try:
            if msg['@type'] == 'PRINT':
                content = msg['content']
                print(content)                
        except asyncio.CancelledError:
            return

    async def routine(self):
        """
        Generic routine to be performed by module.
        """
        try:
            while True:
                await asyncio.sleep(1000)     
        except asyncio.CancelledError:
            return
    
    async def put_message(self, msg):
        """
        Places a message in this modules inbox.
        Intended to be executed by other modules for sending messages to this module.
        """
        await self.inbox.put(msg)

"""
--------------------
  TESTING MODULES
--------------------
"""
class SubModule(Module):
    def __init__(self, name, parent_module) -> None:
        super().__init__(name, parent_module, submodules=[])

    async def run(self):
        """
        Executes any internal routines along with any submodules' routines. 
        If class is modified to perform implementation-specific routines, this function must be overwritten to execute
        said routines. Must include catch for CancelledError exception.
        """
        try:
            internal_message_router_task = asyncio.Task(self.internal_message_router())
            routine_task = asyncio.Task(self.routine())

            await asyncio.gather(internal_message_router_task, routine_task)

        except asyncio.CancelledError:
            internal_message_router_task.cancel()
            await internal_message_router_task

            routine_task.cancel()
            await routine_task

            return

    async def handle_message(self, msg):
        """
        Handles message intended for this module.
        """
        try:
            if msg['@type'] == 'PRINT':
                content = msg['content']
                print(content)                
        except asyncio.CancelledError:
            return

    async def routine(self):
        try:
            print('Starting periodic print routine...')
            while True:
                msg = dict()
                msg['src'] = self.name
                msg['dst'] = self.parent_module.name
                msg['@type'] = 'PRINT'
                msg['content'] = 'TEST_PRINT'

                await self.parent_module.put_message(msg)

                await asyncio.sleep(1)
        except asyncio.CancelledError:
            print('Periodic print routine cancelled')
            return

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