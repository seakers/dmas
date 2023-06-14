from enum import Enum
from typing import Union

import numpy
from applications.chess3d.utils import CoordinateTypes
from dmas.agents import AgentAction
from dmas.messages import SimulationMessage
   
class ActionTypes(Enum):
    IDLE = 'IDLE'
    TRAVEL = 'TRAVEL'
    MANEUVER = 'MANEUVER'
    BROADCAST_MSG = 'BROADCAST_MSG'
    WAIT_FOR_MSG = 'WAIT_FOR_MSG'
    MEASURE = 'MESURE'

def action_from_dict(action_type : str, **kwargs) -> AgentAction:
    if action_type == ActionTypes.IDLE.value:
        return IdleAction(**kwargs)
    elif action_type == ActionTypes.TRAVEL.value:
        return TravelAction(**kwargs)
    elif action_type == ActionTypes.MANEUVER.value:
        return ManeuverAction(**kwargs)
    elif action_type == ActionTypes.BROADCAST_MSG.value:
        return BroadcastMessageAction(**kwargs)
    elif action_type == ActionTypes.WAIT_FOR_MSG.value:
        return WaitForMessages(**kwargs)
    elif action_type == ActionTypes.MEASURE.value:
        return MeasurementAction(**kwargs)
    else:
        raise NotImplemented(f'Action of type {action_type} not yet implemented.')
    
class IdleAction(AgentAction):
    """
    ## Idle Action

    Instructs an agent to idle for a given amount of time

    ### Attributes:
        - action_type (`str`): type of action to be performed
        - t_start (`float`): start time of this action in [s] from the beginning of the simulation
        - t_end (`float`): end time of this this action in [s] from the beginning of the simulation
        - status (`str`): completion status of the action
        - id (`str`) : identifying number for this action in uuid format
    """
    def __init__(   self, 
                    t_start : Union[float, int],
                    t_end : Union[float, int], 
                    status : str = 'PENDING',
                    id: str = None, 
                    **_
                ) -> None:
        """
        Creates an isntance of an Idle Action

        ### Arguments:
            - t_start (`float`): start time of this task in [s] from the beginning of the simulation
            - t_end (`float`): end time of this this task in [s] from the beginning of the simulation
            - status (`str`): completion status of the task
            - id (`str`) : identifying number for this task in uuid format
        """
        super().__init__(ActionTypes.IDLE.value, t_start, t_end, status, id)

class TravelAction(AgentAction):
    """
    ## Travel Action

    Instructs an agent to travel to a particular position
    
    ### Attributes:
        - action_type (`str`): type of action to be performed
        - t_start (`float`): start time of this action in [s] from the beginning of the simulation
        - t_end (`float`): end time of this this action in [s] from the beginning of the simulation
        - status (`str`): completion status of the action
        - id (`str`) : identifying number for this action in uuid format
        - final_pos (`list`): coordinates desired destination
        - pos_type (`str`): coordinate basis being used for the desired destination
    """
    def __init__(self,
                final_pos : list, 
                t_start : Union[float, int],
                pos_type : str = CoordinateTypes.CARTESIAN.value,
                status : str = 'PENDING',
                id: str = None, 
                **_) -> None:
        """
        Creates an instance of a Travel Action

        ### Arguments:
            - final_pos (`list`): coordinates desired destination
            - t_start (`float`): start time of this action in [s] from the beginning of the simulation
            - pos_type (`str`): coordinate basis being used for the desired destination
            - status (`str`): completion status of the action
            - id (`str`) : identifying number for this action in uuid format
        """
            
        super().__init__(ActionTypes.TRAVEL.value, t_start, status=status, id=id)
        
        if not isinstance(final_pos, list):
            raise AttributeError(f'`final_pos` must be of type `list`. is of type {type(final_pos)}.')
        
        if pos_type == CoordinateTypes.CARTESIAN.value and len(final_pos) != 3:
            raise ValueError(f'`final_pos` must be a list of 3 values (x, y, z). is of length {len(final_pos)}.')
        elif pos_type == CoordinateTypes.KEPLERIAN.value and len(final_pos) != 5:
            raise ValueError(f'`final_pos` must be a list of 5 values (lat, lon, alt). is of length {len(final_pos)}.')
        elif pos_type == CoordinateTypes.LATLON.value and len(final_pos) != 3:
            raise ValueError(f'`final_pos` must be a list of 3 values (lat, lon, alt). is of length {len(final_pos)}.')
        elif (pos_type != CoordinateTypes.CARTESIAN.value
             and pos_type != CoordinateTypes.KEPLERIAN.value
             and pos_type != CoordinateTypes.LATLON.value):
            raise NotImplemented(f'`pos_type` or type `{pos_type}` not yet supported for `MoveAction`.')

        self.final_pos = final_pos
        self.pos_type = pos_type

