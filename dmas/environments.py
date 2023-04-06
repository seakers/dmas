import asyncio
import logging

import zmq
from dmas.messages import NodeReceptionAckMessage, SimulationElementRoles
from dmas.modules import InternalModule
from dmas.network import NetworkConfig
from dmas.nodes import Node


class EnvironmentNode(Node):
    """
    # Abstract Environment Node Class

    Represents and environment within a multi-agent simulation.

    Respons to agent requests model the agents' sensing of the environment.
    """
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
    
        if zmq.REP not in env_network_config.get_external_addresses() and zmq.ROUTER not in env_network_config.get_external_addresses():
            raise AttributeError(f'`env_network_config` must contain a REP or ROUTER port and an address within its external address map.')
        if zmq.PUB not in env_network_config.get_external_addresses():
            raise AttributeError(f'`env_network_config` must contain a PUB port and an address within its external address map.')