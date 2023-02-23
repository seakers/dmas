from abc import abstractmethod
import asyncio
from curses.panel import top_panel
from enum import Enum
import logging
import os
import random
import shutil
import sys
import time
from messages import *
from utils import *
from messages import InternalMessage

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
            self.parent_module : Module
            self.START_TIME = self.parent_module.START_TIME
            self.SIMULATION_FREQUENCY = self.parent_module.SIMULATION_FREQUENCY
            self.CLOCK_TYPE = self.parent_module.CLOCK_TYPE
            self.sim_time = self.parent_module.sim_time

        if self.NUMBER_OF_TIMED_COROUTINES < 0:
            raise Exception('module needs to specify how many routines are being performed.')

        self.inbox = asyncio.Queue()   
        for submodule in self.submodules:
            submodule : Module
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
            coroutines : list = []

            ## Internal coroutines            
            router_task = asyncio.create_task(self._internal_message_router())
            router_task.set_name (f'{self.name}_internal_message_router')
            coroutines.append(router_task)

            routine_task = asyncio.create_task(self.coroutines())
            routine_task.set_name (f'{self.name}_coroutines')
            coroutines.append(routine_task)

            ## Submodule coroutines
            for submodule in self.submodules:
                submodule : Module
                task = asyncio.create_task(submodule.run())
                task.set_name (f'{submodule.name}_run')
                coroutines.append(task)

            # wait for the first coroutine to complete
            _, pending = await asyncio.wait(coroutines, return_when=asyncio.FIRST_COMPLETED)
            
            done_name = None
            for coroutine in coroutines:
                if coroutine not in pending:
                    coroutine : asyncio.Task
                    done_name = coroutine.get_name()

            # cancell all other coroutine tasks
            self.log(f'{done_name} Coroutine ended. Terminating all other coroutines...', level=logging.INFO)
            for subroutine in pending:
                subroutine : asyncio.Task
                subroutine.cancel()
                await subroutine
            return

        except asyncio.CancelledError: 
            self.log('Cancelling all internal tasks...')
            for subroutine in coroutines:
                subroutine : asyncio.Task
                if 'router' in subroutine.get_name() or 'coroutines' in subroutine.get_name():
                    self.log(f'Cancelling task \'{subroutine.get_name()}\'...')
                else:
                    self.log(f'Cancelling submodule \'{subroutine.get_name()}\'...')
                
                subroutine.cancel()
                await subroutine

                if 'router' in subroutine.get_name() or 'coroutines' in subroutine.get_name():
                    self.log(f'Successfully cancelled task \'{subroutine.get_name()}\'!')
                else:
                    self.log(f'Successfully cancelled submodule \'{subroutine.get_name()}\'!')

            self.log('Internal tasks successfully cancelled!')
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

                # if dst_name is None or src_name is None:
                if not isinstance(msg, InternalMessage):
                    self.log(f'Received invalid internal message. Discarding message: {msg}')
                    continue
                
                src_name = msg.src_module
                dst_name = msg.dst_module
                self.log(f'Received internal message of type {type(msg)} from \'{src_name}\' intended for \'{dst_name}\'')

                # check destination
                if dst_name == self.name:
                    # if this module is the intended receiver, handle message
                    self.log(f'Handling message of type {type(msg)}...')
                    await self.internal_message_handler(msg)
                    self.log(f'Message handled!',level=logging.DEBUG)
                else:
                    # else, search if any of this module's submodule is the intended destination
                    dst = None

                    for submodule in self.submodules:
                        # first check if any submodule is its intended destination
                        submodule : Module
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
                            dst = self.find_dst(dst_name)
                            if dst is None:
                                self.log(f'Couldn\'t find destination to forward message to. Disregarding message...')
                                continue
                    self.log(f'Forwarding message to \'{dst.name}\'...', level=logging.DEBUG)
                    await dst.put_in_inbox(msg)

        except asyncio.CancelledError:
            return

    @abstractmethod
    async def _shut_down(self):
        """
        Cleanup subroutine that should be used to terminate any thread-sensitive or envent-loop sensitive variables
        """
        self.log(f'Terminated.', level=logging.INFO)
        return
    
    @abstractmethod
    async def internal_message_handler(self, msg: InternalMessage):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            dst_name = msg.dst_module
            if dst_name != self.name:
                # this module is NOT the intended receiver for this message. Forwarding to rightful destination
                await self.send_internal_message(msg)
            else:
                # this module is the intended receiver for this message. Handling message
                self.log(f'Internal messages with contents of type: {type(msg.content)} not yet supported. Discarding message.')
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
                wait_task = asyncio.create_task(self.sim_wait(1e6))
                await wait_task

        except asyncio.CancelledError:
            if wait_task is not None and isinstance(wait_task, asyncio.Task) and not wait_task.done():
                self.log(f'Aborting sim_wait...')
                wait_task : asyncio.Task
                wait_task.cancel()
                await wait_task
    
    """
    HELPING FUNCTIONS
    """
    async def send_internal_message(self, msg: InternalMessage):
        """
        Sends message to its intended destination within this agent's modules. 
        By default it places the message in this module's inbox, which will then be handled by the internal
        message router. The router uses depth-first-search to find its intended destination module. This 
        'send_internal_message' method may be modified to create more analogous communications network between
        modules that better represent the agent being designed. 
        """
        if not isinstance(msg, InternalMessage):
            raise TypeError('Attepmting to send a message of an unknown type')

        self.log(f'Sending internal message of type {type(msg)} to module \'{msg.dst_module}\'...')
        self.log(f'{str(msg)}', logger_type=LoggerTypes.INTERNAL_MESSAGE, level=logging.DEBUG)
        await self.inbox.put(msg)

    async def put_in_inbox(self, msg: InternalMessage):
        """
        Places a message in this module's inbox.
        Intended to be called by other modules for sending messages to this module.
        """
        await self.inbox.put(msg)

    def find_dst(self, dst_name: str):
        """
        Finds Module class object with the same name as the desired destination.
        Searches all modules in the node using depth-first-search.
        """
        top_module = self.get_top_module()
        return self.dfs(top_module, dst_name)

    def dfs(self, module, dst_name):
        """
        Performs depth-first search to find a module in that corresponds to the name being searched
        """
        # self.log(f'Visiting module {module.name} with submodules [{module.submodules}] looking for {dst_name}')
        module : Module
        if module.name == dst_name:
            return module
        elif len(module.submodules) == 0:
            return None
        else:
            for submodule in module.submodules:
                submodule : Module
                dst = self.dfs(submodule, dst_name)
                if dst is not None:
                    return dst
            return None

    def get_current_time(self) -> float:
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
            elif self.CLOCK_TYPE == SimClocks.SERVER_EVENTS:
                return self.sim_time.level
            else:
                raise Exception(f'Clock of type {self.CLOCK_TYPE.value} not yet supported')
        else:
            return self.parent_module.get_current_time()

    def get_current_real_time(self) -> float:
        """
        Returns current time from the start of the simulation
        """
        return (time.perf_counter() - self.START_TIME)


    async def sim_wait(self, delay, module_name=None):
        """
        awaits until simulation time runs for a given delay

        delay:
            duration of delay being waited
        module_name:
            name of the module requesting the wait
        """
        try:
            wait_for_parent_module = None
            message_submission = None
            wait_for_clock = None
    
            if module_name is None:
                module_name = self.name

            if self.parent_module is None:
                if self.CLOCK_TYPE == SimClocks.REAL_TIME or self.CLOCK_TYPE == SimClocks.REAL_TIME_FAST:
                    
                    async def cancel_me():
                        try:
                            await asyncio.sleep(delay / self.SIMULATION_FREQUENCY)
                        except asyncio.CancelledError:
                            self.log(f'Cancelled sleep of delay {delay / self.SIMULATION_FREQUENCY} [s]', module_name=module_name)
                            raise

                    wait_for_clock = asyncio.create_task(cancel_me())
                    await wait_for_clock

                elif (self.CLOCK_TYPE == SimClocks.SERVER_EVENTS 
                            or self.CLOCK_TYPE == SimClocks.SERVER_TIME
                            or self.CLOCK_TYPE == SimClocks.SERVER_TIME_FAST):

                    # if the clock is server-step, then submit a tic request to environment
                    self.sim_time : Container
                    t_req = self.sim_time.level + delay 

                    tic_msg = TicRequestMessage(self.name, EnvironmentModuleTypes.ENVIRONMENT_SERVER_NAME.value, t_req)
                    
                    message_submission = asyncio.create_task(self.submit_environment_message(tic_msg, module_name))
                    await message_submission

                    wait_for_clock = asyncio.create_task(self.sim_time.when_geq_than(t_req))
                    await wait_for_clock
                else:
                    raise Exception(f'clock type {self.CLOCK_TYPE} not yet supported by module.')
            else:
                wait_for_parent_module = asyncio.create_task(self.parent_module.sim_wait(delay, module_name))
                await wait_for_parent_module
        
        except asyncio.CancelledError:
            if wait_for_parent_module is not None and not wait_for_parent_module.done():
                wait_for_parent_module : asyncio.Task
                wait_for_parent_module.cancel()
                await wait_for_parent_module

            if message_submission is not None and not message_submission.done():
                message_submission : asyncio.Task
                message_submission.cancel()
                await message_submission

            if wait_for_clock is not None and not wait_for_clock.done():
                wait_for_clock : asyncio.Task
                wait_for_clock.cancel()
                await wait_for_clock

            raise

    async def sim_wait_to(self, t, module_name=None):
        """
        awaits until simulation time reaches a certain time

        t:
            final time being waited on
        module_name:
            name of the module requesting the wait
        """
        try:
            sim_wait = None            

            if module_name is None:
                module_name = self.name

            t_curr = self.get_current_time()
            delay = t - t_curr

            sim_wait = asyncio.create_task(self.sim_wait(delay, module_name=module_name))
            await sim_wait

        except asyncio.CancelledError:
            if sim_wait is not None and sim_wait.done():
                sim_wait : asyncio.Task
                sim_wait.cancel()
                await sim_wait

    @abstractmethod
    async def environment_message_submitter(self, msg: NodeToEnvironmentMessage, module_name: str=None):
        """
        submitts a request of any type to the environment
        """
        pass

    async def submit_environment_message(self, msg: NodeToEnvironmentMessage, module_name: str=None):
        """
        submits environment request and returns response from environment server
        """
        if module_name is None:
            module_name = self.name

        if self.parent_module is None:
            return await self.environment_message_submitter(msg, module_name)
        else:
            return await self.parent_module.submit_environment_message(msg, module_name)

    @abstractmethod
    async def message_transmitter(self, msg : NodeToEnvironmentMessage):
        """
        transmits a message of any type to an agent
        """
        pass

    async def transmit_message(self, msg : NodeToEnvironmentMessage):
        """
        transmits a message to another agent and returns response from said agent
        """
        if self.parent_module is None:
            return await self.message_transmitter(msg)
        else:
            return await self.parent_module.transmit_message(msg)
      
    def get_top_module(self):
        """
        Finds top-most module that the current module belongs to within its simulation node
        """
        top = self
        while top.parent_module is not None:
            top = top.parent_module

        return top

    def log(self, content : str, module_name : str = None, logger_type : LoggerTypes = LoggerTypes.DEBUG, level : logging = logging.DEBUG):
        """
        Logs a message to a specific logger defined by the user. 
        All loggers are defined at the `setup_loggers()` method. 
        Each logger has a file on which the content is written into. 
        Only the logger of type `LoggerTypes.DEBUG` has a stream handler that prints the content to the terminal.

        content:
            String containing text to be logged
        module_name:
            Name of the module to log the message. By default, the function will detect which module is pefroming
            the log and create a trasable path of said module. Can be overritten by the user if desired.
        logger_type:
            Type of logger to be used to write the content into. Must be of type LoggerTypes. 
            By default all messages are logged into the `LoggerTypes.DEBUG` logger and onto the terminal
        level:
            Logger level (see logging.Logger python documentation for more information) 
        """
        if module_name is None:
            module_name = self.name

        if self.parent_module is None:
            out = self.format_content(content, module_name, logger_type)
            logger : logging.Logger = self.get_logger(logger_type)

            if level is logging.DEBUG:
                logger.debug(out)
            elif level is logging.INFO:
                logger.info(out)
            elif level is logging.WARNING:
                logger.warning(out)
            elif level is logging.ERROR:
                logger.error(out)
            elif level is logging.CRITICAL:
                logger.critical(out)
        else:
            if self.name not in module_name:
                module_name = self.name + '/' + module_name

            self.parent_module.log(content, module_name, logger_type, level)

    def format_content(self, content : str, module_name : str, logger_type : LoggerTypes) -> str:
        if logger_type is LoggerTypes.DEBUG:
            if self.name == module_name:
                out = f'{self.name} @ T{self.get_current_time():.{3}f}: {content}'
            else:
                out = f'{self.name} ({module_name}) @ T{self.get_current_time():.{3}f}: {content}'
        else:
            out = f'{self.name}, {module_name}, {self.get_current_time():.{3}f}, {content}'

        return out

    def get_logger(self, logger_type : LoggerTypes) -> logging.Logger:
        if self.parent_module is None:
            return self.get_logger_from_type(logger_type)
        else:
            return self.parent_module.get_logger(logger_type)

    @abstractmethod
    def get_logger_from_type(self, logger_type : LoggerTypes) -> logging.Logger:
        pass

