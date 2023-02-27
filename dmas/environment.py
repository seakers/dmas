import logging
from dmas.modules import InternalModule, InternalModuleNetworkConfig
from dmas.node import Node
from dmas.element import SimulationElement
from dmas.utils import *
from dmas.network import *

class EnvironmentNetworkConfig(NetworkConfig):
    """
    ## Environment Network Config
    
    Describes the addresses assigned to a simulation environment node
    """
    def __init__(self, 
                internal_send_addresses: list,
                internal_recv_address : str,
                response_address : str,
                broadcast_address: str, 
                manager_address : str,
                monitor_address: str
                ) -> None:
        """
        Initializes an instance of an Agent Network Config Object
        
        ### Arguments:
        - internal_send_addresses (`list`): list of the environment's workers' port addresses
        - internal_recv_address (`str`): the environment's internal listening port address
        - response_address (`str`): the environment's response port address
        - broadcast_address (`str`): the environment's broadcast port address
        - manager_address (`str`): the simulation manager's broadcast port address
        - monitor_address (`str`): the simulation's monitor port address
        """
        internal_address_map = {zmq.PUB:  internal_send_addresses,
                                zmq.SUB:  [internal_recv_address],
                                zmq.PUSH: []}
        external_address_map = {zmq.REQ:  [],
                                zmq.REP:  [response_address],
                                zmq.PUB:  [broadcast_address],
                                zmq.SUB:  [manager_address],
                                zmq.PUSH: [monitor_address]}

        super().__init__(internal_address_map, external_address_map)

class EnvironmentWorkerModuleNetworkConfig(NetworkConfig):
    """
    ## Environment Worker Module Network Config
    
    Describes the addresses assigned to an environment's internal worker module 
    """
    def __init__(self, 
                parent_pub_address: str,
                module_pub_address : str, 
                module_recv_address: str
                ) -> None:
        """
        Initializes an instance of an Environemtn Worker Module Network Config Object
        
        ### Arguments:
        - module_pub_address (`str`): an internal module's parent node's broadcast address
        - parent_pub_address (`str`): the internal module's broadcast address
        - module_recv_address (`str`): the internal module's parent node's push address
        """
        external_address_map = {zmq.SUB: [parent_pub_address],
                                zmq.PUB: [module_pub_address],
                                zmq.PULL: [module_recv_address]}       
        super().__init__(external_address_map=external_address_map)

class EnvironmentWorker(InternalModule):
    def __init__(self, parent_name: str, worker_id : int, network_config: InternalModuleNetworkConfig, logger: logging.Logger) -> None:
        super().__init__(f'worker_{worker_id}', parent_name, network_config, logger)

class EnvironentNode(Node):
    """
    ## Environment Node 

    Represents an environment node in a simulation.

    ### Communications diagram:
    +--------------+       +---------+----------+---------+       +--------------+
    |              |<------| PUB     |          | REQ     |------>|              | 
    |              |       +---------+          +---------+       |              |
    |   INTERNAL   |------>| SUB     | ABSTRACT | PUB     |------>| SIM ELEMENTS |
    |     NODE     |       +---------+   SIM    +---------+       |              |
    |    MODULES   |<------| PUSH    |   ENV    | SUB     |<------|              |
    |              |       +---------+   NODE   +---------+       +==============+ 
    |              |       |                    | PUSH    |------>|  SIM MONITOR |
    +--------------+       +---------+----------+---------+       +--------------+
    """
    __doc__ += SimulationElement.__doc__
    def __init__(self, name: str, network_config: NetworkConfig, n_workers : int = 1, level: int = logging.INFO) -> None:
        modules = []
        for i in range(n_workers):
            worker_network_config : InternalModuleNetworkConfig = self.worker_network_config_factory()
            modules.append(EnvironmentWorker(name, i, worker_network_config))
        
        super().__init__(name, network_config, modules, level)

    def worker_network_config_factory(self) -> InternalModuleNetworkConfig:
        """
        Generates an internal module network config object 
        """
        return InternalModuleNetworkConfig()

    def is_port_in_use(self, port: int) -> bool:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0

    def get_next_available_port(self):
        port = 5555
        while self.is_port_in_use(port):
            port += 1
        return port