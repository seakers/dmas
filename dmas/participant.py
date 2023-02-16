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
    +----------+---------+       +--------------+
    | ABSTRACT | PUB     |------>|              | 
    |   SIM    +---------+       | SIM ELEMENTS |
    |PARTICPANT| PUSH    |------>|              |
    +----------+---------+       +--------------+
    """
    __doc__ += SimulationElement.__doc__

    @abstractmethod
    def _config_network(self) -> dict:
        self._network_config : ParticipantNetworkConfig
        for address in self._network_config.get_my_addresses():
            if self._is_address_in_use(address):
                raise Exception(f"{address} address is already in use.")

        # broadcast message publish (PUB) port
        ## create socket from context
        self._network_config : ParticipantNetworkConfig
        pub_socket : zmq.Socket = self._context.socket(zmq.PUB)                   
        ## set SNDHWM, so we don't drop messages for slow subscribers
        pub_socket.sndhwm = 1100000                                 
        ## bind to address 
        pub_socket.bind(self._network_config.get_broadcast_address())
        ## create threading lock
        pub_lock = asyncio.Lock()

        # message to monitor push (PUSH) port
        ## create socket from context
        push_socket : zmq.Socket = self._context.socket(zmq.PUSH)
        ## connect to monitor address                  
        push_socket.connect( self._network_config.get_monitor_address() )
        push_socket.setsockopt(zmq.LINGER, 0)
        ## create threading lock
        push_lock = asyncio.Lock()

        return {zmq.PUB: (pub_socket, pub_lock), zmq.PUSH: (push_socket, push_lock)}

    async def _broadcast_message(self, msg : SimulationMessage) -> None:
        """
        Broadcasts a message to all elements subscribed to this element's publish socket
        """
        try:
            self._log(f'broadcasting message of type {type(msg)}...')
            task = asyncio.create_task( self._send_external_msg(msg, zmq.PUB) )
            await task
            self._log(f'message broadcasted sucessfully!')
        
        except asyncio.CancelledError as e:
            self._log(f'message broadcast interrupted.')
            task.cancel()
            await task

        except Exception as e:
            self._log(f'message broadcast failed.')
            raise e
    
    async def _push_message(self, msg : SimulationMessage) -> None:
        """
        Pushes a message to the simulation monitor
        """
        try:
            self._log(f'pushing message of type {type(msg)}...')            
            task = asyncio.create_task( self._send_external_msg(msg, zmq.PUSH) )
            await task
            self._log(f'message pushed sucessfully!')
            
        except asyncio.CancelledError as e:
            self._log(f'message broadcast interrupted.')
            task.cancel()
            await task

        except Exception as e:
            self._log(f'message push failed.')
            raise e
