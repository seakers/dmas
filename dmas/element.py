from abc import ABC, abstractmethod
import asyncio
import logging
import zmq
import zmq.asyncio as azmq
import socket

from dmas.messages import SimulationMessage
from .utils import *

logger = logging.getLogger(__name__)

class AbstractSimulationElement(ABC):
    """
    ## Abstract Simulation Element 

    Base class for all simulation elements. This including all agents, environment, and simulation manager.

    ### Attributes:
        - _name (`str`): The name of this simulation element
        - _response_address (`str`): This element's response port address
        - _broadcast_address (`str`): This element's broadcast port address
        - _monitor_address (`str`): This simulation's monitor port address

        - _my_addresses (`list`): List of addresses pointing to this simulation element

        - _peer_in_socket (:obj:`Socket`): The element's response port socket
        - _pub_socket (:obj:`Socket`): The element's broadcast port socket
        - _monitor_push_socket (:obj:`Socket`): The element's monitor port socket

        - _peer_in_socket_lock (:obj:`Lock`): async lock for _peer_in_socket (:obj:`socket`)
        - _pub_socket_lock (:obj:`Lock`): async lock for _pub_socket (:obj:`socket`)
        - _monitor_push_socket_lock (:obj:`Lock`): async lock for _monitor_push_socket (:obj:`socket`)
    """

    def __init__(self, name : str, network_config : ManagerNetworkConfig) -> None:
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

    async def run(self) -> None:
        """
        Main simulation element function. Activates and executes this similation element. 
        """
        try:
            # activate and initialize
            await self._activate()

            # execute 
            await self._live()

        finally:
            # deactivate and clean up
            await self._shut_down()

    async def _activate(self) -> None:
        """
        Initiates and executes commands that are thread-sensitive but that must be performed before the simulation starts.
        By default it only initializes network connectivity of the element.

        May be expanded if more capabilities are needed.
        """
        # inititate base network connections 
        await self._base_network_config()

        # inititate any additional network connections 
        await self._config_network()

    async def _base_network_config(self) -> None:
        """
        Initializes and connects essential network port sockets for this simulation element. 
        
        #### Sockets Initialized:
            - _peer_in_socket (:obj:`Socket`): The entity name
            - _pub_socket (:obj:`Socket`): The entity's response port address
            - _monitor_push_socket (:obj:`Socket`): The entity's broadcast port address
        """
        # initiate ports and connections
        self._context = azmq.Context()

        for address in self._network_config.get_my_addresses():
            if self.__is_address_in_use(address):
                raise Exception(f"{address} address is already in use.")

        # direct message response port
        self._peer_in_socket = self._context.socket(zmq.REP)
        self._peer_in_socket.bind(self._network_config.get_response_address())
        self._peer_in_socket.setsockopt(zmq.LINGER, 0)
        self._peer_in_socket_lock = asyncio.Lock()

        # broadcast message publish port
        self._pub_socket = self._context.socket(zmq.PUB)                   
        self._pub_socket.sndhwm = 1100000                                 ## set SNDHWM, so we don't drop messages for slow subscribers
        self._pub_socket.bind(self._network_config.get_broadcast_address)
        self._pub_socket_lock = asyncio.Lock()

        # push to monitor port
        self._monitor_push_socket = self._context.socket(zmq.PUSH)
        self._monitor_push_socket.connect(self._network_config.get_monitor_address())
        self._monitor_push_socket.setsockopt(zmq.LINGER, 0)
        self._monitor_push_socket_lock = asyncio.Lock()

    @abstractmethod
    async def _config_network(self):
        """
        Initializes and connects any aditional network port sockets for this simulation element. 
        """
        pass

    async def broadcast_message(self, msg : SimulationMessage) -> None:
        """
        Broadcasts a message to all elements subscribed to this element's publish socket
        """
        await self._pub_socket_lock.acquire()
        await self._pub_socket.send_multipart([msg.get_dst(), msg.to_json()])
        self._pub_socket_lock.release()

    async def push_message_to_monitor(self, msg : SimulationMessage) -> None:
        pass

    def __is_address_in_use(address : str) -> bool:
        """
        Checks if an address is already bound to an existing port socket.

        ### Arguments:
            - address (`str`): address being evaluated

        ### Returns:
            - `bool`: True if port is already in use
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(address) == 0

    @abstractmethod
    async def _live(self):
        """
        Procedure to be executed by the simulation element during the simulation. 
        
        Element will shut down once this procedure is completed.
        """
        pass

    async def _shut_down(self) -> None:
        """
        Shut down procedure for this simulation entity. 
        Must close all socket connections.
        """

        # close connections
        self.__close_base_sockets()
        self._close_sockets()

        # close network context
        if self._context is not None:
            self._context.term()

    def __close_base_sockets(self) -> None:
        """
        Closes all sockets present in the abstract class Entity
        """
        if self._peer_in_socket is not None:
            self._peer_in_socket.close()

        if self._pub_socket is not None:
            self._pub_socket.close()

        if self._monitor_push_socket is not None:
            self._monitor_push_socket.close()

    @abstractmethod
    def _close_sockets(self) -> None:
        """
        Closes any additional sockets opened by a simulation Entity
        """
        pass

    
    