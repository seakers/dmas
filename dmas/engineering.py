from abc import abstractmethod
import asyncio
from ctypes import Union
import logging
from telnetlib import XASCII
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
                f_update: float, 
                component_state : type, 
                average_power_consumption: float, 
                health : ComponentHealth = ComponentHealth.NOMINAL,
                status : ComponentStatus = ComponentStatus.DISABLED,
                n_timed_coroutines: int = 3) -> None:
        """
        Describes a generic component of an agent's platform.

        name:
            name of the component
        parent_subsystem:
            subsystem that this component belongs to
        f_update:
            frequency of periodic state checks
        component_state:
            type of component state describing this component's state
        average_power_consumption:
            average power consumption in [W]
        health:
            health of the component
        status:
            status of the component
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

        # component state events
        self.nominal = asyncio.Event() 
        self.critical = asyncio.Event()
        self.failure = asyncio.Event()

        self.enabled = asyncio.Event()       
        self.disabled = asyncio.Event()

        self.updated = asyncio.Event()

        # trigger state events
        if self.health is ComponentHealth.NOMINAL:
            self.nominal.set()
        elif self.health is ComponentHealth.CRITIAL:
            self.critical.set()
        elif self.health is ComponentHealth.FAILURE:
            self.failure.set()

        if self.status is ComponentStatus.ENABLED:
            self.enabled.set()
        elif self.status is ComponentStatus.DISABLED:
            self.disabled.set()

        # initiate update time
        self.t_update : float = self.get_current_time()

        # initiate component properties
        await self.activate_properties()

        # log last update time
        self.t_update = self.get_current_time()

        # update state
        self.update_lock = asyncio.Lock()
        await self.update()        

    """
    --------------------
    TASKS HANDLER
    --------------------
    """

    async def internal_message_handler(self, msg: InternalMessage):
        """
        Processes messages being sent to this component
        May be overriden to expand capabilities.
        """
        try:
            if self.failure.is_set():
                self.log(f'Component is in failure state. Ignoring message...')
                return
                # TODO add capability to recover component by performing some troubleshooting tasks being given to this component

            if msg.dst_module != self.name:
                # this module is NOT the intended receiver for this message. Forwarding to rightful destination
                self.log(f'Received internal message intended for {msg.dst_module}. Rerouting message...')
                await self.send_internal_message(msg)

            elif isinstance(msg, ComponentTaskMessage):
                # unpackage component task
                self.log(f'Received Component Task message from \'{msg.src_module}\'!')
                task = msg.get_task()
                task_process = asyncio.create_task(self.perform_component_task(task))
                conditions = [self.failure, task_process]

                # perform instruction              
                _, pending = await asyncio.wait(conditions, asyncio.FIRST_COMPLETED)

                if self.failure in pending:
                    # task completed
                    task_status = TaskStatus.DONE
                else:
                    # failure state detected before task was completed, aborting task
                    task_process.cancel()
                    await task_process
                    task_status = TaskStatus.ABORTED
                task.set_status(task_status)

                # communicate instruction status to instructor module 
                self.log(f'Sending task performance message to \'{msg.src_module}\' with task status \'{task_status}\'.')
                msg_resp = ComponentTaskMessage(self.name, msg.src_module, task)
                await self.send_internal_message(msg_resp)

            else:
                self.log(f'Internal message of type {type(msg)} not yet supported. Discarting message...')
            
        except asyncio.CancelledError:
            return

    async def perform_component_task(self, task: ComponentTask) -> TaskStatus:
        """
        Handles the performance of a task given to this component. 
        Rejects any tasks not supported by this function. 
        May be overriden to expand capabilities.
        """
        try:
            # update component state
            self.log(f'Starting task of type {type(task)}...')
            await self.update()

            # check if component was the intended performer of this task
            if task.component != self.name:
                self.log(f'Component task not intended for this component. Initially intended for component \'{task.component}\'. Aborting task...')
                raise asyncio.CancelledError

            # perform task
            if isinstance(task, ComponentActuationTask):                
                if task.component_status:
                    self.status = ComponentStatus.ENABLED
                else:
                    self.status = ComponentStatus.DISABLED
                self.log(f'Component status set to {self.status.name}!')

            elif isinstance(task, ComponentPowerSupplyTask):
                await self.power_supplied.set_level(task.power_suppied)
                self.log(f'Received power supply of {task.power_suppied}!')
            else:
                self.log(f'Task of type {type(task)} not yet supported. Aborting task...')
                raise asyncio.CancelledError

            # update component state 
            self.log(f'Task of type {type(task)} successfully completed!')
            await self.update()

        except asyncio.CancelledError:
            self.log(f'Task of type {type(task)} aborted!')
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

        2- Predicting and detecting critical states

        3- Triggering failure states
        
        Component failure leads to no actions being able to be performed by this 
        component. Subsystem-wide failure is to be handled by their parent subsystem.
        """

        # create coroutine tasks
        coroutines = []

        ## Internal coroutines
        periodic_update = asyncio.create_task(self.periodic_update())
        periodic_update.set_name (f'{self.name}_periodic_update')
        coroutines.append(periodic_update)
        
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

    async def periodic_update(self):
        """
        Performs periodic update of the component's state
        """
        try:
            while not self.failure.is_set():
                await self.update()
                dt = 1/self.UPDATE_FREQUENCY
                await self.sim_wait(dt)
            while True:
                await self.sim_wait(1e6)

        except asyncio.CancelledError:
            return

    async def crit_monitor(self) -> None:
        """
        Monitors component state and triggers critical event if a critical state is detected
        """
        try:
            while True:
                # check if failure event was triggered
                if self.failure.is_set():
                    # if comonent is in failure state, sleep
                    await self.sim_wait(1e6)
                
                else:
                    if self.is_critical():
                        # component is in a critical state

                        # erease critical timer object
                        critical_timer = None

                        # set current status to critical
                        if not self.failure.is_set():
                            self.health = ComponentHealth.CRITIAL

                        # trigger critical state event if it hasn't been triggered already
                        if not self.critical.is_set():
                            self.critical.set()

                        # communicate critical state to parent submodule
                        state_msg = ComponentStateMessage(self.name, self.parent_module.name, self.get_state())
                        await self.send_internal_message(state_msg)
                        
                        # wait for component to be updated
                        await self.updated  

                    else:
                        # component is NOT in a critical state

                        # reset critical event if it has been previously triggered
                        if self.critical.is_set():
                            self.critical.clear()

                        # set internal state to nominal if not in a failure nor critical state
                        if not self.failure.is_set():
                            self.health = ComponentHealth.NOMINAL

                        # initiate critical state timer
                        critical_timer = asyncio.create_task(self.wait_for_critical())
                        critical_timer.set_name (f'{self.name}_critical_timer')
                        
                        # wait for the critical timer to run out or for the component to update its state
                        conditions = [self.updated, critical_timer]
                        _, pending = await asyncio.wait(conditions, return_when=asyncio.FIRST_COMPLETED)

                        if self.updated in pending:                 # critical timer ran out before agent updated its state                      
                            await self.update()
                            while not self.is_critical():
                                # if not critical, check periodically until critical state is detected
                                await self.sim_wait(1/self.UPDATE_FREQUENCY)                      
                                await self.update()
                        else:                                       # component updated its state before critical timer ran out
                            # interrupt critical timer and check again
                            critical_timer.cancel()
                            await critical_timer

        except asyncio.CancelledError:
            if critical_timer is not None:
                critical_timer.cancel()
                await critical_timer

    def is_critical(self) -> bool:
        """
        Returns true if the current state of the component is critical. 
        """
        return False

    async def wait_for_critical(self) -> None:
        """
        Count downs to the next predicted critical state of this component given that the current configuration is maintained
        """
        try:
            while True:
                await self.sim_wait(1e6)
        except asyncio.CancelledError:
            return

    async def failure_monitor(self):
        """
        Monitors component state and triggers failure event if a failure state is detected
        """
        try:
            while True: 
                if self.health is ComponentHealth.FAILURE:
                    # if comonent is in failure state, sleep
                    await self.sim_wait(1e6)

                else:
                    # check if in failure state
                    if self.is_failed():
                        # possible failure state detected

                        # erease failure timer object
                        failure_timer = None

                        # set current status to critical
                        self.health = ComponentHealth.CRITIAL
                            
                        # communicate CRITICAL state to parent submodule
                        state_msg = ComponentStateMessage(self.name, self.parent_module.name, self.get_state())
                        await self.send_internal_message(state_msg)

                        # allow for component to react to possible failure state
                        await self.sim_wait(1/self.UPDATE_FREQUENCY)
                        
                        # check if component avoided failure state
                        if self.is_failed():
                            # component is still in a possible failure state 

                            # set current status to failure
                            self.health = ComponentHealth.FAILURE

                            # communicate FAILURE state to parent submodule only if it hasn't been communicated already
                            state_msg = ComponentStateMessage(self.name, self.parent_module.name, self.get_state())
                            await self.send_internal_message(state_msg)

                            # trigger failure state event
                            self.failure.set()

                    else:
                        # reset failure event if it has been previously triggered
                        if self.failure.is_set():
                            self.failure.clear()

                        # set internal state to nominal if not in a failure nor critical state
                        if not self.critical.is_set():
                            self.health = ComponentHealth.NOMINAL

                        # initiate failure state timer
                        failure_timer = asyncio.create_task(self.wait_for_failure())
                        failure_timer.set_name (f'{self.name}_failure_timer')
                        
                        # wait for the failure timer to run out or for the component to update its state
                        conditions = [self.updated, failure_timer]
                        done, _ = await asyncio.wait(conditions, return_when=asyncio.FIRST_COMPLETED)

                        if failure_timer in done:                   
                            # failure timer ran out before agent updated its state
                            await self.update()
                            while not self.is_failed():
                                # if not failed yet, check periodically until failure state is detected
                                await self.sim_wait(1/self.UPDATE_FREQUENCY)     
                                await self.update()
                        else:                                      
                             # component updated its state before critical timer ran out
                             
                            # interrupt critical timer and check again
                            failure_timer.cancel()
                            await failure_timer

        except asyncio.CancelledError:
            return

    def is_failed(self) -> bool:
        """
        Returns true if the current state of the component is a failure state
        """
        return abs( self.power_consumed - self.power_supplied ) >= 1e-6

    async def wait_for_failure(self) -> None:
        """
        Count downs to the next predicted failure state of this component given that the current configuration is maintained
        """
        try:
            while True:
                await self.sim_wait(1e6)
        except asyncio.CancelledError:
            return

    """
    --------------------
    HELPING FUNCTIONS
    --------------------
    """
    async def update(self):
        """
        Updates the state of the component
        """
        try:
            # process indicators
            acquired = False
            update_task = None

            # wait for any possible state accessing process to finish
            await self.update_lock.acquire()
            acquired = True

            # calculate update time-step
            t_curr = self.get_current_time()
            dt = t_curr - self.t_update

            # update component properties
            update_task = asyncio.create_task(self.update_properties(dt))
            await update_task

            # update latest update time
            self.t_update = t_curr  

            # inform other processes that the update has finished
            self.updated.set()
            self.updated.clear()
            self.update_lock.release() 

        except asyncio.CancelledError:
            if update_task is not None:
                if not update_task.done():
                    # Update cancelled before update process finished. Cancelling process
                    update_task.cancel()
                    await update_task
            
                else:
                    # if property update was finished, then finish update process
                    # update latest update time
                    self.t_update = t_curr  

                    # inform other processes that the update has finished
                    self.updated.set()
                    self.updated.clear()

            if self.update_lock.locked() and acquired:
                # if this process had acquired the update_lock and has not released it, then release
                self.update_lock.release()               

    async def update_properties(self, dt):
        """
        Updates the current state of the component given a time-step dt
        """
        try:
            # update power consumption and power differential tracker
            if self.status is ComponentStatus.ENABLED:
                await self.power_consumed.set_level(self.average_power_consumption)
            else:
                await self.power_consumed.set_level(0)
            self.dp = self.power_supplied.level - self.power_consumed.level

            # log state
            self.log_state()
        except asyncio.CancelledError:
            return

    async def get_state(self):
        """
        Returns a state class object capturing the current state of this component 
        """
        try:
            # process indicators
            acquired = False

            # wait for any possible update process to finish
            await self.update_lock.acquire()
            acquired = True

            # get state object from component status
            state = self.component_state.from_component(self)

            # release update lock
            self.update_lock.release()

            return state
        except asyncio.CancelledError:
            if self.update_lock.locked() and acquired:
                # if this process had acquired the update_lock and has not released it, then release
                self.update_lock.release()


    def log_state(self) -> None:
        return self.parent_module.log_state()

