from abc import ABC, abstractmethod
import uuid
from typing import Union
from enum import Enum
import json

from dmas.clocks import *
from dmas.utils import *

class SimulationElementRoles(Enum):
    MANAGER = 'MANAGER'
    MONITOR = 'MONITOR'
    ENVIRONMENT = 'ENVIRONMENT'
    NODE = 'NODE'

class SimulationMessage(object):
    """
    ## Abstract Simulation Message 

    Describes a message to be sent between simulation elements

    ### Attributes:
        - src (`str`): name of the simulation element sending this message
        - dst (`str`): name of the intended simulation element to receive this message
        - msg_type (`str`): type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
    """
    def __init__(self, src : str, dst : str, msg_type : str, id : str = None):
        """
        Initiates an instance of a simulation message.
        
        ### Args:
            - src (`str`): name of the simulation element sending this message
            - dst (`str`): name of the intended simulation element to receive this message
            - msg_type (`str`): type of message being sent
            - id (`str`) : Universally Unique IDentifier for this message
        """
        super().__init__()

        # load attributes from arguments
        self.src = src
        self.dst = dst
        self.msg_type = msg_type
        self.id = str(uuid.UUID(id)) if id is not None else str(uuid.uuid1())

        # check types 
        if not isinstance(self.src , str):
            raise TypeError(f'Message sender `src` must be of type `str`. Is of type {type(self.src)}')
        if not isinstance(self.dst , str):
            raise TypeError(f'Message receiver `dst` must be of type `str`. Is of type {type(self.dst)}')
        if not isinstance(self.msg_type , str):
            raise TypeError(f'Message type `msg_type` must be of type `str`. Is of type {type(self.msg_type)}')
        if not isinstance(self.id , str):
            raise TypeError(f'Message id `id` must be of type `str`. Is of type {type(self.id)}')
        
    def __eq__(self, other) -> bool:
        """
        Compares two instances of a simulation message. Returns True if they represent the same message.
        """
        other : SimulationMessage
        return self.to_dict() == other.to_dict()

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        return dict(self.__dict__)

    def to_json(self) -> str:
        """
        Creates a json file from this message 
        """
        return json.dumps(self.to_dict())

    def __str__(self) -> str:
        """
        Creates a string representing the contents of this message
        """
        return str(self.to_dict())

"""
-----------------
SIMULATION MANAGER MESSAGES
-----------------
"""
class ManagerMessageTypes(Enum):
    """
    Types of broadcasts sent from the simulation manager to simulation members.
        - sim_info: informs all simulation elements of general simulation information
        - sim_start: notifies simulation membersthat the simulation has started
        - sim_end: notifies simulation members that the simulation has ended 
        - reception_ack: notifies a simulation member that its message request has been accepted by the manager
        - reception_ignored: notifies a simulation member that its message request has been ignored by the manager
    """
    SIM_INFO = 'SIM_INFO'
    SIM_START = 'SIM_START'
    SIM_END = 'SIM_END'
    RECEPTION_ACK = 'RECEPTION_ACKNOWLEDGED'
    RECEPTION_IGNORED = 'RECEPTION_ACKNOWLEDGED'
    TEST = 'TEST'

class ManagerMessage(SimulationMessage):
    """
    ## Abstract Simulation Message 

    Describes a message to be sent between simulation elements

    ### Attributes:
        - src (`str`): name of the simulation element sending this message
        - dst (`str`): name of the intended simulation element to receive this message
        - msg_type (`str`): type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
        - t (`float`): manager's simulation clock at the time of transmission in [s]
    """
    __doc__ += SimulationMessage.__doc__
    def __init__(self, dst : str, msg_type : str, t : float, id : uuid.UUID=None, **kwargs):
        """        
        Initialzies an instance of a Manager Message

        ### Arguments:
            - dst (`str`): name of the network set to receive this message when broadcasted
            - msg_type (`str`): type of message being sent
            - t (`float`): manager's simulation clock at the time of transmission in [s]
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(SimulationElementRoles.MANAGER.value, dst, msg_type, id)
        self.t = t

    def __str__(self) -> str:
        return f'{self.msg_type}'

class SimulationStartMessage(ManagerMessage):
    """
    ## Simulation Start Message

    Informs all simulation elements that the simulation has started 

    ### Attributes:
        - src (`str`): name of the simulation element sending this message
        - dst (`str`) = `SimulationElementTypes.ALL.name`: name of the intended simulation element to receive this message
        - msg_type (`str`) = `ManagerMessageTypes.SIM_START`: type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
        - t (`float`): manager's simulation clock at the time of transmission in [s]
    """
    def __init__(self, dst : str, t: Union[int, float], id : uuid.UUID = None, **kwargs):
        """
        Initializes an instance of a Simulaiton Start Message

        ### Arguments:
            - dst (`str`): name of the network being used to broadcast this message
            - t (`float`): manager's simulation clock at the time of transmission in [s]
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(dst, ManagerMessageTypes.SIM_START.value, t, id)

