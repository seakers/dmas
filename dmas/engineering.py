from abc import abstractmethod
from asyncio import CancelledError
from typing import Union
import logging
# from agent import AgentClient
from messages import *
from utils import *
from modules import Module

"""
--------------------------------------------------------
 ________  ___  ___  ________  ________       ___    ___ ________  _________  _______   _____ ______      
|\   ____\|\  \|\  \|\   __  \|\   ____\     |\  \  /  /|\   ____\|\___   ___\\  ___ \ |\   _ \  _   \    
\ \  \___|\ \  \\\  \ \  \|\ /\ \  \___|_    \ \  \/  / | \  \___|\|___ \  \_\ \   __/|\ \  \\\__\ \  \   
 \ \_____  \ \  \\\  \ \   __  \ \_____  \    \ \    / / \ \_____  \   \ \  \ \ \  \_|/_\ \  \\|__| \  \  
  \|____|\  \ \  \\\  \ \  \|\  \|____|\  \    \/  /  /   \|____|\  \   \ \  \ \ \  \_|\ \ \  \    \ \  \ 
    ____\_\  \ \_______\ \_______\____\_\  \ __/  / /       ____\_\  \   \ \__\ \ \_______\ \__\    \ \__\
   |\_________\|_______|\|_______|\_________\\___/ /       |\_________\   \|__|  \|_______|\|__|     \|__|
   \|_________|                  \|_________\|___|/        \|_________|                                   

 _____ ______   ________  ________  ___  ___  ___       _______   ________      
|\   _ \  _   \|\   __  \|\   ___ \|\  \|\  \|\  \     |\  ___ \ |\   ____\     
\ \  \\\__\ \  \ \  \|\  \ \  \_|\ \ \  \\\  \ \  \    \ \   __/|\ \  \___|_    
 \ \  \\|__| \  \ \  \\\  \ \  \ \\ \ \  \\\  \ \  \    \ \  \_|/_\ \_____  \   
  \ \  \    \ \  \ \  \\\  \ \  \_\\ \ \  \\\  \ \  \____\ \  \_|\ \|____|\  \  
   \ \__\    \ \__\ \_______\ \_______\ \_______\ \_______\ \_______\____\_\  \ 
    \|__|     \|__|\|_______|\|_______|\|_______|\|_______|\|_______|\_________\
                                                                    \|_________|
--------------------------------------------------------
"""

