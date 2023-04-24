from enum import Enum
from dmas.messages import *

class SimulationMessageTypes(Enum):
    TASK_REQ = 'TASK_REQUEST'
    AGENT_ACTION = 'AGENT_ACTION'
    AGENT_STATE = 'AGENT_STATE'
    CONNECTIVITY_UPDATE = 'CONNECTIVITY_UPDATE'
    PLANNER_UPDATE = 'PLANNER_UPDATE'

class AgentStateMessage(SimulationMessage):
    """
    ## Tic Request Message

    Request from agents indicating that they are waiting for the next time-step advance

    ### Attributes:
        - src (`str`): name of the agent sending this message
        - dst (`str`): name of the intended simulation element to receive this message
        - msg_type (`str`): type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
        - state (`dict`): dictionary discribing the state of the agent sending this message
    """
    def __init__(self, 
                src: str, 
                dst: str, 
                state : dict,
                id: str = None, 
                **_):
        super().__init__(src, dst, SimulationMessageTypes.AGENT_STATE.value, id)
        self.state = state

class AgentConnectivityUpdate(SimulationMessage):
    """
    ## Agent Connectivity Update Message

    Informs an agent that it's connectivity to another agent has changed

    ### Attributes:
        - src (`str`): name of the agent sending this message
        - dst (`str`): name of the intended agent set to receive this message
        - target (`str`): name of the agent that the destination agent will change its connectivity with
        - connected (`bool`): status of the connection between `dst` and `target`
        - msg_type (`str`): type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
        - state (`dict`): dictionary discribing the state of the agent sending this message
    """
    def __init__(self, dst: str, target : str, connected : int, id: str = None, **_):
        super().__init__(SimulationElementRoles.ENVIRONMENT.value, 
                         dst, 
                         SimulationMessageTypes.CONNECTIVITY_UPDATE.value, 
                         id)
        self.target = target
        self.connected = connected

class TaskRequest(SimulationMessage):
    """
    ## Task Request Message 

    Describes a task request being between simulation elements

    ### Attributes:
        - src (`str`): name of the simulation element sending this message
        - dst (`str`): name of the intended simulation element to receive this message
        - msg_type (`str`): type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
        - task (`dict`) : task request to be performed
    """
    def __init__(self, src: str, dst: str, task : dict, id: str = None, **_):
        super().__init__(src, dst, SimulationMessageTypes.TASK_REQ.value, id)
        
        if not isinstance(task, dict):
            raise AttributeError(f'`task` must be of type `dict`; is of type {type(task)}.')
        self.task = task

class PlannerUpdate(SimulationMessage):
    """
    ## Planner Update Message 

    Informs another agent of the current or proposed plan to be executed by the sender

    ### Attributes:
        - src (`str`): name of the simulation element sending this message
        - dst (`str`): name of the intended simulation element to receive this message
        - msg_type (`str`): type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
    """
    def __init__(self, src: str, dst: str, planner_results : dict, id: str = None, **_):
        super().__init__(src, dst, SimulationMessageTypes.PLANNER_UPDATE.value, id)
        self.planner_results = planner_results

class AgentActionMessage(SimulationMessage):
    """
    ## Agent Action Message

    Informs the receiver of a action to be performed and its completion status
    """
    def __init__(self, src: str, dst: str, action : dict, status : str=None, id: str = None, **_):
        super().__init__(src, dst, SimulationMessageTypes.AGENT_ACTION.value, id)
        self.action = action
        self.status = status if status is not None else action.get('status')