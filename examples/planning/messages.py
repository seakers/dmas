
from enum import Enum

from tasks import Task
from dmas.messages import SimulationMessage

class SimulationMessageTypes(Enum):
    TASK_REQ = 'TASK_REQUEST'

class TaskRequest(SimulationMessage):
    """
    ## Task Request Message 

    Describes a task request being between simulation elements

    ### Attributes:
        - src (`str`): name of the simulation element sending this message
        - dst (`str`): name of the intended simulation element to receive this message
        - msg_type (`str`): type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
        - t (`float`): manager's simulation clock at the time of transmission in [s]
    """
    def __init__(self, src: str, dst: str, task : dict, id: str = None, **kwargs):
        super().__init__(src, dst, SimulationMessageTypes.TASK_REQ.value, id)
        self.task = Task(**task)

if __name__ == '__main__':
    pass