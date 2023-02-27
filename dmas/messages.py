from abc import ABC, abstractmethod
import uuid
from beartype import beartype
from typing import Union
from enum import Enum
import json

from dmas.utils import *

class SimulationElementRoles(Enum):
    MANAGER = 'MANAGER'
    MONITOR = 'MONITOR'
    ENVIRONMENT = 'ENVIRONMENT'
    NODE = 'NODE'
    ALL = 'ALL'

class SimulationMessage(ABC):
    """
    ## Abstract Simulation Message 

    Describes a message to be sent between simulation elements

    ### Attributes:
        - _src (`str`): name of the simulation element sending this message
        - _dst (`str`): name of the intended simulation element to receive this message
        - _msg_type (`Enum`): type of message being sent
        - _id (`uuid.UUID`) : Universally Unique IDentifier for this message
    """
    def __init__(self, src: str, dst: str, msg_type: Enum, id : uuid.UUID = None):
        """
        Initiates an instance of a simulation message.
        
        ### Args:
            - src (`str`): name of the simulation element sending this message
            - dst (`str`): name of the intended simulation element to receive this message
            - msg_type (`str`): type of message being sent
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        self._src = src
        self._dst = dst
        self._msg_type = msg_type
        self._id = id if id is not None else uuid.uuid1()
    
    def get_src(self) -> str:
        """
        Returns name of the original sender this message
        """
        return self._src
    
    def get_dst(self) -> str:
        """
        Returns name of the intended receiver of this message
        """
        return self._dst

    def get_type(self) -> Enum:
        """
        Returns the type of message being sent
        """
        return self._msg_type

    def get_id(self) -> uuid.UUID:
        """
        Returns if of the message being sent
        """
        return self._id

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        msg_dict = dict()
        msg_dict['src'] = self._src
        msg_dict['dst'] = self._dst
        msg_dict['@type'] = self._msg_type.name
        msg_dict['@id'] = str(self._id)
        return msg_dict

    def to_json(self) -> str:
        """
        Creates a json file from this message 
        """
        return json.dumps(self.to_dict())
    
    @abstractmethod
    def from_dict(d : dict):
        """
        Creates an instance of a message class object from a dictionary 
        """
        pass

    @abstractmethod
    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        pass

    @abstractmethod
    def __str__(self) -> str:
        """
        Creates a string representing the contents of this message
        """
        pass

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

class ManagerMessage(SimulationMessage, ABC): 
    """
    ## Manager Message

    Describes a message being brodcasted from the simulation manager to all simulation elements.

    ### Attributes:
        - _src (`str`): name of the simulation element sending this message
        - _dst (`str`) = `SimulationElementTypes.ALL.name`: name of the intended simulation element to receive this message
        - _msg_type (`Enum`): type of message being sent
        - _id (`uuid.UUID`) : Universally Unique IDentifier for this message
        - _t (`float`): manager's simulation clock at the time of transmission in [s]
    """
    def __init__(self, type: ManagerMessageTypes, t : Union[int, float], id : uuid.UUID = None):   
        """        
        Initialzies an instance of a Manager Message

        ### Arguments:
            - msg_type (`Enum`): type of message being sent
            - t (`float`): manager's simulation clock at the time of transmission in [s]
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(SimulationElementRoles.MANAGER.name, SimulationElementRoles.ALL.name, type, id)
        self._t = t

    def to_dict(self) -> dict:
        out = super().to_dict()
        out['t'] = self._t
        return out

    def __str__(self) -> str:
        return f'{self._msg_type.name}, t={self._t}'

