from abc import abstractmethod
from enum import Enum
import json
from re import T

# """
# INTER AGENT MESSAGES
# """
# class BroadcastTypes(Enum):
#     """
#     Types of broadcasts sent from the environemnt to all agents.
#         1- tic: informs all agents of environment server's current time
#         2- eclipse_event: informs agents that an agent has entered eclipse. agents must ignore transmission if they are not the agent affected by the event
#         3- gp_access_event: informs an agent that it can access or can no longer access a ground point. agents must ignore transmission if they are not the agent affected by the event
#         4- gs_access_event: informs an agent that it can access or can no longer access a ground station. agents must ignore transmission if they are not the agent affected by the event
#         5- agent_access_event: informs an agent that it can access or can no longer access another agent. agents must ignore transmission if they are not the agent affected by the event
#         6- sim_start: notifies all agents that the simulation has started
#         7- sim_end: notifies all agents that the simulation has ended 
#     """
#     TIC_EVENT = 'TIC_EVENT'
#     ECLIPSE_EVENT = 'ECLIPSE_EVENT'
#     GP_ACCESS_EVENT = 'GP_ACCESS_EVENT'
#     GS_ACCESS_EVENT = 'GS_ACCESS_EVENT'
#     AGENT_ACCESS_EVENT = 'AGENT_ACCESS_EVENT'
#     SIM_START_EVENT = 'SIM_START_EVENT'
#     SIM_END_EVENT = 'SIM_END_EVENT'

#     def format_check(msg: dict):
#         """
#         Checks if a message of type request contains the proper contents and format.
#         Returns a boolean that indicates if this message meets these criterea.
#         """

#         msg_src = msg.get('src', None)
#         msg_dst = msg.get('dst', None)
#         msg_type = msg.get('@type', None)

#         if msg_src is None or msg_dst is None or msg_type is None:
#             # any message must contain a source, destination, and type.
#             return False
        
#         if BroadcastTypes[msg_type] is BroadcastTypes.TIC_EVENT:
#             t = msg.get('server_clock', None)
            
#             if t is None:
#                 # tic broadcasts must contain current server time
#                 return False
#         elif BroadcastTypes[msg_type] is BroadcastTypes.SIM_START_EVENT or BroadcastTypes[msg_type] is BroadcastTypes.SIM_END_EVENT:
#             return True
#         elif (BroadcastTypes[msg_type] is BroadcastTypes.ECLIPSE_EVENT):
#             return True
#         elif (BroadcastTypes[msg_type] is BroadcastTypes.GP_ACCESS_EVENT):
#             lat = msg.get('lat', None)
#             lon = msg.get('lon', None)
#             rise = msg.get('rise', None)
#             agent = msg.get('agent', None)

#             if lat is None or lon is None or rise is None or agent is None:
#                 return False

#         elif (BroadcastTypes[msg_type] is BroadcastTypes.GS_ACCESS_EVENT
#               or BroadcastTypes[msg_type] is BroadcastTypes.AGENT_ACCESS_EVENT):
#             rise = msg.get('rise', None)
#             agent = msg.get('agent', None)
            
#             if rise is None or agent is None:
#                 return False
#         else:
#             return False
        
#         return True

#     def create_tic_event_broadcast(src: str, t: float, dst: str = 'all') -> dict:
#         msg_dict = dict()
#         msg_dict['src'] = src
#         msg_dict['dst'] = dst
#         msg_dict['@type'] = BroadcastTypes.TIC_EVENT.name
#         msg_dict['server_clock'] = t

#         return msg_dict

#     def create_eclipse_event_broadcast(src: str, dst: str, rise: bool, t: float) -> dict:
#         msg_dict = dict()

#         msg_dict['src'] = src
#         msg_dict['dst'] = dst
#         msg_dict['@type'] = BroadcastTypes.ECLIPSE_EVENT.name
#         msg_dict['server_clock'] = t
#         msg_dict['rise'] = rise

#         return msg_dict

#     def create_gs_access_event_broadcast(src: str, dst: str, rise: bool, t: float, 
#                                         gndStat_name: str, gndStat_id: str, lat: float, lon: float) -> dict:
#         msg_dict = dict()