"""
-------------------------------
CCOMPONENT MODULES
-------------------------------
"""
class ComponentModule(Module):
    def __init__(self, name: str, 
                parent_subsystem: Module,   
                component_state : type, 
                average_power_consumption: float, 
                health : ComponentHealth = ComponentHealth.NOMINAL,
                status : ComponentStatus = ComponentStatus.OFF,
                f_update: float = 1.0,
                n_timed_coroutines: int = 2) -> None:
        """
        Describes a generic component of an agent's platform.

        name:
            name of the component
        parent_subsystem:
            subsystem that this component belongs to
        component_state:
            type of component state describing this component's state
        average_power_consumption:
            average power consumption in [W]
        health:
            health of the component
        status:
            status of the component
        f_update:
            frequency of periodic state checks in [Hz]
        n_timed_coroutines:
            number of time-dependent corroutines being performed by this component
        """

        super().__init__(name, parent_subsystem, [], n_timed_coroutines)
        self.UPDATE_FREQUENCY : float = f_update
        self.component_state : type = component_state
        self.average_power_consumption : float = average_power_consumption
        self.t_update : float = -1.0

        self.health : ComponentHealth = health
        self.status : ComponentStatus = status

        self.power_consumed : float= 0.0                                # power currently being consumed by this component
        self.power_supplied : float = 0.0                               # power currently being fed to this component       
        self.dp : float = self.power_supplied - self.power_consumed     # curent difference between power in and power usage

    async def activate(self):
        await super().activate()

        # component status events
        self.enabled = asyncio.Event()                                  # fires when the component is enabled or turned on
        self.disabled = asyncio.Event()                                 # fires when the component is disabled or turned off

        # component health events
        self.nominal = asyncio.Event()                                  # fires when the component enters a nominal state
        self.critical = asyncio.Event()                                 # fires when the component enters a critical state
        self.failure = asyncio.Event()                                  # fires when the component enters a failure state

        # trigger health events
        if self.health is ComponentHealth.NOMINAL:
            self.nominal.set()
        elif self.health is ComponentHealth.CRITIAL:
            self.critical.set()
        elif self.health is ComponentHealth.FAILURE:
            self.failure.set()

        # component update event    
        self.updated = asyncio.Event()                                  # informs other processes that the component's state has been updated

        # task queues
        self.maintenance_tasks = asyncio.Queue()                        # stores maintenance task commands to be executed by this component
        self.tasks = asyncio.Queue()                                    # stores action task commands to be executed by this component
        self.aborts = asyncio.Queue()                                   # stores task abort commnands to be executed by this component
        self.environment_events = asyncio.Queue()                       # stores environment events that may have an effect on this component

        # initiate update time
        self.t_update : float = self.get_current_time()                 # tracks when the last component update was performed

        # update state
        self.state_lock = asyncio.Lock()                                # prevents two internal processes from affecting the component's state simultaneously  
        await self.update()        

        # request power if on at the beginning of the simulation
        await self.state_lock.acquire()
        if self.status is ComponentStatus.ON and self.average_power_consumption > 0:
            self.log('Component is ON. Requesting power from EPS')

            # ask for power supply from eps
            power_supply_task = PowerSupplyRequestTask(self.name, self.average_power_consumption)
            msg = SubsystemTaskMessage(self.name, SubsystemNames.EPS.value, power_supply_task)
            await self.send_internal_message(msg)
        elif self.status is ComponentStatus.ON:
             self.log('Component is ON')

        self.state_lock.release()

    async def internal_message_handler(self, msg: InternalMessage):
        """
        Processes messages being sent to this component. Only accepts task messages.
        """
        try:
            if msg.dst_module != self.name:
                # this module is NOT the intended receiver for this message. Forwarding to rightful destination
                self.log(f'Received internal message intended for {msg.dst_module}. Rerouting message...')
                await self.send_internal_message(msg)

            elif isinstance(msg, ComponentTaskMessage):
                task = msg.get_task()
                self.log(f'Received a task of type {type(task)}!')
                if isinstance(task, ComponentAbortTask):
                    await self.aborts.put(task)
                elif isinstance(task, ComponentMaintenanceTask):
                    await self.maintenance_tasks.put(task)
                else:
                    await self.tasks.put(task)
            
            elif isinstance(msg.content, EnvironmentBroadcastMessage):
                self.log(f'Received an environment event of type {type(msg.content)}!')
                self.environment_events.put(msg.content)

            else:
                self.log(f'Internal message of type {type(msg)} not yet supported. Discarting message...')
            
        except asyncio.CancelledError:
            return    

    """
    --------------------
    CO-ROUTINES
    --------------------
    """

    async def coroutines(self):
        """
        Each component is in charge of the following routines:

        1- Periodically monitoring its own state

        2- Detecting critical states

        3- Triggering failure states

        4- Perform tasks being given to this component

        5- Processes events from the environment that may affect this component
        
        Component failure leads to no actions being able to be performed by this 
        component. Subsystem-wide failure is to be handled by their parent subsystem.
        """

        # create coroutine tasks
        coroutines = []

        try:
            ## Internal coroutines
            periodic_update = asyncio.create_task(self.periodic_update())
            periodic_update.set_name (f'{self.name}_periodic_update')
            coroutines.append(periodic_update)
        
            # crit_monitor = asyncio.create_task(self.crit_monitor())
            # crit_monitor.set_name (f'{self.name}_crit_monitor')
            # #coroutines.append(crit_monitor)

            # failure_monitor = asyncio.create_task(self.failure_monitor())
            # failure_monitor.set_name (f'{self.name}_failure_monitor')
            # #coroutines.append(failure_monitor)

            maintenance_task_processor = asyncio.create_task(self.maintenance_task_processor())
            maintenance_task_processor.set_name (f'{self.name}_maintenance_task_processor')
            coroutines.append(maintenance_task_processor)

            task_processor = asyncio.create_task(self.task_processor())
            task_processor.set_name (f'{self.name}_task_processor')
            coroutines.append(task_processor)

            environment_event_processor = asyncio.create_task(self.environment_event_processor())
            environment_event_processor.set_name (f'{self.name}_environment_event_processor')
            coroutines.append(environment_event_processor)

            # wait for the first coroutine to complete
            _, pending = await asyncio.wait(coroutines, return_when=asyncio.FIRST_COMPLETED)
            
            done_name = None
            for coroutine in coroutines:
                if coroutine not in pending:
                    coroutine : asyncio.Task
                    done_name = coroutine.get_name()
                    break

            # cancell all other coroutine tasks
            self.log(f'{done_name} Coroutine ended. Terminating all other coroutines...', level=logging.INFO)
            for subroutine in pending:
                subroutine : asyncio.Task
                subroutine.cancel()
                await subroutine
            
        except asyncio.CancelledError:
            if len(coroutines) > 0:
                for coroutine in coroutines:
                    coroutine : asyncio.Task
                    if not coroutine.done():
                        coroutine.cancel()
                        await coroutine

    async def periodic_update(self):
        """
        Performs periodic update of the component's state when the component is Enabled
        """
        try:
            while True:
                # wait for next periodic update
                await self.sim_wait(1/self.UPDATE_FREQUENCY)

                # update component state
                self.log(f'Performing periodic state update...')
                await self.update()
                self.log(f'Periodic state update completed!')

                if self.status is ComponentStatus.OFF:
                    # if component is turned off, wait until it is turned on
                    await self.updated.wait()

                if self.health is ComponentHealth.FAILURE:
                    # else if component is in failure state, stop periodic updates and sleep for the rest of the simulation
                    break

                # inform parent subsystem of current state
                if self.health is ComponentHealth.NOMINAL:
                    state : ComponentState = await self.get_state()
                    msg = ComponentStateMessage(self.name, self.parent_module.name, state)
                    await self.send_internal_message(msg)                  

            while True:
                # sleep for the rest of the simulation
                await self.sim_wait(1e6)

        except asyncio.CancelledError:
            return

    async def crit_monitor(self) -> None:
        """
        Monitors component state after every component state update and communicates critical state 
        to parent subsystem and other processes.
        """
        try:
            while True:
                # check if failure event was triggered
                if self.health is ComponentHealth.FAILURE:
                    # if component is in failure state, sleep for the remainder of the simulation
                    while True:
                        await self.sim_wait(1e6)
                
                else:
                    # wait for next state update 
                    await self.updated.wait()

                    # get latest state and acquire state lock
                    acquired = await self.state_lock.acquire()
                    
                    if self.health is ComponentHealth.CRITIAL:
                        # component is in critical state

                        if not self.critical.is_set():
                            # release state lock
                            self.state_lock.release()
                            acquired = None
                            
                            # inform parent subsystem of component critical state
                            state : ComponentState = await self.get_state()
                            msg = ComponentStateMessage(self.name, self.parent_module.name, state)
                            await self.send_internal_message(msg)                          

                            # trigger critical state event                             
                            self.critical.set()
                    
                    # release state lock
                    if acquired:
                        self.state_lock.release()
                        acquired = None

        except asyncio.CancelledError:
            if acquired:
                self.state_lock.release()

    def is_critical(self) -> bool:
        """
        Returns true if the current state of the component is critical. 
        """
        return False

    async def failure_monitor(self):
        """
        Monitors component state and triggers failure event if a failure state is detected
        """
        try:
            while True: 
                if self.health is ComponentHealth.FAILURE:
                    # if comonent is in failure state, sleep for the rest of the simulation
                    while True:
                        await self.sim_wait(1e6)

                else:
                    # initiate failure state timer
                    failure_timer = asyncio.create_task(self.wait_for_failure())
                    update_event = asyncio.create_task(self.updated.wait())
                    
                    # wait for the failure timer to run out or for the component to update its state
                    conditions = [update_event, failure_timer]
                    await asyncio.wait(conditions, return_when=asyncio.FIRST_COMPLETED)

                    if update_event.done():
                        # component was updated before the component's failure timer ran out

                        # cancel failure timer
                        failure_timer.cancel()
                        await failure_timer
                    else:
                        # component's failure timer ran out before the component had changed its state or configuration

                        # update state
                        await self.update()

                    acquired = await self.state_lock.acquire()    
                    if self.health is ComponentHealth.CRITIAL and self.is_failed():
                        # component is in a potential failure state

                        if not self.failure.is_set():                            
                            # failure event has not been triggered yet

                            # release state lock
                            self.state_lock.release()
                            acquired = None

                            # give parent subsystem or agent one update cycle to respond to potential failure
                            await self.sim_wait(1/self.UPDATE_FREQUENCY)

                            # update state
                            await self.update()
                            
                            # check if component is still in a potential failure state
                            acquired = await self.state_lock.acquire()
                            if self.is_failed():
                                if not self.is_power_supply_failure():                                    
                                    # component is in a non-power-related failure state, triggering failure sequence
                                    self.health = ComponentHealth.FAILURE

                                    # trigger failure event
                                    self.nominal.clear()
                                    self.failure.set()               
                                
                                # release state lock
                                self.state_lock.release()      
                                acquired = None    

                                # update state
                                await self.update()                       

                                # task component to disable itself
                                task = ComponentActuationTask(self.name, ComponentStatus.OFF)
                                await self.maintenance_tasks.put(task)

                                # communicate parent subsystem of component failure state
                                state = await self.get_state()
                                msg = ComponentStateMessage(self.name, self.parent_module.name, state)
                                await self.send_internal_message(msg)
                            
                    # release state lock
                    if acquired:
                        self.state_lock.release()
                        acquired = None

        except asyncio.CancelledError:
            if acquired:
                self.state_lock.release()

    def is_power_supply_failure(self) -> bool:
        """
        returns true if current state is a power supply failure state
        """
        return abs(self.power_consumed - self.power_supplied) >= 1e-6

    def is_failed(self) -> bool:
        """
        Returns true if the current state of the component is a failure state. 
        By default it only considers power supply vs power consumption. Can be extended to add more functionality
        """
        return self.is_power_supply_failure()

    async def wait_for_failure(self) -> None:
        """
        Counts down to the next predicted failure state of this component given that the current configuration is maintained
        """
        try:
            while True:
                await self.sim_wait(1e6)
        except asyncio.CancelledError:
            return


    """
    --------------------
    TASKS AND EVENT HANDLER
    --------------------
    """
    async def maintenance_task_processor(self) -> None:
        """
        Processes maintenance tasks in the order they are received.
        """
        try:
            while True:
                # wait for next incoming maintnance task
                task : ComponentTask = await self.maintenance_tasks.get()

                if not isinstance(task, ComponentMaintenanceTask):
                    # if task is NOT a maintenance ask, move to proper queue
                    await self.tasks.put(task)
                    return
                
                # update component state
                self.log(f'Starting task of type {type(task)}...')
                await self.update(crit_flag=False)

                # perform task 
                status = await self.perform_maintenance_task(task)

                # update component state 
                await self.update()

                # inform parent subsystem of the status of completion of the task at hand
                msg = ComponentTaskCompletionMessage(self.name, self.parent_module.name, task, status)
                await self.send_internal_message(msg)

                # inform parent subsytem of the current component state
                state : ComponentState = await self.get_state()
                if state.health is ComponentHealth.NOMINAL:
                    msg = ComponentStateMessage(self.name, self.parent_module.name, state)
                    await self.send_internal_message(msg)

        except asyncio.CancelledError:
            return

    async def perform_maintenance_task(self, task: ComponentMaintenanceTask) -> TaskStatus:
        """
        Performs a maintenance task given to this component. 
        Rejects any tasks that is not intended to be performed by this component. 
        """
        try:
            # check if component was the intended performer of this task
            if task.component != self.name:
                self.log(f'Component task not intended for this component. Initially intended for component \'{task.component}\'. Aborting task...')
                raise asyncio.CancelledError

            # check if the component or subsystem is disabled or in a failure state
            self.parent_module : SubsystemModule
            if self.parent_module.health is SubsystemHealth.FAILURE and isinstance(task, EnableComponentTask):
                self.log(f'Subsystem is in failure state. Cannot turn on component.')
                raise asyncio.CancelledError

            elif self.health is ComponentHealth.FAILURE and isinstance(task, EnableComponentTask):
                self.log(f'Component is in failure state. Cannot turn on component.')
                raise asyncio.CancelledError

            if isinstance(task, ComponentActuationTask):          
                # obtain state lock
                acquired = await self.state_lock.acquire()

                # actuate component
                if task.component_status is ComponentStatus.ON:
                    if self.status is not ComponentStatus.ON:
                        # turn component on
                        self.status = ComponentStatus.ON
                        self.enabled.set()
                        self.disabled.clear()

                        # ask for power supply from eps
                        power_supply_task = PowerSupplyRequestTask(self.name, self.average_power_consumption)
                        msg = SubsystemTaskMessage(self.name, SubsystemNames.EPS.value, power_supply_task)
                        await self.send_internal_message(msg)
                    else:
                        # release state lock
                        self.state_lock.release()
                        acquired = None

                        self.log(f'Component is already in Status {task.component_status}.')
                        raise asyncio.CancelledError  

                elif task.component_status is ComponentStatus.OFF:
                    if self.status is not ComponentStatus.OFF:
                        # turn component off
                        self.status = ComponentStatus.OFF
                        self.enabled.clear()
                        self.disabled.set()

                        # ask for end of power supply from eps
                        stop_power_supply_task = PowerSupplyStopRequestTask(self.name, self.average_power_consumption)
                        msg = SubsystemTaskMessage(self.name, SubsystemNames.EPS.value, stop_power_supply_task)
                        await self.send_internal_message(msg)
                    else:
                        # release state lock
                        self.state_lock.release()
                        acquired = None

                        self.log(f'Component is already in Status {task.component_status}.')
                        raise asyncio.CancelledError    

                else:
                    # release state lock
                    self.state_lock.release()
                    acquired = None

                    self.log(f'Component Status {task.component_status} not supported for component actuation.')
                    raise asyncio.CancelledError

                # release state lock
                self.state_lock.release()
                acquired = None

                # return task completion status
                self.log(f'Component status set to {self.status.name}!')
                return TaskStatus.DONE

            elif isinstance(task, ReceivePowerTask):
                # obtain state lock
                acquired = await self.state_lock.acquire()

                # provide change in power supply
                self.power_supplied += task.power_to_supply

                if self.power_supplied < 0:
                    self.power_supplied = 0

                # release state lock
                self.state_lock.release()
                acquired = None

                # return task completion status
                self.log(f'Component received power supply of {self.power_supplied}!')
                return TaskStatus.DONE

            else:
                self.log(f'Task of type {type(task)} not yet supported.')
                acquired = None 
                raise asyncio.CancelledError

        except asyncio.CancelledError:
            self.log(f'Aborting task of type {type(task)}.')

            # release update lock if cancelled during task handling
            if acquired:
                self.state_lock.release()

            # return task abort status
            return TaskStatus.ABORTED


    async def task_processor(self) -> None:
        """
        Processes tasks in the order they are received. Listens for any abort commands that may be received during 
        the performance of the task and processes them accordingly. 
        """
        try:
            # initialize task variables
            perform_task = None
            listen_for_abort = None

            while True:
                task = await self.tasks.get()

                if isinstance(task, ComponentMaintenanceTask):
                    # if task is NOT a maintenance ask, move to proper queue
                    await self.maintenance_tasks.put(task)
                    return

                self.log(f'Starting task of type {type(task)}...')

                # update component state
                await self.update()

                # start to perform task
                perform_task = asyncio.create_task(self.perform_task(task))
                listen_for_abort = asyncio.create_task(self.listen_for_abort(task))
                wait_for_subsystem_failure = asyncio.create_task(self.parent_module.failure.wait())
                wait_for_component_failure = asyncio.create_task(self.failure.wait())
                wait_for_disabled_subsystem = asyncio.create_task(self.parent_module.disabled.wait())
                wait_for_disabled_component = asyncio.create_task(self.disabled.wait())
                
                perform_task.set_name(f'{type(task)}')
                listen_for_abort.set_name(f'ListenForAbort')
                wait_for_subsystem_failure.set_name(f'WaitForSubsystemFailure')
                wait_for_component_failure.set_name('WaitForComponentFailure')
                wait_for_disabled_subsystem.set_name('WaitForDisabledSubsystem')
                wait_for_disabled_component.set_name('WaitForDisabledComponent')

                processes = [perform_task, 
                            listen_for_abort, 
                            wait_for_subsystem_failure, 
                            wait_for_component_failure, 
                            wait_for_disabled_subsystem,
                            wait_for_disabled_component]

                # wait for task completion, abort command, or component or subsystem failure
                done, pending = await asyncio.wait(processes, return_when=asyncio.FIRST_COMPLETED)

                if perform_task.done():
                    self.log(f'Task of type {type(task)} successfully completed! Task status: {perform_task.result()}')
                else:
                    for done_process in done:
                        done_process : asyncio.Task
                        self.log(f'{done_process.get_name()} completed before the task of type {type(task)} was successfully completed')

                # cancell all pending processes
                for pending_process in pending:
                    pending_process : asyncio.Task

                    if 'Wait' not in pending_process.get_name():
                        self.log(f'Aborting {pending_process.get_name()}...')
                        pending_process.cancel()
                        await pending_process
                        self.log(f'{pending_process.get_name()} successfully aborted.')

                # inform parent subsystem of the status of completion of the task at hand
                self.log(f'Informing parent subsystem about task completion status...')
                msg = ComponentTaskCompletionMessage(self.name, self.parent_module.name, task, perform_task.result())
                await self.send_internal_message(msg)

                # update component state 
                self.log(f'Task completion communicated! Updating state...')
                await self.update()

                # inform parent subsytem of the current component state
                self.log(f'State updated! Informing parent subsystem about component state...')
                state = await self.get_state()
                msg = ComponentStateMessage(self.name, self.parent_module.name, state)
                await self.send_internal_message(msg)

                self.log(f'Component state communicated! Finished processing task of type {type(task)}!')

        except asyncio.CancelledError:
            if isinstance(perform_task, asyncio.Task) and not perform_task.done():
                perform_task.cancel()
                await perform_task
            
            if isinstance(listen_for_abort, asyncio.Task) and not listen_for_abort.done():
                listen_for_abort.cancel()
                await listen_for_abort

    async def listen_for_abort(self, task: ComponentTask) -> None:
        """
        Listens for any abort command targetted towards the task being performed.
        Any aborts targetted to other tasks are ignored but not discarted.
        """
        try:
            other_aborts = []
            while True:
                abort_task = await self.aborts.get()
                
                if abort_task == task:
                    for abort in other_aborts:
                        self.aborts.put(abort)
                    self.log(f'Received abort command for task of type {type(task)}!')
                    return
                else:
                    other_aborts.append(abort_task)

        except asyncio.CancelledError:
            for abort in other_aborts:
                self.aborts.put(abort)


    async def perform_task(self, task: ComponentTask) -> TaskStatus:
        """
        Performs a task given to this component. 
        Rejects any tasks that is not intended to be performed by this component. 
        """
        try:
            # check if component was the intended performer of this task
            if task.component != self.name:
                self.log(f'Component task not intended for this component. Initially intended for component \'{task.component}\'. Aborting task...')
                raise asyncio.CancelledError
            
            self.log(f'Task of type {type(task)} not yet supported.')
            raise asyncio.CancelledError

        except asyncio.CancelledError:
            self.log(f'Aborting task of type {type(task)}.')

            # return task abort status
            return TaskStatus.ABORTED
        

    async def environment_event_processor(self):
        """
        Processes any incoming events from the environment
        """
        try:
            aquired = None
            environment_event_handler = None
            while True:
                # wait for an event to be received
                event_broadcast : EnvironmentBroadcastMessage = await self.environment_events.get()

                # update the component's state
                await self.update()

                # handle according to event type
                aquired = await self.state_lock.acquire()

                environment_event_handler = asyncio.create_task(self.environment_event_handler(event_broadcast))
                await environment_event_handler

                self.state_lock.release()
                aquired = None

                # if the handler affected the component, update its state
                if environment_event_handler.result():
                    await self.update()

        except asyncio.CancelledError:
            if aquired:
                self.state_lock.release()
            
            if isinstance(environment_event_handler, asyncio.Task) and not environment_event_handler.done():
                environment_event_handler.cancel()
                await environment_event_handler


    async def environment_event_handler(self, event_broadcast : EnvironmentBroadcastMessage) -> bool:
        """ 
        Affects the component depending on the type of event being received. Ignores all events by default.
        """
        return False

    """
    --------------------
    HELPING FUNCTIONS
    --------------------
    """
    async def update(self, crit_flag : bool=True):
        """
        Updates the state of the component. Checks if component is currently in a critical state.

        crit_flag:
            when true, it flags a critical state from being flagged at the end of the state update.
            It is true by default.
        """
        try:
            # wait for any possible state accessing process to finish
            acquired = await self.state_lock.acquire()

            # calculate update time-step
            t_curr = self.get_current_time()
            dt = t_curr - self.t_update

            # update component properties
            await self.update_properties(dt)

            # check component health
            if (self.is_critical() or self.is_failed()) and crit_flag:
                # component is in a critical or a potential failure state
                self.health = ComponentHealth.CRITIAL                    

                # trigger critical state event if it hasn't been triggered already
                if self.is_critical() and not self.critical.is_set():
                    self.critical.set()

            else:
                # component is NOT in a critical state
                self.health = ComponentHealth.NOMINAL
    
                # reset critical and failure event if it has been previously triggered
                if self.critical.is_set():
                    self.critical.clear()

                if self.failure.is_set():
                    self.failure.clear()

            # update latest update time
            self.t_update = t_curr  

            # inform other processes that the update has finished
            self.updated.set()
            self.updated.clear()

            # release state lock
            self.state_lock.release() 
            acquired = None

        except asyncio.CancelledError:
            if acquired:
                # if this process had acquired the update_lock and has not released it, release update lock
                self.state_lock.release()    

    async def update_properties(self, dt):
        """
        Updates the current state of the component given a time-step dt
        """
        # update power consumption
        if self.status is ComponentStatus.ON:
            self.power_consumed = self.average_power_consumption
        else:
            self.power_consumed = 0

        # update power differential tracker
        self.dp = self.power_supplied - self.power_consumed

    async def get_state(self):
        """
        Returns a state class object capturing the current state of this component 
        """
        try:
            # wait for any possible update process to finish
            self.log(f'Awaiting state lock...')
            acquired = await self.state_lock.acquire()

            # get state object from component status
            self.component_state : ComponentState
            state = self.component_state.from_component(self)

            # release update lock
            self.state_lock.release()
            acquired = None

            self.log(f'State lock acquired! Getting current state...')
            return state
        except asyncio.CancelledError:
            if acquired:
                # release state lock
                self.state_lock.release()

            return None

