import logging
import threading
import socket

import zmq
from dmas.element import SimulationElement
from dmas.messages import *
from dmas.utils import *


class Participant(SimulationElement):
    """
    ## Abstract Simulation Participant 

    Base class for all simulation participants. This including all agents, environment, and simulation manager.

    ### Communications diagram:
    +----------+---------+       +   
    | ABSTRACT | PUB     |------>| 
    |   SIM    +---------+       | SIM ELEMENTS
    | ELEMENT  | PUSH    |------>|
    +----------+---------+       +
    """
    __doc__ += SimulationElement.__doc__

    def __init__(self, 
                name: str, 
                network_config: ParticipantNetworkConfig, 
                level: int = logging.INFO) -> None:
        super().__init__(name, network_config, level)

    @abstractmethod
    def _config_network(self) -> dict:
        for address in self._network_config.get_my_addresses():
            if self._is_address_in_use(address):
                raise Exception(f"{address} address is already in use.")

        # broadcast message publish port
        self._network_config : ParticipantNetworkConfig
        pub_socket : zmq.Socket = self._context.socket(zmq.PUB)                   
        pub_socket.sndhwm = 1100000                                 ## set SNDHWM, so we don't drop messages for slow subscribers
        pub_address : str = self._network_config.get_broadcast_address()
        pub_socket.bind(pub_address)
        pub_lock = threading.Lock()

        # push to monitor port
        push_socket : zmq.Socket = self._context.socket(zmq.PUSH)
        monitor_address : str = self._network_config.get_monitor_address()
        push_socket.connect(monitor_address)
        push_socket.setsockopt(zmq.LINGER, 0)
        push_lock = threading.Lock()

        return {zmq.PUB: (pub_socket, pub_lock), zmq.PUSH: (push_socket, push_lock)}

    def _broadcast_message(self, msg : SimulationMessage) -> None:
        """
        Broadcasts a message to all elements subscribed to this element's publish socket
        """
        try:
            self._log(f'broadcasting message of type {type(msg)}...')
            self._send_msg(msg, zmq.PUB)
            self._log(f'message broadcasted sucessfully!')
            
        except Exception as e:
            self._log(f'message broadcast failed.')
            raise e
    
    def _push_message(self, msg : SimulationMessage) -> None:
        """
        Pushes a message to the simulation monitor
        """
        try:
            self._log(f'acquiring port lock for a message of type {type(msg)}...')
            self._monitor_push_socket_lock.acquire()
            self._log(f'port lock acquired!')

            self._log(f'sending message of type {type(msg)}...')
            dst : str = msg.get_dst()
            if dst != SimulationElementTypes.MONITOR.value:
                raise asyncio.CancelledError('attempted to send a non-monitor message to the simulation monitor.')

            await self._send_from_socket(msg, self._monitor_push_socket, self._monitor_push_socket_lock)
            self._log(f'message transmitted sucessfully!')

        except asyncio.CancelledError:
            self._log(f'message transmission interrupted.')
            
        except Exception as e:
            self._log(f'message transmission failed.')
            raise e

        finally:
            self._monitor_push_socket_lock.release()
            self._log(f'port lock released.')