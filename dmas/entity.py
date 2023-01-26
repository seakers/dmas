from abc import ABC
import asyncio
import zmq
import zmq.asyncio as azmq
import socket

class Element(ABC):
    """
        Base class for all simulation elements. This including all agents, environment, and simulation manager.

        Attributes:
            Context
            RES port and address
            PUB port and address
            PUSH port and address
    """

    def __init__(self, response_address : str, publish_address : str, monitor_address : str) -> None:
        """
        Initiates an instance of a simulation element
        """
        super().__init__()

        self._response_address = response_address
        self._publish_address = publish_address
        self._monitor_address = monitor_address

        self._my_addresses = [self._response_address, self._publish_address]

    async def activate(self):
        """
        Initializes and connects essential network ports for this simulation element 
        """
        # initiate ports and connections
        self._context = azmq.Context()

        for address in self._my_addresses:
            if self._is_port_in_use(address):
                raise Exception(f"{address} address is already in use.")

        # direct message response port
        self._peer_in_socket = self._context.socket(zmq.REP)
        self._peer_in_socket.bind(self._response_address)
        self._peer_in_socket.setsockopt(zmq.LINGER, 0)
        self._peer_in_socket_lock = asyncio.Lock()

        # broadcast message publish port
        self._pub_socket = self._context.socket(zmq.PUB)                   
        self._pub_socket.sndhwm = 1100000                                 ## set SNDHWM, so we don't drop messages for slow subscribers
        self._pub_socket.bind(self._publish_address)
        self._pub_socket_lock = asyncio.Lock()

        # push to monitor port
        self._monitor_push_socket = self._context.socket(zmq.PUSH)
        self._monitor_push_socket.connect(self._monitor_address)
        self._monitor_push_socket.setsockopt(zmq.LINGER, 0)
        self._monitor_push_socket_lock = asyncio.Lock()

    def _is_port_in_use(address : str) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(address) == 0

    async def _shut_down(self):
        """
        Closes all 
        """
        self._peer_in_socket.close()
        self._pub_socket.close()
        self._monitor_push_socket.close()

        self._context.term()

    @abstractmethod
    async def 

    

class SimulationElement(ABC):
    def __init__(self) -> None:
        """
        Base class representing a node in the simulation network

        Attributes:

        """
        super().__init__()