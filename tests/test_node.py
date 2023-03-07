import unittest
import concurrent.futures

from tqdm import tqdm
from dmas.node import *
from dmas.manager import *


class TestSimulationNode(unittest.TestCase): 
    class DummyMonitor(SimulationElement):
        def __init__(self, port : int, level: int = logging.INFO, logger: logging.Logger = None) -> None:
            network_config = NetworkConfig('TEST_NETWORK',
                                            external_address_map = {zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                                    zmq.PULL: [f'tcp://localhost:{port+2}']})
            
            super().__init__('MONITOR', network_config, level, logger)

            year = 2023
            month = 1
            day = 1
            hh = 12
            mm = 00
            ss = 00
            start_date = datetime(year, month, day, hh, mm, ss)
            end_date = datetime(year, month, day+1, hh, mm, ss)

            self._clock_config = RealTimeClockConfig(str(start_date), str(end_date))

        
        async def _external_sync(self) -> dict:
            return self._clock_config, dict()
        
        async def _internal_sync(self) -> dict:
            return dict()
        
        async def _wait_sim_start(self) -> None:
            return

        async def _execute(self) -> None:
            try:
                self._log('executing...')
                while True:
                    dst, src, content = await self._receive_external_msg(zmq.PULL)
                    
                    self._log(f'message received: {content}', level=logging.DEBUG)

                    if (dst not in self.name 
                        or SimulationElementRoles.MANAGER.value not in src 
                        or content['msg_type'] != ManagerMessageTypes.SIM_END.value):
                        self._log('wrong message received. ignoring message...')
                    else:
                        self._log('simulation end message received! ending simulation...')
                        break
            except asyncio.CancelledError:
                return

            except Exception as e:
                raise e

        async def _publish_deactivate(self) -> None:
            return 

    class DummyManager(AbstractManager):
        def __init__(self, simulation_element_name_list : list, port : int, level : int = logging.INFO) -> None:
            year = 2023
            month = 1
            day = 1
            hh = 12
            mm = 00
            ss = 00
            start_date = datetime(year, month, day, hh, mm, ss)
            end_date = datetime(year, month, day+1, hh, mm, ss)

            clock_config = RealTimeClockConfig(str(start_date), str(end_date))

            network_config = NetworkConfig('TEST_NETWORK',
                                            external_address_map = {
                                                                    zmq.REP: [f'tcp://*:{port}'],
                                                                    zmq.PUB: [f'tcp://*:{port+1}'],
                                                                    zmq.PUSH: [f'tcp://*:{port+2}']})
            
            super().__init__(simulation_element_name_list, clock_config, network_config, level)

        def _check_element_list(self):
            return

    class NonModularTestNode(Node):
        def __init__(self, id: int, port : int, level: int = logging.INFO) -> None:
            network_config = NetworkConfig('TEST_NETWORK',
                                            external_address_map = {
                                                                    zmq.REQ: [f'tcp://localhost:{port}'],
                                                                    zmq.SUB: [f'tcp://localhost:{port+1}']})


            super().__init__(f'Node_{id}', network_config, [], level)

        

    def test_init(self):
        node = TestSimulationNode.NonModularTestNode(1, 5555)

        self.assertEqual(type(node), TestSimulationNode.NonModularTestNode)