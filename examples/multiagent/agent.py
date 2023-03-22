import asyncio
import logging
import random
import zmq
from dmas.messages import SimulationElementRoles, SimulationMessage
from dmas.network import NetworkConfig

from dmas.nodes import Node

class AgentNode(Node):
    def __init__(self, 
                 name: str, 
                 network_config: NetworkConfig, 
                 logger: logging.Logger
                ) -> None:
        super().__init__(name, network_config, [], logger=logger)

    async def _live(self) -> None:
        try:
            send_task = asyncio.create_task(self._send())
            listen_task = asyncio.create_task(self._listen())

            await asyncio.wait([send_task, listen_task], return_when=asyncio.ALL_COMPLETED)

        except asyncio.CancelledError:
            if not send_task.done():
                send_task.cancel()
            if not listen_task.done():
                listen_task.cancel()
            
            await asyncio.wait([send_task, listen_task], return_when=asyncio.ALL_COMPLETED)
        
    async def _send(self):
        try:
            # connect to every peer's broadcast sockets
            for peer in self._external_address_ledger:
                if peer == self._element_name:
                    continue

                peer_network_config = self._external_address_ledger[peer]
                self._log(f'Peer: {peer}; Network config: {peer_network_config}')

            while True:
                # peer-to-peer message
                self._log('sending request to environment...', level=logging.INFO)
                peer_msg = SimulationMessage(self.name,
                                        SimulationElementRoles.ENVIRONMENT.value,
                                        'TEST')
                await self._send_external_request_message(peer_msg)

                self._log('response received!', level=logging.INFO)
                
                # wait some random period
                await asyncio.sleep(random.random())

                # peer-to-peer broacast
                # broadcast_msg = SimulationMessage(self.name,
                #                         SimulationElementRoles.ENVIRONMENT.value,
                #                         'TEST')
                # await self._send_external_msg(broadcast_msg, zmq.PUB)

        except asyncio.CancelledError:
            return
        
    async def _listen(self):
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            return