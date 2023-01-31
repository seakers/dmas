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
        - _response_address (`str`): This element's response port address
        - _broadcast_address (`str`): This element's broadcast port address
        - _monitor_address (`str`): This simulation's monitor port address

        - _my_addresses (`list`): List of addresses used by this simulation element

        - _peer_in_socket (:obj:`Socket`): The element's response port socket
        - _pub_socket (:obj:`Socket`): The element's broadcast port socket
        - _monitor_push_socket (:obj:`Socket`): The element's monitor port socket

        - _peer_in_socket_lock (:obj:`Lock`): async lock for _peer_in_socket (:obj:`socket`)
        - _pub_socket_lock (:obj:`Lock`): async lock for _pub_socket (:obj:`socket`)
        - _monitor_push_socket_lock (:obj:`Lock`): async lock for _monitor_push_socket (:obj:`socket`)


    ### Communications diagram:
    +----------+---------+       
    |          | PUB     |------>
    |          +---------+       
    |          | PUSH    |------>
    |          +---------+       
    |          | REP     |<------
    |          +---------+       
    |                    |       
    |ABSTRACT SIM ELEMENT|       
    +--------------------+       
    """

    def __init__(self, name : str, network_config : NetworkConfig) -> None:
        """
        Initiates a new simulation element

        ### Args:
            - name (`str`): The element's name
            - response_address (`str`): The element's response port address
            - broadcast_address (`str`): The element's broadcast port address
            - monitor_address (`str`): The element's monitor port address
        """
        super().__init__()

        self.name = name
        self._network_config = network_config

        self._logger : logging.Logger = self._set_up_logger(level=logging.INFO)
    
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
            await self._activate()
            self._log('activated!', level=logging.INFO)

            # execute 
            self._log('starting life...', level=logging.INFO)
            await self._live()
            self._log('i\'m now dead! Terminating processes...', level=logging.INFO)

        finally:
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
            - _peer_in_socket (:obj:`Socket`): The entity name
            - _pub_socket (:obj:`Socket`): The entity's response port address
            - _monitor_push_socket (:obj:`Socket`): The entity's broadcast port address

        #### Returns:
            - `list` containing all sockets used by this simulation element
        """
        # initiate ports and connections
        self._context = azmq.Context()

        for address in self._network_config.get_my_addresses():
            if self.__is_address_in_use(address):
                raise Exception(f"{address} address is already in use.")

        # direct message response port
        self._peer_in_socket = self._context.socket(zmq.REP)
        peer_in_address : str = self._network_config.get_response_address()
        self._peer_in_socket.bind(peer_in_address)
        self._peer_in_socket.setsockopt(zmq.LINGER, 0)
        self._peer_in_socket_lock = asyncio.Lock()

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

        return [self._peer_in_socket, self._pub_socket, self._monitor_push_socket]

    async def _broadcast_message(self, msg : SimulationMessage) -> None:
        """
        Broadcasts a message to all elements subscribed to this element's publish socket
        """
        try:
            self._log(f'acquiring broacasting lock for a message of type {type(msg)}...')
            await self._pub_socket_lock.acquire()
            self._log(f'broacasting lock acquired!')

            self._log(f'broadcasting message of type {type(msg)}...')
            dst : str = msg.get_dst()
            content : str =  str(msg.to_json())
            await self._pub_socket.send_multipart([dst.encode('ascii'), content.encode('ascii')])
            self._log(f'broacasting message sent successfully!')

        except asyncio.CancelledError:
            self._log(f'message broacast interrupted.')   
        
        except:
            self._log(f'broacast failed.')
        
        finally:
            self._pub_socket_lock.release()
            self._log(f'broacasting lock released.')


    async def _push_message_to_monitor(self, msg : SimulationMessage) -> None:
        """
        Pushes a message to the simulation monitor
        """
        try:
            self._log(f'acquiring monitor push lock for a message of type {type(msg)}...')
            await self._monitor_push_socket_lock.acquire()
            self._log(f'monitor push lock acquired!')

            self._log(f'pushing message of type {type(msg)} to monitor...')
            dst : str = msg.get_dst()
            content : str =  str(msg.to_json())
            await self._monitor_push_socket.send_multipart([dst.encode('ascii'), content.encode('ascii')])
            self._log(f'message pushed sucessfully!')

        except asyncio.CancelledError:
            self._log(f'message push interrupted.')
            
        except:
            self._log(f'message push failed.')

        finally:
            self._monitor_push_socket_lock.release()
            self._log(f'monitor push lock released.')

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
    async def _live(self):
        """
        Procedure to be executed by the simulation element during the simulation. 
        
        Element will shut down once this procedure is completed.
        """
        pass    
    