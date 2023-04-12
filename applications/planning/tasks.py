from dmas.agents import AgentAction

class MeasurementTask(AgentAction):
    """
    Describes a measurement task to be performed by the agents in the simulation

    ### Attributes:
        - x (`list`): cartesian coordinates of the location of this task
        - s_max (`float`): maximum score attained from performing this task
        - instrument (`str`): name of the instrument that can perform this task
        - t_start (`float`): start time of the availability of this task in [s] from the beginning of the simulation
        - t_end (`float`): end time of the availability of this task in [s] from the beginning of the simulation
        - id (`str`) : identifying number for this task in uuid format
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
            - id (`str`) : identifying number for this task in uuid format
        """
        super().__init__(t_start, t_end, id)

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
    