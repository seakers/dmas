import copy
from enum import Enum
from itertools import combinations, permutations
from typing import Union

import numpy
from dmas.agents import AgentAction
from dmas.messages import SimulationMessage
   
class ActionTypes(Enum):
    PEER_MSG = 'PEER_MSG'
    BROADCAST_MSG = 'BROADCAST_MSG'
    BROADCAST_STATE = 'BROADCAST_STATE'
    MOVE = 'MOVE'
    MEASURE = 'MEASURE'
    IDLE = 'IDLE'
    WAIT_FOR_MSG = 'WAIT_FOR_MSG'

def action_from_dict(action_type : str, **kwargs) -> AgentAction:
    if action_type == ActionTypes.PEER_MSG.value:
        return PeerMessageAction(**kwargs)
    elif action_type == ActionTypes.BROADCAST_MSG.value:
        return BroadcastMessageAction(**kwargs)
    elif action_type == ActionTypes.BROADCAST_STATE.value:
        return BroadcastStateAction(**kwargs)
    elif action_type == ActionTypes.MOVE.value:
        return MoveAction(**kwargs)
    elif action_type == ActionTypes.MEASURE.value:
        return MeasurementTask(**kwargs)
    elif action_type == ActionTypes.IDLE.value:
        return IdleAction(**kwargs)
    elif action_type == ActionTypes.WAIT_FOR_MSG.value:
        return WaitForMessages(**kwargs)
    else:
        raise NotImplemented(f'Action of type {action_type} not yet implemented.')
    
class PeerMessageAction(AgentAction):
    """
    ## Peer-Message Action 

    Instructs an agent to send a message directly to a peer

    ### Attributes:
        - action_type (`str`): type of action to be performed
        - msg (`dict`): message to be transmitted to the target agent in the network
        - t_start (`float`): start time of this action in [s] from the beginning of the simulation
        - t_end (`float`): start time of this actrion in[s] from the beginning of the simulation
        - status (`str`): completion status of the task
        - id (`str`) : identifying number for this task in uuid format
    """
    def __init__(self, 
                msg : SimulationMessage,
                t_start : Union[float, int],
                t_end : Union[float, int], 
                status : str = 'PENDING',
                id: str = None, 
                **_) -> None:
        """
        Creates an isntance of a Waif For Message Action

        ### Arguments
            - msg (`dict`): message to be transmitted to the target agent in the network
            - t_start (`float`): start time of this action in [s] from the beginning of the simulation
            - t_end (`float`): start time of this actrion in[s] from the beginning of the simulation
            - status (`str`): completion status of the task
            - id (`str`) : identifying number for this task in uuid format
        """
        super().__init__(ActionTypes.PEER_MSG.value, t_start, t_end, status, id)
        self.msg = msg

class BroadcastStateAction(AgentAction):
    """
    ## Broadcast Message Action 

    Instructs an agent to broadcast its state to all of its peers

    ### Attributes:
        - action_type (`str`): type of action to be performed
        - t_start (`float`): start time of this action in [s] from the beginning of the simulation
        - t_end (`float`): start time of this actrion in[s] from the beginning of the simulation
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
        Creates an instance of a Broadcast State Action

        ### Arguments
            - t_start (`float`): start time of this action in [s] from the beginning of the simulation
            - t_end (`float`): start time of this actrion in[s] from the beginning of the simulation
            - status (`str`): completion status of the task
            - id (`str`) : identifying number for this task in uuid format
        """
        super().__init__(ActionTypes.BROADCAST_STATE.value, t_start, t_end, status, id)

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
                msg : SimulationMessage,
                t_start : Union[float, int] = 0.0,
                t_end : Union[float, int] = numpy.Inf, 
                status : str = 'PENDING',
                id: str = None, 
                **_) -> None:
        """
        Creates an instance of a Broadcast Message Action

        ### Arguments
            - msg (`dict`): message to be broadcasted to other agents in the network
            - t_start (`float`): start time of this action in [s] from the beginning of the simulation
            - t_end (`float`): start time of this actrion in[s] from the beginning of the simulation
            - status (`str`): completion status of the task
            - id (`str`) : identifying number for this task in uuid format
        """
        super().__init__(ActionTypes.BROADCAST_MSG.value, t_start, t_end, status, id)
        self.msg = msg

