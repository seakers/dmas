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