from abc import abstractmethod
from asyncio import CancelledError
from typing import Union
import logging
import numpy as np
from messages import *
from utils import *
from modules import Module
from engineering import *

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
                f_update: float = 1,
                n_timed_coroutines: int = 0) -> None:
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
                self.log(f'Internal message of type {type(msg)} not yet supported. Discarding message...')
            
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
                self.log(f'Waiting for next update period...')
                await self.sim_wait(1/self.UPDATE_FREQUENCY)

                # update component state
                self.log(f'Performing periodic state update...')
                await self.update()
                self.log(f'Periodic state update completed!')

                if self.status is ComponentStatus.OFF:
                    # if component is turned off, wait until it is turned on
                    self.log(f'Component is off. Waiting until it is turned on again to restart periodic updates...')
                    await self.updated.wait()

                if self.health is ComponentHealth.FAILURE:
                    # else if component is in failure state, stop periodic updates and sleep for the rest of the simu
                    self.log(f'Component is in a failure state. Stopping periodic updates until the end of the simulation...')
                    break

                # inform parent subsystem of current state
                
                # if self.health is ComponentHealth.NOMINAL:
                #     self.log(f'Component state is nominal. Sharing state with parent subsystem.')
                #     state : ComponentState = await self.get_state()
                #     msg = ComponentStateMessage(self.name, self.parent_module.name, state)
                #     await self.send_internal_message(msg)                  
                
                # TODO: uncomment previous 5 lines and comment out the next 4 lines whenever crit and failure monitures are activated
                self.log(f'Sharing state with parent subsystem.')
                state : ComponentState = await self.get_state()
                msg = ComponentStateMessage(self.name, self.parent_module.name, state)
                await self.send_internal_message(msg) 
                self.log(f'Periodic update completed!')

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
                self.log(f'Starting execution of task of type {type(task)}! Updating component state...')
                self.log(f'{task}, {TaskStatus.IN_PROCESS.name}', logger_type=LoggerTypes.ACTIONS, level=logging.INFO)
                await self.update(crit_flag=False)

                # perform task 
                self.log(f'Component state updated! Performing task...')
                status : TaskStatus = await self.perform_maintenance_task(task)

                # update component state 
                self.log(f'Updating comopnent state...')
                await self.update()

                # inform parent subsystem of the status of completion of the task at hand
                self.log(f'Component state updated! Informing parent subsystem of task completion status: \'{status.name}\'...')
                msg = ComponentTaskCompletionMessage(self.name, self.parent_module.name, task, status)
                await self.send_internal_message(msg)

                # inform parent subsytem of the current component state
                state : ComponentState = await self.get_state()
                if state.health is ComponentHealth.NOMINAL:
                    self.log(f'Component state updated and health is {state.health.name}! Informing parent subsystem of component health...')
                    msg = ComponentStateMessage(self.name, self.parent_module.name, state)
                    await self.send_internal_message(msg)
                    self.log(f'Component state communicated to parent subsystem! Finished processing task of type {type(task)}!')
                else:
                    self.log(f'Component state updated! Finished processing task of type {type(task)}!')
                self.log(f'Performed task of type {type(task)}!', level=logging.DEBUG)

                # log task completion status
                self.log(f'{task}, {status.name}', logger_type=LoggerTypes.ACTIONS, level=logging.INFO)

        except asyncio.CancelledError:
            return

    async def perform_maintenance_task(self, task: ComponentMaintenanceTask) -> TaskStatus:
        """
        Performs a maintenance task given to this component. 
        Rejects any tasks that is not intended to be performed by this component. 
        """
        try:
            self.log(f'Starting task of type {type(task)}...')

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

                self.log(f'Awaiting to acquire state lock...')
                acquired = await self.state_lock.acquire()

                # actuate component
                if task.actuation_status is ComponentStatus.ON:
                    self.log(f'State lock acquired! Turning on component...')
                    if self.status is not ComponentStatus.ON:
                        # turn component on
                        self.status = ComponentStatus.ON
                        self.enabled.set()
                        self.disabled.clear()

                        # ask for power supply from eps
                        self.log(f'Component has been turned on and state lock has been released! Communicating increase of power draw to EPS...')
                        power_supply_task = PowerSupplyRequestTask(self.name, self.average_power_consumption)
                        msg = SubsystemTaskMessage(self.name, SubsystemNames.EPS.value, power_supply_task)
                        await self.send_internal_message(msg)
                        self.log(f'Increase of power draw communicated to EPS! Actuation task successfully performed!')
                    else:
                        # release state lock
                        self.state_lock.release()
                        acquired = None

                        self.log(f'Component is already on. Aborting task...')
                        raise asyncio.CancelledError  

                elif task.actuation_status is ComponentStatus.OFF:
                    self.log(f'State lock acquired! Turning off component...')
                    if self.status is not ComponentStatus.OFF:
                        # turn component off
                        self.status = ComponentStatus.OFF
                        self.enabled.clear()
                        self.disabled.set()

                        # ask for end of power supply from eps
                        self.log(f'Component has been turned off and state lock has been released! Communicating loss of power draw to EPS...')
                        stop_power_supply_task = PowerSupplyRequestTask(self.name, -self.average_power_consumption)
                        msg = SubsystemTaskMessage(self.name, SubsystemNames.EPS.value, stop_power_supply_task)
                        await self.send_internal_message(msg)
                        self.log(f'Loss of power draw communicated to EPS! Actuation task sucessfully performed!')
                    else:
                        # release state lock
                        self.state_lock.release()
                        acquired = None

                        self.log(f'Component is already off. Aborting task...')
                        raise asyncio.CancelledError    

                else:
                    # release state lock
                    self.state_lock.release()
                    acquired = None

                    self.log(f'Component Status {task.actuation_status} not supported for component actuation.')
                    raise asyncio.CancelledError

                # release state lock
                self.state_lock.release()
                acquired = None

                # return task completion status
                self.log(f'Component status set to {self.status.name}!')
                return TaskStatus.DONE

            elif isinstance(task, ReceivePowerTask):
                # obtain state lock
                self.log(f'Awaiting to acquire state lock...')
                acquired = await self.state_lock.acquire()

                # provide change in power supply
                self.log(f'State lock acquired! Changing power received by this component...')
                self.power_supplied += task.power_to_receive

                if self.power_supplied < 0:
                    self.power_supplied = 0

                # release state lock
                self.state_lock.release()
                acquired = None

                # return task completion status
                self.log(f'Component power supply successfully modified and state lock has been released! Component just received power supply of {self.power_supplied}!')
                return TaskStatus.DONE

            else:
                self.log(f'Task of type {type(task)} not yet supported.')
                acquired = None 
                raise asyncio.CancelledError

        except asyncio.CancelledError:
            self.log(f'Task of type {type(task)} was aborted.')

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
                self.log(f'{task}, {TaskStatus.IN_PROCESS.name}', logger_type=LoggerTypes.ACTIONS, level=logging.INFO)

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
                
                # get task completion status
                status : TaskStatus = perform_task.result()
                
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

                # log task completion
                self.log(f'{task}, {status.name}', logger_type=LoggerTypes.ACTIONS, level=logging.INFO)

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
        Any aborts targetted to other tasks are ignored but not discarded.
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
            self.log(f'State lock acquired! Getting current state...')


            # get state object from component status
            self.component_state : ComponentState
            state = self.component_state.from_component(self)

            # release update lock
            self.state_lock.release()
            acquired = None

            self.log(f'State obtained. State lock released.')
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
                n_timed_coroutines: int = 0) -> None:
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
        self.log(f'MSG TYPE: {type(msg)}')

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
                self.log(f'Received subsystem state message from subsystem type \'NONE\'!')
                subsystem_state : SubsystemState = msg.get_state()
                if subsystem_state is None:
                    self.log(f'Received subsystem state message from subsystem type \'NONE\'!')
                else:
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
                self.log(f'Internal message of type {type(msg)} not yet supported. Discarding message...')
            
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

                    if self.is_subsystem_critical():
                        self.log(f'Subsystem is in a subsystem-level critical state!')
                    elif self.is_component_critical():
                        self.log(f'Subsystem is in a component-level critical state!')
                    elif self.is_subsystem_failure():
                        self.log(f'Subsystem is in a subsystem-level failure state!')
                    elif self.is_component_failure():
                        self.log(f'Subsystem is in a component-level failure state!')

                    # set component health to critical
                    self.health = SubsystemHealth.CRITIAL

                    # trigger critical state event if it hasn't been triggered already
                    if self.is_subsystem_critical() and not self.critical.is_set():
                        self.critical.set()
                else:
                    self.log(f'Subsystem state is nominal!')

                    # set component health to nominal
                    self.health = SubsystemHealth.NOMINAL

                    # reset critical state event
                    if not self.critical.is_set():
                        self.critical.clear() 

                # release update lock
                self.state_lock.release()
                acquired = None

                # communicate to other processes that the subsystem's component states have been updated
                self.updated.set()
                self.updated.clear()
                self.log(f'Subsystem state has been updated!')

                # communicate to Command and data handling that the subsystem's state has been updated
                state = await self.get_state()
                msg = SubsystemStateMessage(self.name, SubsystemNames.CNDH.value, state)
                await self.send_internal_message(msg)

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

                            #await self.sim_wait(1/f_min) TODO readd this!!!

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

                self.log(f'Starting task of type: \'{type(task)}\'')
                self.log(f'{task}, {TaskStatus.IN_PROCESS.name}', logger_type=LoggerTypes.ACTIONS, level=logging.INFO)

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
                self.log(f'Subsystem state communicated! Finished processing task of type {type(task)}!')

                # log task completion status
                self.log(f'{task}, {status.name}', logger_type=LoggerTypes.ACTIONS, level=logging.INFO)

        except asyncio.CancelledError:
            for process in processes:
                process : asyncio.Task
                process.cancel()
                await process

    async def listen_for_abort(self, task: Union[PlatformTask, SubsystemTask, ComponentTask]) -> None:
        """
        Listens for any abort command targetted towards the task being performed.
        Any aborts targetted to other tasks are ignored but not discarded.
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
            self.log(f'Task of type {type(task)} was aborted.')
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
                    self.log(f'Completion status for target task received! Status for task of type {type(task)}: {status.value}')
                    break
                else:
                    self.log(f'Received a task completion status for another task. Waiting for task completion status response...')
                    resp.append( (resp_task, resp_status) )

            for resp_task, resp_status in resp:
                await self.recevied_task_status.put( (resp_task, resp_status) )

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
        """
        Creates a component state object from a component module object
        """
        pass

    def to_dict(self) -> dict:
        out = dict()
        out['@type'] = 'ComponentState'
        out['name'] = self.component_name
        out['power_consumed'] = self.power_consumed
        out['power_supplied'] = self.power_supplied
        out['health'] = self.health.name
        out['status'] = self.status.name

        return out

    def __str__(self) -> str:
        return json.dumps(self.to_dict())

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

    def to_dict(self) -> dict:
        out = dict()
        out['@type'] = 'SubsystemState'
        out['name'] = self.subsystem_name
        out['health'] = self.health.name
        out['status'] = self.status.name

        component_states = []
        for component in self.component_states:
            state : ComponentState = self.component_states[component]
            component_states.append(state.to_dict())
        out['component_states'] = component_states

        return out

    def __str__(self) -> str:
        return json.dumps(self.to_dict())

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

    async def activate(self):
        await super().activate()

        # instruct receiver to listen for transmissions
        task = ReceiveMessageTransmission()
        msg = ComponentTaskMessage(self.name, ComponentNames.RECEIVER.value, task)
        await self.send_internal_message(msg)

class CommsSubsystemState(SubsystemState):
    def __init__(self, component_states: dict, health: SubsystemHealth, status: SubsystemStatus):
        super().__init__(SubsystemNames.COMMS.value, CommsSubsystem, component_states, health, status)

    def from_subsystem(comms : CommsSubsystem):
        return CommsSubsystemState(comms.component_states, comms.health, comms.status)

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

                    t_msg = task.msg
                    t_msg_str = t_msg.to_json()
                    t_msg_length = len(t_msg_str.encode('utf-8'))

                    if self.buffer_allocated + t_msg_length <= self.buffer_capacity:
                        self.log(f'Acepted out-going transmission into buffer!')
                        self.tasks.put(task)
                        self.buffer_allocated += t_msg_length
                        self.log(f'Out-going message of length {t_msg_length} now stored in out-going buffer (current state: {self.buffer_allocated}/{self.buffer_capacity}).')
                    else:
                        self.log(f'Rejected out-going transmission into buffer.')
                        self.log(f'Out-going buffer cannot store out-going message of length {t_msg_length} (current state: {self.buffer_allocated}/{self.buffer_capacity}). Discarding message...')

                    self.state_lock.release()                   
            
            elif isinstance(msg.content, EnvironmentBroadcastMessage):
                self.log(f'Received an environment event of type {type(msg.content)}!')
                self.environment_events.put(msg.content)

            # elif isinstance(msg.content, InterNodeMessage):
            #     self.log(f'Received an internode message!',level=logging.INFO)
            #     task_msg = TransmitMessageTask(AgentModuleTypes.IRIDIUM_ENGINEERING_MODULE,msg,1.0)
            #     await self.tasks.put(task_msg)
            
            elif isinstance(msg.content, MeasurementRequest):
                self.log(f'Received a measurement request!',level=logging.DEBUG)
                inter_node_msg = InterNodeMeasurementRequestMessage(self,"Iridium",msg.content)
                task_msg = TransmitMessageTask("Iridium",inter_node_msg,1.0)
                await self.tasks.put(task_msg)

            elif isinstance(msg.content, InterNodeDownlinkMessage):
                self.log(f'Received a downlink message!',level=logging.DEBUG)
                task_msg = TransmitMessageTask("Iridium",msg.content,1.0)
                await self.tasks.put(task_msg)

            else:
                self.log(f'Internal message of type {type(msg)} not yet supported. Discarding message...')
            
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
                self.log(f'Component task not intended for this component. Initially intended for component \'{task.component}\'. Aborting task...',level=logging.DEBUG)
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
                #wait_for_access_start = asyncio.create_task( self.wait_for_access_start(msg.dst) )
                #await wait_for_access_start
                # wait for msg to be transmitted successfully or interrupted due to access end or message timeout
                transmit_msg = asyncio.create_task( self.transmit_message(msg) )
                #wait_for_access_end = asyncio.create_task( self.wait_for_access_end(msg.dst) )
                #wait_for_access_end_event = asyncio.create_task( self.access_events[msg.dst].wait_end() ) 
                #wait_for_message_timeout = asyncio.create_task( self.sim_wait(100.0) )
                processes = [transmit_msg] # TODO add waits back:  wait_for_access_end, wait_for_access_end_event

                _, pending = await asyncio.wait(processes, return_when=asyncio.FIRST_COMPLETED)
                
                # cancel all pending processes
                for pending_task in pending:
                    self.log(f'Cancelling pending processes!',level=logging.DEBUG)
                    pending_task : asyncio.Task
                    pending_task.cancel()
                self.log(f'Cancelled pending processes!',level=logging.DEBUG)
                # remove message from out-going buffer
                # await self.remove_msg_from_buffer(msg)
                # self.access_events.pop(msg.dst)

                # return task completion status                
                if transmit_msg.done() and transmit_msg not in pending:
                    self.log(f'Successfully transmitted message of type {type(msg)} to target \'{msg.dst}\'!', level=logging.DEBUG)                    
                    self.log(f'SENT, {msg}', logger_type=LoggerTypes.AGENT_TO_AGENT_MESSAGE, level=logging.INFO)
                    return TaskStatus.DONE

                # elif (wait_for_access_end.done() and wait_for_access_end not in pending) or (wait_for_access_end_event.done() and wait_for_access_end_event not in pending):
                #     self.log(f'Access to target \'{msg.dst}\' lost during transmission of message of type {type(msg)}!',level=logging.DEBUG)
                #     raise asyncio.CancelledError

                else:
                    self.log(f'Message of type {type(msg)} timed out!',level=logging.DEBUG)
                    raise asyncio.CancelledError

            else:
                self.log(f'Task of type {type(task)} not yet supported.',level=logging.DEBUG)
                acquired = None 
                raise asyncio.CancelledError

        except asyncio.CancelledError:
            self.log(f'Aborting task of type {type(task)}.',level=logging.DEBUG)

            # release update lock if cancelled during task handling
            if acquired:
                self.state_lock.release()

            # cancel any task that's not yet completed
            # if not wait_for_access_start.done():
            #     wait_for_access_start.cancel()
            #     await wait_for_access_start

            for process in processes:
                if process is not None and isinstance(process, asyncio.Task) and not process.done():
                    process.cancel()
                    await process

            # return task abort status
            return TaskStatus.ABORTED

    async def transmit_message(self, msg: InterNodeMessage):
        try:
            # reformat message
            msg.src = self.name
            msg_json = msg.to_json()
            parent_agent = self.get_top_module()
            # connect socket to destination 
            port = parent_agent.AGENT_TO_PORT_MAP[msg.dst]
            self.log(f'Connecting to agent {msg.dst} through port number {port}...',level=logging.DEBUG)
            parent_agent.agent_socket_out.connect(f"tcp://localhost:{port}")
            self.log(f'Connected to agent {msg.dst}!',level=logging.DEBUG)

            # submit request
            self.log(f'Transmitting a message of type {type(msg)} (from {self.name} to {msg.dst})...',level=logging.DEBUG)
            await parent_agent.agent_socket_out_lock.acquire()
            self.log(f'Acquired lock.',level=logging.DEBUG)
            await parent_agent.agent_socket_out.send_json(msg_json)
            self.log(f'{type(msg)} message sent successfully. Awaiting response...',level=logging.DEBUG)
                        
            # wait for server reply
            await parent_agent.agent_socket_out.recv_json()
            self.log(f'Received message reception confirmation!',level=logging.DEBUG)  
            parent_agent.agent_socket_out_lock.release()
            self.log(f'Released agent_socket_out',level=logging.DEBUG)      

            # disconnect socket from destination
            self.log(f'Disconnecting from agent {msg.dst}...',level=logging.DEBUG)
            parent_agent.agent_socket_out.disconnect(f"tcp://localhost:{port}")
            self.log(f'Disconnected from agent {msg.dst}!',level=logging.DEBUG)
        except asyncio.CancelledError:
            self.log(f'asyncio CancelledError in transmit_message',level=logging.DEBUG)
            parent_agent.agent_socket_out_lock.release()
            self.log(f'Released agent_socket_out lock.',level=logging.DEBUG)
            return


    # async def transmit_message(self, msg: InterNodeMessage):
    #     # reformat message
    #     msg.src = self.name
    #     msg_json = msg.to_json()

    #     # connect socket to destination 
    #     port = self.AGENT_TO_PORT_MAP[msg.dst]
    #     self.log(f'Connecting to agent {msg.dst} through port number {port}...')
    #     self.agent_socket_out.connect(f"tcp://localhost:{port}")
    #     self.log(f'Connected to agent {msg.dst}!')

    #     # submit request
    #     self.log(f'Transmitting a message of type {type(msg)} (from {self.name} to {msg.dst})...')
    #     await self.agent_socket_out_lock.acquire()
    #     await self.agent_socket_out.send_json(msg_json)
    #     self.log(f'{type(msg)} message sent successfully. Awaiting response...')
        
    #     # wait for server reply
    #     await self.agent_socket_out.recv()
    #     self.agent_socket_out_lock.release()
    #     self.log(f'Received message reception confirmation!')      

    #     # disconnect socket from destination
    #     self.log(f'Disconnecting from agent {msg.dst}...')
    #     self.agent_socket_out.disconnect(f"tcp://localhost:{port}")
    #     self.log(f'Disconnected from agent {msg.dst}!')

    async def remove_msg_from_buffer(self, msg : InterNodeMessage):
        try:
            self.log(f'Removing message from out-going buffer...',level=logging.DEBUG)
            acquired = await self.state_lock.acquire()

            msg_str = msg.to_json()
            msg_length = len(msg_str.encode('utf-8'))
            if self.buffer_allocated - msg_length >= 0:
                self.buffer_allocated -= msg_length
            else:
                self.buffer_allocated = 0
            self.log(f'Message sucessfully removed from buffer!',level=logging.DEBUG)

            self.state_lock.release()

        except asyncio.CancelledError:
            if acquired:
                self.state_lock.release()
    
    async def wait_for_access_start(self, target : str):
        try:
            msg = AgentAccessSenseMessage(self.get_top_module().name, target)

            response : AgentAccessSenseMessage = await self.submit_environment_message(msg)
            if response is None:
                raise asyncio.CancelledError
            while not response.result:
                await self.sim_wait(1/self.UPDATE_FREQUENCY)
                response : AgentAccessSenseMessage = await self.submit_environment_message(msg)
            self.log(f'Response {response} in wait_for_access_start in perform_task',level=logging.DEBUG)
            if target not in self.access_events:
                self.access_events[target] = EventPair()        

            self.access_events[target].trigger_start()
        except asyncio.CancelledError:
            return

    async def wait_for_access_end(self, target : str):
        try:
            msg = AgentAccessSenseMessage(self.get_top_module().name, target)

            response : AgentAccessSenseMessage = await self.submit_environment_message(msg)
            self.log(f'Response: {response}',level=logging.DEBUG)
            if response is None:
                self.log(f'Raising asyncio cancelled error',level=logging.DEBUG)
                raise asyncio.CancelledError
            self.log(f'After response is none if',level=logging.DEBUG)

            while response.result:
                await self.sim_wait(1/self.UPDATE_FREQUENCY)
                response : AgentAccessSenseMessage = await self.submit_environment_message(msg)

            if target not in self.access_events:
                self.access_events[target] = EventPair()
            self.access_events[target].trigger_end()

        except asyncio.CancelledError:
            self.log(f'In except handler in wait_for_access_end',level=logging.DEBUG)
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
        task = ReceiveMessageTransmission()
        await self.tasks.put(task)

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
            acquired = None
            agent_lock = None

            # check if component was the intended performer of this task
            if task.component != self.name:
                self.log(f'Component task not intended for this component. Initially intended for component \'{task.component}\'. Aborting task...')
                raise asyncio.CancelledError

            if isinstance(task, ReceiveMessageTransmission):
                self.log('Starting transmission reception task.')

                # gain access to incoming agent message port from parent agent
                parent_agent = self.get_top_module()
                agent_lock = await parent_agent.agent_socket_in_lock.acquire()
                self.log('Communication port acquired.')

                while True:
                    msg_dict = None

                    # listen for messages from other agents
                    self.log('Waiting for agent messages...',level=logging.DEBUG)
                    msg_json = await parent_agent.agent_socket_in.recv_json()
                    self.log(f'Agent message received!',level=logging.DEBUG)
                    blank = dict()
                    blank_json = json.dumps(blank)
                    await parent_agent.agent_socket_in.send_json(blank_json)
                    msg = InterNodeMessage.from_json(msg_json)
                    msg_dict = InterNodeMessage.to_dict(msg)
                    # check if message can fit in incoming buffer
                    msg_str = json.dumps(msg_dict)
                    msg_length = len(msg_str.encode('utf-8'))

                    acquired = await self.state_lock.acquire()
                    if self.buffer_allocated + msg_length <= self.buffer_capacity:
                        self.buffer_allocated += msg_length
                        self.log(f'Incoming message of length {msg_length} now stored in incoming buffer (current state: {self.buffer_allocated}/{self.buffer_capacity}).',level=logging.DEBUG)
                        self.state_lock.release()
                        acquired = None
                
                        # handle request
                        msg_type : InterNodeMessageTypes = InterNodeMessageTypes[msg_dict['@type']]

                        if msg_type is InterNodeMessageTypes.PRINT_MESSAGE:
                            # unpack message
                            msg : PrintMessage = PrintMessage.from_dict(msg_dict)
                            
                            # handle message 
                            self.log(f'Received print instruction: \'{msg.content}\'')

                        # elif msg_type is InterNodeMessageTypes.PLANNER_MESSAGE:
                        #     pass
                        elif msg_type is InterNodeMessageTypes.MEASUREMENT_REQUEST:
                            msg : InterNodeMessage = InterNodeMessage.from_dict(msg_dict)
                            msg_contents = json.loads(msg.content)["content"]
                            msg_contents = json.loads(msg_contents)
                            measurement_request = MeasurementRequest(msg_contents["_type"],msg_contents["_target"][0],msg_contents["_target"][1],msg_contents["_science_val"],msg_contents["metadata"])
                            req_msg = InternalMessage(self.name, AgentModuleTypes.PLANNING_MODULE.value, measurement_request)
                            self.log(f'Sending measurement request to planning module (hopefully)!',level=logging.DEBUG)
                            await self.send_internal_message(req_msg) # send measurement request to planning module
                        # elif msg_type is InterNodeMessageTypes.MEASUREMENT_MESSAGE:
                        #     pass
                        # elif msg_type is InterNodeMessageTypes.INFORMATION_REQUEST:
                        #     pass
                        # elif msg_type is InterNodeMessageTypes.INFORMATION_MESSAGE:
                        #     pass
                        elif msg_type is InterNodeMessageTypes.DOWNLINK:
                            self.log(f'Received downlink message!',level=logging.INFO)
                            msg : InterNodeDownlinkMessage = InterNodeDownlinkMessage.from_dict(msg_dict)
                            downlink_msg = InternalMessage(self.name, AgentModuleTypes.SCIENCE_MODULE.value, msg)
                            self.log(f'Sending downlink message to science module (hopefully)!',level=logging.DEBUG)
                            await self.send_internal_message(downlink_msg) # send measurement request to planning module
                        else:
                            msg = None
                            self.log(content=f'Internode message of type {msg_type.name} not yet supported. Discarding message...')

                        acquired = await self.state_lock.acquire()
                        self.buffer_allocated -= msg_length
                        self.log(f'Incoming message of length {msg_length} now stored in incoming buffer (current state: {self.buffer_allocated}/{self.buffer_capacity}).')
                        self.state_lock.release()
                        acquired = None

                        if msg is not None:
                            self.log(f'RECEIVED, {msg}', logger_type=LoggerTypes.AGENT_TO_AGENT_MESSAGE, level=logging.INFO)

                    else:
                        self.log(f'Incoming buffer cannot store incoming message of length {msg_length} (current state: {self.buffer_allocated}/{self.buffer_capacity}). Discarding message...')

            else:
                self.log(f'Task of type {type(task)} not yet supported.')
                raise asyncio.CancelledError

        except asyncio.CancelledError:
            self.log(f'Aborting task of type {type(task)}.')

            # release 
            if agent_lock:
                parent_agent.agent_socket_in_lock.release()

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
        return ReceiverState(receiver.power_consumed, receiver.power_supplied, receiver.buffer_capacity, receiver.buffer_allocated, receiver.health, receiver.status)

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
            CommsSubsystem(self, 1e6),
            PayloadSubsystem(self, 1e6)
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
                    self.log(f'Internal messages with contents of type: {type(msg.content)} not yet supported. Discarding message.')

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
class GroundEngineeringModule(Module):
    def __init__(self, parent_agent : Module) -> None:
        super().__init__(AgentModuleTypes.GROUND_ENGINEERING_MODULE.value, parent_agent, [], 1)
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
                    self.log(f'Internal messages with contents of type: {type(msg.content)} not yet supported. Discarding message.')

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
    