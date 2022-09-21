from abc import abstractmethod
from enum import Enum
import json
from re import T
from unittest import result

from utils import EnvironmentModuleTypes, TaskStatus

"""
------------------------
INTER NODE MESSAGES
------------------------
"""
class SimulationMessage:
    def __init__(self, src: str, dst: str, _type: Enum) -> None:
        """
        Abstract class for a message being sent between two nodes in the simulation
        
        src:
            name of the simulation node sending the message
        dst:
            name of the simulation node receiving the message
        _type:
            type of message being sent
        """
        self.src = src
        self.dst = dst
        self._type = _type
    
    def get_type(self):
        """
        Returns the type of message being sent
        """
        return self._type.name

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        msg_dict = dict()
        msg_dict['src'] = self.src
        msg_dict['dst'] = self.dst
        msg_dict['@type'] = self._type.name
        return msg_dict

    @abstractmethod
    def from_dict(d):
        """
        Creates an instance of a message class object from a dictionary 
        """
        pass

    @abstractmethod
    def to_json(self):
        """
        Creates a json file from this message class object
        """
        pass

    @abstractmethod
    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        pass

class NodeMessageTypes(Enum):
    """
    Contains information on requests available to be sent from an agent to the environment.
    Agents can only talk to the environment via json files. The environment may respond with a any other type of file supported by the zmq library. 
    The agent must know in advance which kind of response it will receive in order to guarantee a safe reception of the message.

    Types of requests between agents and the environment:
        0- sync_request: agent notifies environment server that it is online and ready to start the simulation. Only used before the start of the simulation
        1- tic_request: agents ask to be notified when a certain time has passed in the environment's clock    
        2- agent_access_sense: agent asks the enviroment if the agent is capable of accessing another agent at the current simulation time
        3- gp_access_sense: agent asks the enviroment if the agent is capable of accessing a ground point at the current simulation time
        4- gs_access_sense: agent asks the enviroment if the agent is capable of accessing a ground station at the current simulation time
        5- agent_information_sense: agent asks for information regarding its current position, velocity, and eclipse at the current simulation time
        6- observation_sense: agent requests environment information regarding a the state of a ground point at the current simulation time
        7- agent_end_confirmation: agent notifies the environment that it has successfully terminated its operations
    """
    SYNC_REQUEST = 'SYNC_REQUEST'
    TIC_REQUEST = 'TIC_REQUEST'
    AGENT_ACCESS_SENSE = 'AGENT_ACCESS_SENSE'
    GP_ACCESS_SENSE = 'GP_ACCESS_SENSE'
    GS_ACCESS_SENSE = 'GS_ACCESS_SENSE'
    AGENT_INFO_SENSE = 'AGENT_INFO_SENSE'
    OBSERVATION_SENSE = 'OBSERVATION_SENSE'
    AGENT_END_CONFIRMATION = 'AGENT_END_CONFIRMATION'
    PRINT_REQUEST = 'PRINT_REQUEST'

class NodeMessage(SimulationMessage): 
    def __init__(self, src: str, dst: str, _type: NodeMessageTypes) -> None:
        """
        Abstract class for a message being sent between two agents or between an agent and its environment
        
        src:
            name of the simulation node sending the message
        dst:
            name of the simulation node receiving the message
        _type:
            type of message being sent
        """
        super().__init__(src, dst, _type)

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        return super().to_dict()

    def from_dict(d):
        """
        Creates an instance of a message class object from a dictionary 
        """
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

        return NodeMessage(src, dst, _type)

    def to_json(self):
        """
        Creates a json file from this message 
        """
        return json.dumps(self.to_dict())

    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        return NodeMessage.from_dict(json.loads(j))