#         msg_dict['src'] = src
#         msg_dict['dst'] = dst
#         msg_dict['@type'] = BroadcastTypes.GS_ACCESS_EVENT.name
#         msg_dict['server_clock'] = t
#         msg_dict['rise'] = rise
#         msg_dict['gndStat_name'] = gndStat_name
#         msg_dict['gndStat_id'] = gndStat_id
#         msg_dict['lat'] = lat
#         msg_dict['lon'] = lon

#         return msg_dict

#     def create_gp_access_event_broadcast(src: str, dst: str, rise: bool, t: float, 
#                                         grid_index: int, gp_index: int, lat: float, lon: float) -> dict:
#         msg_dict = dict()

#         msg_dict['src'] = src
#         msg_dict['dst'] = dst
#         msg_dict['@type'] = BroadcastTypes.GP_ACCESS_EVENT.name
#         msg_dict['server_clock'] = t
#         msg_dict['rise'] = rise
#         msg_dict['grid_index'] = grid_index
#         msg_dict['gp_index'] = gp_index
#         msg_dict['lat'] = lat
#         msg_dict['lon'] = lon

#         return msg_dict

#     def create_agent_access_event_broadcast(src: str, dst: str, rise: bool, t: float, target: str) -> dict:
#         msg_dict = dict()

#         msg_dict['src'] = src
#         msg_dict['dst'] = dst
#         msg_dict['@type'] = BroadcastTypes.AGENT_ACCESS_EVENT.name
#         msg_dict['server_clock'] = t
#         msg_dict['rise'] = rise
#         msg_dict['target'] = target

#         return msg_dict

# class RequestTypes(Enum):
#     """
#     Contains information on requests available to be sent from an agent to the environment.
#     Agents can only talk to the environment via json files. The environment may respond with a any other type of file supported by the zmq library. 
#     The agent must know in advance which kind of response it will receive in order to guarantee a safe reception of the message.

#     Types of requests between agents and environment:
#         0- sync_request: agent notifies environment server that it is online and ready to start the simulation. Only used before the start of the simulation
#         1- tic_request: agents ask to be notified when a certain time has passed in the environment's clock    
#         2- agent_access_request: agent asks the enviroment if the agent is capable of accessing another agent at the current simulation time
#         3- gp_access_request: agent asks the enviroment if the agent is capable of accessing a ground point at the current simulation time
#         4- gs_access_request: agent asks the enviroment if the agent is capable of accessing a ground station at the current simulation time
#         5- agent_information_request: agent asks for information regarding its current position, velocity, and eclipse at the current simulation time
#         6- observation_request: agent requests environment information regarding a the state of a ground point at the current simulation time
#         7- agent_end_confirmation: agent notifies the environment that it has successfully terminated its operations
#     """
#     SYNC_REQUEST = 'SYNC_REQUEST'
#     TIC_REQUEST = 'TIC_REQUEST'
#     AGENT_ACCESS_REQUEST = 'AGENT_ACCESS_REQUEST'
#     GP_ACCESS_REQUEST = 'GROUND_POINT_ACCESS_REQUEST'
#     GS_ACCESS_REQUEST = 'GROUND_STATION_ACCESS_REQUEST'
#     AGENT_INFO_REQUEST = 'AGENT_INFO_REQUEST'
#     OBSERVATION_REQUEST = 'OBSERVATION_REQUEST'
#     AGENT_END_CONFIRMATION = 'AGENT_END_CONFIRMATION'

#     def format_check(msg: dict):
#         """
#         Checks if a message of type request contains the proper contents and format.
#         Returns a boolean that indicates if this message meets these criterea.
#         """

#         msg_src = msg.get('src', None)
#         msg_dst = msg.get('dst', None)
#         msg_type = msg.get('@type', None)

#         if msg_src is None or msg_dst is None or msg_type is None:
#             # any message must contain a source, destination, and type.
#             return False
        
#         if RequestTypes[msg_type] is RequestTypes.SYNC_REQUEST:
#             port = msg.get('port', None)
#             n_coroutines = msg.get('n_coroutines', None)

