from abc import abstractmethod
import asyncio
from ctypes import Union
import logging
from messages import *
from utils import *
from modules import Module

"""
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
"""
class ComponentStatus(Enum):
    NOMINAL = 'NOMINAL'
    DISABLED = 'DISABLED'
    CRITIAL = 'CRITICAL'
    FAILURE = 'FAILURE'

class ComponentModule(Module):
    def __init__(self, name: str,  
                f_update: float, 
                average_power_usage: Union[int, float], 
                parent_subsystem: str, 
                n_timed_coroutines: int,
                status : ComponentStatus = ComponentStatus.DISABLED) -> None:
        """
        Describes a generic component of an agent's platform.
        """
        super().__init__(name, parent_subsystem, [], n_timed_coroutines)
        self.average_power_usage = average_power_usage
        self.F_UPDATE = f_update
        self.t_update = 0
        self.status = status

    async def activate(self):
        await super().activate()

        # state status events
        self.nominal = asyncio.Event()
        self.disabled = asyncio.Event()
        self.critical = asyncio.Event()
        self.failure = asyncio.Event()
        self.updated = asyncio.Event()

        # trigger state events
        if self.status is ComponentStatus.NOMINAL:
            self.nominal.set()
        elif self.status is ComponentStatus.DISABLED:
            self.disabled.set()
        elif self.status is ComponentStatus.CRITIAL:
            self.critical.set()
        elif self.status is ComponentStatus.FAILURE:
            self.failure.set()

        # initiate update time
        self.t_update: Union[int, float] = self.get_current_time()

        # initiate component properties
        await self.activate_properties()

        # log last update time
        self.t_update = self.get_current_time()

        # update state
        self.update_lock = asyncio.Lock()

    async def activate_properties(self):
        """
        Activates event-loop-sensitive component properties such as containers and indicators.
        Base case only initiates power used by and power being fed to the component.
        """
        self.power_usage = Container(level=0, capacity=self.average_power_usage)
        self.power_in = Container()
        self.dp = Container(level=self.power_in.level - self.power_usage.level)

    """
    --------------------
    TASKS HANDLER
    --------------------
    """

    async def internal_message_handler(self, msg: InternalMessage):
        """
        Performs instructions given to the component
        """
        try:
            dst_name = msg.dst_module
            if dst_name != self.name:
                # this module is NOT the intended receiver for this message. Forwarding to rightful destination
                await self.send_internal_message(msg)
            elif not isinstance(msg, ComponentInstructionMessage):
                self.log(f'Received internal messages of type {type(content)} and not of type {type(InternalMessage)}. Discarting message.')
            else:
                # this module is the intended receiver for this message. Handling message
                content = msg.content
                if not isinstance(content, ComponentInstruction):
                    text = content.text_to_print
                    self.log(text)    
                else:
                    self.log(f'Internal messages with contents of type: {type(content)} not yet supported. Discarting message.')
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

    @abstractmethod
    async def periodic_update(self):
        """
        Performs periodic update of the component's state
        """
        try:
            dt = 1/self.SIMULATION_FREQUENCY
            await self.sim_wait(dt)
            await self.update()

        except asyncio.CancelledError:
            return

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
            await self.dp.set_level(self.power_in.level - self.power_usage.level)
        except asyncio.CancelledError:
            return

    async def get_state(self):
        """
        Returns a state class object capturing the current state of this component 
        """
        # wait for any possible update process to finish
        await self.update_lock.acquire()

        # get state object from component status
        state = ComponentState.from_component(self)

        # release update lock
        self.update_lock.release()

        return state

class ComponentState:
    def __init__(self, name: str, component_type: type,
                power_in: float, power_consumed: float, power_generated: float, energy_stored: float, energy_capacity: float,
                data_rate_in: float, data_rate_generated: float, data_stored: float, data_capacity: float, 
                status: ComponentStatus) -> None:

        # component info
        self.component_name = name
        self.component_type = component_type

        # power state
        self.power_in = power_in
        self.power_consumed = power_consumed
        self.power_generated = power_generated
        self.energy_stored = energy_stored
        self.energy_capacity = energy_capacity

        # data state 
        self.data_rate_in = data_rate_in
        self.data_rate_generated = data_rate_generated
        self.data_stored = data_stored
        self.data_capacity = data_capacity

        # component status
        self.status = status

    def from_component(component : ComponentModule):
        pass

# class Battery(Component):
#     def __init__(self, name, max_power_generation, power_storage_capacity, parent_subsystem) -> None:
#         super().__init__(name, 0, max_power_generation, power_storage_capacity, 0, 0, parent_subsystem, n_timed_coroutines=1)

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