class SimulationEndMessage(ManagerMessage):
    """
    ## Simulation End Message

    Informs all simulation elements that the simulation has ended 

    ### Attributes:
        - _src (`str`): name of the simulation element sending this message
        - _dst (`str`) = `SimulationElementTypes.ALL.name`: name of the intended simulation element to receive this message
        - _msg_type (`str`) = `ManagerMessageTypes.SIM_END`: type of message being sent
        - _id (`str`) : Universally Unique IDentifier for this message
        - _t (`float`): manager's simulation clock at the time of transmission in [s]
    """
    def __init__(self, dst : str, t: Union[int, float], id : uuid.UUID = None, **kwargs):
        """
        Initializes an instance of a Simulaiton Start Message

        ### Arguments:
            - dst (`str`): name of the network being used to broadcast this message
            - t (`float`): manager's simulation clock at the time of transmission in [s]
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(dst, ManagerMessageTypes.SIM_END.value, t, id)

class SimulationInfoMessage(ManagerMessage):
    """
    ## Simulation Information Message 

    Message from the simulation manager informing all elements of the simulation that informs them of general information about the simulation.
    
    ### Attributes:
        - src (`str`) = `SimulationElementTypes.MANAGER.name`: name of the simulation element sending this message
        - dst (`str`) = `SimulationElementTypes.ALL.name`: name of the intended simulation element to receive this message
        - msg_type (`str`) = `ManagerMessageTypes.SIM_INFO`: type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
        - t (`float`): manager's simulation clock at the time of transmission in [s]
        - address_ledger (`dict`): dictionary mapping simulation element names to network addresses to be used for peer-to-peer communication or broadcast subscription
        - clock_config (:obj:`dict`): dictionary discribing a config object containing information about the clock being used in this simulation
    """

    def __init__(self, dst : str, address_ledger: dict, clock_config: dict, t: float, id : uuid.UUID = None, **kwargs):
        """
        Initiallizes and instance of a Simulation Start Message

        ### Arguments:
            - network_name (`str`): name of the network being used to broadcast this message
            - address_ledger (`dict`): dictionary mapping agent node names to network addresses to be used for peer-to-peer communication
            - clock_config (:obj:`ClockConfig`): config object containing information about the clock being used in this simulation
            - t (`float`): manager's simulation clock at the time of transmission in [s]
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message            
        """
        super().__init__(dst, ManagerMessageTypes.SIM_INFO.value, t, id)

        self.address_ledger = address_ledger.copy()
        self.clock_config = clock_config.copy()

    def get_address_ledger(self) -> dict:
        """
        Returns the address ledger sent from the manager
        """
        return self.address_ledger.copy()

    def get_clock_info(self) -> dict:
        """
        Returns clock information being shared accross the simulation
        """
        return self.clock_config    

class ManagerReceptionAckMessage(ManagerMessage):
    """
    ## Reception Accepted Message

    Notifies a simulation member that its message request has been accepted by the manager
        
    ### Attributes:
        - src (`str`): name of the simulation element sending this message
        - dst (`str`) = `SimulationElementTypes.ALL.name`: name of the intended simulation element to receive this message
        - msg_type (`str`) = `ManagerMessageTypes.RECEPTION_ACK`: type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
        - t (`float`): manager's simulation clock at the time of transmission in [s]
    """
    def __init__(self, dst : str, t : float, id : uuid.UUID = None, **kwargs):
        """
        Initializes an instance of a Reception Accepted Message

        #### Arguments:
            - dst (`str`): name of the network being used to broadcast this message
            - t (`float`): manager's simulation clock at the time of transmission in [s]
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(dst, ManagerMessageTypes.RECEPTION_ACK.value, t, id)

