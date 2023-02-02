from abc import ABC, abstractmethod
import asyncio
import logging
import zmq
import zmq.asyncio as azmq
import socket

from dmas.messages import SimulationMessage
from utils import *

class AbstractSimulationElement(ABC):
    """
    ## Abstract Simulation Element 

    Base class for all simulation elements. This including all agents, environment, and simulation manager.

    ### Attributes:
        - _name (`str`): The name of this simulation element
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

    def __init__(self, name : str, network_config : NetworkConfig) -> None:
        """
        Initiates a new simulation element

        ### Args:
            - name (`str`): The element's name
            - network_config (:obj:`NetworkConfig`): description of the addresses pointing to this simulation element
        """
        super().__init__()

        self.name = name
        self._network_config = network_config
        self._my_addresses = []
        self._logger : logging.Logger = self._set_up_logger(level=logging.INFO)

        self._clock_config = None
        self._address_ledger = dict()
            
    def _set_up_logger(self, level=logging.DEBUG) -> logging.Logger:
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
        asyncio.run(self._excetute())

    async def _excetute(self) -> None:
        """
        Main simulation element function. Activates and executes this similation element. 
        """
        try:
            # activate and initialize
            self._log('activating...', level=logging.INFO)
            pending = None
            await self._activate()
            self._log('activated!', level=logging.INFO)

            # execute 
            self._log('starting life...', level=logging.INFO)
            live_task = asyncio.create_task(self._live())
            listen_task = asyncio.create_task(self._listen())

            _, pending = await asyncio.wait([live_task, listen_task], return_when=asyncio.FIRST_COMPLETED)

        finally:
            self._log('i am now dead! Terminating processes...', level=logging.INFO)
            if pending is not None:
                for task in pending:
                    task : asyncio.Task
                    task.cancel()
                    await task

            # deactivate and clean up
            await self._shut_down()
            self._log('shut down. Good night!', level=logging.INFO)

    async def _activate(self) -> None:
        """
        Initiates and executes commands that are thread-sensitive but that must be performed before the simulation starts.
        By default it only initializes network connectivity of the element.

        May be expanded if more capabilities are needed.
        """
        # inititate base network connections 
        self._socket_list = await self._config_network()

    async def _config_network(self) -> list:
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
        self._context = azmq.Context()

        for address in self._network_config.get_my_addresses():
            if self.__is_address_in_use(address):
                raise Exception(f"{address} address is already in use.")

        # broadcast message publish port
        self._pub_socket = self._context.socket(zmq.PUB)                   
        self._pub_socket.sndhwm = 1100000                                 ## set SNDHWM, so we don't drop messages for slow subscribers
        pub_address : str = self._network_config.get_broadcast_address()
        self._pub_socket.bind(pub_address)
        self._pub_socket_lock = asyncio.Lock()

        # push to monitor port
        self._monitor_push_socket = self._context.socket(zmq.PUSH)
        monitor_address : str = self._network_config.get_monitor_address()
        self._monitor_push_socket.connect(monitor_address)
        self._monitor_push_socket.setsockopt(zmq.LINGER, 0)
        self._monitor_push_socket_lock = asyncio.Lock()

        return [self._pub_socket, self._monitor_push_socket]

    async def _broadcast_message(self, msg : SimulationMessage) -> None:
        """
        Broadcasts a message to all elements subscribed to this element's publish socket
        """
        try:
            self._log(f'acquiring port lock for a message of type {type(msg)}...')
            await self._pub_socket_lock.acquire()
            self._log(f'port lock acquired!')

            self._log(f'sending message of type {type(msg)}...')
            dst : str = msg.get_dst()
            content : str = str(msg.to_json())
            await self._pub_socket.send_multipart([dst, content])
            self._log(f'message transmitted sucessfully!')

        except asyncio.CancelledError:
            self._log(f'message transmission interrupted.')
            
        except:
            self._log(f'message transmission failed.')
            raise

        finally:
            self._pub_socket_lock.release()
            self._log(f'port lock released.')


    async def _push_message_to_monitor(self, msg : SimulationMessage) -> None:
        """
        Pushes a message to the simulation monitor
        """
        try:
            self._log(f'acquiring port lock for a message of type {type(msg)}...')
            await self._monitor_push_socket_lock.acquire()
            self._log(f'port lock acquired!')

            self._log(f'sending message of type {type(msg)}...')
            dst : str = msg.get_dst()
            if dst != SimulationElementTypes.MONITOR.value:
                raise asyncio.CancelledError('attempted to send a non-monitor message to the simulation monitor.')

            content : str = str(msg.to_json())
            await self._monitor_push_socket.send_multipart([dst, content])
            self._log(f'message transmitted sucessfully!')

        except asyncio.CancelledError:
            self._log(f'message transmission interrupted.')
            
        except:
            self._log(f'message transmission failed.')
            raise

        finally:
            self._monitor_push_socket_lock.release()
            self._log(f'port lock released.')

    def __is_address_in_use(self, address : str) -> bool:
        """
        Checks if an address is already bound to an existing port socket.

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

    async def _shut_down(self) -> None:
        """
        Shut down procedure for this simulation entity. 
        Must close all socket connections.
        """
        # close connections
        self._close_sockets()

        # close network context
        if self._context is not None:
            self._context.term()

    def _close_sockets(self) -> None:
        """
        Closes all sockets present in the abstract class Entity
        """
        for socket in self._socket_list:
            socket : zmq.Socket
            socket.close()

    @abstractmethod
    async def _live(self) -> None:
        """
        Procedure to be executed by the simulation element during the simulation. 
        
        Element will shut down once this procedure is completed.
        """
        pass    
    
    @abstractmethod
    async def _listen(self) -> None:
        """
        Procedure for listening for incoming messages from other elements during the simulation.

        Element will deactivate if this method returns.
        """
        pass