class SimulationStartMessage(ManagerMessage):
    """
    ## Simulation Start Message

    Informs all simulation elements that the simulation has started 

    ### Attributes:
        - _src (`str`): name of the simulation element sending this message
        - _dst (`str`) = `SimulationElementTypes.ALL.name`: name of the intended simulation element to receive this message
        - _msg_type (`Enum`) = `ManagerMessageTypes.SIM_START`: type of message being sent
        - _id (`uuid.UUID`) : Universally Unique IDentifier for this message
        - _t (`float`): manager's simulation clock at the time of transmission in [s]
    """
    def __init__(self, t: Union[int, float], id : uuid.UUID = None):
        """
        Initializes an instance of a Simulaiton Start Message

        ### Arguments:
            - t (`float`): manager's simulation clock at the time of transmission in [s]
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(ManagerMessageTypes.SIM_START, t, id)

    def from_dict(d : dict):
        src = d.get('src', None)
        dst = d.get('dst', None)
        t = d.get('t', None)
        type_name = d.get('@type', None)
        id_str = d.get('@id', None)
        
        if src is None or dst is None or type_name is None or t is None or id_str is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in ManagerMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')
        elif _type is not ManagerMessageTypes.SIM_START:
            raise Exception(f'Cannot load a Node Simulation Message from a dictionary request of type {type_name}.')

        return SimulationStartMessage(t, uuid.UUID(id_str))

    def from_json(j):
        return SimulationStartMessage.from_dict(json.loads(j))

class SimulationEndMessage(ManagerMessage):
    """
    ## Simulation End Message

    Informs all simulation elements that the simulation has ended 

    ### Attributes:
        - _src (`str`): name of the simulation element sending this message
        - _dst (`str`) = `SimulationElementTypes.ALL.name`: name of the intended simulation element to receive this message
        - _msg_type (`Enum`) = `ManagerMessageTypes.SIM_END`: type of message being sent
        - _id (`uuid.UUID`) : Universally Unique IDentifier for this message
        - _t (`float`): manager's simulation clock at the time of transmission in [s]
    """
    def __init__(self, t: Union[int, float], id : uuid.UUID = None) -> None:
        """
        Initializes an instance of a Simulaiton End Message

        ### Arguments:
            - t (`float`): manager's simulation clock at the time of transmission in [s]
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(ManagerMessageTypes.SIM_END, t, id)

    def from_dict(d : dict):
        src = d.get('src', None)
        dst = d.get('dst', None)
        t = d.get('t', None)
        type_name = d.get('@type', None)
        id_str = d.get('@id', None)
        
        if src is None or dst is None or type_name is None or t is None or id_str is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in ManagerMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')
        elif _type is not ManagerMessageTypes.SIM_END:
            raise Exception(f'Cannot load a Simulation End Message from a dictionary request of type {type_name}.')

        return SimulationEndMessage(t, uuid.UUID(id_str))

    def from_json(j):
        return SimulationEndMessage.from_dict(json.loads(j))

class SimulationInfoMessage(ManagerMessage):
    """
    ## Simulation Information Message 

    Message from the simulation manager informing all elements of the simulation that informs them of general information about the simulation.
    
    ### Attributes:
        - _src (`str`) = `SimulationElementTypes.MANAGER.name`: name of the simulation element sending this message
        - _dst (`str`) = `SimulationElementTypes.ALL.name`: name of the intended simulation element to receive this message
        - _msg_type (`Enum`) = `ManagerMessageTypes.SIM_INFO`: type of message being sent
        - _id (`uuid.UUID`) : Universally Unique IDentifier for this message
        - _t (`float`): manager's simulation clock at the time of transmission in [s]
        - _address_ledger (`dict`): dictionary mapping simulation element names to network addresses to be used for peer-to-peer communication or broadcast subscription
        - _clock_config (:obj:`ClockConfig`): config object containing information about the clock being used in this simulation
    """

    def __init__(self, address_ledger: dict, clock_config: ClockConfig, t: float, id : uuid.UUID = None):
        """
        Initiallizes and instance of a Simulation Start Message

        ### Arguments:
            - address_ledger (`dict`): dictionary mapping agent node names to network addresses to be used for peer-to-peer communication
            - clock_config (:obj:`ClockConfig`): config object containing information about the clock being used in this simulation
            - t (`float`): manager's simulation clock at the time of transmission in [s]
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message            
        """
        super().__init__(ManagerMessageTypes.SIM_INFO, t, id)

        self._address_ledger = dict()
        for node_name in address_ledger:
            address_config = address_ledger[node_name]
            if isinstance(address_config, dict):
                address_config = NetworkConfig.from_dict(address_config)
            
            self._address_ledger[node_name] = address_config
        self._clock_config = clock_config        

    def get_address_ledger(self):
        """
        Returns the address ledger sent from the manager
        """
        return self._address_ledger.copy()

    def get_clock_info(self):
        return self._clock_config

    def to_dict(self) -> dict:
        msg_dict = super().to_dict()

        address_ledger = dict()
        for node_name in self._address_ledger:
            network_config : NetworkConfig = self._address_ledger[node_name]
            address_ledger[node_name] = network_config.to_dict()

        msg_dict['address ledger'] = address_ledger
        msg_dict['clock info'] = self._clock_config.to_dict()
        return msg_dict

    def from_dict(d : dict):
        type_name = d.get('@type', None)
        id_str = d.get('@id', None)
        t = d.get('t', None)
        address_ledger = d.get('address ledger', None)
        clock_info = d.get('clock info', None)

        if type_name is None or t is None or address_ledger is None or clock_info is None or id_str is None:
            raise AttributeError('Dictionary does not contain necessary information to construct this message object.')

        msg_type = None
        for name, member in ManagerMessageTypes.__members__.items():
            if name == type_name:
                msg_type = member

        if msg_type is None:
            raise AttributeError(f'Could not recognize simulation manager message of type {type_name}.')

        elif msg_type is not ManagerMessageTypes.SIM_INFO:
            raise AttributeError(f'Cannot load a Simulation Info Message from a dictionary of type {type_name}.')

        clock_type = clock_info['@type']
        if clock_type == ClockTypes.REAL_TIME.name:
            clock_info = RealTimeClockConfig.from_dict(clock_info)
        elif clock_type == ClockTypes.ACCELERATED_REAL_TIME.name:
            clock_info = AcceleratedRealTimeClockConfig.from_dict(clock_info)
        else:
            raise AttributeError(f'Could not recognize clock config of type {clock_type}.')

        address_ledger_dict = dict()
        for node_name in address_ledger:
            network_config_dict : dict = address_ledger[node_name]
            address_ledger_dict[node_name] = NetworkConfig.from_dict(network_config_dict)

        return SimulationInfoMessage(address_ledger, clock_config, t, uuid.UUID(id_str))

    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        return SimulationInfoMessage.from_dict(json.loads(j))

