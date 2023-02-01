from abc import ABC, abstractmethod
from typing import Union
from enum import Enum
import json

from dmas.utils import *


class SimulationMessage(ABC):
    """
    ## Abstract Simulation Message 

    Describes a message to be sent between simulation elements

    ### Attributes:
        - _src (`str`): name of the simulation element sending this message
        - _dst (`str`): name of the intended simulation element to receive this message
        - _msg_type (`Enum`): type of message being sent
    """

    def __init__(self, src: str, dst: str, msg_type: Enum) -> None:
        """
        Initiates an instance of a simulation message.
        
        ### Args:
            - src (`str`): name of the simulation element sending this message
            - dst (`str`): name of the intended simulation element to receive this message
            - msg_type (`str`): type of message being sent
        """
        self._src = src
        self._dst = dst
        self._msg_type = msg_type
    
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

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        msg_dict = dict()
        msg_dict['src'] = self._src
        msg_dict['dst'] = self._dst
        msg_dict['@type'] = self._msg_type.name
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
    """
    SIM_INFO = 'SIM_INFO'
    SIM_START = 'SIM_START'
    SIM_END = 'SIM_END'

class ManagerMessage(SimulationMessage, ABC): 
    """
    ## Manager Message

    Describes a message being brodcasted from the simulation manager to all simulation elements.

    ### Attributes:
        - _src (`str`): name of the simulation element sending this message
        - _dst (`str`) = `SimulationElementTypes.ALL.name`: name of the intended simulation element to receive this message
        - _msg_type (`Enum`): type of message being sent
        - _t (`float`): manager's simulation clock at the time of transmission in [s]
    """
    def __init__(self, type: ManagerMessageTypes, t : Union[int, float]) -> None:   
        """        
        Initialzies an instance of a Manager Message
        """
        super().__init__(SimulationElementTypes.MANAGER.name, SimulationElementTypes.ALL.name, type)
        self._t = t

    def to_dict(self) -> dict:
        out = super().to_dict()
        out['t'] = self._t
        return out

    def __str__(self) -> str:
        return f'{self._msg_type.name}, t={self._t}'

class SimulationStartMessage(ManagerMessage):
    """
    ## Simulation Start Message Message

    Informs all simulation elements that the simulation has started 

    ### Attributes:
        - _src (`str`): name of the simulation element sending this message
        - _dst (`str`) = `SimulationElementTypes.ALL.name`: name of the intended simulation element to receive this message
        - _msg_type (`Enum`) = `ManagerMessageTypes.SIM_START`: type of message being sent
        - _t (`float`): manager's simulation clock at the time of transmission in [s]
    """
    def __init__(self, t: Union[int, float]) -> None:
        """
        Initializes an instance of a Simulaiton Start Message
        """
        super().__init__(ManagerMessageTypes.SIM_START, t)

    def from_dict(d : dict):
        src = d.get('src', None)
        dst = d.get('dst', None)
        t = d.get('t', None)
        type_name = d.get('@type', None)
        
        if src is None or dst is None or type_name is None or t is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in ManagerMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')
        elif _type is not ManagerMessageTypes.SIM_START:
            raise Exception(f'Cannot load a Node Simulation Message from a dictionary request of type {type_name}.')

        return SimulationStartMessage(t)

    def from_json(j):
        return SimulationStartMessage.from_dict(json.loads(j))

class SimulationEndMessage(ManagerMessage):
    """
    ## Simulation End Message Message

    Informs all simulation elements that the simulation has ended 

    ### Attributes:
        - _src (`str`): name of the simulation element sending this message
        - _dst (`str`) = `SimulationElementTypes.ALL.name`: name of the intended simulation element to receive this message
        - _msg_type (`Enum`) = `ManagerMessageTypes.SIM_END`: type of message being sent
        - _t (`float`): manager's simulation clock at the time of transmission in [s]
    """
    def __init__(self, t: Union[int, float]) -> None:
        """
        Initializes an instance of a Simulaiton End Message
        """
        super().__init__(ManagerMessageTypes.SIM_END, t)

    def from_dict(d : dict):
        src = d.get('src', None)
        dst = d.get('dst', None)
        t = d.get('t', None)
        type_name = d.get('@type', None)
        
        if src is None or dst is None or type_name is None or t is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in ManagerMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')
        elif _type is not ManagerMessageTypes.SIM_END:
            raise Exception(f'Cannot load a Simulation End Message from a dictionary request of type {type_name}.')

        return SimulationEndMessage(t)

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
        - _t (`float`): manager's simulation clock at the time of transmission in [s]
        - _address_ledger (`dict`): dictionary mapping simulation element names to network addresses to be used for peer-to-peer communication or broadcast subscription
        - _clock_config (:obj:`ClockConfig`): config object containing information about the clock being used in this simulation
    """

    def __init__(self, address_ledger: dict, clock_config: ClockConfig, t: float) -> None:
        """
        Initiallizes and instance of a Simulation Start Message

        ### Arguments:
            - _address_ledger (`dict`): dictionary mapping agent node names to network addresses to be used for peer-to-peer communication
            - _clock_config (:obj:`ClockConfig`): config object containing information about the clock being used in this simulation
        """
        super().__init__(ManagerMessageTypes.SIM_INFO, t)

        self._address_ledger = dict()
        for node_name in address_ledger:
            address_config = address_ledger[node_name]
            if isinstance(address_config, dict):
                address_config = NodeNetworkConfig.from_dict(address_config)
            
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
        t = d.get('t', None)
        address_ledger = d.get('address ledger', None)
        clock_info = d.get('clock info', None)

        if type_name is None or t is None or address_ledger is None or clock_info is None:
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
            address_ledger_dict[node_name] = NodeNetworkConfig.from_dict(network_config_dict)

        return SimulationInfoMessage(address_ledger, clock_config, t)

    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        return SimulationInfoMessage.from_dict(json.loads(j))

