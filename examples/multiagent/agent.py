import asyncio
import logging
import random
import zmq
from dmas.messages import SimulationElementRoles, SimulationMessage
from dmas.network import NetworkConfig

from dmas.nodes import Node

class Agent(Node):
    def __init__(   self, 
                    name: str, 
                    network_config: NetworkConfig, 
                    logger: logging.Logger) -> None:
        super().__init__(name, network_config, [], logger=logger)

    async def _live(self) -> None:
        try:
            while True:
                self._log('sending request to environment...', level=logging.INFO)

                msg = SimulationMessage(self.name,
                                        SimulationElementRoles.ENVIRONMENT.value,
                                        'TEST')
                await self._send_external_request_message(msg)

                self._log('response received!', level=logging.INFO)
                await asyncio.sleep(random.random())

        except asyncio.CancelledError:
            return


if __name__ == '__main__':
    print('Agent debugger')
    port = 5555
    level = logging.DEBUG
    logger = logging.getLogger()
    logger.propagate = False
    logger.setLevel(level)

    c_handler = logging.StreamHandler()
    c_handler.setLevel(level)
    logger.addHandler(c_handler)

    network_config = NetworkConfig( 'TEST_NETWORK',
                                    internal_address_map = {},
                                    external_address_map = {
                                                            zmq.REQ: [f'tcp://localhost:{port}'],
                                                            zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                            zmq.PUSH: [f'tcp://localhost:{port+2}']}
                                    )
    

    agent = Agent('AGENT_i', network_config, logger)