class MoveAction(AgentAction):
    """
    ## Move Action

    Instructs an agent to move to a particular position
    
    ### Attributes:
        - pos (`list`): cartesian coordinates of the destination
        - t_start (`float`): start time of the availability of this task in [s] from the beginning of the simulation
        - t_end (`float`): end time of the availability of this task in [s] from the beginning of the simulation
        - id (`str`) : identifying number for this task in uuid format
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
        - pos (`list`): cartesian coordinates of the location of this task
        - s_max (`float`): maximum score attained from performing this task
        - instruments (`list`): name of the instruments that can perform this task
        - duration (`float`): duration of the measurement being performed
        - t_start (`float`): start time of the availability of this task in [s] from the beginning of the simulation
        - t_end (`float`): end time of the availability of this task in [s] from the beginning of the simulation
        - t_corr (`float`): maximum decorralation time between measurements of different measurements
        - id (`str`) : identifying number for this task in uuid format
    """        
    def __init__(self, 
                pos : list, 
                s_max : float,
                measurements : list,
                t_start: Union[float, int], 
                t_end: Union[float, int], 
                t_corr: Union[float, int] = 0.0,
                duration: Union[float, int] = 0.0, 
                urgency: Union[float, int] = None,  
                status: str = 'PENDING', 
                id: str = None, **_
                ) -> None:
        """
        Creates an instance of a task 

        ### Arguments:
            - pos (`list`): cartesian coordinates of the location of this task
            - s_max (`float`): maximum score attained from performing this task
            - measurements (`list`): list of the measurements that are needed to fully perform this task
            - t_start (`float`): start time of the availability of this task in [s] from the beginning of the simulation
            - t_end (`float`): end time of the availability of this task in [s] from the beginning of the simulation
            - t_corr (`float`): maximum decorralation time between measurements of different measurements
            - id (`str`) : identifying number for this task in uuid format
        """
        super().__init__(ActionTypes.MEASURE.value, t_start, t_end, status, id)
        self.duration = duration

        # check arguments
        if not isinstance(pos, list):
            raise AttributeError(f'`pos` must be of type `list`. is of type {type(pos)}.')
        elif len(pos) != 2:
            raise ValueError(f'`pos` must be a list of 2 values. is of length {len(pos)}.')
        if not isinstance(s_max, float) and not isinstance(s_max, int):
            raise AttributeError(f'`s_max` must be of type `float` or type `int`. is of type {type(s_max)}.')
        if not isinstance(measurements, list):
            raise AttributeError(f'`instruments` must be of type `list`. is of type {type(measurements)}.')
        else:
            for measurement in measurements:
                if not isinstance(measurement, str):
                    raise AttributeError(f'`measurements` must a `list` of elements of type `str`. contains elements of type {type(measurement)}.')
        
        self.pos = pos
        self.s_max = s_max
        self.measurements = measurements    
        self.t_corr = t_corr
        if urgency is not None:
            self.urgency = urgency
        else:
            self.urgency = numpy.log(1e-3) / (t_start - t_end)
        
        self.measurement_groups = self.generate_measurement_groups(measurements)
        self.dependency_matrix = self.generate_dependency_matrix()

    def generate_measurement_groups(self, measurements) -> list:
        """
        Generates all combinations of groups of measures to be performed by a single or multiple agents

        ### Arguments:
            - measurements (`list`): list of the measurements that are needed to fully perform this task

        ### Returns:
            - measurement_groups (`list`): list of measurement group tuples containing the main meausrement and a list of all dependent measurements
        """
        # create measurement groups
        n_measurements = len(measurements)
        measurement_groups = []
        for r in range(1, n_measurements+1):
            # combs = list(permutations(task_types, r))
            combs = list(combinations(measurements, r))
            
            for comb in combs:
                measurement_group = list(comb)

                main_measurement_permutations = list(permutations(comb, 1))
                for main_measurement in main_measurement_permutations:
                    main_measurement = list(main_measurement).pop()

                    dependend_measurements = copy.deepcopy(measurement_group)
                    dependend_measurements.remove(main_measurement)

                    if len(dependend_measurements) > 0:
                        measurement_groups.append((main_measurement, dependend_measurements))
                    else:
                        measurement_groups.append((main_measurement, []))
        
        return measurement_groups     
    
    def generate_dependency_matrix(self) -> list:
        # create dependency matrix
        dependency_matrix = numpy.zeros((len(self.measurement_groups), len(self.measurement_groups)))
        for index_a in range(len(self.measurement_groups)):
            main_a, dependents_a = self.measurement_groups[index_a]

            for index_b in range(index_a, len(self.measurement_groups)):
                main_b, dependents_b = self.measurement_groups[index_b]

                if index_a == index_b:
                    continue

                if len(dependents_a) != len(dependents_b):
                    dependency_matrix[index_a][index_b] = -1
                    dependency_matrix[index_b][index_a] = -1
                elif main_a not in dependents_b or main_b not in dependents_a:
                    dependency_matrix[index_a][index_b] = -1
                    dependency_matrix[index_b][index_a] = -1
                elif main_a == main_b:
                    dependency_matrix[index_a][index_b] = -1
                    dependency_matrix[index_b][index_a] = -1
                else:
                    dependents_a_extended : list = copy.deepcopy(dependents_a)
                    dependents_a_extended.remove(main_b)
                    dependents_b_extended : list = copy.deepcopy(dependents_b)
                    dependents_b_extended.remove(main_a)

                    if dependents_a_extended == dependents_b_extended:
                        dependency_matrix[index_a][index_b] = 1
                        dependency_matrix[index_b][index_a] = 1
                    else:
                        dependency_matrix[index_a][index_b] = -1
                        dependency_matrix[index_b][index_a] = -1
        
        return dependency_matrix

class IdleAction(AgentAction):
    """
    ## Idle Action

    Instructs an agent to idle for a given amount of time

    ### Attributes:
        - action_type (`str`): type of action to be performed
        - t_start (`float`): start time of this task in [s] from the beginning of the simulation
        - t_end (`float`): end time of this this task in [s] from the beginning of the simulation
        - status (`str`): completion status of the task
        - id (`str`) : identifying number for this task in uuid format
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
        super().__init__(   ActionTypes.WAIT_FOR_MSG.value, 
                            t_start, 
                            t_end, 
                            status, 
                            id
                            )