class ManagerReceptionAckMessage(ManagerMessage):
    """
    ## Reception Accepted Message

    Notifies a simulation member that its message request has been accepted by the manager
        
    ### Attributes:
        - _src (`str`): name of the simulation element sending this message
        - _dst (`str`) = `SimulationElementTypes.ALL.name`: name of the intended simulation element to receive this message
        - _msg_type (`Enum`) = `ManagerMessageTypes.RECEPTION_ACK`: type of message being sent
        - _id (`uuid.UUID`) : Universally Unique IDentifier for this message
        - _t (`float`): manager's simulation clock at the time of transmission in [s]
    """
    def __init__(self, t : float, id : uuid.UUID = None):
        """
        Initializes an instance of a Reception Accepted Message

        #### Arguments:
            - t (`float`): manager's simulation clock at the time of transmission in [s]
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(ManagerMessageTypes.RECEPTION_ACK, t, id)

    def from_dict(d: dict):
        src = d.get('src', None)
        dst = d.get('dst', None)
        t = d.get('t', None)
        type_name = d.get('@type', None)
        id_str = d.get('@id', None)
        
        if src is None or dst is None or type_name is None or t is None or id_str is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in ManagerMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')
        elif _type is not ManagerMessageTypes.RECEPTION_ACK:
            raise Exception(f'Cannot load a Node Simulation Message from a dictionary request of type {type_name}.')

        return ManagerReceptionAckMessage(t, uuid.UUID(id_str))

    def from_json(j):
        return ManagerReceptionAckMessage.from_dict(json.loads(j))

class ManagerReceptionIgnoredMessage(ManagerMessage):
    """
    ## Reception Ignored Message

    Notifies a simulation member that its message request has been ignored by the manager

    ### Attributes:
        - _src (`str`): name of the simulation element sending this message
        - _dst (`str`) = `SimulationElementTypes.ALL.name`: name of the intended simulation element to receive this message
        - _msg_type (`Enum`) = `ManagerMessageTypes.RECEPTION_IGNORED`: type of message being sent
        - _id (`uuid.UUID`) : Universally Unique IDentifier for this message
        - _t (`float`): manager's simulation clock at the time of transmission in [s]
    """
    def __init__(self, t : float, id : uuid.UUID = None):
        """
        Initializes an instance of a Sync Request Denied Message

        #### Arguments
            - t (`float`): manager's simulation clock at the time of transmission in [s]
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message            
        """
        super().__init__(ManagerMessageTypes.RECEPTION_IGNORED, t, id)

    def from_dict(d: dict):
        src = d.get('src', None)
        dst = d.get('dst', None)
        t = d.get('t', None)
        type_name = d.get('@type', None)
        id_str = d.get('@id', None)
        
        if src is None or dst is None or type_name is None or t is None or id_str is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in ManagerMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')
        elif _type is not ManagerMessageTypes.RECEPTION_IGNORED:
            raise Exception(f'Cannot load a Node Simulation Message from a dictionary request of type {type_name}.')

        return ManagerReceptionIgnoredMessage(t, uuid.UUID(id_str))

    def from_json(j):
        return ManagerReceptionIgnoredMessage.from_dict(json.loads(j))

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
        4- ReceptionIgnored: notifies a network element that a message has been received but not accepted by ther sending simulation node
    """
    SYNC_REQUEST = 'SYNC_REQUEST'
    NODE_READY = 'NODE_READY'
    NODE_DEACTIVATED = 'NODE_DEACTIVATED'
    RECEPTION_ACK = 'RECEPTION_ACK'
    RECEPTION_IGNORED = 'RECEPTION_IGNORED'
    MODULE_DEACTIVATE = 'MODULE_DEACTIVATE'

