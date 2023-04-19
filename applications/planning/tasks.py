from enum import Enum
from typing import Union

import numpy
from dmas.agents import AgentAction
from dmas.messages import SimulationMessage
   
class ActionTypes(Enum):
    PEER_MSG = 'PEER_MSG'
    BROADCAST_MSG = 'BROADCAST_MSG'
    MOVE = 'MOVE'
    MEASURE = 'MEASURE'
    IDLE = 'IDLE'

class PeerMessageAction(AgentAction):
    """
    ## Peer-Message Action 

    Instructs an agent to send a message directly to a peer
    """
    def __init__(self, 
                msg : SimulationMessage,
                t_start : Union[float, int],
                t_end : Union[float, int], 
                status : str = 'PENDING',
                id: str = None, 
                **_) -> None:
        super().__init__(ActionTypes.PEER_MSG.value, t_start, t_end, status, id)
        self.msg = msg

class BroadcastMessageAction(AgentAction):
    """
    ## Broadcast Message Action 

    Instructs an agent to broadcast a message to all of its peers
    """
    def __init__(self, 
                msg : SimulationMessage,
                t_start : Union[float, int],
                t_end : Union[float, int], 
                status : str = 'PENDING',
                id: str = None, 
                **_) -> None:
        super().__init__(ActionTypes.BROADCAST_MSG.value, t_start, t_end, status, id)
        self.msg = msg

class MoveAction(AgentAction):
    """
    ## Move Action

    Instructs an agent to move to a particular position
    """
    def __init__(self,
                pos : list, 
                t_start : Union[float, int],
                t_end : Union[float, int] = numpy.Inf, 
                status : str = 'PENDING',
                id: str = None, 
                **_) -> None:
        super().__init__(ActionTypes.MOVE.value, t_start, t_end, status, id)
        self.pos = pos

class MeasurementTask(AgentAction):
    """
    Describes a measurement task to be performed by agents in the simulation

    ### Attributes:
        - x (`list`): cartesian coordinates of the location of this task
        - s_max (`float`): maximum score attained from performing this task
        - instruments (`list`): name of the instruments that can perform this task
        - t_start (`float`): start time of the availability of this task in [s] from the beginning of the simulation
        - t_end (`float`): end time of the availability of this task in [s] from the beginning of the simulation
        - id (`str`) : identifying number for this task in uuid format
    """        
    def __init__(self, 
                pos : list, 
                s_max : float,
                instruments : list,
                t_start: Union[float, int], 
                t_end: Union[float, int], 
                status: str = 'PENDING', 
                id: str = None, **_
                ) -> None:
        """
        Creates an instance of a task 

        ### Arguments:
            - x (`list`): cartesian coordinates of the location of this task
            - s_max (`float`): maximum score attained from performing this task
            - instrument (`str`): name of the instrument that can perform this task
            - t_start (`float`): start time of the availability of this task in [s] from the beginning of the simulation
            - t_end (`float`): end time of the availability of this task in [s] from the beginning of the simulation
            - id (`str`) : identifying number for this task in uuid format
        """
        super().__init__(ActionTypes.MEASURE.value, t_start, t_end, status, id)

        # check arguments
        if not isinstance(pos, list):
            raise AttributeError(f'`pos` must be of type `list`. is of type {type(pos)}.')
        elif len(pos) != 2:
            raise ValueError(f'`pos` must be a list of 2 values. is of length {len(pos)}.')
        if not isinstance(s_max, float) and not isinstance(s_max, int):
            raise AttributeError(f'`s_max` must be of type `float` or type `int`. is of type {type(s_max)}.')
        if not isinstance(instruments, list):
            raise AttributeError(f'`instruments` must be of type `list`. is of type {type(instruments)}.')
        else:
            for instrument in instruments:
                if not isinstance(instrument, str):
                    raise AttributeError(f'`instruments` must a `list` of elements of type `str`. contains elements of type {type(instrument)}.')
        
        self.pos = pos
        self.s_max = s_max
        self.instruments = instruments    

class IdleAction(AgentAction):
    """
    ## Idle Action

    Instructs an agent to idle for a given amount of time
    """
    def __init__(self, 
                t_start : Union[float, int],
                t_end : Union[float, int], 
                status : str = 'PENDING',
                id: str = None, 
                **_) -> None:
        super().__init__(ActionTypes.IDLE.value, t_start, t_end, status, id)