class ManagerReceptionIgnoredMessage(ManagerMessage):
    """
    ## Reception Ignored Message

    Notifies a simulation member that its message request has been ignored by the manager

    ### Attributes:
        - src (`str`): name of the simulation element sending this message
        - dst (`str`) = `SimulationElementTypes.ALL.name`: name of the intended simulation element to receive this message
        - msg_type (`str`) = `ManagerMessageTypes.RECEPTION_IGNORED`: type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
        - t (`float`): manager's simulation clock at the time of transmission in [s]
    """
    def __init__(self, dst : str, t : float, id : uuid.UUID = None, **kwargs):
        """
        Initializes an instance of a Sync Request Denied Message

        #### Arguments
            - dst (`str`): name of the network being used to broadcast this message
            - t (`float`): manager's simulation clock at the time of transmission in [s]
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message            
        """
        super().__init__(dst, ManagerMessageTypes.RECEPTION_IGNORED.value, t, id)

"""
-----------------
NODE MESSAGES
-----------------
"""
class NodeMessageTypes(Enum):
    """
    Types of messages to be sent from a simulated agent
        1- SimulationSyncRequest: notifies the simulation manager that the sending node is online.
        2- NodeReady:  notifies the simulation manager that the sending node is ready to start the simulation
        3- NodeDeactivated:  notifies the simulation manager that the sending node is offline.
        4- ReceptionAck: notifies a network element that a message has been received and accepted by the sending simulation node
        5- ReceptionIgnored: notifies a network element that a message has been received but not accepted by ther sending simulation node
        6- ModuleDeactivate: instructs an internal module to terminate its process
    """
    TEST = 'TEST'
    SYNC_REQUEST = 'SYNC_REQUEST'
    NODE_READY = 'NODE_READY'
    NODE_DEACTIVATED = 'NODE_DEACTIVATED'
    RECEPTION_ACK = 'RECEPTION_ACK'
    RECEPTION_IGNORED = 'RECEPTION_IGNORED'
    MODULE_DEACTIVATE = 'MODULE_DEACTIVATE'

class NodeSyncRequestMessage(SimulationMessage):
    """
    ## Sync Request Message

    Request from a simulation node to synchronize with the simulation manager

    ### Attributes:
        - src (`str`): name of the simulation node sending this message
        - dst (`str`): name of the intended simulation element to receive this message
        - msg_type (`str`): type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
        - network_config (`dict`): dictiory discribing a network configuration from sender node
    """

    def __init__(self, src: str, network_config : dict, id : uuid.UUID = None, **kwargs):
        """
        Initializes an instance of a Sync Request Message

        ### Arguments:
            - src (`str`): name of the simulation node sending this message
            - network_config (:obj:`NodeNetworkConfig`): network configuration from sender node
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(src, SimulationElementRoles.MANAGER.value, NodeMessageTypes.SYNC_REQUEST.value, id)
        self.network_config = network_config

    def get_network_config(self) -> dict:
        """
        Returns a dictionary describing the network configuration from the sender of this message
        """
        return self.network_config

class NodeReadyMessage(SimulationMessage):
    """
    ## Node Ready Message

    Informs the simulation manager that a simulation node has activated and is ready to start the simulation

    ### Attributes:
        - src (`str`): name of the simulation node sending this message
        - dst (`str`): name of the intended simulation element to receive this message
        - msg_type (`str`): type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
    """
    def __init__(self, src: str, id : uuid.UUID = None, **kwargs):
        """
        Initializes an instance of a Node Ready Message

        ### Arguments:
            - src (`str`): name of the simulation node sending this message
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(src, SimulationElementRoles.MANAGER.value, NodeMessageTypes.NODE_READY.value, id)

