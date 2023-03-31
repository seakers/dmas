import asyncio
import logging

import zmq
from dmas.messages import NodeReceptionAckMessage, SimulationElementRoles
from dmas.modules import InternalModule
from dmas.network import NetworkConfig
from dmas.nodes import Node


class EnvironmentNode(Node):
    def __init__(   self, 
                    env_network_config: NetworkConfig, 
                    manager_network_config: NetworkConfig, 
                    modules : list = [],
                    level: int = logging.INFO, 
                    logger: logging.Logger = None
                ) -> None:      

        super().__init__(SimulationElementRoles.ENVIRONMENT.value, 
                        env_network_config, 
                        manager_network_config, 
                        modules, 
                        level, 
                        logger)
    
        if zmq.REQ not in env_network_config.get_external_addresses():
            pass
        if zmq.PUB not in env_network_config.get_external_addresses():
            pass