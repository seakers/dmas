from abc import ABC, abstractmethod
from ctypes import Union
from enum import Enum
import json


class SimulationMessage(ABC):
    def __init__(self, src: str, dst: str, msg_type: Enum) -> None:
        """
        Abstract class for a message being sent between two elements in the simulation
        
        src:
            name of the simulation member sending the message
        dst:
            name of the simulation member receiving the message
        type:
            type of message being sent
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
    def from_dict(d):
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

"""
-----------------
SIMULATION MANAGER MESSAGES
-----------------
"""

class ManagerMessageTypes(Enum):
    """
    Types of broadcasts sent from the simulation manager to simulation members.
        1- tic: informs simulation members of the simulation's current time
        2- sim_start: notifies simulation membersthat the simulation has started
        3- sim_end: notifies simulation members that the simulation has ended 
    """
    TIC_EVENT = 'TIC_EVENT'
    SIM_START_EVENT = 'SIM_START_EVENT'
    SIM_END_EVENT = 'SIM_END_EVENT'

class ManagerMessage(SimulationMessage): 
    def __init__(self, type: ManagerMessageTypes, t : Union[int, float]) -> None:   
        """
        Message being sent from the simulation manager to all simulation elements
        
        msg_type:
            type of messsage being sent
        t:
            server simulation clock at the time of transmission in [s]
        """
        super().__init__('manager', 'all', type)
        self._t = t

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        msg_dict = super().to_dict()
        msg_dict['t'] = self._t
        return msg_dict

    def from_dict(d : dict):
        """
        Creates an instance of a message class object from a dictionary 
        """
        type_name = d.get('@type', None)
        t = d.get('t', None)

        if type_name is None or t is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        msg_type = None
        for name, member in ManagerMessageTypes.__members__.items():
            if name == type_name:
                msg_type = member

        if msg_type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')

        return ManagerMessage(msg_type, t)

    
    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        return ManagerMessage.from_dict(json.loads(j))

class SimulationStartMessage(ManagerMessage):
    def __init__(self, address_ledger: dict, clock_info: dict) -> None:
        """
        Message from the simulation manager informing all memebers in the simulation that the simulation has started. 
        It also gives the network general information about the simulation.

        address_ledger:
            dictionary mapping agent node names to network addresses to be used for peer-to-peer communication
        clock_info:
            dictionary containing information about the clock being used in this simulation
        """
        super().__init__(ManagerMessageTypes.SIM_START_EVENT, t=-1)
        self._address_ledger = address_ledger
        self._clock_info = clock_info

    def get_address_ledger(self):
        return self._address_ledger.copy()

    def get_clock_info(self):
        return self._clock_info.copy()

    def to_dict(self) -> dict:
        msg_dict = super().to_dict()
        msg_dict['port ledger'] = self._address_ledger.copy()
        msg_dict['clock info'] = self._clock_info.copy()
        return msg_dict

    def from_dict(d : dict):
        type_name = d.get('@type', None)
        port_ledger = d.get('port ledger', None)
        clock_info = d.get('clock info', None)

        if type_name is None or port_ledger is None or clock_info is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        msg_type = None
        for name, member in ManagerMessageTypes.__members__.items():
            if name == type_name:
                msg_type = member

        if msg_type is None:
            raise Exception(f'Could not recognize simulation manager message of type {type_name}.')

        elif msg_type is not ManagerMessageTypes.SIM_START_EVENT:
            raise Exception(f'Cannot load a Simulation Start Message from a dictionary of type {type_name}.')

        return SimulationStartMessage(port_ledger, clock_info)

    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        return SimulationStartMessage.from_dict(json.loads(j))

class SimulationEndMessage(ManagerMessage):
    def __init__(self, t_end: float) -> None:
        """
        Message from the simulation manager informing all memebers in the simulation that the simulation has emded. 

        t_end:
            environment server clock time at the end of the simulation
        """
        super().__init__(ManagerMessageTypes.SIM_END_EVENT, t_end)

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        return super().to_dict()

    def from_dict(d : dict):
        """
        Creates an instance of a Simulation End Broadcast Message class object from a dictionary
        """
        type_name = d.get('@type', None)
        t_end = d.get('t_end', None)

        if type_name is None or t_end is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        msg_type = None
        for name, member in ManagerMessageTypes.__members__.items():
            if name == type_name:
                msg_type = member

        if msg_type is None:
            raise Exception(f'Could not recognize broadcast of type {type_name}.')
        elif msg_type is not ManagerMessageTypes.SIM_END_EVENT:
            raise Exception(f'Cannot load a Simulation End Event Broadcast Message from a dictionary of type {type_name}.')

        return SimulationEndMessage(t_end)

    def to_json(self) -> str:
        """
        Creates a json file from this message 
        """
        return super().to_json()

    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        return SimulationEndMessage.from_dict(json.loads(j))

"""
-----------------
AGENT MESSAGES
-----------------
"""
class AgentMessageTypes(Enum):
    """
    Types of messages to be sent from a simulated agent
        1- SimulationSyncRequest: agent notifies environment server that it is online and ready to start the simulation. Only used before the start of the simulation
    """
    SYNC_REQUEST = 'SYNC_REQUEST'

class AgentMessage(SimulationMessage):
    def __init__(self, src: str, dst: str, msg_type: AgentMessageTypes) -> None:
        """
        class for a message being sent by an agent
        
        src:
            name of the agent sending the message
        dst:
            name of the simulation member receiving the message
        type:
            type of message being sent
        """
        super().__init__(src, dst, msg_type)

    def to_dict(self) -> dict:
        return super().to_dict()

    def from_dict(d : dict):
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)

        if src is None or dst is None or type_name is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in AgentMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')

        return AgentMessage(src, dst, _type)

    def to_json(self):
        """
        Creates a json file from this message 
        """
        return json.dumps(self.to_dict())

    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        return AgentMessage.from_dict(json.loads(j))

    def __str__(self) -> str:
        return str(self.to_dict())

class SyncRequestMessage(AgentMessage):
    def __init__(self, src: str, dst: str, port_address: str) -> None:
        """
        Message from a node requesting to be synchronized to the simulation manager at the beginning of the simulation.

        src:
            name of the agent making the request
        dst:
            name of the environment receiving the request
        port_address:
            message reception port adrress used by the agent sending the request
        """
        super().__init__(src, dst, AgentMessageTypes.SYNC_REQUEST)
        self._port_address = port_address

    def get_port_address(self):
        """
        Returns the message reception port address used by the agent sending the request
        """
        return self._port_address

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        msg_dict = super().to_dict()
        msg_dict['port address'] = self._port_address
        return msg_dict

    def from_dict(d : dict):
        """
        Creates an instance of a message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        port_address = d.get('port address', None)

        if src is None or dst is None or type_name is None or port_address is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in AgentMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')
        elif _type is not AgentMessageTypes.SYNC_REQUEST:
            raise Exception(f'Cannot load a Sync Request from a dictionary request of type {type_name}.')

        return SyncRequestMessage(src, dst, port_address)


    def from_json(d):
        """
        Creates an instance of a message class object from a json object 
        """
        return SyncRequestMessage.from_dict(json.loads(d))

"""
-----------------
SIMULATION MONITOR MESSAGES
-----------------
"""