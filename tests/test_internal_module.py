
import unittest

from dmas.modules import *


class TestSimulationNode(unittest.TestCase):
    class DummyModule(InternalModule):
        def __init__(self, module_name: str, network_config: InternalModuleNetworkConfig, logger: logging.Logger = None) -> None:
            super().__init__(module_name, network_config, [], logger=logger)

        async def _listen(self):
            try:
                self._log(f'waiting for parent module to deactivate me...')
                while True:
                    dst, src, content = await self._receive_internal_msg(zmq.SUB)
                    self._log(f'message received: {content}', level=logging.DEBUG)

                    if (dst not in self.name 
                        or self.get_parent_name() not in src 
                        or content['msg_type'] != NodeMessageTypes.MODULE_DEACTIVATE.value):
                        self._log('wrong message received. ignoring message...')
                    else:
                        self._log('deactivate module message received! ending simulation...')
                        break

            except asyncio.CancelledError:
                self._log(f'`_listen()` interrupted. {e}')
                return
            except Exception as e:
                self._log(f'`_listen()` failed. {e}')
                raise e
            
        async def _routine(self):
            try:
                while True:
                    # does some "work"
                    asyncio.sleep(1e6)
                    
            except asyncio.CancelledError:
                self._log(f'`_routine()` interrupted. {e}')
                return
            except Exception as e:
                self._log(f'`_routine()` failed. {e}')
                raise e
        
    def test_dummy_module(self):
        port = 5555

        network_config = NetworkConfig('TEST_NETWORK',
                                            internal_address_map = {
                                                                    zmq.PUB: [f'tcp://*:{port}'],
                                                                    zmq.SUB: [f'tcp://*:{port+1}']})
            
        module = TestSimulationNode.DummyModule('TEST_MODULE', network_config)

        self.assertTrue(isinstance(module,InternalModule))