"""
-------------------------------
SUBSYSTEM MODULES
-------------------------------
"""
class SubsystemModule(Module):
    def __init__(self, 
                name: str, 
                parent_platform_sim: Module,   
                subsystem_state : type, 
                health : ComponentHealth = ComponentHealth.NOMINAL,
                status : ComponentStatus = ComponentStatus.OFF,
                n_timed_coroutines: int = 2) -> None:
        """
        Describes a generic subsyem of an agent's platform.

        name:
            name of the subsystem
        parent_platform_sim:
            platform simulator that this subsystem belongs to
        subsystem_state:
            type of subsystem state describing this subsystem
        health:
            health of the subsystem
        status:
            status of the subsystem
        n_timed_coroutines:
            number of time-dependent corroutines being performed by this component
        """
        super().__init__(name, parent_platform_sim, [], n_timed_coroutines)
        self.subsystem_state = subsystem_state
        self.health = health
        self.status = status

    async def activate(self):
        await super().activate()

        # subssytem status events
        self.enabled = asyncio.Event()                                  # fires when the subsystem is enabled
        self.disabled = asyncio.Event()                                 # fires when the subsystem is disabled

        # subsystem health events
        self.nominal = asyncio.Event()                                  # fires when the subsystem enters a nominal state
        self.critical = asyncio.Event()                                 # fires when the subsystem enters a critical state
        self.failure = asyncio.Event()                                  # fires when the subsystem enters a failure state

        # trigger health events
        if self.health is ComponentHealth.NOMINAL:
            self.nominal.set()
        elif self.health is ComponentHealth.CRITIAL:
            self.critical.set()
        elif self.health is ComponentHealth.FAILURE:
            self.failure.set()

        # task queues
        self.tasks = asyncio.Queue()                                    # stores task commands to be executed by this subsystem
        self.aborts = asyncio.Queue()                                   # stores task abort commnands to be executed by this subsystem
        self.component_state_updates = asyncio.Queue()                  # stores component state updates to be processed by this subsystem
        self.subsystem_state_updates = asyncio.Queue()                  # stores subsystem state updates to be processed by this subsystem
        self.recevied_task_status = asyncio.Queue()                     # stores component tasks' status after they've been submitted to components for completion
        self.environment_events = asyncio.Queue()                       # stores environment events that may have an effect on this subsystem

        # subsystem update event
        self.updated = asyncio.Event()                                  # informs other processes that the subsystem's state has been updated

        # initiate update time
        self.t_update : float = self.get_current_time()                 # tracks when the last component update was performed

        # initiate state
        self.state_lock = asyncio.Lock()                               # prevents two internal processes from updating the component's state simultaneously  
        
        self.component_states = dict()                                  # tracks the state of each component contained in this subsystem
        await self.state_lock.acquire()
        for component in self.submodules:
            component : ComponentModule
            self.component_states[component.name] = await component.get_state()
        self.state_lock.release()

    async def internal_message_handler(self, msg: InternalMessage):
        """
        Processes messages being sent to this subsystem.
        """
        try:
            if self.failure.is_set():
                self.log(f'Subsystem is in failure state. Ignoring message...')
                return
                # TODO add capability to recover component by performing some troubleshooting tasks being given to this component

            if msg.dst_module != self.name:
                # this module is NOT the intended receiver for this message. Forwarding to rightful destination
                self.log(f'Received internal message intended for {msg.dst_module}. Rerouting message...')
                await self.send_internal_message(msg)

            elif (isinstance(msg, PlatformTaskMessage) 
                  or isinstance(msg, SubsystemTaskMessage)
                  or isinstance(msg, ComponentTaskMessage)
                  ):
                task = msg.get_task()
                self.log(f'Received a task of type {type(task)}!')

                if isinstance(task, PlatformAbortTask) or isinstance(task, SubsystemAbortTask) or isinstance(task, ComponentAbortTask):
                    await self.aborts.put(task)
                else:
                    await self.tasks.put(task)
                    
            elif isinstance(msg.content, EnvironmentBroadcastMessage):
                self.log(f'Received internal message containing an environment broadcast of type {type(msg)}!')
                await self.environment_events.put(msg.content)

                self.log(f'Forwarding internal message containing an environment broadcast of type {type(msg)} to components...')
                for component in self.submodules:
                    component : ComponentModule
                    msg_copy = InternalMessage(self.name, component.name, msg.content)

                    await self.send_internal_message(msg_copy)
            
            elif isinstance(msg, ComponentStateMessage):
                component_state : ComponentState = msg.get_state()
                self.log(f'Received component state message from component type {component_state.component_type}. Updating subsystem state...')
                await self.component_state_updates.put(component_state)
                
            elif isinstance(msg, SubsystemStateMessage):
                subsystem_state : SubsystemState = msg.get_state()
                self.log(f'Received subsystem state message from subsystem type {subsystem_state.subsystem_type}!')
                await self.subsystem_state_updates.put(subsystem_state)

            elif isinstance(msg, SubsystemStateRequestMessage):
                self.log(f'Received a subsystem state request from subsystem \'{msg.src_module}\'. Sending latest subsystem state...')
                state = await self.get_state()
                msg = SubsystemStateMessage(self.name, msg.src_module, state)
                await self.send_internal_message(msg)

            elif isinstance(msg, ComponentTaskCompletionMessage):
                self.log(f'Received a component task completion message from component \'{msg.src_module}\' with status ({msg.get_task_status()}). Processing response...')
                await self.recevied_task_status.put(msg.content)

            elif isinstance(msg, SubsystemTaskCompletionMessage):
                self.log(f'Received a subsystem task completion message from subsystem \'{msg.src_module}\'. Processing response...')
                await self.recevied_task_status.put(msg.content)

            else:
                self.log(f'Internal message of type {type(msg)} not yet supported. Discarting message...')
            
        except asyncio.CancelledError:
            return

    """
    --------------------
    CO-ROUTINES
    --------------------
    """
    async def coroutines(self):
        """
        Each subsystem is in charge of the following routines:

        1- Updating subsystem state using incoming component states

        2- Updating knowledge of other subsystems' states

        3- Detecting critical states

        4- Triggering failure states

        5- Perform tasks being given to this component

        6- Processes events from the environment that may affect this component
        
        Subsystem failure leads to no actions being able to be performed by this 
        subsystem. Agent-wide failure is to be handled by the platform simulator.
        """
        # create coroutine tasks
        coroutines = []
        try:
            # Internal coroutines
            update_component_state = asyncio.create_task(self.update_component_state())
            update_component_state.set_name (f'{self.name}_update_component_state')
            coroutines.append(update_component_state)

            update_subsytem_state = asyncio.create_task(self.update_subsytem_state())
            update_subsytem_state.set_name (f'{self.name}_update_subsytem_state')
            coroutines.append(update_subsytem_state)

            # crit_monitor = asyncio.create_task(self.crit_monitor())
            # crit_monitor.set_name (f'{self.name}_crit_monitor')
            #coroutines.append(crit_monitor)

            # failure_monitor = asyncio.create_task(self.failure_monitor())
            # failure_monitor.set_name (f'{self.name}_failure_monitor')
            # coroutines.append(failure_monitor)

            task_processor = asyncio.create_task(self.task_processor())
            task_processor.set_name (f'{self.name}_task_processor')
            coroutines.append(task_processor)

            environment_event_processor = asyncio.create_task(self.environment_event_processor())
            environment_event_processor.set_name (f'{self.name}_environment_event_processor')
            coroutines.append(environment_event_processor)

            # wait for the first coroutine to complete
            _, pending = await asyncio.wait(coroutines, return_when=asyncio.FIRST_COMPLETED)
            
            done_name = None
            for coroutine in coroutines:
                if coroutine not in pending:
                    coroutine : asyncio.Task
                    done_name = coroutine.get_name()
                    break

            # cancell all other coroutine tasks
            self.log(f'{done_name} Coroutine ended. Terminating all other coroutines...', level=logging.INFO)
            for subroutine in pending:
                subroutine : asyncio.Task
                subroutine.cancel()
                await subroutine

        except asyncio.CancelledError:
            if len(coroutines) > 0:
                for coroutine in coroutines:
                    coroutine : asyncio.Task
                    if not coroutine.done():
                        coroutine.cancel()
                        await coroutine

    async def update_component_state(self) -> None:
        """
        Receives and processes incoming component state updates. 
        """
        try:
            acquired = None
            while True:
                # wait for next incoming component state updates
                component_state : ComponentState = await self.component_state_updates.get()
                self.log(f'Component state received! Updating subsystem state...')

                # update component state list
                acquired = await self.state_lock.acquire()
                self.component_states[component_state.component_name] = component_state
                
                # check for subsystem and component-level critical or failure states
                if (self.is_subsystem_critical() or self.is_component_critical()
                    or self.is_subsystem_failure() or self.is_component_failure()):

                    # set component health to critical
                    self.health = SubsystemHealth.CRITIAL

                    # trigger critical state event if it hasn't been triggered already
                    if self.is_subsystem_critical() and not self.critical.is_set():
                        self.critical.set()

                # release update lock
                self.state_lock.release()
                acquired = None

                # communicate to other processes that the subsystem's component states have been updated
                self.updated.set()
                self.updated.clear()
                self.log(f'Sybsystem state updated!')

        except asyncio.CancelledError:
            self.log(f'Update interrupted!')
            if acquired:
                self.state_lock.release()

    async def update_subsytem_state(self) -> None:
        """
        Receives state updates from other subsystems and reacts accordingly
        """
        try:
            while True:
                subsystem_state : SubsystemState = await self.subsystem_state_updates.get()
                await self.state_lock.acquire()
                await self.subsystem_state_update_handler(subsystem_state)
                self.state_lock.release()

        except asyncio.CancelledError:
            return

    async def subsystem_state_update_handler(self, subsystem_state):
        """
        Reacts to other subsystem state updates.
        """
        pass

    async def crit_monitor(self) -> None:
        """
        Monitors subsystem state and triggers critical event if a critical state is detected
        """
        try:
            acquired = None
            while True:
                if self.health is SubsystemHealth.FAILURE:
                    # if subsystem is in failure state, sleep for the remainder of the simulation
                    while True:
                        await self.sim_wait(1e6)
                                
                # wait for next state update 
                await self.updated.wait()

                # get latest state and acquire state lock
                acquired = await self.state_lock.acquire()
                
                if self.health is SubsystemHealth.CRITIAL:
                    # subsystem is in critical state

                    if not self.critical.is_set():
                        # release state lock
                        self.state_lock.release()
                        acquired = None
                        
                        # inform Command and Data Handling subsystem of current subsystem critical state
                        state : SubsystemState = await self.get_state()
                        msg = SubsystemStateMessage(self.name, SubsystemNames.CNDH.value, state)
                        await self.send_internal_message(msg)                          

                        # trigger critical state event                             
                        self.critical.set()
                
                # release state lock
                if acquired:
                    self.state_lock.release()
                    acquired = None

        except asyncio.CancelledError:
            await self.sim_wait(1e6)
            if acquired:
                self.state_lock.release()

    def is_subsystem_critical(self) -> bool:
        """
        Detects subsystem-level critical state using latest component states received by this subsystem
        """
        return False

    def is_component_critical(self) -> bool:
        """
        Detects component-level critical state using latest component states received by this subsystem
        """
        for component_name in self.component_states:
            component_state : ComponentState = self.component_states[component_name]
            if component_state.health is ComponentHealth.CRITIAL:
                return True
        return False

    async def failure_monitor(self):
        """
        Monitors subsystem state and triggers failure event if a failure state is detected
        """
        try:
            acquired = None
            while True: 
                if self.health is SubsystemHealth.FAILURE:
                    # if subsystem is in failure state, sleep for the rest of the simulation
                    while True:
                        await self.sim_wait(1e6)

                else:
                    # wait for next component update
                    await self.updated.wait()

                    acquired = await self.state_lock.acquire()   

                    if self.health is SubsystemHealth.CRITIAL and self.is_subsystem_failure():
                        # subsystem is in a potential failure state
                        self.log('Possible subsystem failure state detected!')

                        if not self.failure.is_set():                            
                            # failure event has not been triggered yet
                            self.log('Waiting for CNDH subsytem to revert possible subsystem failure state...')

                            # release state lock
                            self.state_lock.release()
                            acquired = None

                            # give Command and Data Handling subsystem one update cycle to respond to potential failure
                            f_min = 1
                            for component in self.submodules:
                                component : ComponentModule
                                if component.UPDATE_FREQUENCY < f_min:
                                    f_min = component.UPDATE_FREQUENCY

                            await self.sim_wait(1/f_min)

                            acquired = await self.state_lock.acquire()

                            if self.is_subsystem_failure():
                                # subsystem is still in a failure state, triggering failure sequence
                                self.log('Possible subsystem failure state persisted. Triggering subsystem failure...')

                                # update subsystem's health to failure state and disable subsystem
                                self.health = SubsystemHealth.FAILURE
                                self.status = SubsystemStatus.OFF
                                
                                # release state lock
                                self.state_lock.release()      
                                acquired = None                

                                # disable every component that comprises this subsystem
                                self.log(f'Disabling all subsystem components.')
                                for component in self.submodules:
                                    component : ComponentModule
                                    if component.status is ComponentStatus.ON:
                                        self.log(f'Disabling component {component.name}...')
                                        kill_task = DisableComponentTask(component.name)
                                        kill_msg = ComponentTaskMessage(self.name, component.name, kill_task)
                                        await self.send_internal_message(kill_msg)
                                    else:
                                        self.log(f'Component {component.name} already disabled!')

                                # wait for every component to turn off
                                for component in self.submodules:
                                    component : ComponentModule
                                    await component.disabled.wait()
                                    self.log(f'Component {component.name} successfully disabled!')

                                # communicate CNDH Subsystem of subsystem failure state
                                state : SubsystemState = await self.get_state()
                                msg = SubsystemStateMessage(self.name, SubsystemNames.CNDH.value, state)
                                await self.send_internal_message(msg)

                                # trigger failure state
                                self.log('Failure event triggered.')
                                self.failure.set()
                            else:
                                self.log('Possible subsystem failure state adverted!')
                    
                    # release state lock
                    self.state_lock.release()
                    acquired = None
                    

        except asyncio.CancelledError:
            await self.sim_wait(1e6)
            if acquired:
                self.state_lock.release()

    def is_subsystem_failure(self) -> bool:
        """
        Detects subsystem-level failure state using latest component states received by this subsystem. 
        By default it fails only if all components are in a failure state.
        """
        all_comp_failure = True
        for component in self.submodules:
            component : ComponentModule
            if component.health is not ComponentHealth.FAILURE:
                all_comp_failure = True
                break

        return all_comp_failure

    def is_component_failure(self) -> bool:
        """
        Detects component-level failure state using latest component states received by this subsystem
        """
        for component_name in self.component_states:
            component_state : ComponentState = self.component_states[component_name]
            if component_state.health is ComponentHealth.FAILURE:
                return True
        return False

    """
    --------------------
    TASKS AND EVENT HANDLER
    --------------------
    """
    async def task_processor(self) -> None:
        """
        Processes tasks in the order they are received. Listens for any abort commands that may be received during 
        the performance of the task and processes them accordingly. 
        """
        try:
            while True:
                processes = []

                # wait for the next incoming task
                task : Union[ComponentTask, SubsystemTask, PlatformTask] = await self.tasks.get()

                # inform Command and Data Handling subsytem of the current subsystem state
                state = await self.get_state()
                msg = SubsystemStateMessage(self.name, SubsystemNames.CNDH.value, state)

                # start to perform task
                perform_task = asyncio.create_task(self.perform_task(task))
                listen_for_abort = asyncio.create_task(self.listen_for_abort(task))
                wait_for_failure = asyncio.create_task(self.failure.wait())
                wait_for_disable = asyncio.create_task(self.disabled.wait())

                perform_task.set_name('PerformTask')
                listen_for_abort.set_name('ListenForAbort')
                wait_for_failure.set_name('WaitForSubsystemFailure')
                wait_for_disable.set_name('WaitForSubsystemDisable')

                processes = [perform_task, listen_for_abort, wait_for_failure, wait_for_disable]

                # wait for task completion, abort signal, or subsystem failure/disable event
                _, pending = await asyncio.wait(processes, return_when=asyncio.FIRST_COMPLETED)

                for pending_process in pending:
                    pending_process : asyncio.Task
                    if 'Wait' not in pending_process.get_name():
                        self.log(f'Aborting {pending_process.get_name()}...')
                        pending_process.cancel()
                        await pending_process
                        self.log(f'{pending_process.get_name()} successfully aborted!')

                # get task completion status
                status = perform_task.result()
                self.log(f'Task status: \'{status.name}\'')
                
                self.log(f'Informing Command and Data Handling Subsystem of task status...')
                # inform Command and Data Handling subsystem of the status of completion of component tasks
                msg = SubsystemTaskCompletionMessage(self.name, SubsystemNames.CNDH.value, task, status)
                await self.send_internal_message(msg)

                if isinstance(task, PlatformTask) and self.name == SubsystemNames.CNDH.value:
                    self.log(f'Task status communicated to CNDH subsystem! Informing Planning Module of task status...')
                    # inform Scheduling Module of the status of completion of platform-level tasks
                    msg = PlatformTaskCompletionMessage(self.name, AgentModuleTypes.PLANNING_MODULE.value, task, status)
                    await self.send_internal_message(msg)

                # inform Command and Data Handling subsytem of the new subsystem state
                self.log(f'Task status communicated! Informing Command and Data Handling subsystem of subsystem state...')
                state = await self.get_state()
                msg = SubsystemStateMessage(self.name, SubsystemNames.CNDH.value, state)
                await self.send_internal_message(msg)
                self.log(f'Subsystem state communicated! Finished processing task of type {type(task)}')

        except asyncio.CancelledError:
            for process in processes:
                process : asyncio.Task
                process.cancel()
                await process

    async def listen_for_abort(self, task: Union[PlatformTask, SubsystemTask, ComponentTask]) -> None:
        """
        Listens for any abort command targetted towards the task being performed.
        Any aborts targetted to other tasks are ignored but not discarted.
        """
        try:
            other_aborts = []
            while True:
                abort_task = await self.aborts.get()
                
                if abort_task == task:
                    for abort in other_aborts:
                        self.aborts.put(abort)
                    return
                else:
                    other_aborts.append(abort_task)

        except asyncio.CancelledError:
            for abort in other_aborts:
                self.aborts.put(abort)

    async def perform_task(self, task: Union[PlatformTask, SubsystemTask, ComponentTask]) -> TaskStatus:
        """
        Performs a task given to this subsystem. If the task is a subsystem-level task, it decomposes the task into a list of component tasks to be performed.
        Rejects any tasks if the subsystem is in a failure mode of if it is not intended for to be performed by this subsystem. 
        """
        try:
            self.log(f'Starting task of type {type(task)}...')
            
            # Decompose subsytem task into component tasks
            task_handler = None
            tasks = []
            if isinstance(task, PlatformTask):
                tasks = await self.decompose_platform_task(task)
            elif isinstance(task, SubsystemTask):
                tasks = await self.decompose_subsystem_task(task)
            elif isinstance(task, ComponentTask):
                tasks = [task]

            if len(tasks) == 0:
                self.log(f'Task of type {type(task)} not supported.')
                raise asyncio.CancelledError
                
            self.log(f'Decomposed task of type {type(task)} into a set of {len(tasks)} subtasks.')

            # submit component tasks
            for task_i in tasks:
                task_handler = asyncio.create_task(self.task_handler(task_i))

                await task_handler

                task_status = task_handler.result()

                if task_status is TaskStatus.ABORTED:
                    self.log(f'Subtask of type {type(task_i)} was aborted.')
                    raise asyncio.CancelledError

                elif task_status is TaskStatus.DONE:
                    self.log(f'Subtask of type {type(task_i)} successfully completed!')
            
            # return task completion status
            self.log(f'Task of type {type(task)} successfully completed!')
            return TaskStatus.DONE

        except asyncio.CancelledError:
            # cancel task_handler
            if task_handler is not None and not task_handler.done():
                task_handler.cancel()
                await task_handler

            # return task abort status
            self.log(f'Task of type {type(task)} aborted.')
            return TaskStatus.ABORTED

    async def decompose_platform_task(self, task : PlatformTask) -> list:
        """
        Decomposes a platform-level task and returns a list of subsystem-level tasks to be performed by this or other subsystems.
        """
        self.log(f'Module does not support platform-level tasks.')
        return []

    async def decompose_subsystem_task(self, task : SubsystemTask) -> list:
        """
        Decomposes a subsystem-level task and returns a list of component-level tasks to be performed by this subsystem.
        """
        self.log(f'Module does not support subsystem-level tasks.')
        return []

    async def task_handler(self, task: Union[SubsystemTask, ComponentTask]) -> None:
        """
        Handles component tasks to be performed by this subsystem's components or subsystem tasks intended for other subsystems.
        Will abort any subsystem task submitted to itself to avoid locking.
        """
        try:
            if isinstance(task, ComponentTask):
                component_found = False
                for component in self.submodules:
                    component : ComponentModule
                    if component.name == task.component:
                        component_found = True
                        break

                if not component_found:
                    self.log(f'Component task intended for another subsystem. Initially intended for component \'{task.component}\'.')
                    raise asyncio.CancelledError

                # submit task to be performed by component
                self.log(f'Submitting component task to \'{task.component}\'...')
                msg = ComponentTaskMessage(self.name, task.component, task)
                await self.send_internal_message(msg)

            elif isinstance(task, SubsystemTask):
                if task.subsystem == self.name:
                    # Cannot submit a task to itself while performing other tasks. Will lead to blocking.
                    self.log(f'Attempting to submit a subsystem task intended for self.')
                    raise asyncio.CancelledError

                # submit task to be performed by subsystem
                self.log(f'Submitting subsystem task to \'{task.subsystem}\'...')
                msg = SubsystemTaskMessage(self.name, task.subsystem, task)
                await self.send_internal_message(msg)

            # wait for response
            self.log(f'Waiting for task completion status response...')
            status : TaskStatus = None
            resp : list = []
            while True:
                resp_task, resp_status = await self.recevied_task_status.get()

                if resp_task == task:
                    status = resp_status              
                    self.log(f'Completion status for target task received! Status for task of type {type(task)}: {status.name}')
                    break
                else:
                    self.log(f'Received a task completion status for another task. Waiting for task completion status response...')
                    resp.append( (resp_task, resp_status) )

            for resp_task, resp_status in resp:
                self.recevied_task_status.put( (resp_task, resp_status) )

            return status

        except asyncio.CancelledError:
            return TaskStatus.ABORTED

    async def environment_event_processor(self):
        """
        Processes any incoming events from the environment
        """
        try:
            aquired = None
            while True:
                # wait for an event to be received
                event_broadcast : EventBroadcastMessage = await self.environment_events.get()

                # handle according to event type
                aquired = await self.state_lock.acquire()

                # record subsystem-level effects
                await self.environment_event_handler(event_broadcast)

                # release state lock
                self.state_lock.release()
                aquired = False       

        except asyncio.CancelledError:
            if aquired:
                self.state_lock.release()

    async def environment_event_handler(self, event_broadcast : EnvironmentBroadcastMessage) -> bool:
        """ 
        Affects the component depending on the type of event being received. Forwards all events
        to all of this subsystem's components by default.
        """
        for component in self.submodules:
            component : ComponentModule
            msg = InternalMessage(self.name, component.name, event_broadcast)
            await self.send_internal_message(msg)
        return

    """
    --------------------
    HELPING FUNCTIONS
    --------------------
    """
    async def get_state(self):
        """
        Returns a state class object capturing the state of this subsystem
        """
        try:
            # process indicators
            acquired = False

            # wait for any possible update process to finish
            acquired = await self.state_lock.acquire()

            # get state object from component status
            self.subsystem_state : SubsystemState
            state = self.subsystem_state.from_subsystem(self)

            # release update lock
            self.state_lock.release()

            return state
        except asyncio.CancelledError:
            if self.state_lock.locked() and acquired:
                # if this process had acquired the update_lock and has not released it, then release
                self.state_lock.release()
            return None