class TerminateInternalModuleMessage(SimulationMessage):
    """
    ## Terminate Internal Module Message

    Insturcts an internal module to terminate its processes.

    ### Attributes:
        - _src (`str`): name of the simulation node sending this message
        - _dst (`str`): name of the intended simulation element to receive this message
        - _msg_type (`Enum`) = NodeMessageTypes.MODULE_DEACTIVATE: type of message being sent
        - _id (`uuid.UUID`) : Universally Unique IDentifier for this message
    """

    def __init__(self, src: str, dst: str, id: uuid.UUID = None):
        """
        Initializes an instance of a Terminate Internal Module Message

        ### Arguments:
            - src (`str`): name of the simulation node sending this message
            - dst (`str`): name of the intended simulation element to receive this message
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(src, dst, NodeMessageTypes.MODULE_DEACTIVATE, id)
    
    def from_dict(d: dict):
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        id_str = d.get('@id', None)

        if src is None or dst is None or type_name is None or id_str is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in NodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')
        elif _type is not NodeMessageTypes.MODULE_DEACTIVATE:
            raise Exception(f'Cannot load a module terminate message from a dictionary request of type {type_name}.')

        return TerminateInternalModuleMessage(src, dst, uuid.UUID(id_str))
    
    def from_json(j):
        return TerminateInternalModuleMessage.from_dict(json.loads(j))

class NodeSyncRequestMessage(SimulationMessage):
    """
    ## Sync Request Message

    Request from a simulation node to synchronize with the simulation manager

    ### Attributes:
        - _src (`str`): name of the simulation node sending this message
        - _dst (`str`): name of the intended simulation element to receive this message
        - _msg_type (`Enum`): type of message being sent
        - _id (`uuid.UUID`) : Universally Unique IDentifier for this message
        - _network_config (:obj:`NetworkConfig`): network configuration from sender node
    """

    def __init__(self, src: str, network_config : NetworkConfig, id : uuid.UUID = None):
        """
        Initializes an instance of a Sync Request Message

        ### Arguments:
            - src (`str`): name of the simulation node sending this message
            - network_config (:obj:`NodeNetworkConfig`): network configuration from sender node
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(src, SimulationElementRoles.MANAGER.value, NodeMessageTypes.SYNC_REQUEST, id)
        self._network_config = network_config

    def get_network_config(self):
        """
        Returns the network configuration from the sender of this message
        """
        return self._network_config

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        msg_dict = super().to_dict()
        msg_dict['network config'] = self._network_config.to_dict()
        return msg_dict

    def from_dict(d : dict):
        """
        Creates an instance of a message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        id_str = d.get('@id', None)
        network_config = d.get('network config', None)

        if src is None or dst is None or type_name is None or network_config is None or id_str is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in NodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')
        elif _type is not NodeMessageTypes.SYNC_REQUEST:
            raise Exception(f'Cannot load a Sync Request from a dictionary request of type {type_name}.')

        network_config = NetworkConfig.from_dict(network_config)

        return NodeSyncRequestMessage(src, network_config, uuid.UUID(id_str))

    def from_json(d):
        """
        Creates an instance of a message class object from a json object 
        """
        return NodeSyncRequestMessage.from_dict(json.loads(d))

    def __str__(self) -> str:
        return f'{NodeMessageTypes.SYNC_REQUEST.name}'

class NodeReadyMessage(SimulationMessage):
    """
    ## Node Ready Message

    Informs the simulation manager that a simulation node has activated and is ready to start the simulation

    ### Attributes:
        - _src (`str`): name of the simulation node sending this message
        - _dst (`str`): name of the intended simulation element to receive this message
        - _msg_type (`Enum`): type of message being sent
        - _id (`uuid.UUID`) : Universally Unique IDentifier for this message
        - _network_config (:obj:`NetworkConfig`): network configuration from sender node
    """
    def __init__(self, src: str, id : uuid.UUID = None):
        """
        Initializes an instance of a Node Ready Message

        ### Arguments:
            - src (`str`): name of the simulation node sending this message
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(src, SimulationElementRoles.MANAGER.value, NodeMessageTypes.NODE_READY, id)
    
    def from_dict(d : dict):
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        id_str = d.get('@id', None)
        
        if src is None or dst is None or type_name is None or id_str is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in NodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')
        elif _type is not NodeMessageTypes.NODE_READY:
            raise Exception(f'Cannot load a Node Ready Message from a dictionary request of type {type_name}.')

        return NodeReadyMessage(src, uuid.UUID(id_str))

    def from_json(j):
        return NodeReadyMessage.from_dict(json.loads(j))

    def __str__(self) -> str:
        return f'{self._src} is ready!'

