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
    +-----------+---------+       +--------------+
    | ABSTRACT  | PUB     |------>| SIM ELEMENTS | 
    |    SIM    +---------+       +==============+ 
    |PARTICIPANT| PUSH    |------>|  SIM MONITOR |
    +-----------+---------+       +--------------+
    """
    __doc__ += SimulationElement.__doc__
    
    async def _broadcast_external_message(self, msg : SimulationMessage) -> bool:
        """
        Broadcasts a message to all elements subscribed to this element's publish socket
        """
        try:
            self._log(f'broadcasting message of type {type(msg)}...')
            task = asyncio.create_task( self._send_external_msg(msg, zmq.PUB) )
            await task
            self._log(f'message broadcasted sucessfully!')
            return task.result()
        
        except asyncio.CancelledError as e:
            self._log(f'message broadcast interrupted.')
            task.cancel()
            await task

        except Exception as e:
            self._log(f'message broadcast failed.')
            raise e
    
    async def _push_external_message(self, msg : SimulationMessage) -> bool:
        """
        Pushes a message to the simulation monitor
        """
        try:
            self._log(f'pushing message of type {type(msg)}...')            
            task = asyncio.create_task( self._send_external_msg(msg, zmq.PUSH) )
            await task
            self._log(f'message pushed sucessfully!')
            return task.result()
            
        except asyncio.CancelledError as e:
            self._log(f'message broadcast interrupted.')
            task.cancel()
            await task

        except Exception as e:
            self._log(f'message push failed.')
            raise e
