import logging
from dmas.nodes import Node
from dmas.utils import *
from dmas.network import *

class EnvironmentNode(Node):
    def __init__(self, port, logger: logging.Logger) -> None:
        network_config = NetworkConfig( 'TEST_NETWORK', 
                                        internal_address_map={},
                                        external_address_map={  zmq.REQ:  [f'tcp://localhost:{port}'],
                                                                zmq.SUB:  [f'tcp://localhost:{port+1}'],
                                                                zmq.PUSH: [f'tcp://localhost:{port+2}'],
                                                                zmq.REP:  [f'tcp://*:{port+3}'],
                                                                }
                                        )        

        super().__init__(SimulationElementRoles.ENVIRONMENT.name, network_config, [], logger=logger)

    async def _live(self):
        try:
            while True:
                self._log('waiting on messages...', level=logging.INFO)

                _, src, msg_dict = await self._receive_external_msg(zmq.REP)
                await self._receive_external_msg(zmq.REP)
                src : str; msg_dict : dict  

                self._log(f'Message from {src}: {msg_dict}', level=logging.INFO)

                resp = NodeReceptionAckMessage(self.name, src)
                await self._send_external_msg(resp, zmq.REP)

        except asyncio.CancelledError:
            return
    
if __name__ == '__main__':
    print('Environment debugger')
    port = 5555
    level = logging.DEBUG
    logger = logging.getLogger()
    logger.propagate = False
    logger.setLevel(level)

    c_handler = logging.StreamHandler()
    c_handler.setLevel(level)
    logger.addHandler(c_handler)

    env = EnvironmentNode('EXAMPLE_NETWORK', port, logger)