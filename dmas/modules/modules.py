import asyncio
import json
import logging
from multiprocessing import parent_process
import time
"""
MODULE
"""
class Module:
    """
    Abstract module class. Can house multiple submodules 
    """
    def __init__(self, name, parent_module, submodules = []) -> None:
        self.name = name
        self.parent_module = parent_module

        self.inbox = None       
        self.submodules = submodules

        self.START_TIME = -1                # simulation start time in real-time seconds
        self.sim_time = -1                  # current simulation time in simulation time-steps
        self.SIMULATION_FREQUENCY = 0       # [times-steps/real second]
        
        self.actions_logger = None

    async def activate(self):
        """
        Initiates any thread sensitive or envent-loop sensitive variables
        """
        if self.parent_module is not None:
            self.START_TIME = self.parent_module.START_TIME
            self.SIMULATION_FREQUENCY = self.parent_module.SIMULATION_FREQUENCY

        self.inbox = asyncio.Queue()   
        for submodule in self.submodules:
            await submodule.activate()
        self.log('Activated!', level=logging.INFO)

    async def run(self):
        """
        Executes any internal routines along with any submodules' routines. 
        If class is modified to perform implementation-specific routines, this function must be overwritten to execute
        said routines. Must include catch for CancelledError exception.
        """
        try:
            self.log('starting module coroutines...', level=logging.INFO)
            # create coroutine tasks
            coroutines = []
            for submodule in self.submodules:
                task = asyncio.create_task(submodule.run())
                task.set_name (f'{self.name}_run')
                coroutines.append(task)

            routine_task = asyncio.create_task(self.routine())
            routine_task.set_name (f'{self.name}_routine')
            coroutines.append(routine_task)
            
            router_task = asyncio.create_task(self.internal_message_router())
            router_task.set_name (f'{self.name}_internal_message_router')
            coroutines.append(router_task)

            # wait for the first one to complete
            _, pending = await asyncio.wait(coroutines, return_when=asyncio.FIRST_COMPLETED)
            
            done_name = None
            for coroutine in coroutines:
                if coroutine not in pending:
                    done_name = coroutine.get_name()

            # cancell all other coroutine tasks
            self.log(f'{done_name} Coroutine ended. Terminating all other coroutines...', level=logging.INFO)
            for subroutine in pending:
                subroutine.cancel()
                await subroutine
            return

        except asyncio.CancelledError: 
            self.log('Cancelling all coroutines...')
            for subroutine in coroutines:
                subroutine.cancel()
                await subroutine
            return
        finally:
            await self.shut_down()
    
    async def internal_message_router(self):
        """
        Listens for internal messages being sent between modules and routes them to their respective destinations.
        If this module is the intended destination for this message, then handle the message.
        """
        try:
            while True:
                # wait for any incoming messages
                msg = await self.inbox.get()
                src_name = msg.get('src',None)
                dst_name = msg.get('dst',None)

                if dst_name is None or src_name is None:
                    continue

                self.log(f'Received message from \'{src_name}\' intended for \'{dst_name}\'')

                # if this module is the intended receiver, handle message
                if dst_name == self.name:
                    self.log(f'handling message...')
                    await self.internal_message_handler(msg)
                else:
                    # else, search if any of this module's submodule is the intended destination
                    dst = None
                    for submodule in self.submodules:
                        if submodule.name == dst_name:
                            dst = submodule
                            break
                    
                    if dst is None:
                        if self.parent_module is not None:
                            # if no module is found, forward to parent agent
                            dst = self.parent_module
                        else:
                            # if this is the main module and the destination has not been found, perform depth-first search
                            dst = self.dfs(self, dst_name)
                            if dst is None:
                                self.log(f'couldn\'t find destination to forward message to. Disregarding message...')
                                continue
                    self.log(f'forwarding message to {dst.name}...')
                    await dst.put_message(msg)
        except asyncio.CancelledError:
            return

    """
    FUNCTIONS TO IMPLEMENT:
    """
    async def shut_down(self):
        self.log(f'Terminated.', level=logging.INFO)

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

    async def routine(self):
        """
        Generic routine to be performed by module. May be modified to perform other coroutines.
        """
        try:
            while True:
                await asyncio.sleep(1000)     
        except asyncio.CancelledError:
            return
    
    """
    HELPING FUNCTIONS
    """
    async def put_message(self, msg):
        """
        Places a message in this modules inbox.
        Intended to be executed by other modules for sending messages to this module.
        """
        await self.inbox.put(msg)

    def dfs(self, module, dst_name):
        """
        Performs depth-first search to find a module in that corresponds to the name being searched
        """
        if module.name == dst_name:
            return module
        elif len(module.submodules) == 0:
            return None
        else:
            for submodule in module.submodules:
                dst = self.dfs(submodule, dst_name)
                if dst is not None:
                    return dst
            return None

    def get_current_time(self):
        if self.parent_module is None:
            if self.START_TIME < 0:
                self.sim_time = 0
            else:
                self.sim_time = (time.perf_counter() - self.START_TIME) * self.SIMULATION_FREQUENCY
            
            return self.sim_time
        else:
            self.parent_module.get_current_time()

    def get_current_real_time(self):
        return (time.perf_counter() - self.START_TIME)

    async def sim_wait(self, delay):
        await asyncio.sleep(delay / self.SIMULATION_FREQUENCY)

    def log(self, content, level=logging.DEBUG, module_name=None):
        if module_name is None:
            module_name = self.name

        if self.parent_module is None:
            if self.name == module_name:
                out = f'{module_name} @ T{self.get_current_time():.{3}f}: {content}'
            else:
                out = f'{self.name} ({module_name}) @ T{self.get_current_time():.{3}f}: {content}'

            if level == logging.DEBUG:
                self.actions_logger.debug(out)
            elif level == logging.INFO:
                self.actions_logger.info(out)
            elif level == logging.WARNING:
                self.actions_logger.warning(out)
            elif level == logging.ERROR:
                self.actions_logger.error(out)
            elif level == logging.CRITICAL:
                self.actions_logger.critical(out)
        else:
            self.parent_module.log(content, level, module_name)
"""
--------------------
  TESTING MODULES
--------------------
"""
class SubModule(Module):
    def __init__(self, name, parent_module) -> None:
        super().__init__(name, parent_module, submodules=[])

    async def routine(self):
        try:
            self.log('Starting periodic print routine...')
            while True:
                msg = dict()
                msg['src'] = self.name
                msg['dst'] = self.parent_module.name
                msg['@type'] = 'PRINT'
                msg['content'] = 'TEST_PRINT'

                await self.parent_module.put_message(msg)

                await self.sim_wait(1)
        except asyncio.CancelledError:
            self.log('Periodic print routine cancelled')
            return

class TestModule(Module):
    def __init__(self, parent_agent) -> None:
        submodules = [SubModule('sub_test', self)]
        super().__init__('test', parent_agent, submodules)