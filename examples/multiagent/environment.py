import logging
from dmas.modules import InternalModule, InternalModuleNetworkConfig
from dmas.nodes import Node
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

    def config_factory(env_network_config : EnvironmentNetworkConfig) -> InternalModuleNetworkConfig:
        """
        Generates an internal module network config object 
        """
        parent_pub_addresses : dict = env_network_config.get_internal_addresses()
        parent_pub_address : list = parent_pub_addresses.get(zmq.PUB)
        module_pub_address = NetworkConfig.get_next_available_local_address()
        module_recv_address = NetworkConfig.get_next_available_local_address()

        return EnvironmentWorkerModuleNetworkConfig(parent_pub_address[-1], module_pub_address, module_recv_address)

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
            worker_network_config : InternalModuleNetworkConfig = EnvironmentWorkerModuleNetworkConfig.config_factory()
            modules.append(EnvironmentWorker(name, i, worker_network_config))
        
        super().__init__(name, network_config, modules, level)

    