class SyncRequestMessage(NodeMessage):
    def __init__(self, src: str, dst: str, port: str, n_coroutines: int) -> None:
        """
        Message from a node requesting to be synchronized to the environment server at the beginning of the simulation.

        src:
            name of the node making the request
        dst:
            name of the environment receiving the request
        port:
            port number used by the node sending the request
        n_coroutines:
            number of time-dependent coroutines contianed within the agnodeent sending the request
        """
        super().__init__(src, dst, NodeMessageTypes.SYNC_REQUEST)
        self.port = port
        self.n_coroutines = n_coroutines

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        msg_dict = super().to_dict()
        msg_dict['port'] = self.port
        msg_dict['n_coroutines'] = self.n_coroutines
        return msg_dict

    def from_dict(d):
        """
        Creates an instance of a message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        port = d.get('port', None)
        n_coroutines = d.get('n_coroutines', None)

        if src is None or dst is None or type_name is None or port is None or n_coroutines is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in NodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')
        elif _type is not NodeMessageTypes.SYNC_REQUEST:
            raise Exception(f'Cannot load a Sync Request from a dictionary request of type {type_name}.')

        return SyncRequestMessage(src, dst, port, n_coroutines)


    def from_json(d):
        """
        Creates an instance of a message class object from a json object 
        """
        return SyncRequestMessage.from_dict(json.loads(d))

class TicRequestMessage(NodeMessage):
    def __init__(self, src: str, dst: str, t_req: float) -> None:
        """
        Message from an agent or an internal environment module to the environemnt requesting to be notified when 
        the current simulation time reaches a desired value.

        src:
            name of the node making the request
        dst:
            name of the node receiving the request
        t_req:
            time requested by source node
        """
        super().__init__(src, dst, NodeMessageTypes.TIC_REQUEST)
        self.t_req = t_req

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        req_dict = super().to_dict()
        req_dict['t'] = self.t_req
        return req_dict

    def from_dict(d):
        """
        Creates an instance of a message class object from a dictionary 
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        t_req = d.get('t', None)

        if src is None or dst is None or type_name is None or t_req is None:
            raise Exception('Dictionary does not contain necessary information to construct a Tic Request object.')

        _type = None
        for name, member in NodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize request of type {type_name}.')
        elif _type is not NodeMessageTypes.TIC_REQUEST:
            raise Exception(f'Cannot load a Tic Request from a dictionary request of type {type_name}.')

        return TicRequestMessage(src, dst, t_req)
    
    def to_json(self):
        """
        Creates a json file from this message 
        """
        return super().to_json()


    def from_json(d):
        """
        Creates an instance of a Request class object from a json object 
        """
        return TicRequestMessage.from_dict(json.loads(d))

class AccessSenseMessage(NodeMessage):
    def __init__(self, src: str, _type: NodeMessageTypes, target, result: bool=None) -> None:
        """
        Abstract message from an agent to the environment asking to be informed if it has access to a generic target

        src:
            name of the node sending the message
        _type:
            type of access sense being performed
        target:
            name of the target to be accessed by the source node
        result:
            result from sensing if the agent is accessing the target
        """
        super().__init__(src, EnvironmentModuleTypes.ENVIRONMENT_SERVER_NAME.value, _type)
        self.target = target
        self.result = result

    def set_result(self, result):
        self.result = result
    
    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        msg_dict = super().to_dict()
        msg_dict['target'] = self.target

        if self.result is None:
            msg_dict['result'] = 'None'
        else:
            msg_dict['result'] = self.result

        return msg_dict
    
    def from_dict(d):
        """
        Creates an instance of a Access Sense Message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        target = d.get('target', None)
        result = d.get('result', None)

        if src is None or dst is None or type_name is None or target is None or result is None:
            raise Exception('Dictionary does not contain necessary information to construct a message object.')

        _type = None
        for name, member in NodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize Access Sense Message of type {type_name}.')
        elif (_type is not NodeMessageTypes.AGENT_ACCESS_SENSE 
                and _type is not NodeMessageTypes.GP_ACCESS_SENSE
                and _type is not NodeMessageTypes.GS_ACCESS_SENSE):
            raise Exception(f'Cannot load a Access Sense Message from a dictionary of type {type_name}.')

        if result == 'None':
            result = None

        return AccessSenseMessage(src, _type, target, result)

    def to_json(self):
        """
        Creates a json file from this message 
        """
        return super().to_json()

    def from_json(d):
        """
        Creates an instance of a message class object from a json object 
        """
        return AccessSenseMessage.from_dict(json.loads(d))

class AgentAccessSenseMessage(AccessSenseMessage):
    def __init__(self, src: str, target: str, result: bool=None) -> None:
        """
        Message from an agent node to the environment asking to be informed if it has access to a particular agent node

        src:
            name of the agent node sending the message
        target:
            name of the target node to be accessed by the source node
        result:
            result from sensing if the agent is accessing the target
        """
        super().__init__(src, NodeMessageTypes.AGENT_ACCESS_SENSE, target, result)

    def from_dict(d):
        """
        Creates an instance of a Agent Access Sense Message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        target = d.get('target', None)
        result = d.get('result', -1)

        if src is None or dst is None or type_name is None or target is None or result == -1:
            raise Exception('Dictionary does not contain necessary information to construct a message object.')

        _type = None
        for name, member in NodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize Agent Access Sense Message of type {type_name}.')
        elif _type is not NodeMessageTypes.AGENT_ACCESS_SENSE:
            raise Exception(f'Cannot load a Agent Access Sense Message from a dictionary of type {type_name}.')

        if result == 'None':
            result = None

        return AgentAccessSenseMessage(src, target, result)

    def from_json(d):
        """
        Creates an instance of a message class object from a json object 
        """
        return AgentAccessSenseMessage.from_dict(json.loads(d))