class NodeDeactivatedMessage(SimulationMessage):
    """
    ## Node Deactivated Message

    Informs the simulation manager that a simulation node has deactivated

    ### Attributes:
        - src (`str`): name of the simulation node sending this message
        - dst (`str`): name of the intended simulation element to receive this message
        - msg_type (`str`): type of message being sent
        - id (`uuid.UUID`) : Universally Unique IDentifier for this message
    """
    def __init__(self, src: str, id : uuid.UUID = None, **kwargs):
        """
        Initializes an instance of a Node Deactivated Message

        ### Arguments:
            - src (`str`): name of the simulation node sending this message
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(src, SimulationElementRoles.MANAGER.value, NodeMessageTypes.NODE_DEACTIVATED.value, id)

class NodeReceptionAckMessage(SimulationMessage):
    """
    ## Reception Acknowledged Message

    Notifies an network element that that its message has been accepted by the sending simulation node
        
    ### Attributes:
        - src (`str`): name of the simulation node sending this message
        - dst (`str`): name of the network element set to receive this message
        - msg_type (`str`) = `ManagerMessageTypes.RECEPTION_ACK`: type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
    """
    def __init__(self, src : str, dst : str, id : uuid.UUID = None, **kwargs):
        """
        Initializes an instance of a Reception Accepted Message

        #### Arguments:
            - src (`str`): name of the simulation node sending this message
            - dst (`str`): name of the network element set to receive this message
            - t (`float`): manager's simulation clock at the time of transmission in [s]
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(src, dst, NodeMessageTypes.RECEPTION_ACK.value, id)

class NodeReceptionIgnoredMessage(SimulationMessage):
    """
    ## Reception Accepted Message

    Notifies an network element that that its message has been accepted by the sending simulation node
        
    ### Attributes:
        - src (`str`): name of the simulation node sending this message
        - dst (`str`): name of the network element set to receive this message
        - msg_type (`str`) = `ManagerMessageTypes.RECEPTION_ACK`: type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
    """
    def __init__(self, src : str, dst : str, id : uuid.UUID = None, **kwargs):
        """
        Initializes an instance of a Reception Accepted Message

        #### Arguments:
            - src (`str`): name of the simulation node sending this message
            - dst (`str`): name of the network element set to receive this message
            - t (`float`): manager's simulation clock at the time of transmission in [s]
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(src, dst, NodeMessageTypes.RECEPTION_IGNORED.value, id)

class TerminateInternalModuleMessage(SimulationMessage):
    """
    ## Terminate Internal Module Message

    Insturcts an internal module to terminate its processes.

    ### Attributes:
        - src (`str`): name of the simulation node sending this message
        - dst (`str`): name of the intended simulation element to receive this message
        - msg_type (`str`) = NodeMessageTypes.MODULE_DEACTIVATE: type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
    """

    def __init__(self, src: str, dst: str, id: uuid.UUID = None, **kwargs):
        """
        Initializes an instance of a Terminate Internal Module Message

        ### Arguments:
            - src (`str`): name of the simulation node sending this message
            - dst (`str`): name of the intended simulation element to receive this message
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(src, dst, NodeMessageTypes.MODULE_DEACTIVATE.value, id)

"""
-----------------
INTERNAL MODULE MESSAGES
-----------------
"""
class ModuleMessageTypes(Enum):
    """
    Types of messages to be sent from a simulated agent
        1- SimulationSyncRequest: notifies the parent node that the sending module is online.
        2- ModuleReady: notifies the parent node that the sending module is ready to start the simulation
        2- ModuleDeactivated: notifies the parent node that the sending module is offline.
    """
    SYNC_REQUEST = 'SYNC_REQUEST'
    MODULE_READY = 'MODULE_READY'
    MODULE_DEACTIVATED = 'MODULE_DEACTIVATED'

class ModuleSyncRequestMessage(SimulationMessage):
    """
    ## Module Sync Request Message

    Notifies the parent node that the sending module is online

    ### Attributes:
        - src (`str`): name of the internal module sending this message
        - dst (`str`): name of the simulation node to receive this message
        - msg_type (`str`): type of message being sent
        - id (`str`) : Universally Unique IDentifier for this message
    """

    def __init__(self, src: str, dst: str, id : uuid.UUID = None, **kargs):
        """
        Initializes an instance of a Sync Request Message

        ### Arguments:
            - src (`str`): name of the internal module sending this message
            - dst (`str`): name of the simulation node to receive this message
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(src, dst, ModuleMessageTypes.SYNC_REQUEST.value, id)