#             if port is None or n_coroutines is None or n_coroutines < 0:
#                 # sync requests must contain 
#                 return False
#         elif RequestTypes[msg_type] is RequestTypes.TIC_REQUEST:
#             t_end = msg.get('t', None)
            
#             if t_end is None:
#                 return False
#         elif RequestTypes[msg_type] is RequestTypes.AGENT_ACCESS_REQUEST:
#             target = msg.get('target', None)
            
#             if target is None:
#                 return False
        
#         elif RequestTypes[msg_type] is RequestTypes.GP_ACCESS_REQUEST:
#             lat = msg.get('lat', None)
#             lon = msg.get('lon', None)
            
#             if lat is None or lon is None:
#                 return False

#         elif RequestTypes[msg_type] is RequestTypes.GS_ACCESS_REQUEST:
#             target = msg.get('target', None)
            
#             if target is None:
#                 return False

#         elif RequestTypes[msg_type] is RequestTypes.AGENT_INFO_REQUEST:
#             return True
            
#         # elif RequestTypes[msg_type] is RequestTypes.OBSERVATION_REQUEST:
#         #     pass
#         elif RequestTypes[msg_type] is RequestTypes.AGENT_END_CONFIRMATION:
#             return True
#         else:
#             return False
        
#         return True
    
#     def create_tic_request(src: str, t: float):
#         tic_req_msg = dict()
#         tic_req_msg['src'] = src
#         tic_req_msg['dst'] = 'ENV'
#         tic_req_msg['@type'] = RequestTypes.TIC_REQUEST.name
#         tic_req_msg['t'] = t

#         return tic_req_msg

#     def create_agent_access_request(src: str, target: str):
#         access_req_msg = dict()
#         access_req_msg['src'] = src
#         access_req_msg['dst'] = 'ENV'
#         access_req_msg['@type'] = RequestTypes.AGENT_ACCESS_REQUEST.name
#         access_req_msg['target'] = target

#         return access_req_msg

#     def create_ground_station_access_request(src: str, target: str):
#         gs_access_req_msg = dict()
#         gs_access_req_msg['src'] = src
#         gs_access_req_msg['dst'] = 'ENV'
#         gs_access_req_msg['@type'] = RequestTypes.GS_ACCESS_REQUEST.name
#         gs_access_req_msg['target'] = target

#         return gs_access_req_msg

#     def create_ground_point_access_request(src: str, lat: float, lon: float):
#         gs_access_req_msg = dict()
#         gs_access_req_msg['src'] = src
#         gs_access_req_msg['dst'] = 'ENV'
#         gs_access_req_msg['@type'] = RequestTypes.GP_ACCESS_REQUEST.name
#         gs_access_req_msg['lat'] = lat
#         gs_access_req_msg['lon'] = lon

#         return gs_access_req_msg

#     def create_agent_info_request(src: str):
#         msg = dict()
#         msg['src'] = src
#         msg['dst'] = 'ENV'
#         msg['@type'] = RequestTypes.AGENT_INFO_REQUEST.name

#         return msg

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

class InterNodeMessageTypes(Enum):
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

class InterNodeMessage(SimulationMessage): 
    def __init__(self, src: str, dst: str, _type: InterNodeMessageTypes) -> None:
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
        for name, member in InterNodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')

        return InterNodeMessage(src, dst, _type)

    def to_json(self):
        """
        Creates a json file from this message 
        """
        return json.dumps(self.to_dict())

    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        return InterNodeMessage.from_dict(json.loads(j))

class SyncRequestMessage(InterNodeMessage):
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
        super().__init__(src, dst, InterNodeMessageTypes.SYNC_REQUEST)
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
        for name, member in InterNodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize message of type {type_name}.')
        elif _type is not InterNodeMessageTypes.SYNC_REQUEST:
            raise Exception(f'Cannot load a Sync Request from a dictionary request of type {type_name}.')

        return SyncRequestMessage(src, dst, port, n_coroutines)


    def from_json(d):
        """
        Creates an instance of a message class object from a json object 
        """
        return SyncRequestMessage.from_dict(json.loads(d))

