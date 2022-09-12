from abc import abstractclassmethod
from enum import Enum
from this import s

"""
INTER AGENT MESSAGES
"""
class MessageTypes(Enum):
    @abstractclassmethod
    def format_check(msg: dict):
        """
        Checks if a message of type request contains the proper contents and format.
        Returns a boolean that indicates if this message meets these criterea.
        """
        pass

class BroadcastTypes(Enum):
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

    def format_check(msg: dict):
        """
        Checks if a message of type request contains the proper contents and format.
        Returns a boolean that indicates if this message meets these criterea.
        """

        msg_src = msg.get('src', None)
        msg_dst = msg.get('dst', None)
        msg_type = msg.get('@type', None)

        if msg_src is None or msg_dst is None or msg_type is None:
            # any message must contain a source, destination, and type.
            return False
        
        if BroadcastTypes[msg_type] is BroadcastTypes.TIC_EVENT:
            t = msg.get('server_clock', None)
            
            if t is None:
                # tic broadcasts must contain current server time
                return False
        elif BroadcastTypes[msg_type] is BroadcastTypes.SIM_START_EVENT or BroadcastTypes[msg_type] is BroadcastTypes.SIM_END_EVENT:
            return True
        elif (BroadcastTypes[msg_type] is BroadcastTypes.ECLIPSE_EVENT):
            return True
        elif (BroadcastTypes[msg_type] is BroadcastTypes.GP_ACCESS_EVENT):
            lat = msg.get('lat', None)
            lon = msg.get('lon', None)
            rise = msg.get('rise', None)
            agent = msg.get('agent', None)

            if lat is None or lon is None or rise is None or agent is None:
                return False

        elif (BroadcastTypes[msg_type] is BroadcastTypes.GS_ACCESS_EVENT
              or BroadcastTypes[msg_type] is BroadcastTypes.AGENT_ACCESS_EVENT):
            rise = msg.get('rise', None)
            agent = msg.get('agent', None)
            
            if rise is None or agent is None:
                return False
        else:
            return False
        
        return True

    def create_eclipse_event_broadcast(src: str, dst: str, agent_name: str, rise: bool, t: float) -> dict:
        msg_dict = dict()

        msg_dict['src'] = src
        msg_dict['dst'] = dst
        msg_dict['@type'] = BroadcastTypes.ECLIPSE_EVENT.name
        msg_dict['server_clock'] = t
        msg_dict['agent'] = agent_name
        msg_dict['rise'] = rise

        return msg_dict

    def create_gs_access_event_broadcast(src: str, dst: str, agent_name: str, rise: bool, t: float, 
                                        gndStat_name: str, gndStat_id: str, lat: float, lon: float) -> dict:
        msg_dict = dict()

        msg_dict['src'] = src
        msg_dict['dst'] = dst
        msg_dict['@type'] = BroadcastTypes.GS_ACCESS_EVENT.name
        msg_dict['server_clock'] = t
        msg_dict['agent'] = agent_name
        msg_dict['rise'] = rise
        msg_dict['gndStat_name'] = gndStat_name
        msg_dict['gndStat_id'] = gndStat_id
        msg_dict['lat'] = lat
        msg_dict['lon'] = lon

        return msg_dict

    def create_gp_access_event_broadcast(src: str, dst: str, agent_name: str, rise: bool, t: float, 
                                        grid_index: int, gp_index: int, lat: float, lon: float) -> dict:
        msg_dict = dict()

        msg_dict['src'] = src
        msg_dict['dst'] = dst
        msg_dict['@type'] = BroadcastTypes.GP_ACCESS_EVENT.name
        msg_dict['server_clock'] = t
        msg_dict['agent'] = agent_name
        msg_dict['rise'] = rise
        msg_dict['grid_index'] = grid_index
        msg_dict['gp_index'] = gp_index
        msg_dict['lat'] = lat
        msg_dict['lon'] = lon

        return msg_dict

    def create_agent_access_event_broadcast(src: str, dst: str, rise: bool, t: float, agent_name: str, target: str) -> dict:
        msg_dict = dict()

        msg_dict['src'] = src
        msg_dict['dst'] = dst
        msg_dict['@type'] = BroadcastTypes.AGENT_ACCESS_EVENT.name
        msg_dict['server_clock'] = t
        msg_dict['rise'] = rise
        msg_dict['agent'] = agent_name
        msg_dict['target'] = target

        return msg_dict