"""
-------------------------------
COMPONENT AND SUBSYSTEM STATES
-------------------------------
"""
class ComponentState:
    def __init__(self, name: str, component_type: type, power_consumed : float, power_supplied : float, health: ComponentHealth, status : ComponentStatus) -> None:
        """
        Describes the state of a generic component. Each component type must have its own component state class if it contains any
        extra metrics that describe its state besides power consumed, power supplied, health, and operational status. 
        """
        # component info
        self.component_name = name
        self.component_type = component_type

        # power state
        self.power_consumed = power_consumed
        self.power_supplied = power_supplied

        # component status
        self.health = health
        self.status = status

    @abstractmethod
    def from_component(component : ComponentModule):
        pass

class SubsystemState:
    def __init__(self, name: str, subsystem_type : type, component_states : dict, health : SubsystemHealth, status : SubsystemStatus):
        """
        Describes the state of a generic subsystem. Each subsystem type must have its own component state class if it contains any
        extra metrics that describe its state besides health, operational status, and subcomponent states. 
        """
        # subsystem info
        self.subsystem_name = name
        self.subsystem_type = subsystem_type

        # subsystem status
        self.health = health
        self.status = status

        # component states
        self.component_states = dict()
        for component in component_states:
            self.component_states[component] = component_states[component]

    @abstractmethod
    def from_subsystem(subsystem : SubsystemModule):
        pass

"""
COMMAND AND DATA HANDLING SUBSYSTEM
"""
class CommandAndDataHandlingSubsystem(SubsystemModule):
    def __init__(self, 
                parent_platform_sim: Module, 
                health: ComponentHealth = ComponentHealth.NOMINAL, 
                status: ComponentStatus = ComponentStatus.ON) -> None:
        super().__init__(SubsystemNames.CNDH.value, parent_platform_sim, CommandAndDataHandlingState, health, status)
        self.submodules = [ OnboardComputerModule(self, 1, 1e9) ]
    
    async def subsystem_state_update_handler(self, subsystem_state):
        """
        Reacts to other subsystem state updates.
        """
        return

    async def decompose_platform_task(self, task : PlatformTask) -> list:
        """
        Decomposes a platform-level task and returns a list of subsystem-level tasks to be performed by this or other subsystems.
        """

        if isinstance(task, ObservationTask):
            lat, lon = task.target
            self.log(f'Decompose observation platform-level task into subsystem-level tasks')
            return [ PerformMeasurement(lat, lon, task.instrument_list, task.durations) ]
        else:
            return await super().decompose_platform_task(task)

class CommandAndDataHandlingState(SubsystemState):
    def __init__(self, 
                component_states: dict, 
                health: SubsystemHealth, 
                status: SubsystemStatus):
        super().__init__(SubsystemNames.CNDH.value, CommandAndDataHandlingSubsystem, component_states, health, status)