class TicRequestMessage(InterNodeMessage):
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
        super().__init__(src, dst, InterNodeMessageTypes.TIC_REQUEST)
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
        for name, member in InterNodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize request of type {type_name}.')
        elif _type is not InterNodeMessageTypes.TIC_REQUEST:
            raise Exception(f'Cannot load a Tic Request from a dictionary request of type {type_name}.')

        return TicRequestMessage(src, dst, t_req)
    
    def from_json(d):
        """
        Creates an instance of a Request class object from a json object 
        """
        return TicRequestMessage.from_dict(json.loads(d))

class AccessSenseMessage(InterNodeMessage):
    def __init__(self, src: str, dst: str, _type: InterNodeMessageTypes, target, result: bool=None) -> None:
        """
        Abstract message from an agent to the environment asking to be informed if it has access to a generic target

        src:
            name of the node sending the message
        dst:
            name of the node receiving the message
        _type:
            type of access sense being performed
        target:
            name of the target to be accessed by the source node
        result:
            result from sensing if the agent is accessing the target
        """
        super().__init__(src, dst, _type)
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
        for name, member in InterNodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize request of type {type_name}.')
        elif (_type is not InterNodeMessageTypes.AGENT_ACCESS_SENSE 
                and _type is not InterNodeMessageTypes.GP_ACCESS_SENSE
                and _type is not InterNodeMessageTypes.GS_ACCESS_SENSE):
            raise Exception(f'Cannot load a Access Sense Message from a dictionary of type {type_name}.')

        if result == 'None':
            result = None

        return AccessSenseMessage(src, dst, target, _type, result)

    def from_json(d):
        """
        Creates an instance of a message class object from a json object 
        """
        return AccessSenseMessage.from_dict(json.loads(d))

class AgentAccessSenseMessage(AccessSenseMessage):
    def __init__(self, src: str, dst: str, target: str, result: bool=None) -> None:
        """
        Message from an agent node to the environment asking to be informed if it has access to a particular agent node

        src:
            name of the agent node sending the message
        dst:
            name of the environment node receiving the message
        target:
            name of the target node to be accessed by the source node
        result:
            result from sensing if the agent is accessing the target
        """
        super().__init__(src, dst, InterNodeMessageTypes.AGENT_ACCESS_SENSE, target, result)

    def from_dict(d):
        """
        Creates an instance of a Agent Access Sense Message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        target = d.get('target', None)
        result = d.get('result', None)

        if src is None or dst is None or type_name is None or target is None or result is None:
            raise Exception('Dictionary does not contain necessary information to construct a message object.')

        _type = None
        for name, member in InterNodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize request of type {type_name}.')
        elif _type is not InterNodeMessageTypes.AGENT_ACCESS_SENSE:
            raise Exception(f'Cannot load a Access Sense Message from a dictionary of type {type_name}.')

        if result == 'None':
            result = None

        return AgentAccessSenseMessage(src, dst, target, result)

    def from_json(d):
        """
        Creates an instance of a message class object from a json object 
        """
        return AgentAccessSenseMessage.from_dict(json.loads(d))

class GndStnAccessSenseMessage(AccessSenseMessage):
    def __init__(self, src: str, dst: str, target, result: bool=None) -> None:
        """
        Message from an agent node to the environment asking to be informed if it has access to a particular Ground Station

        src:
            name of the agent node sending the message
        dst:
            name of the environment node receiving the message
        target:
            name of the target ground station to be accessed by the source node
        result:
            result from sensing if the agent is accessing the target
        """
        super().__init__(src, dst, InterNodeMessageTypes.GS_ACCESS_SENSE, target, result)
    
    def from_dict(d):
        """
        Creates an instance of a Ground Station Access Sense Message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        target = d.get('target', None)
        result = d.get('result', None)

        if src is None or dst is None or type_name is None or target is None or result is None:
            raise Exception('Dictionary does not contain necessary information to construct a message object.')

        _type = None
        for name, member in InterNodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize request of type {type_name}.')
        elif _type is not InterNodeMessageTypes.GS_ACCESS_SENSE:
            raise Exception(f'Cannot load a Access Sense Message from a dictionary of type {type_name}.')

        if result == 'None':
            result = None

        return GndStnAccessSenseMessage(src, dst, target, result)

    def from_json(d):
        """
        Creates an instance of a message class object from a json object 
        """
        return GndStnAccessSenseMessage.from_dict(json.loads(d))