class GndStnAccessSenseMessage(AccessSenseMessage):
    def __init__(self, src: str, target, result: bool=None) -> None:
        """
        Message from an agent node to the environment asking to be informed if it has access to a particular Ground Station

        src:
            name of the agent node sending the message
        target:
            name of the target ground station to be accessed by the source node
        result:
            result from sensing if the agent is accessing the target
        """
        super().__init__(src, NodeMessageTypes.GS_ACCESS_SENSE, target, result)
    
    def from_dict(d):
        """
        Creates an instance of a Ground Station Access Sense Message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        target = d.get('target', None)
        result = d.get('result', -1)

        if src is None or dst is None or type_name is None or target is None or result == -1:
            raise Exception('Dictionary does not contain necessary information to construct a message object.')

        _type = None
        for name, member in NodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize Ground Station Access Sense Message of type {type_name}.')
        elif _type is not NodeMessageTypes.GS_ACCESS_SENSE:
            raise Exception(f'Cannot load a Access Sense Message from a dictionary of type {type_name}.')

        if result == 'None':
            result = None

        return GndStnAccessSenseMessage(src, target, result)

    def from_json(d):
        """
        Creates an instance of a message class object from a json object 
        """
        return GndStnAccessSenseMessage.from_dict(json.loads(d))

class GndPntAccessSenseMessage(AccessSenseMessage):
    def __init__(self, src: str, lat: float, lon: float, result: bool=None) -> None:
        """
        Message from an agent node to the environment asking to be informed if it has access to a particular Ground Station

        src:
            name of the agent node sending the message
        lat:
            latitude of the target ground point to be accessed by the source node (in degrees)
        lon:
            lingitude of the target ground point to be accessed by the source node (in degrees)
        result:
            result from sensing if the agent is accessing the target
        """
        super().__init__(src, NodeMessageTypes.GP_ACCESS_SENSE, [lat, lon], result)
        self.target = [lat, lon]

    def from_dict(d):
        """
        Creates an instance of a Ground Point Access Sense Message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        target = d.get('target', None)
        result = d.get('result', -1)

        if src is None or dst is None or type_name is None or target is None or result == -1:
            raise Exception('Dictionary does not contain necessary information to construct a message object.')

        _type = None
        for name, member in NodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize Ground Point Access Sense Message of type {type_name}.')
        elif _type is not NodeMessageTypes.GP_ACCESS_SENSE:
            raise Exception(f'Cannot load a Access Sense Message from a dictionary of type {type_name}.')

        if result == 'None':
            result = None
        lat, lon = target

        return GndPntAccessSenseMessage(src, lat, lon, result)

    def from_json(d):
        """
        Creates an instance of a message class object from a json object 
        """
        return GndPntAccessSenseMessage.from_dict(json.loads(d))