class OnboardComputerModule(ComponentModule):
    def __init__(self, 
                parent_subsystem: Module, 
                average_power_consumption: float, 
                memory_capacity : float,
                health: ComponentHealth = ComponentHealth.NOMINAL, 
                status: ComponentStatus = ComponentStatus.ON, 
                f_update: float = 1.0) -> None:
        super().__init__(ComponentNames.ONBOARD_COMPUTER.value, parent_subsystem, OnboardComputerState, average_power_consumption, health, status, f_update)
        self.memory_stored = 0
        self.memory_capacity = memory_capacity

    def is_critical(self) -> bool:
        """
        Returns true if the current state of the component is critical. 
        Is true when the memory has reached 80% of its capacity
        """
        threshold = 0.90
        return self.memory_stored >= self.memory_capacity * threshold

    def is_failed(self) -> bool:
        """
        Returns true if the current state of the component is a failure state
        """
        return super().is_failed() or self.memory_stored > self.memory_capacity

    async def perform_task(self, task: ComponentTask) -> TaskStatus:
        """
        Performs a task given to this component. 
        Rejects any tasks if the component is in a failure mode of if it is not intended for to be performed by this component. 
        """
        try:
            acquired = None

            # check if component was the intended performer of this task
            if task.component != self.name:
                self.log(f'Component task not intended for this component. Initially intended for component \'{task.component}\'. Aborting task...')
                raise asyncio.CancelledError

            if isinstance(task, SaveToMemoryTask):
                self.log(f'In save to memory task')
                #await self.enabled.set() TODO fix this enable setting?
                self.log(f'In save to memory task')
                data = task.get_data()
                lat, lon = task.get_target()
                data_vol = len(data.encode('utf-8'))

                if isinstance(task, DeleteFromMemoryTask):
                    if self.memory_stored - data_vol < 0:
                        # insufficient data to be deleted, discarding task.
                        self.log(f'Module does NOT contain data to delete. Data size: {data_vol}, memory state: ({self.memory_stored}/{self.memory_capacity}).')
                        raise asyncio.CancelledError

                    else:
                        # data successfully stored in internal memory, send to science module for processing
                        
                        msg = DataDeletedMessage(self.name, AgentModuleTypes.SCIENCE_MODULE.value, lat, lon, data)
                        self.log(f'Deleting data from {AgentModuleTypes.SCIENCE_MODULE}...')

                        self.memory_stored -= data_vol
                        self.log(f'Data successfully deleted from internal memory! New internal memory state: ({self.memory_stored}/{self.memory_capacity}).')
                else:
                    self.log(f'In else')
                    if self.memory_stored + data_vol > self.memory_capacity:
                        # insufficient memory storage for incoming data, discarding task.
                        self.log(f'Module does NOT contain enough memory space to store data. Data size: {data_vol}, memory state: ({self.memory_stored}/{self.memory_capacity}).')
                        raise asyncio.CancelledError

                    else:
                        # data successfully stored in internal memory, send to science module for processing
                        msg = DataMessage(self.name, AgentModuleTypes.SCIENCE_MODULE.value, lat, lon, data)
                        self.log(f'Sending data to {AgentModuleTypes.SCIENCE_MODULE} for processing...')
                        
                        self.memory_stored += data_vol
                        self.log(f'Data successfully stored in internal memory! New internal memory state: ({self.memory_stored}/{self.memory_capacity}).')
                        
                        await self.send_internal_message(msg)

                return TaskStatus.DONE

            else:
                self.log(f'Task of type {type(task)} not yet supported.')
                acquired = None 
                raise asyncio.CancelledError

        except asyncio.CancelledError:
            self.log(f'Aborting task of type {type(task)}.')

            # release update lock if cancelled during task handling
            await self.sim_wait(1e6)
            if acquired:
                self.state_lock.release()

            # return task abort status
            return TaskStatus.ABORTED

class OnboardComputerState(ComponentState):
    def __init__(self, 
                name: str, 
                component_type: type, 
                power_consumed: float, 
                power_supplied: float, 
                memory_stored: float,
                memory_capacity: float,
                health: ComponentHealth, 
                status: ComponentStatus) -> None:
        super().__init__(name, component_type, power_consumed, power_supplied, health, status)
        self.dmemory_stored = memory_stored
        self.memory_capacity = memory_capacity

    def from_component(component: OnboardComputerModule):
        return OnboardComputerState(component.name, 
                                    OnboardComputerModule, 
                                    component.power_consumed, 
                                    component.power_supplied, 
                                    component.memory_stored, 
                                    component.memory_capacity, 
                                    component.health, 
                                    component.status)

"""
GNC SUBSYSTEM
"""
class GuidanceAndNavigationSubsystem(SubsystemModule):
    def __init__(self, 
                parent_platform_sim: Module, 
                health: ComponentHealth = ComponentHealth.NOMINAL, 
                status: ComponentStatus = ComponentStatus.ON) -> None:
        super().__init__(SubsystemNames.GNC.name, parent_platform_sim, GuidanceAndNavigationSubsystemState, health, status)
        self.submodules = [
                            PositionDeterminationModule(self, 1.0),
                            SunSensorModule(self, 1.0)
                          ]

class GuidanceAndNavigationSubsystemState(SubsystemState):
    def __init__(self, component_states: dict, health: SubsystemHealth, status: SubsystemStatus):
        super().__init__(SubsystemNames.GNC.name, GuidanceAndNavigationSubsystem, component_states, health, status)
    
    def from_subsystem(gnc: GuidanceAndNavigationSubsystem):
        return GuidanceAndNavigationSubsystemState(gnc.component_states, gnc.health, gnc.status)

class PositionDeterminationModule(ComponentModule):
    def __init__(self, 
                parent_subsystem: Module, 
                average_power_consumption: float, 
                health: ComponentHealth = ComponentHealth.NOMINAL, 
                status: ComponentStatus = ComponentStatus.ON, 
                f_update: float = 1) -> None:
        super().__init__(ComponentNames.POS.value, parent_subsystem, PositionDeterminationState, average_power_consumption, health, status, f_update)
        self.pos = [None, None, None]
        self.vel = [None, None, None]

    async def update_properties(self, dt):
        await super().update_properties(dt)

        # sense linear position and velocity vectors
        self.log(f'Sensing agent position and velocity from environment...')
        src = self.get_top_module()
        msg = AgentSenseMessage(src.name, dict())
        response = await self.submit_environment_message(msg)

        if response is not None:
            response : AgentSenseMessage
            self.log(f'Current state: pos=[{response.pos}], vel=[{response.vel}]')
            
            self.pos = []
            for x_i in response.pos:
                self.pos.append(x_i)

            self.vel = []
            for v_i in response.vel:
                self.vel.append(v_i)

class PositionDeterminationState(ComponentState):
    def __init__(self,
                power_consumed: float, 
                power_supplied: float, 
                pos : list,
                vel : list,
                health: ComponentHealth, 
                status: ComponentStatus) -> None:
        super().__init__(ComponentNames.POS.value, PositionDeterminationModule, power_consumed, power_supplied, health, status)
        self.pos = []
        for x_i in pos:
            self.pos.append(x_i)

        self.vel = []
        for v_i in vel:
            self.vel.append(v_i)

    def from_component(component: PositionDeterminationModule):
        return PositionDeterminationState(component.power_consumed, component.power_supplied, component.pos, component.vel, component.health, component.status)

class SunSensorModule(ComponentModule):
    def __init__(self, 
                parent_subsystem: Module, 
                average_power_consumption: float, 
                health: ComponentHealth = ComponentHealth.NOMINAL, 
                status: ComponentStatus = ComponentStatus.ON, 
                f_update: float = 1) -> None:
        super().__init__(ComponentNames.SUN_SENSOR.value, parent_subsystem, SunSensorState, average_power_consumption, health, status, f_update)
        self.eclipse = None
        self.sun_vector = [None, None, None]

    async def update_properties(self, dt):
        await super().update_properties(dt)

        # sense eclipse state and sun-vector
        self.log(f'Sensing eclipse state from environment...')
        src = self.get_top_module()
        msg = AgentSenseMessage(src.name, dict())
        response = await self.submit_environment_message(msg)

        if response is not None:
            response : AgentSenseMessage
            self.log(f'Current state: eclpise={response.eclipse}')
            self.eclipse = response.eclipse
            #TODO add sun-vector to response output

class SunSensorState(ComponentState):
    def __init__(self,
                power_consumed: float, 
                power_supplied: float, 
                eclipse : bool,
                sun_vector : list,
                health: ComponentHealth, 
                status: ComponentStatus) -> None:
        super().__init__(ComponentNames.SUN_SENSOR.value, SunSensorModule, power_consumed, power_supplied, health, status)
        self.eclipse = eclipse
        self.sun_vector = []
        for x_i in sun_vector:
            self.sun_vector.append(x_i)

    def from_component(component: SunSensorModule):
        return SunSensorState(component.power_consumed, component.power_supplied, component.eclipse, component.sun_vector, component.health, component.status)

"""
PAYLOAD SUBSYSTEM
"""
class PayloadSubsystem(SubsystemModule):
    def __init__(self, parent_platform_sim: Module, health: ComponentHealth = ComponentHealth.NOMINAL, status: ComponentStatus = ComponentStatus.OFF) -> None:
        super().__init__(SubsystemNames.PAYLOAD.value, parent_platform_sim, PayloadState, health, status)
        self.submodules = [ InstrumentComponent(InstrumentNames.TEST.value, self, 10, 1, 100) ]

    async def activate(self):
        await super().activate()

        self.attitude_state = asyncio.Queue()

    async def subsystem_state_update_handler(self, subsystem_state):
        """
        Reacts to other subsystem state updates.
        """
        self.log(f'payload subsystem state update handler')
        if isinstance(subsystem_state, AttitudeDeterminationAndControlState):
            await self.attitude_state.put(subsystem_state)

    async def decompose_subsystem_task(self, task : SubsystemTask) -> list:
        """
        Decomposes a subsystem-level task and returns a list of component-level tasks to be performed by this subsystem.
        """
        if isinstance(task, PerformMeasurement):
            comp_tasks = []
            self.log(f'In decompose subsystem task in Payload')
            # ask for latest attitude state
            msg = SubsystemStateRequestMessage(self.name, SubsystemNames.ADCS.value)
            await self.send_internal_message(msg)

            attitude_state = await self.attitude_state.get()
            self.log(f'Past attitude state')
            # instruct each instrument in the observation task to perform the masurement 
            for instrument in task.instruments:
                i = task.instruments.index(instrument)
                target_lat, target_lon = task.target
                comp_tasks.append( MeasurementTask(instrument, task.durations[i], target_lat, target_lon, attitude_state) )
            self.log(f'End of decompose subsystem task in Payload')
            return comp_tasks
        else:
            return await super().decompose_subsystem_task(task)

class PayloadState(SubsystemState):
    def __init__(self, component_states: dict, health: SubsystemHealth, status: SubsystemStatus):
        super().__init__(SubsystemNames.PAYLOAD.value, PayloadSubsystem, component_states, health, status)

    def from_subsystem(payload: PayloadSubsystem):
        return PayloadState(payload.component_states, payload.health, payload.status)

class InstrumentComponent(ComponentModule):
    def __init__(self, 
                name: str, 
                parent_subsystem: Module,  
                average_power_consumption: float, 
                data_rate: float,
                buffer_capacity: float,
                health: ComponentHealth = ComponentHealth.NOMINAL, 
                status: ComponentStatus = ComponentStatus.OFF, 
                f_update: float = 1, 
                n_timed_coroutines: int = 3) -> None:
        super().__init__(name, parent_subsystem, InstrumentState, average_power_consumption, health, status, f_update, n_timed_coroutines)
        self.data_rate = data_rate
        self.buffer_capacity = buffer_capacity
        self.buffer_allocated = 0

    def is_critical(self) -> bool:
        buffer_capacity_threshold = 0.90
        return super().is_critical() or self.buffer_allocated / self.buffer_capacity >= buffer_capacity_threshold

    def is_failed(self) -> bool:
        return super().is_failed() or self.buffer_allocated / self.buffer_capacity >= 1.0

    async def wait_for_failure(self) -> None:
        try:
            acquired = await self.state_lock.acquire()
            if self.status is ComponentStatus.ON:
                self.state_lock.release()
                acquired = None

                # estimate when buffer will be full
                dt = (self.buffer_capacity - self.buffer_allocated) / self.data_rate

                # wait for buffer to be full 
                await self.sim_wait(dt)
            
            else:
                self.state_lock.release()
                acquired = None

                # if instrument is disabled, then it will never fail
                while True:
                    await self.sim_wait(1e6)
                
        except asyncio.CancelledError:
            if acquired:
                self.state_lock.release()

    async def perform_task(self, task : ComponentTask) -> None:
        """
        Handles tasks to be performed by this battery component. 
        """
        try:
            # check if component was the intended performer of this task
            if task.component != self.name:
                self.log(f'Component task not intended for this component. Initially intended for component \'{task.component}\'. Aborting task...')
                raise asyncio.CancelledError

            if isinstance(task, MeasurementTask):
                self.status = ComponentStatus.ON # TODO remove this hardcode
                if self.status is ComponentStatus.OFF:
                    self.log(f'Cannot perform measurement while component status is {self.status}.')
                    raise asyncio.CancelledError
                
                # sense environment
                self.log(f'Performing measurement...')
                src = self.get_top_module()
                lat, lon = task.target
                msg = ObservationSenseMessage(src.name, lat, lon, "radiances") # TODO replace hardcoded radiances with instrument specific measurements
                response = await self.submit_environment_message(msg)
        
                # wait for measurement duration
                # TODO consider real-time delays from environment server querying for the data being sensed
                self.log(f'sim_wait in payload')
                print(task.duration)
                await self.sim_wait(task.duration)

                self.log(f'Measurement complete! Sending data to internal memory.')
                # package data and send to memory
                if response is not None:
                    response : ObservationSenseMessage
                    data_save_task = SaveToMemoryTask(lat, lon, response.obs)
                    data_msg = ComponentTaskMessage(self.name, ComponentNames.ONBOARD_COMPUTER.name, data_save_task)

                    await self.send_internal_message(data_msg)

                # update state
                await self.update()

                # obtain state lock
                acquired = await self.state_lock.acquire()

                # delete data from buffer
                self.buffer_allocated -= self.data_rate * task.duration

                # release state lock
                self.state_lock.release()
                acquired = None

            else:
                self.log(f'Task of type {type(task)} not yet supported.')
                acquired = None 
                raise asyncio.CancelledError

        except asyncio.CancelledError:
            self.log(f'Aborting task of type {type(task)}.')

            # release update lock if cancelled during task handling
            if acquired:
                self.state_lock.release()

            # return task abort status
            return TaskStatus.ABORTED

    async def update_properties(self, dt):
        await super().update_properties(dt)

        if self.status is ComponentStatus.ON and abs(self.dp) < 1e-6:
            # if component is on and receiving sufficient power, then it collects data in its buffer
            if self.buffer_allocated + dt * self.data_rate <= self.buffer_capacity:
                self.buffer_allocated += dt * self.data_rate
            else:
                self.buffer_allocated = self.buffer_capacity