class NodeDeactivatedMessage(SimulationMessage):
    """
    ## Node Deactivated Message

    Informs the simulation manager that a simulation node has deactivated

    ### Attributes:
        - _src (`str`): name of the simulation node sending this message
        - _dst (`str`): name of the intended simulation element to receive this message
        - _msg_type (`Enum`): type of message being sent
        - _id (`uuid.UUID`) : Universally Unique IDentifier for this message
        - _network_config (:obj:`NetworkConfig`): network configuration from sender node
    """
    def __init__(self, src: str, id : uuid.UUID = None):
        """
        Initializes an instance of a Node Ready Message

        ### Arguments:
            - src (`str`): name of the simulation node sending this message
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(src, SimulationElementRoles.MANAGER.value, NodeMessageTypes.NODE_DEACTIVATED, id)
    
    def from_dict(d : dict):
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        id_str = d.get('@id', None)
        
        if src is None or dst is None or type_name is None or id_str is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in NodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')
        elif _type is not NodeMessageTypes.NODE_DEACTIVATED:
            raise Exception(f'Cannot load a Node Deactivated Message from a dictionary request of type {type_name}.')

        return NodeDeactivatedMessage(src, uuid.UUID(id_str))

    def from_json(j):
        return NodeDeactivatedMessage.from_dict(json.loads(j))

    def __str__(self) -> str:
        return f'{self._src} is deactivated!'

class NodeReceptionAckMessage(SimulationMessage):
    """
    ## Reception Accepted Message

    Notifies an network element that that its message has been accepted by the sending simulation node
        
    ### Attributes:
        - _src (`str`): name of the simulation node sending this message
        - _dst (`str`): name of the network element set to receive this message
        - _msg_type (`Enum`) = `ManagerMessageTypes.RECEPTION_ACK`: type of message being sent
        - _id (`uuid.UUID`) : Universally Unique IDentifier for this message
        - _t (`float`): manager's simulation clock at the time of transmission in [s]
    """
    def __init__(self, src : str, dst : str, id : uuid.UUID = None):
        """
        Initializes an instance of a Reception Accepted Message

        #### Arguments:
            - t (`float`): manager's simulation clock at the time of transmission in [s]
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(src, dst, NodeMessageTypes.RECEPTION_ACK, id)

    def from_dict(d: dict):
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        id_str = d.get('@id', None)
        
        if src is None or dst is None or type_name is None or id_str is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in NodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')
        elif _type is not ManagerMessageTypes.RECEPTION_ACK:
            raise Exception(f'Cannot load a Node Simulation Message from a dictionary request of type {type_name}.')

        return NodeReceptionAckMessage(src, dst, uuid.UUID(id_str))

    def from_json(j):
        return NodeReceptionAckMessage.from_dict(json.loads(j))

