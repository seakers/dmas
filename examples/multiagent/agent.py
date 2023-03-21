from yaml import Node
import zmq

from dmas.network import NetworkConfig

class AgentNetworkConfig(NetworkConfig):
    """
    ## Agent Network Config
    
    Describes the addresses assigned to a simulation agent node
    """
    def __init__(self, 
                internal_send_address: str,
                internal_recv_addresses : list,
                manager_request_address : str,
                agent_broadcast_address: str, 
                manager_broadcast_address : str,
                monitor_address: str
                ) -> None:
        """
        Initializes an instance of an Agent Network Config Object
        
        ### Arguments:
        - internal_send_address (`str`): an agent's internal bradcast port address
        - internal_recv_addresses (`list`): list of an agent's modules' publish port addresses
        - broadcast_address (`str`): an agent's broadcast port address
        - manager_address (`str`): the simulation manager's broadcast port address
        - monitor_address (`str`): the simulation's monitor port address
        """
        internal_address_map = {zmq.PUB:  [internal_send_address],
                                zmq.SUB:  internal_recv_addresses}
        external_address_map = {zmq.REQ:  [manager_request_address],
                                zmq.PUB:  [agent_broadcast_address],
                                zmq.SUB:  [manager_broadcast_address],
                                zmq.PUSH: [monitor_address]}

        super().__init__(internal_address_map, external_address_map)


class AgentNode(Node):
    """    
    ## Abstract Agent Node 
    
    ### Attributes:
        - _modules (`list`): list of modules contained within 

    ### Communications diagram:
    +--------------+       +---------+----------+---------+       +--------------+
    |              |<------| PUB     |          | REQ     |------>|              | 
    |              |       +---------+          +---------+       |              |
    |   INTERNAL   |------>| SUB     | ABSTRACT | PUB     |------>| SIM ELEMENTS |
    |     NODE     |       +---------+   SIM    +---------+       |              |
    |    MODULES   |       |         PARTICIPANT| SUB     |<------|              |
    |              |       |                    +---------+       +==============+ 
    |              |       |                    | PUSH    |------>|  SIM MONITOR |
    +--------------+       +---------+----------+---------+       +--------------+
    """