"""
-------------------------------
CCOMPONENT STATES
-------------------------------
"""
class ComponentState:
    def __init__(self, name: str, component_type: type, power_consumed : float, power_supplied : float, health: ComponentHealth, status : ComponentStatus) -> None:
        """
        Describes the state of a generic component. Each component type must have its own component state class if it contains more parameters that 
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

    def from_component(component : ComponentModule):
        pass

"""
-------------------------------
SUBSYSTEM MODULES
-------------------------------
"""
class SubsystemModule(Module):
    def __init__(self, name, parent_module) -> None:
        super().__init__(name, parent_module, [], n_timed_coroutines=1)
        self.submodules = []

"""
GNC SUBSYTEM
"""
class GPSModule(ComponentModule):
    def __init__(self, f_update: float, 
                parent_subsystem: Module, 
                average_power_consumption: float, 
                health: ComponentHealth = ComponentHealth.NOMINAL, 
                n_timed_coroutines: int = 3) -> None:
        super().__init__(ComponentNames.GPS, parent_subsystem, f_update, GPSState, average_power_consumption, health, ComponentStatus.ENABLED, n_timed_coroutines)
        self.pos = [None, None, None]
        self.vel = [None, None, None]

    async def update_properties(self, dt) -> None:
        await super().update_properties(dt)
        # sense environment for position and velocity data
        src = self.get_top_module()
        msg = AgentSenseMessage(src.name)

        self.log(f'Sensing environment for position and velocity data.')
        response : AgentSenseMessage = await self.submit_environment_message(msg)
        self.log(f'Current state: pos:{response.pos}, vel=[{response.vel}]')

        self.pos = []
        for x_i in response.pos:
            self.pos.append(x_i)

        self.vel = []
        for v_i in response.vel:
            self.vel.append(v_i)

class SunSensorModule(ComponentModule):
    def __init__(self, f_update: float, 
                parent_subsystem: Module, 
                average_power_consumption: float, 
                health: ComponentHealth = ComponentHealth.NOMINAL, 
                n_timed_coroutines: int = 3) -> None:
        super().__init__(ComponentNames.IMU, parent_subsystem, f_update, SunSensorState, average_power_consumption, health, ComponentStatus.ENABLED, n_timed_coroutines)
        self.sun_vector = [None, None, None]   
        self.eclipse = None

    async def update_properties(self, dt) -> None:
        await super().update_properties(dt)
        # sense environment for position and velocity data
        src = self.get_top_module()
        msg = AgentSenseMessage(src.name)

        self.log(f'Sensing environment for position and velocity data.')
        response : AgentSenseMessage = await self.submit_environment_message(msg)
        self.log(f'Current state: eclipse:{response.eclipse}]')

        self.eclipse = response.eclipse

class GPSState(ComponentState):
    def __init__(self, 
                    component_type: type,
                    power_consumed: float, 
                    power_supplied: float, 
                    pos : list,
                    vel : list,
                    health: ComponentHealth, 
                    status: ComponentStatus) -> None:
        super().__init__(ComponentNames.GPS.value, component_type, power_consumed, power_supplied, health, status)
        self.pos = []
        for x_i in pos:
            self.pos.append(x_i)

        self.vel = []
        for v_i in vel:
            self.vel.append(v_i)

    def from_component(component : GPSModule):
        return GPSState(type(component), component.power_consumed.level, component.power_supplied.level, component.pos, component.vel, component.health, component.status)

class SunSensorState(ComponentState):
    def __init__(self, 
                    component_type: type,
                    power_consumed: float, 
                    power_supplied: float, 
                    pos : list,
                    vel : list,
                    health: ComponentHealth, 
                    status: ComponentStatus) -> None:
        super().__init__(ComponentNames.GPS.value, component_type, power_consumed, power_supplied, health, status)
        self.pos = []
        for x_i in pos:
            self.pos.append(x_i)

        self.vel = []
        for v_i in vel:
            self.vel.append(v_i)

    def from_component(component : GPSModule):
        return GPSState(type(component), component.power_consumed.level, component.power_supplied.level, component.pos, component.vel, component.health, component.status)

"""
EPS SUBSYSTEM
"""

# class Battery(Component):
#     def __init__(self, name, max_power_generation, power_storage_capacity, parent_subsystem) -> None:
#         super().__init__(name, 0, max_power_generation, power_storage_capacity, 0, 0, parent_subsystem, n_timed_coroutines=1)

"""
PAYLAOD SUBSYSTEM
"""
# class Instrument(ComponentModule):
#     def __init__(self, name: str, f_update: float, 
#                 average_power_usage: Union[int, float], 
#                 data_rate: Union[int, float], 
#                 data_buffer_capacity: Union[int, float], 
#                 parent_subsystem: str, n_timed_coroutines: int, 
#                 status: ComponentHealth = ComponentHealth.DISABLED) -> None:
#         super().__init__(name, f_update, average_power_usage, parent_subsystem, n_timed_coroutines, status)
#         # self.


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
    def __init__(self, name, parent_module=None, submodules=..., n_timed_coroutines=1) -> None:
        super().__init__(name, parent_module, submodules, n_timed_coroutines)


"""
--------------------
DEBUGGING MAIN
--------------------    
"""
if __name__ == '__main__':
    # print('Initializing agent...')
    class C:
        def __init__(self) -> None:
            pass

        def from_x(x):
            return C
    
    class Test:
        def __init__(self, x, y) -> None:
            self.x = x
            self.t = y.from_x(x)

    a = Test(1, C)
    print(a.x)
    print(type(a.t))
    