class NodeModule(Module):
    def __init__(self, name, scenario_dir, n_timed_coroutines) -> None:
        """
        Represents the top-most module in an agent or environment class. 
        Sets up results folders and loggers to be used throughout the 
        """
        super().__init__(name, None, submodules=[], n_timed_coroutines=n_timed_coroutines)

        # set up results dir
        self.SCENARIO_RESULTS_DIR, self.NODE_RESULTS_DIR = self.set_up_results_directory(scenario_dir)

        # set up loggers
        self.logger_map = self.set_up_loggers()

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
                path = os.path.join(agent_results_path, f)
                try:
                    shutil.rmtree(path)
                except:
                    os.remove(path)
        else:
            # if directory does not exist, create a new onw
            os.mkdir(agent_results_path)

        if(os.path.exists(agent_results_path+'/sd')):
            pass
        else:
            os.mkdir(agent_results_path+'/sd')

        return scenario_results_path, agent_results_path

    def set_up_loggers(self) -> None:
        """
        set root logger to default settings
        """

        logging.root.setLevel(logging.INFO)
        logging.basicConfig(level=logging.INFO)
        
        loggers = dict()
        for logger_type in (LoggerTypes):
            path = self.NODE_RESULTS_DIR + f'/{logger_type.value}.log'

            if os.path.exists(path):
                # if file already exists, delete
                os.remove(path)

            # create logger
            logger = logging.getLogger(f'{self.name}_{logger_type.value}')
            logger.propagate = False

            # create stream handler for debug logger
            if logger_type is LoggerTypes.DEBUG:
                c_handler = logging.StreamHandler(sys.stderr)
                c_handler.setLevel(logging.DEBUG)
                logger.addHandler(c_handler)

            # create file handler 
            f_handler = logging.FileHandler(path)
            f_handler.setLevel(logging.DEBUG)
            f_format = logging.Formatter('%(message)s')
            f_handler.setFormatter(f_format)

            # add handlers to logger
            logger.addHandler(f_handler)

            loggers[logger_type] = logger

        logging.getLogger('neo4j').setLevel(logging.WARNING)
        return loggers
        
    def get_logger_from_type(self, logger_type: LoggerTypes) -> logging.Logger:
        return self.logger_map[logger_type]   
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

                    self.log('Waiting for 1 second')
                    await self.sim_wait_to(int(self.get_current_time()) + 1)
                    self.log('Wait over!')

                    # sense requests
                    src = self.get_top_module()
                    sense_msgs = []
                    
                    ## agent access req
                    target = 'Mars2'
                    msg = AgentAccessSenseMessage(src.name, target)
                    sense_msgs.append(msg)

                    # gs access req
                    target = 'NEN2'
                    msg = GndStnAccessSenseMessage(src.name, target)
                    sense_msgs.append(msg)

                    # gp access req
                    lat, lon = 1.0, 158.0
                    msg = GndPntAccessSenseMessage(src.name, lat, lon)
                    sense_msgs.append(msg)

                    for sense_msg in sense_msgs:
                        self.log(f'Sending access sense message of type {msg.get_type()} for target {target}.')
                        response = await self.submit_environment_message(sense_msg)

                        if response is not None:
                            self.log(f'Access to {response.target}: {response.result}')
                            await self.sim_wait(1.1)

                    # agent info req 
                    msg = AgentSenseMessage(src.name, dict())
                    self.log(f'Sending Agent Info sense message to Envirnment.')
                    response = await self.submit_environment_message(msg)

                    if response is not None:
                        self.log(f'Current state: pos=[{response.pos}], vel=[{response.vel}], eclipse={response.eclipse}')
                        await self.sim_wait(1.1)

                    lat, lon = 45.590934, 47.716708
                    obs = "radiances"
                    msg = ObservationSenseMessage(src.name, lat, lon, obs)
                    self.log(f'Sending Observation Sense message to Environment.')
                    response = await self.submit_environment_message(msg)

                    if response is not None:
                        #self.log(f'Current status: {response.obs}')
                        self.log(f'Received response observation')
                        await self.sim_wait(0.1)
                    self.log('done waiting')
                    msg = InternalMessage(self.name, AgentModuleTypes.SCIENCE_MODULE.value, response)

                    self.log('Sending measurement result to onboard processing module.')
                    await self.send_internal_message(msg)

                else:
                    await self.sim_wait( 1e6 )
                
        except asyncio.CancelledError:
            self.log('Periodic print routine cancelled')
            return