class InstrumentState(ComponentState):
    def __init__(self, 
                name: str, 
                power_consumed: float, 
                power_supplied: float,
                data_rate: float,
                buffer_capacity: float, 
                buffer_allocated: float,
                health: ComponentHealth, 
                status: ComponentStatus) -> None:
        super().__init__(name, InstrumentComponent, power_consumed, power_supplied, health, status)
        self.data_rate = data_rate
        self.buffer_capacity = buffer_capacity
        self.buffer_allocated = buffer_allocated

    def from_component(instrument : InstrumentComponent):
        return InstrumentState(instrument.name, instrument.power_consumed, instrument.power_supplied, instrument.data_rate, instrument.buffer_capacity, instrument.buffer_allocated, instrument.health, instrument.status)

"""
ADCS 
"""
class AttitudeDeterminationAndControlSubsystem(SubsystemModule):
    def __init__(self, 
                parent_platform_sim: Module, 
                health: ComponentHealth = ComponentHealth.NOMINAL, 
                status: ComponentStatus = ComponentStatus.ON) -> None:
        super().__init__(SubsystemNames.ADCS.value, parent_platform_sim, AttitudeDeterminationAndControlState, health, status)
        self.submodules = [
                            InertialMeasurementUnitModule(self, 1)
                          ]

    async def decompose_subsystem_task(self, task : SubsystemTask) -> list:
        """
        Decomposes a subsystem-level task and returns a list of component-level tasks to be performed by this subsystem.
        """
        if isinstance(task, PerformAttitudeManeuverTask):
            return [ AttitudeUpdateTask(task.target_angular_pos, task.target_angular_vel) ]
        else:
            await super().decompose_subsystem_task(task)

class AttitudeDeterminationAndControlState(SubsystemState):
    def __init__(self, 
                component_states: dict,
                health: SubsystemHealth, 
                status: SubsystemStatus):
        super().__init__(SubsystemNames.ADCS.value, AttitudeDeterminationAndControlSubsystem, component_states, health, status)
    
    def from_subsystem(adcs: AttitudeDeterminationAndControlSubsystem):
        return AttitudeDeterminationAndControlState(adcs.component_states, adcs.health, adcs.status)

class InertialMeasurementUnitModule(ComponentModule):
    def __init__(self, 
                parent_subsystem: Module, 
                average_power_consumption: float, 
                health: ComponentHealth = ComponentHealth.NOMINAL, 
                status: ComponentStatus = ComponentStatus.ON, 
                f_update: float = 1) -> None:
        super().__init__(ComponentNames.IMU.value, parent_subsystem, InertialMeasurementUnitState, average_power_consumption, health, status, f_update)

        self.angular_pos = [None, None, None, None]
        self.angular_vel = [None, None, None, None]

    async def update_properties(self, dt):
        await super().update_properties(dt)
        # TODO sense angular position and velocity

    async def perform_task(self, task: ComponentTask) -> TaskStatus:
        """
        Performs a task given to this component. 
        Rejects any tasks that is not intended to be performed by this component. 
        """
        try:
            # check if component was the intended performer of this task
            if task.component != self.name:
                self.log(f'Component task not intended for this component. Initially intended for component \'{task.component}\'. Aborting task...')
                raise asyncio.CancelledError
            
            acquire = None
            if isinstance(task, AttitudeUpdateTask):
                acquire = await self.state_lock.acquire()
                
                self.angular_pos = task.new_angular_pos
                self.angular_vel = task.new_angular_vel

                self.log(f'Attitude updated! New state: angular pos=[{self.angular_pos}], angular vel=[{self.angular_vel}]')

                self.state_lock.release()
            else:
                self.log(f'Task of type {type(task)} not yet supported.')
                raise asyncio.CancelledError

        except asyncio.CancelledError:
            self.log(f'Aborting task of type {type(task)}.')

            if acquire:
                self.state_lock.release()

            # return task abort status
            return TaskStatus.ABORTED

class InertialMeasurementUnitState(ComponentState):
    def __init__(self,
                power_consumed: float, 
                power_supplied: float, 
                angular_pos : list,
                angular_vel : list,
                health: ComponentHealth, 
                status: ComponentStatus) -> None:
        super().__init__(ComponentNames.IMU.value, InertialMeasurementUnitModule, power_consumed, power_supplied, health, status)
        self.angular_pos = []
        for x_i in angular_pos:
            self.angular_pos.append(x_i)

        self.angular_vel = []
        for v_i in angular_vel:
            self.angular_pos.append(v_i)

    def from_component(imu: InertialMeasurementUnitModule):
        return InertialMeasurementUnitState(imu.power_consumed, imu.power_supplied, imu.angular_pos, imu.angular_vel, imu.health, imu.status)

"""
EPS
"""
class ElectricPowerSubsystem(SubsystemModule):
    def __init__(self,
                parent_platform_sim: Module, 
                health: ComponentHealth = ComponentHealth.NOMINAL, 
                status: ComponentStatus = ComponentStatus.OFF) -> None:
        """
        Describes the agent's Electric Power Subsystem

        parent_platform_sim:
            parent platform simulator module
        health:
            health of the component
        status:
            status of the component
        """
        super().__init__(SubsystemNames.EPS.value, parent_platform_sim, ElectricPowerSubsystemState, health, status)

        self.submodules = [
                            # BatteryModule(self, 100, 1000),
                            # PowerSupplyComponent(ComponentNames.POWER_SUPPLY.value, self, EPSComponentState, 100)
                          ]

    def is_subsystem_critical(self) -> bool:
        """
        Detects subsystem-level critical state using latest component states received by this subsystem.
        Returns true when the total power output of the 
        """
        threshold = 0.05
        current_power_out_total = 0
        maximum_power_outout = 0
        for component in self.submodules:
            component : ComponentModule
            
            comp_state : EPSComponentState = self.component_states[component.name]
            current_power_out_total += comp_state.power_output
            maximum_power_outout += comp_state.maximum_power_output

        return current_power_out_total/maximum_power_outout >= 1 - threshold
    
    def is_subsystem_failure(self) -> bool:
        """
        Detects subsystem-level failure state using latest component states received by this subsystem. 
        It fails when a single component in the subsystem is in a failure state.
        """
        return self.is_component_failure()

    async def decompose_subsystem_task(self, task : SubsystemTask) -> list:
        """
        Decomposes a subsystem-level task and returns a list of component-level tasks to be performed by this subsystem.
        """
        try:
            if isinstance(task, PowerSupplyRequestTask):
                # from all available components, it instructs an available power supply to provide power to a component requesting it
                
                # unpackage task 
                remaining_power_to_supply = task.power_requested
                power_to_supply = dict()

                # check if power is to be provided or stopped
                if remaining_power_to_supply > 0:
                    self.log(f'\'{task.target}\' is requesting {task.power_requested} [W] to be provided.')

                    # check which components are available to provide power to target
                    for component in self.submodules:
                        component : PowerSupplyComponent
                        power_available = component.maximum_power_output - component.power_output

                        if power_available > 0.0:
                            if remaining_power_to_supply <= power_available:
                                power_to_supply[component.name] = remaining_power_to_supply
                                remaining_power_to_supply -= remaining_power_to_supply
                            else:
                                power_to_supply[component.name] = power_available
                                remaining_power_to_supply -= power_available
                        
                        if remaining_power_to_supply < 1e-6:
                            break
                    
                    if remaining_power_to_supply < 1e-6:
                        # if enough power can be provided, send tasks to eps components
                        comp_tasks = []
                        for eps_component_name in power_to_supply:
                            self.log(f'Instructing \'{eps_component_name}\' to provide \'{task.target}\' with {power_to_supply[eps_component_name]} [W] of power...')
                            comp_tasks.append( ProvidePowerTask(eps_component_name, power_to_supply[eps_component_name], task.target) )
                        return comp_tasks
                    else:
                        # else abort task
                        self.log(f'{self.name} cannot meet power request of {task.power_requested} [W].')
                        return []
                else:
                    self.log(f'\'{task.target}\' is requesting {-task.power_requested} [W] to no longer be provided.')

                    for component in self.submodules:
                        component : PowerSupplyComponent
                        
                        state : EPSComponentState = await self.get_state()

                        for component_name in state.components_powered:
                            if component_name == task.target:
                                remaining_power_to_supply -= state.components_powered[component_name]
                                power_to_supply[component_name] = state.components_powered[component_name]

                            if remaining_power_to_supply < 1e-6:
                                break
                    
                    if remaining_power_to_supply < 1e-6:
                        # if enough power can be provided, send tasks to eps components
                        comp_tasks = []
                        for eps_component_name in power_to_supply:
                            self.log(f'Instructing \'{eps_component_name}\' to stop providing \'{task.target}\' with {power_to_supply[eps_component_name]}[W] of power...')
                            comp_tasks.append( StopProvidingPowerTask(eps_component_name, power_to_supply[eps_component_name], task.target) )
                        return comp_tasks
                    else:
                        # else abort task
                        self.log(f'{self.name} cannot meet power stop request of {task.power_requested} [W].')
                        return []

            else:
                return await super().decompose_subsystem_task(task)
        
        except asyncio.CancelledError:
            return

class ElectricPowerSubsystemState(SubsystemState):
    def __init__(self, 
                component_states: dict, 
                health: SubsystemHealth, 
                status: SubsystemStatus):
        super().__init__(SubsystemNames.EPS.value, ElectricPowerSubsystem, component_states, health, status)

    def from_subsystem(eps: ElectricPowerSubsystem):
        return ElectricPowerSubsystemState(eps.component_states, eps.health, eps.status)

class PowerSupplyComponent(ComponentModule):
    def __init__(self, 
                name : str, 
                parent_subsystem : Module, 
                state_type : type,
                maximum_power_output : float = 1e10,
                health: ComponentHealth = ComponentHealth.NOMINAL, 
                status: ComponentStatus = ComponentStatus.ON, 
                f_update: float = 1) -> None:
        """
        Describes a generic power supply component within the EPS subsystem

        parent_subsystem:
            parent EPS subsystem
        maximum_power_output:
            maximum power output of this battery in [W]
        health:
            health of the component
        status:
            status of the component
        f_update:
            frequency of periodic state checks in [Hz]
        """
        average_power_consumption=0.0
        super().__init__(name, parent_subsystem, state_type, average_power_consumption, health, status, f_update)
        self.maximum_power_output = maximum_power_output
        self.power_output = 0

        self.components_powered = dict()

    def is_critical(self) -> bool:
        """
        Returns true if the current state of the component is critical. 
        Is true when the current power output is within 5% of the maximumim power output.
        """
        crit_threshold = 0.05
        return self.power_output/self.maximum_power_output > 1 - crit_threshold

    def is_power_supply_failure(self):
        """
        returns true if more power is being outputted than the maximum power output
        """
        return self.power_output/self.maximum_power_output > 1

    async def update_properties(self, dt):
        """
        Updates the current state of the component given a time-step dt
        """
        super().update_properties(dt)

        # update power output
        self.power_output = 0
        if self.status is ComponentStatus.ON:
            for component in self.components_powered:
                self.power_output += self.components_powered[component]

    async def perform_task(self, task: ComponentTask) -> TaskStatus:
        """
        Performs a task given to this component. 
        Rejects any tasks if the component is in a failure mode of if it is not intended for to be performed by this component. 
        """
        try:
            acquired = None

            # check if component was the intended performer of this task
            if task.component != self.name:
                self.log(f'Component task not intended for this component. Initially intended for component \'{task.component}\'. Aborting task...')
                raise asyncio.CancelledError

            if isinstance(task, ProvidePowerTask):               
                if task.power_to_supply > 0:
                    # component is requesting for power to be provided

                    if self.power_output == self.maximum_power_output:
                        # insuficient power output to perform this task
                        self.log(f'Component cannot provide {task.power_to_supply} [W]. Current power output state: ({self.power_output} [W]/{self.maximum_power_output} [W]). Aborting task...')
                        raise asyncio.CancelledError

                    # check if component can satisfy power supply demand
                    if self.power_output + task.power_to_supply > self.maximum_power_output:
                        task.power_to_supply = self.maximum_power_output - self.power_output

                    # update internal power ouput 
                    self.power_output += task.power_to_supply

                    # update internal list of powered components    
                    if task.target in self.components_powered:
                        self.components_powered[task.target] += task.power_to_supply
                    else:
                        self.components_powered[task.target] = task.power_to_supply
                    
                    # inform target component of its new power supply
                    power_supply_task = ReceivePowerTask(task.target, task.power_to_supply)
                    msg = ComponentTaskMessage(self.name, task.target, power_supply_task)
                    self.send_internal_message(msg)
                    self.log(f'Now providing { task.power_to_supply} [W] of power to \'{task.target}\'! (Current power output: {self.power_output}[W]/{self.maximum_power_output}[W])')

                    return TaskStatus.DONE
                else:
                    # component is requesting for power to no longer be provided
                    
                    if task.target in self.components_powered:
                        # check if component can satisfy power supply demand and update internal power output 
                        if self.components_powered[task.target] < abs(task.power_to_supply):
                            task.power_to_supply = -self.components_powered[task.target]

                        # update internal list of powered components    
                        if abs(self.components_powered[task.target] + task.power_to_supply) < 1e-6:
                            # if component is no longer being powered, then remove from dictionary of components powered
                            self.components_powered.pop(task.target)
                        else:
                            self.components_powered[task.target] += task.power_to_supply
                    else:
                        self.log('Cannot stop proving power to a component that is not being powered by this coomponent.')
                        raise asyncio.CancelledError

                    # inform target component of its new power supply
                    power_supply_task = StopReceivingPowerTask(task.target, task.power_to_supply)
                    msg = ComponentTaskMessage(self.name, task.target, power_supply_task)
                    self.send_internal_message(msg)
                    self.log(f'No longer providing { task.power_to_supply} [W] of power to \'{task.target}\'! (Current power output: {self.power_output}[W]/{self.maximum_power_output}[W])')

                    return TaskStatus.DONE
            else:
                self.log(f'Task of type {type(task)} not yet supported.')
                acquired = None 
                raise asyncio.CancelledError

        except asyncio.CancelledError:
            self.log(f'Aborting task of type {type(task)}.')

            # release update lock if cancelled during task handling
            if acquired:
                self.state_lock.release()

            # return task abort status
            return TaskStatus.ABORTED

