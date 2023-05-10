from enum import Enum
from dmas.messages import *

class SimulationMessageTypes(Enum):
    TASK_REQ = 'TASK_REQUEST'
    AGENT_ACTION = 'AGENT_ACTION'
    AGENT_STATE = 'AGENT_STATE'
    CONNECTIVITY_UPDATE = 'CONNECTIVITY_UPDATE'
    PLANNER_RESULTS = 'PLANNER_RESULTS'
    TASK_BID = 'TASK_BID'
    PLAN = 'PLAN'
    SENSES = 'SENSES'
    MEASUREMENT = 'MEASUREMENT'

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

class MeasurementResultsRequest(SimulationMessage):
    """
    ## Measurement Results Request Message 

    Carries information regarding a measurement performed on the environment

    ### Attributes:
        - src (`str`): name of the simulation element sending this message
        - dst (`str`): name of the intended simulation element to receive this message
        - msg_type (`str`): type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
        - measurement (`dict`) : measurement data being communicated
    """
    def __init__(self, src: str, dst: str, masurement_req : dict, id: str = None, **_):
        super().__init__(src, dst, SimulationMessageTypes.MEASUREMENT.value, id)
        
        if not isinstance(masurement_req, dict):
            raise AttributeError(f'`measurement_request_id` must be of type `dict`; is of type {type(masurement_req)}.')

        self.masurement_req = masurement_req
        self.measurement = {}

class PlannerResultsMessage(SimulationMessage):
    """
    ## Planner Update Message 

    Informs another agents of the current or proposed plan to be executed by the sender

    ### Attributes:
        - src (`str`): name of the simulation element sending this message
        - dst (`str`): name of the intended simulation element to receive this message
        - msg_type (`str`): type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
    """
    def __init__(self, src: str, dst: str, planner_results : dict, id: str = None, **_):
        super().__init__(src, dst, SimulationMessageTypes.PLANNER_RESULTS.value, id)
        self.planner_results = planner_results

class TaskBidMessage(SimulationMessage):
    """
    ## Task Bid Message

    Informs another agents of the bid information held by the sender

    ### Attributes:
        - src (`str`): name of the simulation element sending this message
        - dst (`str`): name of the intended simulation element to receive this message
        - bid (`dict`): bid information being shared
        - msg_type (`str`): type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
    """
    def __init__(self, 
                src: str, 
                dst: str, 
                bid: dict, 
                id: str = None, **_):
        """
        Creates an instance of a task bid message

        ### Arguments:
            - src (`str`): name of the simulation element sending this message
            - dst (`str`): name of the intended simulation element to receive this message
            - bid (`dict`): bid information being shared
            - id (`str`) : Universally Unique IDentifier for this message
        """
        super().__init__(src, dst, SimulationMessageTypes.TASK_BID.value, id)
        self.bid = bid

class PlanMessage(SimulationMessage):
    """
    # Plan Message
    
    Informs an agent of a set of tasks to perform. 
    Sent by either an external or internal planner

    ### Attributes:
        - src (`str`): name of the simulation element sending this message
        - dst (`str`): name of the intended simulation element to receive this message
        - plan (`list`): list of agent actions to perform
        - msg_type (`str`): type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
    """
    def __init__(self, src: str, dst: str, plan : list, id: str = None, **_):
        """
        Creates an instance of a plan message

        ### Attributes:
            - src (`str`): name of the simulation element sending this message
            - dst (`str`): name of the intended simulation element to receive this message
            - plan (`list`): list of agent actions to perform
            - id (`str`) : Universally Unique IDentifier for this message
        """
        super().__init__(src, dst, SimulationMessageTypes.PLAN.value, id)
        self.plan = plan

class SensesMessage(SimulationMessage):
    """
    # Plan Message
    
    Informs an agent of a set of tasks to perform. 
    Sent by either an external or internal planner

    ### Attributes:
        - src (`str`): name of the simulation element sending this message
        - dst (`str`): name of the intended simulation element to receive this message
        - senses (`list`): list of senses from the agent
        - msg_type (`str`): type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
    """
    def __init__(self, src: str, dst: str, state : dict, senses : list, id: str = None, **_):
        """
        Creates an instance of a plan message

        ### Attributes:
            - src (`str`): name of the simulation element sending this message
            - dst (`str`): name of the intended simulation element to receive this message
            - senses (`list`): list of senses from the agent
            - id (`str`) : Universally Unique IDentifier for this message
        """
        super().__init__(src, dst, SimulationMessageTypes.SENSES.value, id)
        self.state = state
        self.senses = senses

class AgentActionMessage(SimulationMessage):
    """
    ## Agent Action Message

    Informs the receiver of a action to be performed and its completion status
    """
    def __init__(self, src: str, dst: str, action : dict, status : str=None, id: str = None, **_):
        super().__init__(src, dst, SimulationMessageTypes.AGENT_ACTION.value, id)
        self.action = action
        self.status = None
        self.status = status if status is not None else action.get('status', None)