class GndPntAccessSenseMessage(AccessSenseMessage):
    def __init__(self, src: str, dst: str, lat: float, lon: float, result: bool=None) -> None:
        """
        Message from an agent node to the environment asking to be informed if it has access to a particular Ground Station

        src:
            name of the agent node sending the message
        dst:
            name of the environment node receiving the message
        lat:
            latitude of the target ground point to be accessed by the source node (in degrees)
        lon:
            lingitude of the target ground point to be accessed by the source node (in degrees)
        result:
            result from sensing if the agent is accessing the target
        """
        super().__init__(src, dst, InterNodeMessageTypes.GP_ACCESS_SENSE, [lat, lon], result)
        self.target = [lat, lon]

    def from_dict(d):
        """
        Creates an instance of a Ground Point Access Sense Message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        target = d.get('target', None)
        result = d.get('result', None)

        if src is None or dst is None or type_name is None or target is None or result is None:
            raise Exception('Dictionary does not contain necessary information to construct a message object.')

        _type = None
        for name, member in InterNodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize request of type {type_name}.')
        elif _type is not InterNodeMessageTypes.GS_ACCESS_SENSE:
            raise Exception(f'Cannot load a Access Sense Message from a dictionary of type {type_name}.')

        if result == 'None':
            result = None
        lat, lon = target

        return GndStnAccessSenseMessage(src, dst, lat, lon, result)

    def from_json(d):
        """
        Creates an instance of a message class object from a json object 
        """
        return GndStnAccessSenseMessage.from_dict(json.loads(d))

class AgentSenseMessage(InterNodeMessage):
    def __init__(self, src: str, dst: str, internal_state: dict, pos: list=None, vel: list=None, eclipse: bool=None) -> None:
        """
        Message from an agent node to the environment asking to be informed about its current position, velocity, and eclipse state

        src:
            name of the agent node sending the message
        dst:
            name of the environment node receiving the message
        internal_state:
            internal_state of the source node 
        pos:
            position vector of the source node (result from sensing)
        vel:
            velocity vector of the source node (result from sensing)
        eclipse:
            eclipse state of the source node (result from sensing)
        """
        super().__init__(src, dst, InterNodeMessageTypes.AGENT_INFO_SENSE)
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

        if self.pos is None:
            msg_dict['pos'] = 'None'
        else:
            msg_dict['pos'] = self.pos

        if self.vel is None:
            msg_dict['vel'] = 'None'
        else:
            msg_dict['vel'] = self.pos

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
        internal_state = d.get('target', None)
        pos = d.get('pos', None)
        vel = d.get('vel', None)
        eclipse = d.get('eclipse', None)

        if src is None or dst is None or type_name is None or internal_state is None or pos is None or vel is None or eclipse is None:
            raise Exception('Dictionary does not contain necessary information to construct a message object.')

        _type = None
        for name, member in InterNodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize request of type {type_name}.')
        elif _type is not InterNodeMessageTypes.AGENT_INFO_SENSE:
            raise Exception(f'Cannot load a Agent State Sense Message from a dictionary of type {type_name}.')

        if pos == 'None':
            pos = None
        if vel == 'None':
            vel = None
        if eclipse == 'None':
            eclipse = None

        return AgentSenseMessage(src, dst, internal_state, pos, vel, eclipse)

    def from_json(d):
        """
        Creates an instance of a message class object from a json object 
        """
        return AgentSenseMessage.from_dict(json.loads(d))

class AgentEndConfirmationMessage(InterNodeMessage):
    def __init__(self, src: str, dst: str) -> None:
        """
        Message being sent from a client to an environment server confirming that it has successfully terminated its 
        processes at the end of the simulation

        src:
            name of the cleint node sending the message
        dst:
            name of the server node receiving the message
        """
        super().__init__(src, dst, InterNodeMessageTypes.AGENT_END_CONFIRMATION)

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
        for name, member in InterNodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize request of type {type_name}.')
        elif _type is not InterNodeMessageTypes.AGENT_END_CONFIRMATION:
            raise Exception(f'Cannot load a Agent End Confirmation Message from a dictionary of type {type_name}.')

        return AgentEndConfirmationMessage(src, dst)

    def from_json(d):
        """
        Creates an instance of a message class object from a json object 
        """
        return AgentEndConfirmationMessage.from_dict(json.loads(d))

class ObservationSenseMessage(InterNodeMessage):
    def __init__(self, src: str, dst: str, internal_state: dict, lat: float, lon: float, obs: str) -> None:
        """
        Message from an agent node to the environment asking to be informed about a GP's current state

        src:
            name of the agent node sending the message
        dst:
            name of the environment node receiving the message
        internal_state:
            internal_state of the source node 
        lat:
            latitude of the target ground point to be accessed by the source node (in degrees)
        lon:
            lingitude of the target ground point to be accessed by the source node (in degrees)
        result:
            result from sensing if the agent is accessing the target
        """
        super().__init__(src, dst, InterNodeMessageTypes.OBSERVATION_SENSE)
        self.target = [lat, lon]

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this message object
        """
        msg_dict = super().to_dict()

        msg_dict['internal state'] = self.internal_state
        msg_dict['obs'] = self.obs

        if self.lat is None:
            msg_dict['lat'] = 'None'
        else:
            msg_dict['lat'] = self.lat

        if self.lon is None:
            msg_dict['lon'] = 'None'
        else:
            msg_dict['lon'] = self.lon   

        return msg_dict

    def from_dict(d):
        """
        Creates an instance of a Access Sense Message class object from a dictionary
        """
        src = d.get('src', None)
        dst = d.get('dst', None)
        type_name = d.get('@type', None)
        internal_state = d.get('target', None)
        lat = d.get('lat', None)
        lon = d.get('lon', None)
        obs = d.get('obs', None)

        if src is None or dst is None or type_name is None or internal_state is None or lat is None or lon is None or obs is None:
            raise Exception('Dictionary does not contain necessary information to construct a message object.')

        _type = None
        for name, member in InterNodeMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize request of type {type_name}.')
        elif _type is not InterNodeMessageTypes.OBSERVATION_SENSE:
            raise Exception(f'Cannot load a Observation Sense Message from a dictionary of type {type_name}.')


        return ObservationSenseMessage(src, dst, internal_state, lat, lon, obs)

    def from_json(d):
        """
        Creates an instance of a message class object from a json object 
        """
        return ObservationSenseMessage.from_dict(json.loads(d))

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
            type of request
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

    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        return BroadcastMessage.from_dict(json.loads(j))
    
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

    def to_json(j):
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
            raise Exception(f'Could not recognize request of type {type_name}.')
        elif (_type is not BroadcastMessageTypes.ECLIPSE_EVENT
                and _type is not BroadcastMessageTypes.AGENT_ACCESS_EVENT
                and _type is not BroadcastMessageTypes.GP_ACCESS_EVENT
                and _type is not BroadcastMessageTypes.GS_ACCESS_EVENT):
            raise Exception(f'Cannot load a Event Broadcast Message from a dictionary of type {type_name}.')

        return EventBroadcastMessage(src, dst, _type, t, rise)

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
            raise Exception(f'Could not recognize request of type {type_name}.')
        elif _type is not BroadcastMessageTypes.AGENT_ACCESS_EVENT:
            raise Exception(f'Cannot load a Agent Access Event Broadcast Message from a dictionary of type {type_name}.')

        return AgentAccessEventBroadcastMessage(src, dst, target, t, rise)

    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        return AgentAccessEventBroadcastMessage.from_dict(json.loads(j))