class RequestTypes(Enum):
    """
    Types of requests between agents and environment.
        0- sync_request: agent notifies environment server that it is online and ready to start the simulation. Only used before the start of the simulation
        1- tic_request: agents ask to be notified when a certain time has passed in the environment's clock    
        2- agent_access_request: agent asks the enviroment if the agent is capable of accessing another agent at the current simulation time
        3- gp_access_request: agent asks the enviroment if the agent is capable of accessing a ground point at the current simulation time
        4- gs_access_request: agent asks the enviroment if the agent is capable of accessing a ground station at the current simulation time
        5- agent_information_request: agent asks for information regarding its current position, velocity, and eclipse at the current simulation time
        6- observation_request: agent requests environment information regarding a the state of a ground point at the current simulation time
        7- agent_end_confirmation: agent notifies the environment that it has successfully terminated its operations
    """
    SYNC_REQUEST = 'SYNC_REQUEST'
    TIC_REQUEST = 'TIC_REQUEST'
    AGENT_ACCESS_REQUEST = 'AGENT_ACCESS_REQUEST'
    GP_ACCESS_REQUEST = 'GROUND_POINT_ACCESS_REQUEST'
    GS_ACCESS_REQUEST = 'GROUND_STATION_ACCESS_REQUEST'
    AGENT_INFO_REQUEST = 'AGENT_INFO_REQUEST'
    OBSERVATION_REQUEST = 'OBSERVATION_REQUEST'
    AGENT_END_CONFIRMATION = 'AGENT_END_CONFIRMATION'

    def format_check(msg: dict):
        """
        Checks if a message of type request contains the proper contents and format.
        Returns a boolean that indicates if this message meets these criterea.
        """

        msg_src = msg.get('src', None)
        msg_dst = msg.get('dst', None)
        msg_type = msg.get('@type', None)

        if msg_src is None or msg_dst is None or msg_type is None:
            # any message must contain a source, destination, and type.
            return False
        
        if RequestTypes[msg_type] is RequestTypes.SYNC_REQUEST:
            port = msg.get('port', None)
            n_coroutines = msg.get('n_coroutines', None)

            if port is None or n_coroutines is None or n_coroutines < 0:
                # sync requests must contain 
                return False
        elif RequestTypes[msg_type] is RequestTypes.TIC_REQUEST:
            t_end = msg.get('t', None)
            
            if t_end is None:
                return False
        elif RequestTypes[msg_type] is RequestTypes.AGENT_ACCESS_REQUEST:
            target = msg.get('target', None)
            
            if target is None:
                return False
        
        elif RequestTypes[msg_type] is RequestTypes.GP_ACCESS_REQUEST:
            lat = msg.get('lat', None)
            lon = msg.get('lon', None)
            
            if lat is None or lon is None:
                return False

        elif RequestTypes[msg_type] is RequestTypes.GS_ACCESS_REQUEST:
            target = msg.get('target', None)
            
            if target is None:
                return False

        elif RequestTypes[msg_type] is RequestTypes.AGENT_INFO_REQUEST:
            return True
            
        # elif RequestTypes[msg_type] is RequestTypes.OBSERVATION_REQUEST:
        #     pass
        elif RequestTypes[msg_type] is RequestTypes.AGENT_END_CONFIRMATION:
            return True
        else:
            return False
        
        return True
    
    def create_tic_request(src: str, dst: str, t: float):
        tic_req_msg = dict()
        tic_req_msg['src'] = src
        tic_req_msg['dst'] = dst
        tic_req_msg['@type'] = RequestTypes.TIC_REQUEST.name
        tic_req_msg['t'] = t

        return tic_req_msg

    def create_agent_access_request(src: str, dst: str, target: str):
        access_req_msg = dict()
        access_req_msg['src'] = src
        access_req_msg['dst'] = dst
        access_req_msg['@type'] = RequestTypes.AGENT_ACCESS_REQUEST.name
        access_req_msg['target'] = target

        return access_req_msg

    def create_ground_station_access_request(src: str, dst: str, target: str):
        gs_access_req_msg = dict()
        gs_access_req_msg['src'] = src
        gs_access_req_msg['dst'] = dst
        gs_access_req_msg['@type'] = RequestTypes.GS_ACCESS_REQUEST.name
        gs_access_req_msg['target'] = target

        return gs_access_req_msg

    def create_ground_point_access_request(src: str, dst: str, lat: float, lon: float):
        gs_access_req_msg = dict()
        gs_access_req_msg['src'] = src
        gs_access_req_msg['dst'] = dst
        gs_access_req_msg['@type'] = RequestTypes.GP_ACCESS_REQUEST.name
        gs_access_req_msg['lat'] = lat
        gs_access_req_msg['lon'] = lon

        return gs_access_req_msg

    def create_agent_info_request(src: str, dst: str):
        msg = dict()
        msg['src'] = src
        msg['dst'] = dst
        msg['@type'] = RequestTypes.AGENT_INFO_REQUEST.name

        return msg

"""
INTRA AGENT MESSAGES
"""

class AgentInternalMessageType(Enum):
    pass

class InternalMessage:
    """
    Abstract message used to for inter-module communication
    """
    def __init__(self, src: str, dst: str, msg) -> None:
        """
        src: name of the module sending the message
        dst: name of the module to receive the message
        msg: content of the message being transmitted
        """
        self.src = src  
        self.dst = dst 
        self.msg = msg

class AgentRequestOut(InternalMessage):
    """
    Internal message containing a request to be sent out to another agent
    """
    def __init__(self, src, dst, req_out) -> None:
        super().__init__(src, dst, req_out)

class EnvironmentRequestOut(InternalMessage):
    """
    Internal message containing a request to be sent out to the environment
    """
    def __init__(self, src, dst, req_out) -> None:
        super().__init__(src, dst, req_out)

class TransmissionOut(InternalMessage):
    """
    Internal message meant to be transmitted out to another agent
    """
    def __init__(self, src, dst, msg_out) -> None:
        super().__init__(src, dst, msg_out)
