import logging
from dmas.modules import InternalModule
from dmas.nodes import Node
from dmas.element import SimulationElement
from dmas.utils import *
from dmas.network import *

class Environment(Node):
    def __init__(self, network_name, port, logger: logging.Logger) -> None:
        network_config = NetworkConfig( network_name, 
                                        internal_address_map={},
                                        external_address_map={  zmq.REQ: [f'tcp://localhost:{port}'],
                                                                zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                                zmq.PUSH: [f'tcp://localhost:{port+2}'],
                                                                zmq.REP: [f'tcp://*:{port+3}'],
                                                                }
                                        )        

        super().__init__(SimulationElementRoles.ENVIRONMENT.name, network_config, [], logger=logger)

    async def _live(self):
        dst, src, msg_dict = await self._send_external_request_message(zmq.REP)
        dst : str; src : str; msg_dict : dict
        msg_type = msg_dict.get('msg_type', None)    

        if (
            dst not in self.name
            or src not in module_names 
            or msg_type != ModuleMessageTypes.MODULE_DEACTIVATED.value
            or src in responses
            ):
            # undesired message received. Ignoring and trying again later
            self._log(f'received undesired message of type {msg_type}, expected tye {ModuleMessageTypes.MODULE_DEACTIVATED.value}. Ignoring...')
            resp = NodeReceptionIgnoredMessage(self._element_name, src)
            await self._send_internal_msg(resp, zmq.REP)

        else:

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

    env = Environment('EXAMPLE_NETWORK', port, logger)