class GndPointAccessEventBroadcastMessage(EventBroadcastMessage):
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
            raise Exception(f'Could not recognize request of type {type_name}.')
        elif _type is not BroadcastMessageTypes.GP_ACCESS_EVENT:
            raise Exception(f'Cannot load a Ground Point Access Event Broadcast Message from a dictionary of type {type_name}.')

        return GndPointAccessEventBroadcastMessage(src, dst, lat, lon, grid_index, gp_index, t, rise)

    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        return GndPointAccessEventBroadcastMessage.from_dict(json.loads(j))

class GndStationAccessEventBroadcastMessage(EventBroadcastMessage):
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
            raise Exception(f'Could not recognize request of type {type_name}.')
        elif _type is not BroadcastMessageTypes.GS_ACCESS_EVENT:
            raise Exception(f'Cannot load a Ground Station Access Event Broadcast Message from a dictionary of type {type_name}.')

        return GndStationAccessEventBroadcastMessage(src, dst, target, t, rise)

    def from_json(j):
        """
        Creates an instance of a message class object from a json object 
        """
        return GndStationAccessEventBroadcastMessage.from_dict(json.loads(j))


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

        if src is None or dst is None or type_name or port_ledger is None or clock_info is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in BroadcastMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize request of type {type_name}.')
        elif _type is not BroadcastMessageTypes.SIM_START_EVENT:
            raise Exception(f'Cannot load a Simulation Start Event Broadcast Message from a dictionary of type {type_name}.')

        return SimulationStartBroadcastMessage(src, port_ledger, clock_info)

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

        if src is None or dst is None or type_name or t_end is None:
            raise Exception('Dictionary does not contain necessary information to construct this message object.')

        _type = None
        for name, member in BroadcastMessageTypes.__members__.items():
            if name == type_name:
                _type = member

        if _type is None:
            raise Exception(f'Could not recognize request of type {type_name}.')
        elif _type is not BroadcastMessageTypes.SIM_END_EVENT:
            raise Exception(f'Cannot load a Simulation End Event Broadcast Message from a dictionary of type {type_name}.')

        return SimulationEndBroadcastMessage(src, t_end)

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

