from enum import Enum
import json
import uuid

from dmas.messages import SimulationMessage


class AgentTask(object):
    """
    Describes a task to be performed by the agents in the simulation

    ### Attributes:
        - x (`list`): cartesian coordinates of the location of this task
        - s_max (`float`): maximum score attained from performing this task
        - instrument (`str`): name of the instrument that can perform this task
        - t_start (`float`): start time of the availability of this task in [s] from the beginning of the simulation
        - t_end (`float`): end time of the availability of this task in [s] from the beginning of the simulation
    """
    def __init__(self, 
                pos : list, 
                s_max : float, 
                instruments : list,
                t_start : float,
                t_end : float,
                id : str = None) -> None:
        """
        Creates an instance of a task 

        ### Arguments:
            - x (`list`): cartesian coordinates of the location of this task
            - s_max (`float`): maximum score attained from performing this task
            - instrument (`str`): name of the instrument that can perform this task
            - t_start (`float`): start time of the availability of this task in [s] from the beginning of the simulation
            - t_end (`float`): end time of the availability of this task in [s] from the beginning of the simulation
        """
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

        if not isinstance(t_start, float) and not isinstance(t_start, int):
            raise AttributeError(f'`t_start` must be of type `float` or type `int`. is of type {type(t_start)}.')
        elif t_start < 0:
            raise ValueError(f'`t_start` must be a value higher than 0. is of value {t_start}.')
        if not isinstance(t_end, float) and not isinstance(t_end, int):
            raise AttributeError(f'`t_end` must be of type `float` or type `int`. is of type {type(t_end)}.')
        elif t_end < 0:
            raise ValueError(f'`t_end` must be a value higher than 0. is of value {t_end}.')
        
        self.pos = pos
        self.s_max = s_max
        self.instruments = instruments
        self.t_start = t_start
        self.t_end = t_end
        self.id = str(uuid.UUID(id)) if id is not None else str(uuid.uuid1())

    def __eq__(self, other) -> bool:
        """
        Compares two instances of a measurement task. Returns True if they represent the same task.
        """
        return self.to_dict() == other.to_dict()

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this task object
        """
        return dict(self.__dict__)
    
    def to_json(self) -> str:
        """
        Creates a json file from this task 
        """
        return json.dumps(self.to_dict())

    def __str__(self) -> str:
        """
        Creates a string representing the contents of this task
        """
        return str(self.to_dict())