class AgentSenseMessage(NodeMessage):
    def __init__(self, src: str, internal_state: dict, pos: list=[None, None, None], vel: list=[None, None, None], eclipse: bool=None) -> None:
        """
        Message from an agent node to the environment asking to be informed about its current position, velocity, and eclipse state

        src:
            name of the agent node sending the message
        internal_state:
            internal_state of the source node 
        pos:
            position vector of the source node (result from sensing)
        vel:
            velocity vector of the source node (result from sensing)
        eclipse:
            eclipse state of the source node (result from sensing)
        """
        super().__init__(src, EnvironmentModuleTypes.ENVIRONMENT_SERVER_NAME.value, NodeMessageTypes.AGENT_INFO_SENSE)
        self.internal_state = internal_state

        self.pos = []
        for x_i in pos:
            self.pos.append(x_i)

        self.vel = []
        for v_i in vel:
            self.vel.append(v_i)

        self.eclipse = eclipse

    def set_result(self, pos: list, vel: list, eclipse: bool):
        self.pos = []
        for x_i in pos:
            self.pos.append(x_i)

        self.vel = []
        for v_i in vel:
            self.vel.append(v_i)

        self.eclipse = eclipse

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        msg_dict = super().to_dict()

        msg_dict['internal state'] = self.internal_state

        if self.pos[-1] is None:
            msg_dict['pos'] = ['None', 'None', 'None']
        else:
            msg_dict['pos'] = self.pos

        if self.vel[-1] is None:
            msg_dict['vel'] = ['None', 'None', 'None']
        else:
            msg_dict['vel'] = self.vel

        if self.vel is None:
            msg_dict['eclipse'] = 'None'
        else:
            msg_dict['eclipse'] = self.eclipse       

        return msg_dict

    def from_dict(d):
        """
        Creates an instance of a Access Sense Message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        internal_state = d.get('internal state', None)
        pos = d.get('pos', -1)
        vel = d.get('vel', -1)
        eclipse = d.get('eclipse', -1)

        if (src is None 
            or dst is None 
            or type_name is None 
            or internal_state is None 
            or pos == -1 
            or vel == -1 
            or eclipse == -1):
            raise Exception('Dictionary does not contain necessary information to construct a message object.')

        _type = None
        for name, member in NodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize Agent State Sense Message of type {type_name}.')
        elif _type is not NodeMessageTypes.AGENT_INFO_SENSE:
            raise Exception(f'Cannot load a Agent State Sense Message from a dictionary of type {type_name}.')

        if eclipse == 'None':
            eclipse = None

        return AgentSenseMessage(src, internal_state, pos, vel, eclipse)

    def from_json(d):
        """
        Creates an instance of a message class object from a json object 
        """
        return AgentSenseMessage.from_dict(json.loads(d))

class AgentEndConfirmationMessage(NodeMessage):
    def __init__(self, src: str, dst: str) -> None:
        """
        Message being sent from a client to an environment server confirming that it has successfully terminated its 
        processes at the end of the simulation

        src:
            name of the cleint node sending the message
        dst:
            name of the server node receiving the message
        """
        super().__init__(src, dst, NodeMessageTypes.AGENT_END_CONFIRMATION)

    def from_dict(d):
        """
        Creates an instance of a Agent End Confirmation Message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)

        if src is None or dst is None or type_name is None:
            raise Exception('Dictionary does not contain necessary information to construct a message object.')

        _type = None
        for name, member in NodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')
        elif _type is not NodeMessageTypes.AGENT_END_CONFIRMATION:
            raise Exception(f'Cannot load a Agent End Confirmation Message from a dictionary of type {type_name}.')

        return AgentEndConfirmationMessage(src, dst)

    def from_json(d):
        """
        Creates an instance of a message class object from a json object 
        """
        return AgentEndConfirmationMessage.from_dict(json.loads(d))

