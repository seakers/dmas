from abc import abstractmethod
import asyncio
from enum import Enum
import logging
import random
import time
from messages import BroadcastTypes, RequestTypes

from utils import Container, SimClocks
"""
MODULE
"""
class Module:
    """
    Abstract module class. Can house multiple submodules 
    """
    def __init__(self, name, parent_module=None, submodules = [], n_timed_coroutines=1) -> None:
        self.name = name
        self.parent_module = parent_module

        self.inbox = None       
        self.submodules = submodules

        self.START_TIME = -1                                    # Simulation start time in real-time seconds
        self.sim_time = None                                    # Current simulation time
        self.CLOCK_TYPE = None                                  # Clock type being used in this simulation

        self.NUMBER_OF_TIMED_COROUTINES = n_timed_coroutines    # number of coroutines to be executed by this module
        
        self.actions_logger = None

    async def activate(self):
        """
        Initiates any thread-sensitive or envent-loop sensitive variables to be used in this module.
        """
        if self.parent_module is not None:
            self.START_TIME = self.parent_module.START_TIME
            self.SIMULATION_FREQUENCY = self.parent_module.SIMULATION_FREQUENCY
            self.CLOCK_TYPE = self.parent_module.CLOCK_TYPE
            self.sim_time = self.parent_module.sim_time

        if self.NUMBER_OF_TIMED_COROUTINES < 0:
            raise Exception('module needs to specify how many routines are being performed.')

        self.inbox = asyncio.Queue()   
        for submodule in self.submodules:
            await submodule.activate()
            self.NUMBER_OF_TIMED_COROUTINES += submodule.NUMBER_OF_TIMED_COROUTINES
        
        self.log('Activated!', level=logging.INFO)


    async def run(self):
        """
        Executes any internal routines along with any submodules' routines. 
        If class is modified to perform implementation-specific routines, this function must be overwritten to execute
        said routines. Must include catch for CancelledError exception.
        """
        try:
            self.log('Starting module coroutines...', level=logging.INFO)
            # create coroutine tasks
            coroutines = []

            ## Internal coroutines
            routine_task = asyncio.create_task(self.coroutines())
            routine_task.set_name (f'{self.name}_routine')
            coroutines.append(routine_task)
            
            router_task = asyncio.create_task(self.internal_message_router())
            router_task.set_name (f'{self.name}_internal_message_router')
            coroutines.append(router_task)

            ## Submodule coroutines
            for submodule in self.submodules:
                task = asyncio.create_task(submodule.run())
                task.set_name (f'{self.name}_run')
                coroutines.append(task)

            # wait for the first coroutine to complete
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
                # wait for any incoming internal messages
                msg = await self.inbox.get()
                src_name = msg.get('src',None)
                dst_name = msg.get('dst',None)

                if dst_name is None or src_name is None:
                    self.log(f'Received invalid internal message. Discarting message.')
                    continue

                self.log(f'Received internal message from \'{src_name}\' intended for \'{dst_name}\'')

                # check destination
                if dst_name == self.name:
                    # if this module is the intended receiver, handle message
                    self.log(f'handling message...')
                    await self.internal_message_handler(msg)
                else:
                    # else, search if any of this module's submodule is the intended destination
                    dst = None

                    for submodule in self.submodules:
                        # first check if any submodule is its intended destination
                        if submodule.name == dst_name:
                            dst = submodule
                            break
                    
                    if dst is None:
                        if self.parent_module is not None:
                            # if no module is found, forward to parent agent
                            dst = self.parent_module
                        else:
                            # if this is the main module with no parent and the destination module has not been 
                            # found yet, perform depth-first search with all submodules until the destination is found
                            dst = self.dfs(self, dst_name)
                            if dst is None:
                                self.log(f'couldn\'t find destination to forward message to. Disregarding message...')
                                continue
                    self.log(f'forwarding message to {dst.name}...')
                    await dst.put_message(msg)

        except asyncio.CancelledError:
            return

    @abstractmethod
    async def shut_down(self):
        """
        Cleanup subroutine that should be used to terminate any thread-sensitive or envent-loop sensitive variables
        """
        self.log(f'Terminated.', level=logging.INFO)
        pass
    
    @abstractmethod
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
        """
        Generic routine to be performed by module. May be modified to perform other coroutines.
        Must not return unless an exception is raised. If method returns or raises an unhandled 
        exception, this module and its parent module will terminate.
        """
        try:
            while True:
                await self.sim_wait(1000)     
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
        """
        Returns the current simulation time
        """
        if self.parent_module is None:
            if self.sim_time is None:
                return 0

            if self.CLOCK_TYPE == SimClocks.REAL_TIME or self.CLOCK_TYPE == SimClocks.REAL_TIME_FAST:
                if self.START_TIME >= 0:
                    self.sim_time = (time.perf_counter() - self.START_TIME) * self.SIMULATION_FREQUENCY
                
                return self.sim_time
            elif self.CLOCK_TYPE == SimClocks.SERVER_STEP:
                return self.sim_time.level
            else:
                raise Exception(f'Clock of type {self.CLOCK_TYPE.value} not yet supported')
        else:
            self.parent_module.get_current_time()

    def get_current_real_time(self):
        """
        Returns current time from the start of the simulation
        """
        return (time.perf_counter() - self.START_TIME)

    @abstractmethod
    async def submit_tic_request(self, delay, module_name):
        """
        creates a tic-request to be submitted to the environment
        """
        pass

    async def sim_wait(self, delay, module_name=None):
        """
        awaits until simulation time runs for a given delay
        """
        if self.parent_module is None:
            if self.CLOCK_TYPE == SimClocks.REAL_TIME or self.CLOCK_TYPE == SimClocks.REAL_TIME_FAST:
                await asyncio.sleep(delay / self.SIMULATION_FREQUENCY)
            elif (self.CLOCK_TYPE == SimClocks.SERVER_STEP 
                        or self.CLOCK_TYPE == SimClocks.SERVER_TIME
                        or self.CLOCK_TYPE == SimClocks.SERVER_TIME_FAST):

                # if the clock is server-step, then submit a tic request to environment
                await self.submit_tic_request(delay, module_name)

                t_end = self.sim_time.level + delay
                await self.sim_time.when_geq_than(t_end)
            else:
                raise Exception(f'clock type {self.CLOCK_TYPE} not yet supported by module.')
        else:
            await self.parent_module.sim_wait(delay, module_name)       

    async def sim_wait_to(self, t, module_name=None):
        """
        awaits until simulation time reaches a time t
        """
        if self.parent_module is None:
            t_curr = self.get_current_time()
            delay = t - t_curr
            await self.sim_wait(delay, module_name=module_name)
        else:
            await self.parent_module.sim_wait_to(t, module_name)       

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