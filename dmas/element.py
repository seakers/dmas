from abc import ABC, abstractmethod
import logging
from multiprocessing import Queue
import socket
import time
import zmq
import zmq.asyncio as azmq
import asyncio

from dmas.network import NetworkElement
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

    def __init__(self, name : str, network_config : NetworkConfig, level : int = logging.INFO, logger : logging.Logger = None) -> None:
        """
        Initiates a new simulation element

        ### Args:
            - name (`str`): The element's name
            - network_config (:obj:`NetworkConfig`): description of the addresses pointing to this simulation element
            - level (`int`): logging level for this simulation element. Level set to INFO by defauly
            - logger (`logging.Logger`) : logger for this simulation element. If none is given, a new one will be generated
        """
        super().__init__(name, network_config, level, logger)

        self._status = SimulationElementStatus.INIT
        self._clock_config = None     

    """
    ELEMENT OPERATION METHODS
    """
    def run(self) -> int:
        """
        Main function. Executes this similation element.

        Procedure follows the sequence:
        1. Initiates `activate()` sequence
        2. `listen()` is excecuted concurrently during `live()` procedure. 
        3. `deactivate()` procedure once either the `listen()` or `live()` procedures terminate.

        Returns `1` if excecuted successfully or if `0` otherwise

        Do NOT override
        """
        try:
            # initiate successful completion flag
            out = 0

            # activate simulation element
            self._log('activating...', level=logging.INFO)
            self._activate()

            ## update status to ACTIVATED
            self._status = SimulationElementStatus.ACTIVATED
            self._log('activated! Waiting for simulation to start...', level=logging.INFO)

            # wait for simulatio nstart
            self._wait_sim_start()
            self._log('simulation has started!', level=logging.INFO)

            ## update status to RUNNING
            self._status = SimulationElementStatus.RUNNING

            ## register simulation runtime start
            self._clock_config.set_simulation_runtime_start( time.perf_counter() )

            # start element life
            self._log('living...', level=logging.INFO)
            self._live()
            self._log('living completed!', level=logging.INFO)
            
            out = 1

        finally:
            # deactivate element
            self._log('deactivating...', level=logging.INFO)
            self._deactivate()
            self._log('deactivating completed!', level=logging.INFO)

            # update status to DEACTIVATED
            self._status = SimulationElementStatus.DEACTIVATED
            self._log('`run()` executed properly.') if out == 1 else self._log('`run()` interrupted.')

            #reguster simulation runtime end
            self._clock_config.set_simulation_runtime_end( time.perf_counter() )
            return out

    def _activate(self) -> None:
        """
        Initiates and executes commands that are thread-sensitive but that must be performed before the simulation starts.
        By default it only initializes network connectivity of the element.

        May be expanded if more capabilities are needed.
        """
        # inititate base network connections 
        self._external_socket_map, self._internal_socket_map = self.config_network()
        
        # check for correct socket initialization
        if self._external_socket_map is None:
            raise AttributeError(f'{self.name}: Inter-element communication sockets not activated during activation.')

        # synchronize with other elements in the simulation or internal modules
        self._external_address_ledger, self._internal_address_ledger = self.sync()     

        # check for correct element activation
        if self._clock_config is None:
            raise RuntimeError(f'{self.name}: Clock config not received during activation.')

        elif self._external_address_ledger is None:
            raise RuntimeError(f'{self.name}: External address ledger not received during activation.')

    @abstractmethod
    def _wait_sim_start(self) -> None:
        """
        Waits for the simulation to start
        """
        pass

    @abstractmethod
    def _live(self) -> None:
        """
        Procedure to be executed by the simulation element during the simulation. 

        Element will deactivate if this method returns.
        """
        pass
    
    def _deactivate(self) -> None:
        """
        Shut down procedure for this simulation entity. 
        """
        # inform others of deactivation
        self._publish_deactivate()

        # close connections
        super()._deactivate()
    
    @abstractmethod
    def _publish_deactivate(self) -> None:
        """
        Notifies other elements of the simulation that this element has deactivated and is no longer participating in the simulation.
        """
        pass

    async def _sim_wait(self, delay : float) -> None:
        """
        Simulation element waits for a given delay to occur according to the clock configuration being used

        ### Arguments:
            - delay (`float`): number of seconds to be waited
        # """
        try:
            wait_for_clock = None

            if isinstance(self._clock_config, AcceleratedRealTimeClockConfig):
                async def cancellable_wait(delay : float, freq : float):
                    try:
                        await asyncio.sleep(delay / freq)
                    except asyncio.CancelledError:
                        self._log(f'Cancelled sleep of delay {delay / freq} [s]')
                        raise
                    
                self._clock_config : AcceleratedRealTimeClockConfig
                freq = self._clock_config.sim_clock_freq
                wait_for_clock = asyncio.create_task(cancellable_wait(delay, freq))
                await wait_for_clock

            else:
                raise NotImplementedError(f'clock type {type(self._clock_config)} is not yet supported.')
        
        except asyncio.CancelledError:
            if wait_for_clock is not None and not wait_for_clock.done():
                wait_for_clock : asyncio.Task
                wait_for_clock.cancel()
                await wait_for_clock
