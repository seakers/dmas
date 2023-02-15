from abc import ABC, abstractmethod
import logging
from multiprocessing import Queue
import socket
import time
import zmq
import concurrent.futures
import threading

from dmas.utils import *

class ElementStatus(Enum):
    INIT = 'INITIALIZED'
    ACTIVATED = 'ACTIVATED'
    RUNNING = 'RUNNING'
    DEACTIVATED = 'DEACTIVATED'

class SimulationElement(ABC):
    """
    ## Abstract Simulation Element 

    Base class for all simulation elements. This including all agents, environment, and simulation manager.

    ### Attributes:
        - _name (`str`): The name of this simulation element
        - _status (`Enum`) : Status of the element within the simulation
        - _network_config (:obj:`NetworkConfig`): description of the addresses pointing to this simulation element
        - _my_addresses (`list`): List of addresses used by this simulation element
        - _logger (`Logger`): debug logger

        - _pub_socket (:obj:`Socket`): The element's broadcast port socket
        - _pub_socket_lock (:obj:`Lock`): async lock for _pub_socket (:obj:`Socket`)
        - _monitor_push_socket (:obj:`Socket`): The element's monitor port socket
        - _monitor_push_socket_lock (:obj:`Lock`): async lock for _monitor_push_socket (:obj:`Socket`)

        - _clock_config (:obj:`ClockConfig`): description of this simulation's clock configuration
        - _address_ledger (`dict`): ledger containing the addresses pointing to each node's connecting ports

    ### Communications diagram:
    +----------+---------+       
    | ABSTRACT | PUB     |------>
    |   SIM    +---------+       
    | ELEMENT  | PUSH    |------>
    +----------+---------+       
    """
    def __init__(self, name : str, network_config : NetworkConfig, level : int = logging.INFO) -> None:
        """
        Initiates a new simulation element

        ### Args:
            - name (`str`): The element's name
            - network_config (:obj:`NetworkConfig`): description of the addresses pointing to this simulation element
            - level (`int`): logging level for this simulation element
        """
        super().__init__()

        self.name = name
        self._status = ElementStatus.INIT
        self._network_config = network_config
        self._logger : logging.Logger = self._set_up_logger(level)

        self._clock_config = None
        self._address_ledger = dict()

    def __set_up_logger(self, level=logging.DEBUG) -> logging.Logger:
        """
        Sets up a logger for this simulation element

        TODO add save to file capabilities
        """
        logger = logging.getLogger()
        logger.propagate = False
        logger.setLevel(level)

        c_handler = logging.StreamHandler()
        c_handler.setLevel(level)
        logger.addHandler(c_handler)

        return logger 

    def _log(self, msg : str, level=logging.DEBUG) -> None:
        """
        Logs a message to the desired level.
        """
        if level is logging.DEBUG:
            self._logger.debug(f'{self.name}: {msg}')
        elif level is logging.INFO:
            self._logger.info(f'{self.name}: {msg}')
        elif level is logging.WARNING:
            self._logger.warning(f'{self.name}: {msg}')
        elif level is logging.ERROR:
            self._logger.error(f'{self.name}: {msg}')
        elif level is logging.CRITICAL:
            self._logger.critical(f'{self.name}: {msg}')

    def run(self) -> None:
        """
        Executes this similation element.
        """
        try:
            # activate simulation element
            self._activate()
            self._status = ElementStatus.ACTIVATED

            kill_switch = threading.Event()
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                listen_future = pool.submit(self._listen, *[kill_switch])
                live_future = pool.submit(self._live, *[kill_switch])
                futures = [listen_future, live_future]

                self._status = ElementStatus.RUNNING
                _, pending = concurrent.futures.wait(futures, return_when=concurrent.futures.FIRST_COMPLETED)

                kill_switch.set()

        finally:
            self._status = ElementStatus.DEACTIVATED
            self._deactivate()

    def _activate(self) -> None:
        """
        Initiates and executes commands that are thread-sensitive but that must be performed before the simulation starts.
        By default it only initializes network connectivity of the element.

        May be expanded if more capabilities are needed.
        """
        # inititate base network connections 
        self._socket_list = self._config_network()

        # synchronize with other elements in the simulation
        self._sync()

    def _config_network(self) -> list:
        """
        Initializes and connects essential network port sockets for this simulation element. 

        Must be expanded if more connections are needed.
        
        #### Sockets Initialized:
            - _pub_socket (:obj:`Socket`): The entity's broadcast port address
            - _monitor_push_socket (:obj:`Socket`): The simulation's monitor port address

        #### Returns:
            - `list` containing all sockets used by this simulation element
        """
        # initiate ports and connections
        self._context = zmq.Context()

        for address in self._network_config.get_my_addresses():
            if self.__is_address_in_use(address):
                raise Exception(f"{address} address is already in use.")

        # broadcast message publish port
        self._pub_socket = self._context.socket(zmq.PUB)                   
        self._pub_socket.sndhwm = 1100000                                 ## set SNDHWM, so we don't drop messages for slow subscribers
        pub_address : str = self._network_config.get_broadcast_address()
        self._pub_socket.bind(pub_address)

        # push to monitor port
        self._monitor_push_socket = self._context.socket(zmq.PUSH)
        monitor_address : str = self._network_config.get_monitor_address()
        self._monitor_push_socket.connect(monitor_address)
        self._monitor_push_socket.setsockopt(zmq.LINGER, 0)

        return [self._pub_socket, self._monitor_push_socket]

    def __is_address_in_use(self, address : str) -> bool:
        """
        Checks if an address within `localhost` is already bound to an existing socket.

        ### Arguments:
            - address (`str`): address being evaluated

        ### Returns:
            - `bool`: True if port is already in use
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            address : str
            _, _, port = address.split(':')
            port = int(port)
            return s.connect_ex(('localhost', port)) == 0

    @abstractmethod
    def _sync() -> None:
        """
        Awaits for all other simulation elements to undergo their initialization and activation routines and become online. 
        
        Elements will then reach out to the manager subscribe to future broadcasts.

        The manager will use these incoming messages to create a ledger mapping simulation elements to their assigned ports
        and broadcast it to all memebers of the simulation. 
        """
        pass

    @abstractmethod
    def _live(self, kill_switch : threading.Event) -> None:
        """
        Procedure to be executed by the simulation element during the simulation. 

        Element will deactivate if this method returns.
        """
        pass

    @abstractmethod
    def _listen(self, kill_switch : threading.Event) -> None:
        """
        Procedure for listening for incoming messages from other elements during the simulation.

        Element will deactivate if this method returns.
        """
        pass
    
    def _deactivate(self) -> None:
        """
        Shut down procedure for this simulation entity. 
        Must close all socket connections.
        """
        # close connections
        for socket in self._socket_list:
            socket : zmq.Socket
            socket.close()  

        # close network context
        if self._context is not None:
            self._context.term()  

    def _sim_wait(self, delay : float) -> None:
        """
        Waits for a given delay to occur according to the clock configuration being used

        ### Arguments:
            - delay (`float`): number of seconds to be waited
        """
        if isinstance(self._clock_config, RealTimeClockConfig):
            self._clock_config : RealTimeClockConfig
            time.sleep(delay)

        elif isinstance(self._clock_config, AcceleratedRealTimeClockConfig):
            self._clock_config : AcceleratedRealTimeClockConfig
            time.sleep(delay / self._clock_config._sim_clock_freq)
