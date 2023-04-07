from enum import Enum
import json
import uuid

from dmas.messages import SimulationMessage


class Task(object):
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
                x : list, 
                s_max : float, 
                instrument : str,
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
        if not isinstance(x, list):
            raise AttributeError(f'`x` must be of type `list`. is of type {type(x)}.')
        elif len(x) != 2:
            raise ValueError(f'`x` must be a list of 2 values. is of length {len(x)}.')
        if not isinstance(s_max, float) and not isinstance(s_max, int):
            raise AttributeError(f'`s_max` must be of type `float` or type `int`. is of type {type(s_max)}.')
        if not isinstance(instrument, str):
            raise AttributeError(f'`instrument` must be of type `str`. is of type {type(instrument)}.')
        if not isinstance(t_start, float) and not isinstance(t_start, int):
            raise AttributeError(f'`t_start` must be of type `float` or type `int`. is of type {type(t_start)}.')
        elif t_start < 0:
            raise ValueError(f'`t_start` must be a value higher than 0. is of value {t_start}.')
        if not isinstance(t_end, float) and not isinstance(t_end, int):
            raise AttributeError(f'`t_end` must be of type `float` or type `int`. is of type {type(t_end)}.')
        elif t_end < 0:
            raise ValueError(f'`t_end` must be a value higher than 0. is of value {t_end}.')
        
        self.x = x
        self.s_max = s_max
        self.instrument = instrument
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

if __name__ == '__main__':
    src = 'TEST_SRC'
    dst = 'TEST_DST'
    id = str(uuid.uuid1())
    
    task_1 = Task([1,1], 1.0, 'INS', 0.0, 1.0, id)
    task_2 = Task([1,1], 1.0, 'INS', 0.0, 1.0)

    assert task_1 == Task(**task_1.to_dict())
    assert task_1 != task_2
    