"""
-----------------
AGENT MESSAGES
-----------------
"""
class NodeMessageTypes(Enum):
    """
    Types of messages to be sent from a simulated agent
        1- SimulationSyncRequest: agent notifies environment server that it is online and ready to start the simulation. Only used before the start of the simulation
    """
    SYNC_REQUEST = 'SYNC_REQUEST'
    NODE_READY = 'NODE_READY'
    NODE_DEACTIVATED = 'NODE_DEACTIVATED'

class SyncRequestMessage(SimulationMessage):
    """
    ## Sync Request Message

    Request from a simulation node to synchronize with the simulation manager

    ### Attributes:
        - _src (`str`): name of the simulation node sending this message
        - _dst (`str`): name of the intended simulation element to receive this message
        - _msg_type (`Enum`): type of message being sent
        - _network_config (:obj:`NetworkConfig`): network configuration from sender node
    """

    def __init__(self, src: str, network_config : NodeNetworkConfig) -> None:
        """
        Initializes an instance of a Sync Request Message

        ### Arguments:
            - src (`str`): name of the simulation node sending this message
            - network_config (:obj:`NodeNetworkConfig`): network configuration from sender node
        """
        super().__init__(src, SimulationElementTypes.MANAGER.name, NodeMessageTypes.SYNC_REQUEST)
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
        network_config = d.get('network config', None)

        if src is None or dst is None or type_name is None or network_config is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in NodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')
        elif _type is not NodeMessageTypes.SYNC_REQUEST:
            raise Exception(f'Cannot load a Sync Request from a dictionary request of type {type_name}.')

        network_config = NodeNetworkConfig.from_dict(network_config)

        return SyncRequestMessage(src, network_config)

    def from_json(d):
        """
        Creates an instance of a message class object from a json object 
        """
        return SyncRequestMessage.from_dict(json.loads(d))

    def __str__(self) -> str:
        return f'{NodeMessageTypes.SYNC_REQUEST.name}'

class NodeReadyMessage(SimulationMessage):
    def __init__(self, src: str) -> None:
        super().__init__(src, SimulationElementTypes.MANAGER.name, NodeMessageTypes.NODE_READY)
    
    def from_dict(d : dict):
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)

        
        if src is None or dst is None or type_name is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in NodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')
        elif _type is not NodeMessageTypes.NODE_READY:
            raise Exception(f'Cannot load a Node Ready Message from a dictionary request of type {type_name}.')

        return NodeReadyMessage(src)

    def from_json(j):
        return NodeReadyMessage.from_dict(json.loads(j))

    def __str__(self) -> str:
        return f'{self._src} is ready!'

class NodeDeactivatedMessage(SimulationMessage):
    def __init__(self, src: str) -> None:
        super().__init__(src, SimulationElementTypes.MANAGER.name, NodeMessageTypes.NODE_DEACTIVATED)
    
    def from_dict(d : dict):
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)

        
        if src is None or dst is None or type_name is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in NodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')
        elif _type is not NodeMessageTypes.NODE_DEACTIVATED:
            raise Exception(f'Cannot load a Node Deactivated Message from a dictionary request of type {type_name}.')

        return NodeDeactivatedMessage(src)

    def from_json(j):
        return NodeDeactivatedMessage.from_dict(json.loads(j))

    def __str__(self) -> str:
        return f'{self._src} is deactivated!'

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