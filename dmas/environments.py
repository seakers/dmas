import asyncio
import logging

import zmq
from dmas.messages import NodeReceptionAckMessage
from dmas.modules import InternalModule
from dmas.network import NetworkConfig
from dmas.nodes import Node


class EnvironmentNode(Node):
    def __init__(   self, 
                    env_name: str, 
                    env_network_config: NetworkConfig, 
                    manager_network_config: NetworkConfig, 
                    modules : list = [],
                    level: int = logging.INFO, 
                    logger: logging.Logger = None
                ) -> None:      

        super().__init__(env_name, 
                        env_network_config, 
                        manager_network_config, 
                        modules, 
                        level, 
                        logger)
    
    async def setup():
        pass

    async def live(self):
        try:
            while True:
                self.log('waiting on messages...', level=logging.INFO)

                _, src, msg_dict = await self._receive_external_msg(zmq.REP)
                src : str; msg_dict : dict  

                self.log(f'Message from {src}: {msg_dict}', level=logging.INFO)

                resp = NodeReceptionAckMessage(self.name, src)
                await self._send_external_msg(resp, zmq.REP)

        except asyncio.CancelledError:
            return

    async def teardown(self) -> None:
        pass

    async def sim_wait(self, delay: float) -> None:
        return await super().sim_wait(delay)