class NodeReceptionIgnoredMessage(ManagerMessage):
    """
    ## Reception Rejected Message

    Notifies an network element that that its message has been accepted by the sending simulation node
        
    ### Attributes:
        - _src (`str`): name of the simulation node sending this message
        - _dst (`str`): name of the network element set to receive this message
        - _msg_type (`Enum`) = `ManagerMessageTypes.RECEPTION_IGNORED`: type of message being sent
        - _id (`uuid.UUID`) : Universally Unique IDentifier for this message
        - _t (`float`): manager's simulation clock at the time of transmission in [s]
    """
    def __init__(self, src : str, dst : str, id : uuid.UUID = None):
        """
        Initializes an instance of a Reception Accepted Message

        #### Arguments:
            - t (`float`): manager's simulation clock at the time of transmission in [s]
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(src, dst, NodeMessageTypes.RECEPTION_IGNORED, id)

    def from_dict(d: dict):
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        id_str = d.get('@id', None)
        
        if src is None or dst is None or type_name is None or id_str is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in NodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')
        elif _type is not ManagerMessageTypes.RECEPTION_IGNORED:
            raise Exception(f'Cannot load a Node Simulation Message from a dictionary request of type {type_name}.')

        return NodeReceptionIgnoredMessage(src, dst, uuid.UUID(id_str))

    def from_json(j):
        return NodeReceptionIgnoredMessage.from_dict(json.loads(j))
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
        - _msg_type (`Enum`): type of message being sent
        - _id (`uuid.UUID`) : Universally Unique IDentifier for this message
    """

    def __init__(self, src: str, dst: str, id : uuid.UUID = None):
        """
        Initializes an instance of a Sync Request Message

        ### Arguments:
            - src (`str`): name of the internal module sending this message
            - dst (`str`): name of the simulation node to receive this message
            - id (`uuid.UUID`) : Universally Unique IDentifier for this message
        """
        super().__init__(src, dst, ModuleMessageTypes.SYNC_REQUEST, id)

    def from_dict(d : dict):
        """
        Creates an instance of a message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        id_str = d.get('@id', None)

        if src is None or dst is None or type_name is None or id_str is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in ModuleMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')
        elif _type is not ModuleMessageTypes.SYNC_REQUEST:
            raise Exception(f'Cannot load a Sync Request from a dictionary request of type {type_name}.')

        return ModuleSyncRequestMessage(src, uuid.UUID(id_str))

    def from_json(d):
        """
        Creates an instance of a message class object from a json object 
        """
        return ModuleSyncRequestMessage.from_dict(json.loads(d))

    def __str__(self) -> str:
        return f'{ModuleMessageTypes.SYNC_REQUEST.name}'

"""
-----------------
SIMULATION MONITOR MESSAGES
-----------------
"""


from datetime import datetime, timezone

if __name__ == "__main__":
    
    start = datetime(2020, 1, 1, 7, 20, 0, tzinfo=timezone.utc)
    end = datetime(2020, 1, 1, 8, 20, 0, tzinfo=timezone.utc)

    clock_config = RealTimeClockConfig(start, end)

    address_ledger = dict()
    address_ledger['TEST'] = NodeNetworkConfig('0.0.0.0.1', '0.0.0.0.2', '0.0.0.0.3', '0.0.0.0.4', '0.0.0.0.5')

    ## Sim info message test
    # msg = SimulationInfoMessage(address_ledger, clock_config, 0.0)
    # msg_json = msg.to_json()    
    # print(msg_json)
    # msg_reconstructed = SimulationInfoMessage.from_json(msg_json)
    # print(msg_reconstructed.to_json())

    ## Node sync request test
    # msg = SyncRequestMessage('TEST', NodeNetworkConfig('0.0.0.0.1', '0.0.0.0.2', '0.0.0.0.3', '0.0.0.0.4', '0.0.0.0.5'))
    # msg_json = msg.to_json()
    # print(msg_json)
    # msg_reconstructed = SyncRequestMessage.from_json(msg_json)
    # print(msg_reconstructed.to_json())

    ## Node ready message test
    # msg = NodeReadyMessage('Test')
    # msg_json = msg.to_json()
    # print(msg)
    # print(msg_json)
    # msg_reconstructed = NodeReadyMessage.from_json(msg_json)
    # print(msg_reconstructed)
    # print(msg_reconstructed.to_json())

    ## sim start message test
    msg = SimulationStartMessage(0.0)
    msg_json = msg.to_json()
    print(msg)
    print(msg_json)
    msg_reconstructed = SimulationStartMessage.from_json(msg_json)
    print(msg_reconstructed)
    print(msg_reconstructed.to_json())