class ManeuverAction(AgentAction):
    """
    ## Maneuver Action

    Instructs a satellite agent to perform an attitude maneuver
    
    ### Attributes:
        - action_type (`str`): type of action to be performed
        - t_start (`float`): start time of this action in [s] from the beginning of the simulation
        - t_end (`float`): end time of this this action in [s] from the beginning of the simulation
        - status (`str`): completion status of the action
        - id (`str`) : identifying number for this action in uuid format
        - final_attitude (`float`): desired off-nadir angle parallel to velocity vector
    """
    def __init__(self,
                final_attitude : list, 
                t_start : Union[float, int],
                status : str = 'PENDING',
                id: str = None, 
                **_) -> None:
        super().__init__(ActionTypes.TRAVEL.value, t_start, status=status, id=id)
        
        if not isinstance(final_attitude, list):
            raise AttributeError(f'`final_attitude` must be of type `list`. is of type {type(final_attitude)}.')
        self.pos = final_attitude

class BroadcastMessageAction(AgentAction):
    """
    ## Broadcast Message Action 

    Instructs an agent to broadcast a message to all of its peers

    ### Attributes:
        - action_type (`str`): type of action to be performed
        - msg (`dict`): message to be broadcasted to other agents in the network
        - t_start (`float`): start time of this action in [s] from the beginning of the simulation
        - t_end (`float`): start time of this actrion in[s] from the beginning of the simulation
        - status (`str`): completion status of the task
        - id (`str`) : identifying number for this task in uuid format
    """
    def __init__(self, 
                msg : dict,
                t_start : Union[float, int],
                status : str = 'PENDING',
                id: str = None, 
                **_) -> None:
        """
        Creates an instance of a Broadcast Message Action

        ### Arguments
            - msg (`dict`): message to be broadcasted to other agents in the network
            - t_start (`float`): start time of this action in [s] from the beginning of the simulation
            - status (`str`): completion status of the task
            - id (`str`) : identifying number for this task in uuid format
        """
        super().__init__(ActionTypes.BROADCAST_MSG.value, t_start, status=status, id=id)
        self.msg = msg

class MeasurementAction(AgentAction):
    """
    Describes a measurement to be performed by agents in the simulation

    ### Attributes:
        - measurement_req (`dict`): dictionary containing the measurement request being met by this measurement 
        - subtask_index (`int`): index of the subtask being performed by this measurement
        - instrument_name (`str`): name of the instrument_name that will perform this action
        - u_exp (`int` or `float`): expected utility from this measurement
        - t_start (`float`): start time of the measurement of this action in [s] from the beginning of the simulation
        - t_end (`float`): end time of the measurment of this action in [s] from the beginning of the simulation
        - id (`str`) : identifying number for this task in uuid format
    """  
    def __init__(   self,
                    measurement_req : dict,
                    subtask_index : int,
                    instrument_name : str,
                    u_exp : Union[float, int], 
                    t_start: Union[float, int], 
                    t_end: Union[float, int], 
                    status: str = 'PENDING', 
                    id: str = None, 
                    **_) -> None:
        """
        Creates an instance of a 
        ### Arguments:
            - measurement_req (`dict`): dictionary containing the measurement request being met by this measurement 
            - subtask_index (`int`): index of the subtask being performed by this measurement
            - instrument_name (`str`): name of the instrument_name that will perform this action
            - u_exp (`int` or `float`): expected utility from this measurement
            - t_start (`float`): start time of the measurement of this action in [s] from the beginning of the simulation
            - t_end (`float`): end time of the measurment of this action in [s] from the beginning of the simulation
            - id (`str`) : identifying number for this task in uuid format
        """
        super().__init__(ActionTypes.MEASURE.value, t_start, t_end, status, id)
        self.measurement_req = measurement_req
        self.subtask_index = subtask_index
        self.instrument_name = instrument_name
        self.u_exp = u_exp

class WaitForMessages(AgentAction):
    """
    ## Wait for Messages Action

    Instructs an agent to idle until a roadcast from a peer is received or a timer runs out

    ### Attributes:
        - action_type (`str`): type of action to be performed
        - t_start (`float`): start time of the waiting period in [s] from the beginning of the simulation
        - t_end (`float`): start time of the waiting period in[s] from the beginning of the simulation
        - status (`str`): completion status of the task
        - id (`str`) : identifying number for this task in uuid format
    """
    def __init__(   self, 
                    t_start: Union[float, int], 
                    t_end: Union[float, int], 
                    status: str = 'PENDING', 
                    id: str = None, 
                    **_
                ) -> None:
        """
        Creates an isntance of a Waif For Message Action

         ### Arguments:
            - t_start (`float`): start time of the waiting period in [s] from the beginning of the simulation
            - t_end (`float`): start time of the waiting period in[s] from the beginning of the simulation
            - status (`str`): completion status of the task
            - id (`str`) : identifying number for this task in uuid format
        """
        super().__init__(ActionTypes.WAIT_FOR_MSG.value, t_start, t_end, status, id)