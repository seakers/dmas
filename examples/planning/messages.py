
from enum import Enum
from typing import Union

from tasks import Task
from dmas.messages import SimulationMessage, SimulationElementRoles

class SimulationMessageTypes(Enum):
    TASK_REQ = 'TASK_REQUEST'
    TIC_REQ = 'TIC_REQUEST'
    TOC = 'TOC'

class TicRequest(SimulationMessage):
    """
    ## Tic Request Message

    Request from agents indicating that they are waiting for the next time-step advance

    ### Attributes:
        - src (`str`): name of the simulation element sending this message
        - dst (`str`): name of the intended simulation element to receive this message
        - msg_type (`str`): type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
        - t0 (`float` or `int`): current time registered by the agent
        - tf (`float` or `int`): desired time to be reached by agent
    """
    def __init__(self, src: str, t0 : Union[float, int], tf : Union[float, int], id: str = None, **_):
        super().__init__(src, SimulationElementRoles.MANAGER.value, SimulationMessageTypes.TIC_REQ.value, id)
        
        # check types
        if not isinstance(t0 , float) and not isinstance(t0 , int):
            raise TypeError(f'`t0` must be of type `float` or `int`. Is of type {type(t0)}')
        if not isinstance(tf , float) and not isinstance(tf , int):
            raise TypeError(f'`tf` must be of type `float` or `int`. Is of type {type(tf)}')

        self.t0 = t0
        self.tf = tf

class TocMessage(SimulationMessage):
    """
    ## Clock Update Message

    Informs all simulation elements that the simulation time has been updated

    ### Attributes:
        - src (`str`): name of the simulation element sending this message
        - dst (`str`): name of the intended simulation element to receive this message
        - msg_type (`str`): type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
        - t (`float` or `int`): new current simulation time
    """
    def __init__(self, src: str, dst: str, t: Union[float, int], id: str = None, **_):
        super().__init__(src, dst, SimulationMessageTypes.TOC.value, id)

        # check type
        if not isinstance(t , float) and not isinstance(t , int):
            raise TypeError(f'`t` must be of type `float` or `int`. Is of type {type(t)}')
        
        self.t = t

class TaskRequest(SimulationMessage):
    """
    ## Task Request Message 

    Describes a task request being between simulation elements

    ### Attributes:
        - src (`str`): name of the simulation element sending this message
        - dst (`str`): name of the intended simulation element to receive this message
        - msg_type (`str`): type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
    """
    def __init__(self, src: str, dst: str, task : dict, id: str = None, **kwargs):
        super().__init__(src, dst, SimulationMessageTypes.TASK_REQ.value, id)
        self.task = Task(**task)

if __name__ == '__main__':
    pass