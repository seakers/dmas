
from enum import Enum

from tasks import Task
from dmas.messages import SimulationMessage

class SimulationMessageTypes(Enum):
    TASK_REQ = 'TASK_REQUEST'

class TaskRequest(SimulationMessage):
    def __init__(self, src: str, dst: str, task : dict, id: str = None, **kwargs):
        super().__init__(src, dst, SimulationMessageTypes.TASK_REQ.value, id)
        self.task = Task(**task)

if __name__ == '__main__':
    pass