# """
# INTRA ENVIRONMENT MESSAGES
# """


# class RequestMessage(InternalMessage):
#     """
#     Internal message that carries a request to be handled by the destination module
#     """
#     def __init__(self, src_module: str, dst_module: str, req: InterNodeMessage) -> None:
#         super().__init__(src_module, dst_module, req)


# class TicRequestMessage(InternalMessage):
#     def __init__(self, src_module: str, dst_module: str, t_req: float) -> None:
#         super().__init__(src_module, dst_module, t_req)
    
#     def get_t(self):
#         return self.content

# class EnvironmentBroadcast(InternalMessage):
#     def __init__(self, src_module: str, dst_module: str, broadcast_type: BroadcastTypes=None, content=None) -> None:
#         super().__init__(src_module, dst_module, content)
#         self.BROADCAST_TYPE = broadcast_type

#     def content_to_dict(self):
#         msg_dict = dict()
#         msg_dict['src'] = 'ENV'
#         msg_dict['dst'] = 'ALL'
#         msg_dict['@type'] = self.BROADCAST_TYPE
#         return msg_dict

# class TicBroadcast(EnvironmentBroadcast):
#     def __init__(self, src: str, dst: str, t_next: float) -> None:
#         super().__init__(src, dst, BroadcastTypes.TIC_EVENT, t_next)

#     def content_to_dict(self):
#         msg_dict = super().content_to_dict()
#         msg_dict['server_clock'] = self.content
#         return msg_dict

# """
# INTRA AGENT MESSAGES
# """
# class EnvironmentRequestOut(InternalMessage):
#     """
#     Internal message containing a request to be sent out to the environment
#     """
#     def __init__(self, src, dst, req_out) -> None:
#         super().__init__(src, dst, req_out)

# class TransmissionOut(InternalMessage):
#     """
#     Internal message meant to be transmitted out to another agent
#     """
#     def __init__(self, src, dst, msg_out) -> None:
#         super().__init__(src, dst, msg_out)