class EPSComponentState(ComponentState):
    def __init__(self, 
                name : str,
                component_type : type,
                power_consumed: float, 
                power_supplied: float, 
                power_output: float,
                maximum_power_output: float,
                components_powered: dict,
                health: ComponentHealth, 
                status: ComponentStatus) -> None:
        super().__init__(name, component_type, power_consumed, power_supplied, health, status)
        self.components_powered = dict()
        for component in components_powered:
            self.components_powered[component] = components_powered[component]

        self.power_output: float = power_output
        self.maximum_power_output: float = maximum_power_output

    def from_component(component: PowerSupplyComponent):
        return EPSComponentState(component.name,
                            type(component),
                            component.power_consumed,
                            component.power_supplied, 
                            component.power_output, 
                            component.maximum_power_output,
                            component.components_powered,
                            component.health,
                            component.status)

class BatteryModule(PowerSupplyComponent):
    def __init__(self, 
                parent_subsystem: Module, 
                maximum_power_output: float,
                energy_capacity: float,
                initial_charge: float = 1.0,
                charging_efficiency: float = 1.0,
                depth_of_discharge: float = 1.0,
                health: ComponentHealth = ComponentHealth.NOMINAL, 
                status: ComponentStatus = ComponentStatus.OFF, 
                f_update: float = 1) -> None:
        """
        Describes a battery component in the EPS subsystem

        parent_subsystem:
            parent EPS subsystem
        maximum_power_output:
            maximum power output of this battery in [W]
        energy_capacity:
            maximum energy storage capacity in [Whr]
        initial_charge:
            initial battery charge percentage from [0, 1]
        charging_efficiency:
            charging efficiency from [0, 1]
        depth_of_discharge:
            maximum allowable depth of discharge for this battery from [0, 1]
        health:
            health of the component
        status:
            status of the component
        f_update:
            frequency of periodic state checks in [Hz]
        """
        super().__init__(ComponentNames.BATTERY.value, parent_subsystem, BatteryState, maximum_power_output, health, status, f_update)
        self.energy_capacity = energy_capacity
        self.energy_stored = energy_capacity * initial_charge
        self.charging_efficiency = charging_efficiency
        self.depth_of_discharge = depth_of_discharge

        if initial_charge < 0 or initial_charge > 1:
            raise Exception('Initial charge must be a value within the interval [0, 1]')
        if charging_efficiency < 0 or charging_efficiency > 1:
            raise Exception('Charging effciency must be a value within the interval [0, 1]')
        if depth_of_discharge < 0 or depth_of_discharge > 1:
            raise Exception('Depth of Discharge must be a value within the interval [0, 1]')

    def is_critical(self) -> bool:
        """
        Returns true if the current state of the component is critical. 
        Is true when the state of discharge is within 5% of the battery's maximum depth of discharge and the battery
        is being drained or when the battery is charging and it reaches 95% charging capacity
        """
        crit_threshold = 0.05
        
        batt_crit = False
        if self.dp < 0.0:
            batt_crit = (1 - self.energy_stored/self.energy_capacity) >= self.depth_of_discharge - crit_threshold
        elif self.dp > 0.0:
            batt_crit = self.energy_stored/self.energy_capacity >= 1 - crit_threshold
        
        return super().is_critical() or batt_crit

    def is_failed(self) -> bool:
        """
        Returns true if the current state of the component is a failure state.
        Is true when the state of discharge equals or surpasses the battery's maximum depth of discharge and the battery
        is being drained or when the battery is charging and reaches full charge capacity
        """
        batt_failed = False
        if self.dp < 0.0:
            batt_failed = (1 - self.energy_stored/self.energy_capacity) > self.depth_of_discharge 
        elif self.dp > 0.0:
            batt_failed = self.energy_stored/self.energy_capacity > 1

        return super().is_failed() or batt_failed

    def is_power_supply_failure(self):
        """
        returns true if more power is being outputted than the maximum power output or when the battery is still being charged
        after it has reached its maximum capacity.
        """
        battery_at_capacity = abs(self.energy_stored/self.energy_capacity - 1) < 1e-6
        is_charging = self.power_supplied > 0
        battery_over_charge = battery_at_capacity and is_charging

        return super().is_power_supply_failure() or battery_over_charge

    async def wait_for_failure(self) -> None:
        """
        Count downs to the next predicted failure state of this component given that the current configuration is maintained.
        """
        try:
            if self.dp < 0.0:
                # battery is discharging, count-down to next predicted discharge below maximum depth of discharge
                dt = ((1 - self.depth_of_discharge) * self.energy_capacity - self.energy_stored) / self.dp
                await self.sim_wait(dt)

            elif self.dp > 0.0:
                # battery is charging, count-down to full battery status
                dt = (self.energy_capacity - self.energy_stored) / self.dp
                await self.sim_wait(dt)

            else:
                # battery is not being used nor being charged, wait indefinitively 
                while True:
                    await self.sim_wait(1e6)
        except asyncio.CancelledError:
            return

    async def update_properties(self, dt):
        """
        Updates the current state of the component given a time-step dt
        """
        super().update_properties(dt)

        # update power differential tracker
        self.dp = self.power_supplied * self.charging_efficiency - self.power_output

        # update energy storage
        dE = self.dp * dt
        if self.energy_stored + dE < 0.0:
            self.energy_stored = 0.0
        elif self.energy_stored + dE > self.energy_capacity:
            self.energy_stored = self.energy_capacity
        else:
            self.energy_stored += dE        

class BatteryState(EPSComponentState):
    def __init__(self, 
                power_consumed: float, 
                power_supplied: float, 
                power_output: float, 
                maximum_power_output: float, 
                components_powered: dict,
                energy_stored: float,
                energy_capacity: float,
                charging_efficiency: float,
                depth_of_discharge: float,
                health: ComponentHealth, 
                status: ComponentStatus) -> None:
        super().__init__(ComponentNames.BATTERY.value, power_consumed, power_supplied, power_output, maximum_power_output, components_powered, health, status)
        self.energy_stored: float = energy_stored
        self.energy_capacity: float = energy_capacity
        self.charging_efficiency: float = charging_efficiency
        self.depth_of_discharge: float = depth_of_discharge

    def from_component(battery: BatteryModule):
        return BatteryState(battery.power_consumed, 
                            battery.power_supplied, 
                            battery.power_output, 
                            battery.maximum_power_output, 
                            battery.components_powered,
                            battery.energy_stored, 
                            battery.energy_capacity, 
                            battery.charging_efficiency, 
                            battery.depth_of_discharge, 
                            battery.health, 
                            battery.status)
"""
COMMS
"""
class CommsSubsystem(SubsystemModule):
    def __init__(self,
                parent_platform_sim: Module, 
                buffer_size: float,
                health: ComponentHealth = ComponentHealth.NOMINAL,
                status: ComponentStatus = ComponentStatus.ON) -> None:
        """
        Represents the communications subsystem in an agent. Can receive and transmit messages between agents.
        parent_platform_sim:
            platform simulation that the subsystem exists in
        buffer_size:
            size of the buffer in bytes
        """
        super().__init__(SubsystemNames.COMMS.value, parent_platform_sim, CommsSubsystemState, health, status)
        self.submodules = [
                            TransmitterComponent(self, 1, buffer_size),
                            ReceiverComponent(self, 1, buffer_size)
                            ]

class CommsSubsystemState(SubsystemState):
    def __init__(self, component_states: dict, health: SubsystemHealth, status: SubsystemStatus):
        super().__init__(SubsystemNames.COMMS.value, CommsSubsystem, component_states, health, status)

class TransmitterComponent(ComponentModule):
    def __init__(self, 
                parent_subsystem: Module, 
                average_power_consumption: float, 
                buffer_capacity: float,
                health: ComponentHealth = ComponentHealth.NOMINAL, 
                status: ComponentStatus = ComponentStatus.OFF, 
                f_update: float = 1) -> None:
        """
        Describes a receiver transmitter capable of sending messages to other agents

        parent_subsystem:
            parent comms subsystem
        average_power_consumption:
            average power consumption in [W]
        buffer_capacity:
            size of the buffer in [Mbytes]
        health:
            health of the component
        status:
            status of the component
        f_update:
            frequency of periodic state checks in [Hz]
        """
        super().__init__(ComponentNames.TRANSMITTER.value, parent_subsystem, TransmitterState, average_power_consumption, health, status, f_update)
        self.buffer_capacity = buffer_capacity * 1e6
        self.buffer_allocated = 0

    async def activate(self):
        await super().activate()

        self.access_events = dict()

    async def internal_message_handler(self, msg: InternalMessage):
        """
        Processes messages being sent to this component. Only accepts task messages.
        """
        try:
            if msg.dst_module != self.name:
                # this module is NOT the intended receiver for this message. Forwarding to rightful destination
                self.log(f'Received internal message intended for {msg.dst_module}. Rerouting message...')
                await self.send_internal_message(msg)

            elif isinstance(msg, ComponentTaskMessage):
                task = msg.get_task()
                self.log(f'Received a task of type {type(task)}!')
                if isinstance(task, ComponentAbortTask):
                    self.aborts.put(task)
                elif isinstance(task, ComponentMaintenanceTask):
                    self.maintenance_tasks.put(task)
                elif isinstance(task, TransmitMessageTask):
                    await self.state_lock.acquire()

                    t_msg : NodeToEnvironmentMessage = task.msg
                    t_msg_str = t_msg.to_json()
                    t_msg_length = len(t_msg_str.encode('utf-8'))

                    if self.buffer_allocated + t_msg_length <= self.buffer_capacity:
                        self.log(f'Acepted out-going transmission into buffer!')
                        self.tasks.put(task)
                        self.buffer_allocated += t_msg_length
                        self.log(f'Out-going message of length {t_msg_length} now stored in out-going buffer (current state: {self.buffer_allocated}/{self.buffer_capacity}).')
                    else:
                        self.log(f'Rejected out-going transmission into buffer.')
                        self.log(f'Out-going buffer cannot store out-going message of length {t_msg_length} (current state: {self.buffer_allocated}/{self.buffer_capacity}). Discarting message...')

                    self.state_lock.release()                   
            
            elif isinstance(msg.content, EnvironmentBroadcastMessage):
                self.log(f'Received an environment event of type {type(msg.content)}!')
                self.environment_events.put(msg.content)

            else:
                self.log(f'Internal message of type {type(msg)} not yet supported. Discarting message...')
            
        except asyncio.CancelledError:
            return  

    def is_critical(self) -> bool:
        threshold = 0.05
        return super().is_critical() or self.buffer_allocated/self.buffer_capacity > 1-threshold 

    def is_failed(self) -> bool:
        return super().is_failed() or self.buffer_allocated/self.buffer_capacity >= 1

    async def perform_task(self, task: ComponentTask) -> TaskStatus:
        """
        Performs a task given to this component. 
        Rejects any tasks if the component is in a failure mode of if it is not intended for to be performed by this component. 
        """
        try:
            # check if component was the intended performer of this task
            if task.component != self.name:
                self.log(f'Component task not intended for this component. Initially intended for component \'{task.component}\'. Aborting task...')
                raise asyncio.CancelledError

            if isinstance(task, TransmitMessageTask):
                # create task variables
                wait_for_access_start = None
                transmit_msg = None
                wait_for_access_end = None
                wait_for_access_end_event = None
                wait_for_message_timeout = None
                processes = []
                acquired = None

                # unpackage message
                msg : InterNodeMessage = task.msg

                # wait for access to target node
                wait_for_access_start = asyncio.create_task( self.wait_for_access_start(msg.dst) )
                await wait_for_access_start

                # wait for msg to be transmitted successfully or interrupted due to access end or message timeout
                transmit_msg = asyncio.create_task( self.transmit_message(msg) )
                wait_for_access_end = asyncio.create_task( self.wait_for_access_end(msg.dst) )
                wait_for_access_end_event = asyncio.create_task( self.access_events[msg.dst].wait_end() ) 
                wait_for_message_timeout = asyncio.create_task( self.sim_wait(task.timeout) )
                processes = [transmit_msg, wait_for_access_end, wait_for_access_end_event, wait_for_message_timeout]

                _, pending = await asyncio.wait(processes, return_when=asyncio.FIRST_COMPLETED)
                
                # cancel all pending processes
                for pending_task in pending:
                    pending_task : asyncio.Task
                    pending_task.cancel()
                    await pending_task

                # remove message from out-going buffer
                await self.remove_msg_from_buffer(msg)
                self.access_events.pop(msg.dst)

                # return task completion status                
                if transmit_msg.done() and transmit_msg not in pending:
                    self.log(f'Sucessfully transmitted message of type {type(msg)} to target \'{msg.dst}\'!')                    
                    return TaskStatus.DONE

                elif (wait_for_access_end.done() and wait_for_access_end not in pending) or (wait_for_access_end_event.done() and wait_for_access_end_event not in pending):
                    self.log(f'Access to target \'{msg.dst}\' lost during transmission of message of type {type(msg)}!')
                    raise asyncio.CancelledError

                else:
                    self.log(f'Message of type {type(msg)} timed out!')
                    raise asyncio.CancelledError

            else:
                self.log(f'Task of type {type(task)} not yet supported.')
                acquired = None 
                raise asyncio.CancelledError

        except asyncio.CancelledError:
            self.log(f'Aborting task of type {type(task)}.')

            # release update lock if cancelled during task handling
            if acquired:
                self.state_lock.release()

            # cancel any task that's not yet completed
            if not wait_for_access_start.done():
                wait_for_access_start.cancel()
                await wait_for_access_start

            for process in processes:
                if process is not None and isinstance(process, asyncio.Task) and not process.done():
                    process.cancel()
                    await process

            # return task abort status
            return TaskStatus.ABORTED

    async def remove_msg_from_buffer(self, msg : NodeToEnvironmentMessage):
        try:
            self.log(f'Removing message from out-going buffer...')
            acquired = await self.state_lock.acquire()

            msg_str = msg.to_json()
            msg_length = len(msg_str.encode('utf-8'))
            if self.buffer_allocated - msg_length >= 0:
                self.buffer_allocated -= msg_length
            else:
                self.buffer_allocated = 0
            self.log(f'Message sucessfully removed from buffer!')

            self.state_lock.release()

        except asyncio.CancelledError:
            if acquired:
                self.state_lock.release()
    
    async def wait_for_access_start(self, target : str):
        try:
            msg = AgentAccessSenseMessage(self.name, target)

            response : AgentAccessSenseMessage = await self.submit_environment_message(msg)
            while not response.result:
                self.sim_wait(1/self.UPDATE_FREQUENCY)
                response : AgentAccessSenseMessage = await self.submit_environment_message(msg)

            if target not in self.access_events:
                self.access_events[target] = EventPair()        

            self.access_events[target].trigger_start()
        except asyncio.CancelledError:
            return

    async def wait_for_access_end(self, target : str):
        try:
            msg = AgentAccessSenseMessage(self.name, target)

            response : AgentAccessSenseMessage = await self.submit_environment_message(msg)
            while response.result:
                self.sim_wait(1/self.UPDATE_FREQUENCY)
                response : AgentAccessSenseMessage = await self.submit_environment_message(msg)

            if target not in self.access_events:
                self.access_events[target] = EventPair()
            self.access_events[target].trigger_end()

        except asyncio.CancelledError:
            return

    async def environment_event_handler(self, event_msg : EnvironmentBroadcastMessage) -> bool:
        """ 
        Affects the component depending on the type of event being received.
        """
        if isinstance(event_msg, AgentAccessEventBroadcastMessage):
            if not event_msg.rise and event_msg.target in self.access_events:
                # an end of access event for a target agent has been recevied

                # fire end of access event
                self.access_events[event_msg].trigger_end()
                
                return True

        return False

