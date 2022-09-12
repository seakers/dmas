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
            
            router_task = asyncio.create_task(self._internal_message_router())
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
            await self._shut_down()
    
    async def _internal_message_router(self):
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
                    self.log(f'Received invalid internal message. Discarting message: {msg}')
                    continue

                self.log(f'Received internal message from \'{src_name}\' intended for \'{dst_name}\'')

                # check destination
                if dst_name == self.name:
                    # if this module is the intended receiver, handle message
                    self.log(f'Handling message...')
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
                    await dst.put_in_inbox(msg)

        except asyncio.CancelledError:
            return

    @abstractmethod
    async def _shut_down(self):
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
                await self.send_internal_message(msg)
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
                await self.sim_wait(1e6)     
        except asyncio.CancelledError:
            return
    
    """
    HELPING FUNCTIONS
    """
    @abstractmethod
    async def send_internal_message(self, msg):
        """
        Sends message to its intended destination within this agent's modules. 
        By default it places the message in this module's inbox, which will then be handled by the internal
        message router. The router uses depth-first-search to find its intended destination module. This 
        'send_internal_message' method may be modified to create more analogous communications network between
        modules that better represent the agent being designed. 
        """
        await self.inbox.put(msg)

    async def put_in_inbox(self, msg):
        """
        Places a message in this module's inbox.
        Intended to be called by other modules for sending messages to this module.
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
            return self.parent_module.get_current_time()

    def get_current_real_time(self):
        """
        Returns current time from the start of the simulation
        """
        return (time.perf_counter() - self.START_TIME)


    async def sim_wait(self, delay, module_name=None):
        """
        awaits until simulation time runs for a given delay
        """
        if module_name is None:
            module_name = self.name

        if self.parent_module is None:
            if self.CLOCK_TYPE == SimClocks.REAL_TIME or self.CLOCK_TYPE == SimClocks.REAL_TIME_FAST:
                await asyncio.sleep(delay / self.SIMULATION_FREQUENCY)
            elif (self.CLOCK_TYPE == SimClocks.SERVER_STEP 
                        or self.CLOCK_TYPE == SimClocks.SERVER_TIME
                        or self.CLOCK_TYPE == SimClocks.SERVER_TIME_FAST):

                # if the clock is server-step, then submit a tic request to environment
                t_end = self.sim_time.level + delay       
                tic_msg = RequestTypes.create_tic_request(self.name, 'ENV', t_end)

                await self.submit_request(tic_msg)

                await self.sim_time.when_geq_than(t_end)
            else:
                raise Exception(f'clock type {self.CLOCK_TYPE} not yet supported by module.')
        else:
            await self.parent_module.sim_wait(delay, module_name)       

    @abstractmethod
    async def request_submitter(self, req):
        """
        submitts a request of any type to the environment
        """
        pass

    async def submit_request(self, req):
        """
        submits environment request and returns response from environment server
        """
        if self.parent_module is None:
            return await self.request_submitter(req)
        else:
            return await self.parent_module.submit_request(req)

    @abstractmethod
    async def message_transmitter(self, msg):
        """
        transmits a message of any type to an agent
        """
        pass

    async def transmit_message(self, msg):
        """
        transmits a message to another agent and returns response from said agent
        """
        if self.parent_module is None:
            return await self.message_transmitter(msg)
        else:
            return await self.parent_module.transmit_message(msg)

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



"""
--------------------------------------------------------
 ____                                                                              
/\  _`\                   __                                __                     
\ \ \L\_\    ___      __ /\_\    ___      __     __   _ __ /\_\    ___      __     
 \ \  _\L  /' _ `\  /'_ `\/\ \ /' _ `\  /'__`\ /'__`\/\`'__\/\ \ /' _ `\  /'_ `\   
  \ \ \L\ \/\ \/\ \/\ \L\ \ \ \/\ \/\ \/\  __//\  __/\ \ \/ \ \ \/\ \/\ \/\ \L\ \  
   \ \____/\ \_\ \_\ \____ \ \_\ \_\ \_\ \____\ \____\\ \_\  \ \_\ \_\ \_\ \____ \ 
    \/___/  \/_/\/_/\/___L\ \/_/\/_/\/_/\/____/\/____/ \/_/   \/_/\/_/\/_/\/___L\ \
                      /\____/                                               /\____/
                      \_/__/                                                \_/__/    
 /'\_/`\            /\ \         /\_ \            
/\      \    ___    \_\ \  __  __\//\ \      __   
\ \ \__\ \  / __`\  /'_` \/\ \/\ \ \ \ \   /'__`\ 
 \ \ \_/\ \/\ \L\ \/\ \L\ \ \ \_\ \ \_\ \_/\  __/ 
  \ \_\\ \_\ \____/\ \___,_\ \____/ /\____\ \____\
   \/_/ \/_/\/___/  \/__,_ /\/___/  \/____/\/____/                                                                                                                                                    
--------------------------------------------------------
"""
class Component(Module):
    """
    Describes a generic component of an agent's platform.
    Each component is in charge of performing tasks given to it and checking if it is in a nominal state.
    Components can fail. Their failure is to be handled by their parent subsystem.
    """
    def __init__(self, name, max_power_usage, max_power_generation, power_storage_capacity, max_data_generation, data_storage_capacity, parent_subsystem, n_timed_coroutines) -> None:
        super().__init__(name, parent_subsystem, [], n_timed_coroutines)
        self.power_specs = [max_power_usage, max_power_generation, power_storage_capacity]
        self.data_specs = [max_data_generation, data_storage_capacity]


    async def activate(self):
        await super().activate()

        # state events
        self.nominal = asyncio.Event()
        self.critical = asyncio.Event()
        self.failure = asyncio.Event()

        # power state metrics
        self.power_usage = Container(level=0, capacity=self.power_specs[0])
        self.power_generation = Container(level=0, capacity=self.power_specs[1])
        self.power_storage = Container(level=self.power_specs[2], capacity=self.power_specs[2])

        # data state metrics
        self.power_generation = Container(level=0, capacity=self.power_specs[0])
        self.power_storage = Container(level=0, capacity=self.power_specs[1])

        # log last update time
        self.t_update = self.get_current_time()

    async def coroutines(self):
        # create coroutine tasks
        coroutines = []

        ## Internal coroutines
        nominal_operations = asyncio.create_task(self.nominal_operations())
        nominal_operations.set_name (f'{self.name}_nom_ops')
        coroutines.append(nominal_operations)
        
        crit_monitor = asyncio.create_task(self.crit_monitor())
        crit_monitor.set_name (f'{self.name}_crit_monitor')
        coroutines.append(crit_monitor)

        failure_monitor = asyncio.create_task(self.failure_monitor())
        failure_monitor.set_name (f'{self.name}_failure_monitor')
        coroutines.append(failure_monitor)

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



    @abstractmethod
    async def nominal_operations(self):
        """
        Performs instructions given to component
        """
        pass

    @abstractmethod
    async def crit_monitor(self):
        """
        Monitors component state and triggers critical event if a critical state is detected
        """
        pass

    @abstractmethod
    async def failure_monitor(self):
        """
        Monitors component state and triggers failure event if a failure state is detected
        """
        pass

class Battery(Component):
    def __init__(self, name, max_power_generation, power_storage_capacity, parent_subsystem) -> None:
        super().__init__(name, 0, max_power_generation, power_storage_capacity, 0, 0, parent_subsystem, n_timed_coroutines=1)

    