import logging
import time
import asyncio

from dmas.network import *
from dmas.utils import *
from dmas.messages import *

class SimulationElementStatus(Enum):
    INIT = 'INITIALIZED'
    ACTIVATED = 'ACTIVATED'
    RUNNING = 'RUNNING'
    DEACTIVATED = 'DEACTIVATED'

class SimulationElement(NetworkElement):
    """
    ## Abstract Simulation Element 

    Base class for all simulation elements. This including all agents, environments, simulation managers, and simulation monitors.

    ### Attributes:
        - _status (`Enum`) : Status of the element within the simulation
        - _logger (`Logger`): debug logger
        - _clock_config (:obj:`ClockConfig`): description of this simulation's clock configuration

    +--------------------+                                                                                          
    |   SIM ELEMENTS     |                                                                                          
    +--------------------+                                                                                          
              ^                                                                                                     
              |                                                                                                     
              v                                                                                                     
    +--------------------+                                                                                          
    |   External Ports   |                                                                                          
    |--------------------|                                                                                          
    |ABSTRACT SIM ELEMENT|                                                                                          
    |--------------------|                                                                                          
    |   Internal Ports   |                                                                                          
    +--------------------+                                                                                          
              ^                                                                                                     
              |                                                                                                     
              v                                                                                                     
    +--------------------+                                                                                          
    | INTERNAL PROCESSES |                                                                                          
    +--------------------+   
    """
    __doc__ += NetworkElement.__doc__       
    def __init__(   self, 
                    element_name : str, 
                    element_network_config : NetworkConfig, 
                    level : int = logging.INFO, 
                    logger : logging.Logger = None) -> None:
        """
        Initiates a new simulation element

        ### Args:
            - network_name (`str`): The name of the network that the element belongs to
            - element_name (`str`): The element's name
            - network_config (:obj:`NetworkConfig`): description of the addresses pointing to this simulation element
            - level (`int`): logging level for this simulation element. Level set to INFO by defauly
            - logger (`logging.Logger`) : logger for this simulation element. If none is given, a new one will be generated
        """
        super().__init__(element_name, element_network_config, level, logger)
        self._status = SimulationElementStatus.INIT
        self._clock_config : ClockConfig = None     

    """
    ELEMENT OPERATION METHODS
    """
    def run(self) -> int:
        """
        Main function. Executes this similation element.

        Returns `1` if excecuted successfully or if `0` otherwise
        """
        try:
            return asyncio.run(self._run_routine())

        except Exception as e:
            self.log(f'`run()` interrupted. {e}')
            raise e

    async def _run_routine(self) -> None:
        """
        Asynchronous procedure that follows the sequence:
        1. `activate()`
        2. `execute()`
        3. `deactivate()`
        """
        try:
            # activate simulation element
            self.log('activating...', level=logging.INFO)
            await self._activate()

            ## update status to ACTIVATED
            self._status = SimulationElementStatus.ACTIVATED
            self.log('activated! Waiting for simulation to start...', level=logging.INFO)

            # wait for simulatio nstart
            await self._wait_sim_start()
            self.log('simulation has started!', level=logging.INFO)

            ## update status to RUNNING
            self._status = SimulationElementStatus.RUNNING

            ## register simulation runtime start
            self._clock_config.set_simulation_runtime_start( time.perf_counter() )

            # start element life
            self.log('executing...', level=logging.INFO)
            await self._execute()
            self.log('execution completed!', level=logging.INFO)
            
            self.log('`run()` executed properly.')
            return 1

        finally:
            # deactivate element
            self.log('deactivating...', level=logging.INFO)
            await self._deactivate()
            self.log('deactivation completed!', level=logging.INFO)

            # update status to DEACTIVATED
            self._status = SimulationElementStatus.DEACTIVATED

            #reguster simulation runtime end
            self._clock_config.set_simulation_runtime_end( time.perf_counter() )
        

    async def _activate(self) -> None:
        """
        Initiates and executes commands that are thread-sensitive but that must be performed before the simulation starts.
        By default it only initializes network connectivity of the element.

        May be expanded if more capabilities are needed.
        """
        # inititate base network connections 
        self.log(f'configuring network...')
        self._network_context, self._manager_socket_map, self._external_socket_map, self._internal_socket_map = self._config_network()
        self.log(f'NETWORK CONFIGURED!')

        # check for correct socket initialization
        if self._external_socket_map is None:
            raise AttributeError(f'{self.name}: Inter-element communication sockets not activated during activation.')

        # synchronize with other elements in the simulation or internal modules
        self.log('Syncing network...')
        self._clock_config, self._external_address_ledger, self._internal_address_ledger = await self._network_sync()     
        self.log('NETWORK SYNCED!')

        # check for correct element activation
        if self._clock_config is None:
            raise RuntimeError(f'{self.name}: Clock config not received during activation.')

        elif self._external_address_ledger is None:
            raise RuntimeError(f'{self.name}: External address ledger not received during activation.')

        # perform user-defined setup method
        await self.setup()

    async def _network_sync(self) -> tuple:
        """
        Awaits for all other simulation elements to undergo their initialization and activation routines and become online. 
        
        Elements will then reach out to the manager subscribe to future broadcasts.

        The manager will use these incoming messages to create a ledger mapping simulation elements to their assigned ports
        and broadcast it to all memebers of the simulation once they all become online. 

        This will signal the beginning of the simulation.

        #### Returns:
            - `tuple` of a `ClockConfig` describing the simulation clock to be used and two `dict` mapping simulation 
                elements' names to the addresses pointing to their respective connecting ports    
        """
        try:
            # sync external network
            external_sync_task = asyncio.create_task(self._external_sync(), name='External Sync Task')
            timeout_task = asyncio.create_task( asyncio.sleep(10) , name='Timeout Task')
            
            await asyncio.wait([external_sync_task, timeout_task], return_when=asyncio.FIRST_COMPLETED)
            
            if timeout_task.done():
                external_sync_task.cancel()
                await external_sync_task
                raise TimeoutError('Sync with external network elements timed out.')

            clock_config, external_address_ledger = external_sync_task.result()

            # sync internal network
            internal_sync_task = asyncio.create_task(self._internal_sync(clock_config), name='Internal Sync Task')

            await asyncio.wait([internal_sync_task, timeout_task], return_when=asyncio.FIRST_COMPLETED)
                            
            if timeout_task.done():
                internal_sync_task.cancel()
                await internal_sync_task
                raise TimeoutError('Sync with internal network elements timed out.')          

            # return external and internal address ledgers
            internal_address_ledger = internal_sync_task.result()

            return (clock_config, external_address_ledger, internal_address_ledger)             
            
        except Exception as e:
            self.log(f'Sync aborted. {e}')
            
            # cancel sync subroutine
            if not external_sync_task.done():
                external_sync_task.cancel()
                await external_sync_task

            if not external_sync_task.done():
                external_sync_task.  cancel()
                await external_sync_task

            raise e

    @abstractmethod
    async def _external_sync(self) -> tuple:
        """
        Synchronizes with other simulation elements

        #### Returns:
            - `ClockConfig` discribing the clock to be used in the simulation 
            - `dict` mapping simulation elements' names to the addresses pointing to their respective connecting ports    
        """
        pass

    @abstractmethod
    async def _internal_sync(self, clock_config : ClockConfig) -> dict:
        """
        Synchronizes with this element's internal components

        #### Arguments:
            - `clock_config` (:obj:`ClockConfig`): clock configuration to be shared with internal processes

        #### Returns:
            - `dict` mapping a simulation element's components' names to the addresses pointing to their respective connecting ports
        """
        pass

    @abstractmethod
    async def setup(self) -> None:
        """
        Performs user-defined set up instructions to be done before the simulation is started.

        Nothing is done by default but functionality may be expanded by the user.
        """
        return

    @abstractmethod
    async def _wait_sim_start(self) -> None:
        """
        Waits for the simulation to start
        """
        pass

    @abstractmethod
    async def _execute(self) -> None:
        """
        Procedure to be executed by the simulation element during the simulation. 

        Element will deactivate if this method returns.
        """
        pass

    @abstractmethod
    async def teardown(self) -> None:
        """
        Performs user-defined tear-down instructions to be performed after the simulation has been terminated.

        Nothing is done by default but functionality may be expanded by the user.
        """
        return
    
    async def _deactivate(self) -> None:
        """
        Shut down procedure for this simulation entity. 
        """
        # inform others of deactivation
        if self._external_socket_map is not None:
            await self._publish_deactivate()

        # perform tear-down procedure
        await self.teardown()


    @abstractmethod
    async def sim_wait(self, delay : float) -> None:
        """
        Simulation element waits for a given delay to occur according to the clock configuration being used

        ### Arguments:
            - delay (`float`): number of seconds to be waited
        """
        pass
