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
    
        

    async def setup():
        pass

    async def live(self):
        pass

    async def teardown(self) -> None:
        pass

    async def sim_wait(self, delay: float) -> None:
        return await super().sim_wait(delay)