class ObservationSenseMessage(NodeMessage):
    def __init__(self, src: str, dst: str, internal_state: dict, lat: float, lon: float, result: str = None) -> None:
        """
        Message from an agent node to the environment asking to be informed about a GP's current state

        src:
            name of the agent node sending the message
        dst:
            name of the environment node receiving the message
        internal_state:
            internal state of the source node. Includes information such as position, sensor(s) used, and sensor attitude
        lat:
            latitude of the target ground point to be accessed by the source node (in degrees)
        lon:
            lingitude of the target ground point to be accessed by the source node (in degrees)
        result:
            result from sensing if the agent is accessing the target
        """
        super().__init__(src, dst, NodeMessageTypes.OBSERVATION_SENSE)
        self.internal_state = internal_state
        self.target = [lat, lon]
        self.result = result

    def set_result(self, results: str):
        """
        Sets the observation results 
        """
        self.result = results

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        msg_dict = super().to_dict()
        lat, lon = self.target
        msg_dict['lat'] = lat
        msg_dict['lon'] = lon 
        msg_dict['internal state'] = self.internal_state
        
        if self.result is None:
            msg_dict['result'] = "None"
        else:
            msg_dict['result'] = self.result        

        return msg_dict

    def from_dict(d):
        """
        Creates an instance of a Access Sense Message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        internal_state = d.get('internal state', None)
        lat = d.get('lat', None)
        lon = d.get('lon', None)
        result = d.get('result', -1)

        if src is None or dst is None or type_name is None or internal_state is None or lat is None or lon is None or result == -1:
            raise Exception('Dictionary does not contain necessary information to construct a message object.')

        _type = None
        for name, member in NodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')
        elif _type is not NodeMessageTypes.OBSERVATION_SENSE:
            raise Exception(f'Cannot load a Observation Sense Message from a dictionary of type {type_name}.')


        return ObservationSenseMessage(src, dst, internal_state, lat, lon, result)

    def from_json(d):
        """`
        Creates an instance of a message class object from a json object 
        """
        return ObservationSenseMessage.from_dict(json.loads(d))

class PrintRequestMessage(NodeMessage):
    def __init__(self, src: str, dst: str, content: str) -> None:
        super().__init__(src, dst, NodeMessageTypes.PRINT_REQUEST)
        self.content = content

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        req_dict = super().to_dict()
        req_dict['content'] = self.conten

    def from_dict(d):
        """
        Creates an instance of a message class object from a dictionary 
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        content = d.get('content', None)

        if src is None or dst is None or type_name is None or content is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in NodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')

        return PrintRequestMessage(src, dst, content)

    def to_json(self):
        """
        Creates a json file from this message 
        """
        return json.dumps(self.to_dict())

    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        return PrintRequestMessage.from_dict(json.loads(j))

class BroadcastMessageTypes(Enum):
    """
    Types of broadcasts sent from the environemnt to all agents.
        1- tic: informs all agents of environment server's current time
        2- eclipse_event: informs agents that an agent has entered eclipse. agents must ignore transmission if they are not the agent affected by the event
        3- gp_access_event: informs an agent that it can access or can no longer access a ground point. agents must ignore transmission if they are not the agent affected by the event
        4- gs_access_event: informs an agent that it can access or can no longer access a ground station. agents must ignore transmission if they are not the agent affected by the event
        5- agent_access_event: informs an agent that it can access or can no longer access another agent. agents must ignore transmission if they are not the agent affected by the event
        6- sim_start: notifies all agents that the simulation has started
        7- sim_end: notifies all agents that the simulation has ended 
    """
    TIC_EVENT = 'TIC_EVENT'
    ECLIPSE_EVENT = 'ECLIPSE_EVENT'
    GP_ACCESS_EVENT = 'GP_ACCESS_EVENT'
    GS_ACCESS_EVENT = 'GS_ACCESS_EVENT'
    AGENT_ACCESS_EVENT = 'AGENT_ACCESS_EVENT'
    SIM_START_EVENT = 'SIM_START_EVENT'
    SIM_END_EVENT = 'SIM_END_EVENT'

class BroadcastMessage(SimulationMessage): 
    def __init__(self, src: str, _type: BroadcastMessageTypes, dst: str='all') -> None:   
        """
        Abstract class for a message being sent from an environment server to all simulation node clients that are subscribed to it
        
        src:
            name of the simulation node sending the message
        dst:
            name of the simulation node receiving the message
        _type:
            type of broadcast being sent
        """
        super().__init__(src, dst, _type)

    def from_dict(d):
        """
        Creates an instance of a message class object from a dictionary 
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)

        if src is None or dst is None or type_name is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in BroadcastMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')

        return BroadcastMessage(src, dst, _type)

    def to_json(self):
        """
        Creates a json file from this message 
        """
        return json.dumps(self.to_dict())

    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        return NodeMessage.from_dict(json.loads(j))
    
class TicEventBroadcast(BroadcastMessage):
    def __init__(self, src: str, t: float) -> None:
        """
        Message from the environment to be broadcasted to all agents containig the latest simulation time 
        """
        super().__init__(src, BroadcastMessageTypes.TIC_EVENT)
        self.t = t

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        msg_dict = super().to_dict()
        msg_dict['server clock'] = self.t
        return msg_dict

    def from_dict(d):
        """
        Creates an instance of a message class object from a dictionary 
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        t = d.get('server clock', None)

        if src is None or dst is None or type_name is None or t is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in BroadcastMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')

        return TicEventBroadcast(src, t)
    
    def to_json(self):
        """
        Creates a json file from this message 
        """
        return super().to_json()

    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        return TicEventBroadcast.from_dict(json.loads(j))
    
class EventBroadcastMessage(BroadcastMessage):
    def __init__(self, src: str, dst: str, _type: BroadcastMessageTypes, t: float, rise: bool) -> None:
        """
        Message from the environment server informing agents that an event has started or ended

        src:
            name of the environment server sending the message
        dst:
            name of the agent node receiving the message
        _type:
            type of event broadcast
        t:
            simulation time at which the event will occur
        rise:
            indicates whether the event in question started or ended
        """
        super().__init__(src, _type, dst)
        self.t = t
        self.rise = rise

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        msg_dict = super().to_dict()
        msg_dict['rise'] = self.rise
        msg_dict['t'] = self.t
        return msg_dict

    def from_dict(d):
        """
        Creates an instance of an Event Broadcast Message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        t = d.get('t', None)
        rise = d.get('rise', None)

        if src is None or dst is None or type_name is None or t is None or rise is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in BroadcastMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize broadcast of type {type_name}.')
        elif (_type is not BroadcastMessageTypes.ECLIPSE_EVENT
                and _type is not BroadcastMessageTypes.AGENT_ACCESS_EVENT
                and _type is not BroadcastMessageTypes.GP_ACCESS_EVENT
                and _type is not BroadcastMessageTypes.GS_ACCESS_EVENT):
            raise Exception(f'Cannot load a Event Broadcast Message from a dictionary of type {type_name}.')

        return EventBroadcastMessage(src, dst, _type, t, rise)

    def to_json(self):
        """
        Creates a json file from this message 
        """
        return super().to_json()

    def from_json(d):
        """
        Creates an instance of a message class object from a json object 
        """
        return AccessSenseMessage.from_dict(json.loads(d))

class EclipseEventBroadcastMessage(EventBroadcastMessage):
    def __init__(self, src: str, dst: str, t: float, rise: bool) -> None:
        """
        Message from the environment server informing a specific agent that an eclipse event has started or ended

        src:
            name of the environment server sending the event message
        dst:
            name of the agent node affected by this event
        t:
            simulation time at which the event will occur
        rise:
            indicates whether the eclipse event started or ended
        """
        super().__init__(src, dst, BroadcastMessageTypes.ECLIPSE_EVENT, t, rise)

    def from_dict(d):
        """
        Creates an instance of an access Event Broadcast Message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        t = d.get('t', None)
        rise = d.get('rise', None)

        if src is None or dst is None or type_name is None or t is None or rise is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in BroadcastMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize broadcast of type {type_name}.')
        elif _type is not BroadcastMessageTypes.ECLIPSE_EVENT:
            raise Exception(f'Cannot load a Eclipse Event Broadcast Message from a dictionary of type {type_name}.')

        return EclipseEventBroadcastMessage(src, dst, t, rise)

    def to_json(self):
        """
        Creates a json file from this message 
        """
        return super().to_json()

    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        return EclipseEventBroadcastMessage.from_dict(json.loads(j))

class AgentAccessEventBroadcastMessage(EventBroadcastMessage):
    def __init__(self, src: str, dst: str, target: str, t: float, rise: bool) -> None:
        """
        Message from the environment server informing a specific agent that an access event with another agent has started or ended

        src:
            name of the environment server sending the event message
        dst:
            name of the agent node affected by this event
        target:
            name of the agent being accessed by the destination agent
        t:
            simulation time at which the event will occur
        rise:
            indicates whether the access event started or ended
        """
        super().__init__(src, dst, BroadcastMessageTypes.AGENT_ACCESS_EVENT, t, rise)
        self.target = target

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        msg_dict = super().to_dict()
        msg_dict['target'] = self.target
        return msg_dict

    def from_dict(d):
        """
        Creates an instance of an access Event Broadcast Message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        target= d.get('target', None)
        t = d.get('t', None)
        rise = d.get('rise', None)

        if src is None or dst is None or type_name is None or target is None or t is None or rise is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in BroadcastMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize broadcast of type {type_name}.')
        elif _type is not BroadcastMessageTypes.AGENT_ACCESS_EVENT:
            raise Exception(f'Cannot load a Agent Access Event Broadcast Message from a dictionary of type {type_name}.')

        return AgentAccessEventBroadcastMessage(src, dst, target, t, rise)

    def to_json(self):
        """
        Creates a json file from this message 
        """
        return super().to_json()

    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        return AgentAccessEventBroadcastMessage.from_dict(json.loads(j))

class GndPntAccessEventBroadcastMessage(EventBroadcastMessage):
    def __init__(self, src: str, dst: str, lat: float, lon: float, grid_index: int, gp_index: int, t: float, rise: bool) -> None:
        """
        Message from the environment server informing a specific agent that an access event with a ground point has started or ended

        src:
            name of the environment server sending the event message
        dst:
            name of the agent node affected by this event
        lat:
            latitude of ground point in question (in degrees)
        lon:
            longitude of ground point in question (in degrees)
        grid_index:
            index of the grid used to define this ground point
        gp_index:
            index of the ground point within the grid's ground point definition
        t:
            simulation time at which the event will occur
        rise:
            indicates whether the access event started or ended
        """
        super().__init__(src, dst, BroadcastMessageTypes.GP_ACCESS_EVENT, t, rise)
        self.lat = lat
        self.lon = lon
        self.grid_index= grid_index
        self.gp_index = gp_index

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        msg_dict = super().to_dict()
        msg_dict['lat'] = self.lat
        msg_dict['lon'] = self.lat
        msg_dict['grid index'] = self.grid_index
        msg_dict['point index'] = self.gp_index
        return msg_dict
    
    def from_dict(d):
        """
        Creates an instance of an access Event Broadcast Message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        lat = d.get('lat', None)
        lon = d.get('lon', None)
        grid_index = d.get('grid index', None)
        gp_index = d.get('point index', None)
        t = d.get('t', None)
        rise = d.get('rise', None)

        if src is None or dst is None or type_name is None or lat is None or lon is None or grid_index is None or gp_index is None or t is None or rise is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in BroadcastMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize broadcast of type {type_name}.')
        elif _type is not BroadcastMessageTypes.GP_ACCESS_EVENT:
            raise Exception(f'Cannot load a Ground Point Access Event Broadcast Message from a dictionary of type {type_name}.')

        return GndPntAccessEventBroadcastMessage(src, dst, lat, lon, grid_index, gp_index, t, rise)

    def to_json(self):
        """
        Creates a json file from this message 
        """
        return super().to_json()

    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        return GndPntAccessEventBroadcastMessage.from_dict(json.loads(j))

class GndStnAccessEventBroadcastMessage(EventBroadcastMessage):
    def __init__(self, src: str, dst: str, target: str, t: float, rise: bool) -> None:
        """
        Message from the environment server informing a specific agent that an access event with a ground station has started or ended

        src:
            name of the environment server sending the event message
        dst:
            name of the agent node affected by this event
        target:
            name of the ground station being accessed by the destination agent
        t:
            simulation time at which the event will occur
        rise:
            indicates whether the access event started or ended
        """
        super().__init__(src, dst, BroadcastMessageTypes.GS_ACCESS_EVENT, t, rise)
        self.target = target

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        msg_dict = super().to_dict()
        msg_dict['target'] = self.target
        return msg_dict

    def from_dict(d):
        """
        Creates an instance of an access Event Broadcast Message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        target= d.get('target', None)
        t = d.get('t', None)
        rise = d.get('rise', None)

        if src is None or dst is None or type_name is None or target is None or t is None or rise is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in BroadcastMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize broadcast of type {type_name}.')
        elif _type is not BroadcastMessageTypes.GS_ACCESS_EVENT:
            raise Exception(f'Cannot load a Ground Station Access Event Broadcast Message from a dictionary of type {type_name}.')

        return GndStnAccessEventBroadcastMessage(src, dst, target, t, rise)

    def to_json(self):
        """
        Creates a json file from this message 
        """
        return super().to_json()

    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        return GndStnAccessEventBroadcastMessage.from_dict(json.loads(j))


class SimulationStartBroadcastMessage(BroadcastMessage):
    def __init__(self, src: str, port_ledger: dict, clock_info: dict) -> None:
        """
        Message from the environment server informing all agent nodes that the simulation has started. 
        It also gives all agents general information about the simulation.

        src:
            name of the environment server sending the event message
        port_ledger:
            dictionary mapping agent node names to port addresses to be used for inter-agent communication
        clock_info:
            dictionary containing information about the clock being used in this simulation
        """
        super().__init__(src, BroadcastMessageTypes.SIM_START_EVENT)
        self.port_ledger = port_ledger
        self.clock_info = clock_info

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        msg_dict = super().to_dict()
        msg_dict['port ledger'] = self.port_ledger.copy()
        msg_dict['clock info'] = self.clock_info.copy()
        return msg_dict

    def from_dict(d):
        """
        Creates an instance of a Simulation Start Broadcast Message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        port_ledger = d.get('port ledger', None)
        clock_info = d.get('clock info', None)

        if src is None or dst is None or type_name is None or port_ledger is None or clock_info is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in BroadcastMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize broadcast of type {type_name}.')
        elif _type is not BroadcastMessageTypes.SIM_START_EVENT:
            raise Exception(f'Cannot load a Simulation Start Event Broadcast Message from a dictionary of type {type_name}.')

        return SimulationStartBroadcastMessage(src, port_ledger, clock_info)

    def to_json(self) -> str:
        """
        Creates a json file from this message 
        """
        return super().to_json()

    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        return SimulationStartBroadcastMessage.from_dict(json.loads(j))
        

class SimulationEndBroadcastMessage(BroadcastMessage):
    def __init__(self, src: str, t_end: float) -> None:
        """
        Message from the environment server informing all agent nodes that the simulation has ended.

        src:
            name of the environment server sending the event message
        t_end:
            environment server clock time at the end of the simulation
        """
        super().__init__(src, BroadcastMessageTypes.SIM_END_EVENT)
        self.t_end = t_end

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        msg_dict = super().to_dict()
        msg_dict['t_end'] = self.t_end
        return msg_dict

    def from_dict(d):
        """
        Creates an instance of a Simulation End Broadcast Message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        t_end = d.get('t_end', None)

        if src is None or dst is None or type_name is None or t_end is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in BroadcastMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize broadcast of type {type_name}.')
        elif _type is not BroadcastMessageTypes.SIM_END_EVENT:
            raise Exception(f'Cannot load a Simulation End Event Broadcast Message from a dictionary of type {type_name}.')

        return SimulationEndBroadcastMessage(src, t_end)

    def to_json(self) -> str:
        """
        Creates a json file from this message 
        """
        return super().to_json()

    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        return SimulationEndBroadcastMessage.from_dict(json.loads(j))

"""
------------------------
INTER MODULE MESSAGES
------------------------
"""
class InternalMessage:
    def __init__(self, src_module: str, dst_module: str, content) -> None:
        """
        Abstract message used to for inter-module communication

        src_module: 
            name of the module sending the message
        dst_module: 
            name of the module to receive the message
        content: 
            content of the message being sent
        """
        self.src_module = src_module  
        self.dst_module = dst_module 
        self.content = content

    def generate_response(self):
        return InternalMessage(src_module=self.dst_module, dst_module=self.src_module, content=self.content)

class ComponentStateMessage(InternalMessage):
    def __init__(self, src_module: str, dst_module: str, state) -> None:
        """
        Inter module communicating the state of a module to another
        """
        super().__init__(src_module, dst_module, state)

"""
-------------------------------
MODULE TASKS
-------------------------------
"""

"""
COMPONENT TASKS
"""
class ComponentTask:
    def __init__(self, component: str, task_status : TaskStatus = TaskStatus.PENDING) -> None:
        """
        Abstract component task class meant to communicate a task to be performed by a specific component

        component:
            Name of component to perform the task
        task_status:
            Initial task status
        """
        self.component : str = component
        self._task_status : TaskStatus = task_status
    
    def set_status(self, status: TaskStatus):
        """
        Sets the status of the task being performed
        """
        self._task_status = status

    def get_status(self):
        """
        returns the status of the task being performed
        """
        return self._task_status

class ComponentActuationTask(ComponentTask):
    def __init__(self, component: str, actuation_status: bool) -> None:
        """
        Tasks a specific component to actuate on or off

        component:
            Name of component to be actuated
        actuation_status:
            Status of the component actuation to be set by this task. 
            True for turning the component ON and False for turning the component OFF
        """
        super().__init__(component)
        self.component_status : bool = actuation_status

"""
COMPONENT TASK MESSAGES
"""
class ComponentTaskMessage(InternalMessage):
    def __init__(self, src_module: str, dst_module: str, task: ComponentTask) -> None:
        """
        Intermodule message carrying a component task
        """
        super().__init__(src_module, dst_module, task)

    def get_task(self) -> ComponentTask:
        return self.content

"""
SUBSYSTEM TASK
"""
class SubsystemTask:
    def __init__(self, subsystem: str, task_status : TaskStatus = TaskStatus.PENDING) -> None:
        """
        Abstract subsystem task class meant to communicate a task to be performed by a particular subsystem

        subsystem:
            Name of subsystem to perform the task
        task_status:
            Initial task status
        """
        self.subsystem : str = subsystem
        self._task_status : TaskStatus = task_status
    
    def set_task_status(self, status: TaskStatus):
        """
        Sets the status of the task being performed
        """
        self._task_status = status

"""
SUBSYSTEM TASK MESSAGES
"""
class SubsystemTaskMessage(InternalMessage):
    def __init__(self, src_module: str, dst_module: str, task: SubsystemTask) -> None:
        """
        Intermodule message carrying a subsystem task
        """
        super().__init__(src_module, dst_module, task)