class TransmitterState(ComponentState):
    def __init__(self,
                power_consumed: float, 
                power_supplied: float, 
                buffer_capacity: float,
                buffer_allocated: float,
                health: ComponentHealth, 
                status: ComponentStatus) -> None:
        super().__init__(ComponentNames.TRANSMITTER.value, TransmitterComponent, power_consumed, power_supplied, health, status)
        self.buffer_capacity = buffer_capacity
        self.buffer_allocated = buffer_allocated

    def from_component(transmitter: TransmitterComponent):
        return TransmitterState(transmitter.power_consumed, transmitter.power_supplied, transmitter.buffer_capacity, transmitter.buffer_allocated, transmitter.health, transmitter.status)

class ReceiverComponent(ComponentModule):
    def __init__(self, 
                parent_subsystem: Module,
                average_power_consumption: float,
                buffer_capacity: float,
                health: ComponentHealth = ComponentHealth.NOMINAL,
                status: ComponentStatus = ComponentStatus.ON, 
                f_update: float = 1) -> None:
        """
        Describes a radio receiver capable of sending messages to other agents

        parent_subsystem:
            parent comms subsystem
        average_power_consumption:
            average power consumption in [W]
        buffer_capacity:
            size of the buffer in [Mbytes]
        health:
            health of the component
        status:
            status of the component
        f_update:
            frequency of periodic state checks in [Hz]
        """
        super().__init__(ComponentNames.RECEIVER.value, parent_subsystem, ReceiverState, average_power_consumption, health, status, f_update)
        self.buffer_capacity = buffer_capacity * 1e6
        self.buffer_allocated = 0

    async def activate(self):
        await super().activate()

        self.access_events = dict()

    def is_critical(self) -> bool:
        threshold = 0.05
        return super().is_critical() or self.buffer_allocated/self.buffer_capacity > 1-threshold 

    def is_failed(self) -> bool:
        return super().is_failed() or self.buffer_allocated/self.buffer_capacity >= 1

    async def perform_task(self, task: ComponentTask) -> TaskStatus:
        """
        Listens for any incoming transmissions. Needs to be told to start a ReceiveMessageTransmission
        task from its parent subsystem or CNDH subsystem at the beginning of the simulation otherwise
        all messages will not be received
        """
        try:
            # check if component was the intended performer of this task
            if task.component != self.name:
                self.log(f'Component task not intended for this component. Initially intended for component \'{task.component}\'. Aborting task...')
                raise asyncio.CancelledError

            if isinstance(task, ReceiveMessageTransmission):
                acquired = None

                # gain access to incoming agent message port from parent agent
                parent_agent = self.get_top_module()

                await parent_agent.agent_socket_lock.acquire()

                while True:
                    msg_dict = None

                    # listen for messages from other agents
                    self.log('Waiting for agent messages...')
                    msg_dict = await parent_agent.agent_socket_in.recv_json()
                    self.log(f'Agent message received!')

                    # check if message can fit in incoming buffer
                    msg_str = json.dumps(msg_dict)
                    msg_length = len(msg_str.encode('utf-8'))

                    acquired = await self.state_lock.acquire()
                    if self.buffer_allocated + msg_length <= self.buffer_capacity:
                        self.buffer_allocated += msg_length
                        self.log(f'Incoming message of length {msg_length} now stored in incoming buffer (current state: {self.buffer_allocated}/{self.buffer_capacity}).')
                        self.state_lock.release()
                
                        # handle request
                        msg_type : InterNodeMessageTypes = InterNodeMessageTypes[msg_dict['@type']]

                        if msg_type is InterNodeMessageTypes.PRINT_MESSAGE:
                            # unpack message
                            msg : PrintMessage = PrintMessage.from_dict(msg_dict)
                            
                            # handle message 
                            self.log(f'Received print instruction: \'{msg.content}\'')

                        # elif msg_type is InterNodeMessageTypes.PLANNER_MESSAGE:
                        #     pass
                        # elif msg_type is InterNodeMessageTypes.MEASUREMENT_REQUEST:
                        #     pass
                        # elif msg_type is InterNodeMessageTypes.MEASUREMENT_MESSAGE:
                        #     pass
                        # elif msg_type is InterNodeMessageTypes.INFORMATION_REQUEST:
                        #     pass
                        # elif msg_type is InterNodeMessageTypes.INFORMATION_MESSAGE:
                        #     pass
                        else:
                            self.log(content=f'Internode message of type {msg_type.name} not yet supported. Discarding message...')

                        acquired = await self.state_lock.acquire()
                        self.buffer_allocated -= msg_length
                        self.log(f'Incoming message of length {msg_length} now stored in incoming buffer (current state: {self.buffer_allocated}/{self.buffer_capacity}).')
                        self.state_lock.release()

                    else:
                        self.log(f'Incoming buffer cannot store incoming message of length {msg_length} (current state: {self.buffer_allocated}/{self.buffer_capacity}). Discarting message...')
                    
            else:
                self.log(f'Task of type {type(task)} not yet supported.')
                raise asyncio.CancelledError

        except asyncio.CancelledError:
            self.log(f'Aborting task of type {type(task)}.')

            # release update lock if cancelled during task handling
            if acquired:
                self.state_lock.release()

            # return task abort status
            return TaskStatus.ABORTED

    async def environment_event_handler(self, event_msg : EnvironmentBroadcastMessage) -> bool:
        """ 
        Affects the component depending on the type of event being received.
        """
        if isinstance(event_msg, AgentAccessEventBroadcastMessage):
            if not event_msg.rise and event_msg.target in self.access_events:
                # an end of access event for a target agent has been recevied

                # fire end of access event
                self.access_events[event_msg].trigger_end()
                
                return True

        return False


class ReceiverState(ComponentState):
    def __init__(self, 
                power_consumed: float, 
                power_supplied: float, 
                buffer_capacity: float,
                buffer_allocated: float,
                health: ComponentHealth, status: ComponentStatus) -> None:
        super().__init__(ComponentNames.RECEIVER.value, ReceiverComponent, power_consumed, power_supplied, health, status)
        self.buffer_capacity = buffer_capacity
        self.buffer_allocated = buffer_allocated

    def from_component(receiver: ReceiverComponent):
        return

class PlatformSim(Module):
    def __init__(self, parent_module : Module) -> None:
        super().__init__(EngineeringModuleParts.PLATFORM_SIMULATION.value, parent_module)
        """
        Simulates the agent's platform including all components and subsystems that comprise the agent.
        Can receive instructions via internal messages of type 'PlatformTaskMessage', 'SubsystemTaskMessage',
        or 'ComponentTaskMessage'.
        """
        
        # TODO create list of subsystems based on component list given to the platform
        self.submodules = [
            # CommandAndDataHandlingSubsystem(self)
            # GuidanceAndNavigationSubsystem(self),
            ElectricPowerSubsystem(self)
            # PayloadSubsystem(self),
            # CommsSubsystem(self, 1e6),
            # AttitudeDeterminationAndControlSubsystem(self)
        ]

    # TODO include internal state routing that kills the platform sim and the agent if a platform-level failure is detected    

    async def internal_message_handler(self, msg: InternalMessage):
        """
        Forwards any task to the command and data handling subsystem
        """
        try:
            dst_name = msg.dst_module
            if dst_name != self.name:
                # this module is NOT the intended receiver for this message. Forwarding to rightful destination
                await self.send_internal_message(msg)
            else:
                if isinstance(msg, PlatformTaskMessage) or isinstance(msg, SubsystemTaskMessage) or isinstance(msg, ComponentTaskMessage):
                    self.log(f'Received a tasks message. Forwarding to \'{SubsystemNames.CNDH.value}\' for handling.')
                    msg.dst_module = SubsystemNames.CNDH.value
                    await self.send_internal_message(msg)
                else:
                    # this module is the intended receiver for this message. Handling message
                    self.log(f'Internal messages with contents of type: {type(msg.content)} not yet supported. Discarting message.')

        except asyncio.CancelledError:
            return

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
class EngineeringModule(Module):
    def __init__(self, parent_agent : Module) -> None:
        super().__init__(AgentModuleTypes.ENGINEERING_MODULE.value, parent_agent, [], 1)
        self.submodules = [
            PlatformSim(self)
        ]

    async def internal_message_handler(self, msg: InternalMessage):
        """
        Forwards any task to the platform simulator
        """
        try:
            dst_name = msg.dst_module
            if dst_name != self.name:
                # this module is NOT the intended receiver for this message. Forwarding to rightful destination
                await self.send_internal_message(msg)
            else:
                if isinstance(msg, PlatformTaskMessage) or isinstance(msg, SubsystemTaskMessage) or isinstance(msg, ComponentTaskMessage):
                    self.log(f'Received a tasks message. Forwarding to \'{EngineeringModuleParts.PLATFORM_SIMULATION.value}\' for handling.')
                    msg.dst_module = EngineeringModuleParts.PLATFORM_SIMULATION.value
                    await self.send_internal_message(msg)
                else:
                    # this module is the intended receiver for this message. Handling message
                    self.log(f'Internal messages with contents of type: {type(msg.content)} not yet supported. Discarting message.')

        except asyncio.CancelledError:
            return

"""
--------------------
DEBUGGING MAIN
--------------------    
"""
# if __name__ == '__main__':
#     # print('Initializing agent...')
#     class PlanningModule(Module):
#         def __init__(self, parent_module : Module) -> None:
#             super().__init__(AgentModuleTypes.PLANNING_MODULE.value, parent_module)

#         # async def coroutines(self):
#         #     """
#         #     Routinely sends out a measurement task to the agent to perform every minute
#         #     """
#         #     try:
#         #         while True:
#         #             task = ObservationTask(0, 0, [InstrumentNames.TEST.value], [1])
#         #             msg = PlatformTaskMessage(self.name, AgentModuleTypes.ENGINEERING_MODULE.value, task)
#         #             await self.send_internal_message(msg)

#         #             await self.sim_wait(100)
#         #     except asyncio.CancelledError:
#         #         return

#     class ScienceModule(Module):
#         def __init__(self, parent_module : Module) -> None:
#             super().__init__(AgentModuleTypes.SCIENCE_MODULE.value, parent_module)

#     class TestAgent(AgentClient):    
#         def __init__(self, name, scenario_dir) -> None:
#             super().__init__(name, scenario_dir)
#             self.submodules = [
#                 EngineeringModule(self),
#                 ScienceModule(self),
#                 PlanningModule(self)
#                 ]  

#     print('Initializing agent...')
    
#     agent = TestAgent('Mars1', './scenarios/sim_test')
    
#     asyncio.run(agent.live())
    