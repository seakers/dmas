import unittest
import concurrent.futures

from tqdm import tqdm
from dmas.nodes import *
from dmas.managers import *
from dmas.modules import *


class TestSimulationNode(unittest.TestCase): 
    class DummyMonitor(SimulationElement):
        def __init__(self, clock_config : ClockConfig, port : int, level: int = logging.INFO, logger: logging.Logger = None) -> None:
            network_config = NetworkConfig('TEST_NETWORK',
                                            external_address_map = {zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                                    zmq.PULL: [f'tcp://*:{port+2}']})
            
            super().__init__('MONITOR', network_config, level, logger)
            self._clock_config = clock_config

        
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
        def __init__(self, clock_config, simulation_element_name_list : list, port : int, level : int = logging.INFO, logger : logging.Logger = None) -> None:
            network_config = NetworkConfig('TEST_NETWORK',
                                            external_address_map = {
                                                                    zmq.REP: [f'tcp://*:{port}'],
                                                                    zmq.PUB: [f'tcp://*:{port+1}'],
                                                                    zmq.PUSH: [f'tcp://localhost:{port+2}']})
            
            super().__init__(simulation_element_name_list, clock_config, network_config, level, logger)

        def _check_element_list(self):
            return

    class NonModularTestNode(Node):
        def __init__(self, id: int, port : int, level: int = logging.INFO, logger:logging.Logger=None) -> None:
            network_config = NetworkConfig('TEST_NETWORK',
                                            external_address_map = {
                                                                    zmq.REQ: [f'tcp://localhost:{port}'],
                                                                    zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                                    zmq.PUSH: [f'tcp://localhost:{port+2}']})


            super().__init__(f'Node_{id}', network_config, [], level, logger)

        async def _live(self) -> None:
            self._log(f'waiting for manager to end simulation...')
            while True:
                dst, src, content = await self._receive_external_msg(zmq.SUB)
                self._log(f'message received: {content}', level=logging.DEBUG)

                if (dst not in self.name 
                    or SimulationElementRoles.MANAGER.value not in src 
                    or content['msg_type'] != ManagerMessageTypes.SIM_END.value):
                    self._log('wrong message received. ignoring message...')
                else:
                    self._log('simulation end message received! ending simulation...')
                    break

    def run_tester(self, clock_config : ClockConfig, n_nodes : int = 1, port : int = 5556, level : int = logging.WARNING):
        monitor = TestSimulationNode.DummyMonitor(clock_config, port, level)
        logger = monitor.get_logger()

        nodes = []
        simulation_element_name_list = []
        for i in range(n_nodes):
            node = TestSimulationNode.NonModularTestNode(i, port, level, logger)
            nodes.append(node)
            simulation_element_name_list.append(node.name)

        manager = TestSimulationNode.DummyManager(clock_config, simulation_element_name_list, port, level, logger)
        
        with concurrent.futures.ThreadPoolExecutor(len(nodes) + 2) as pool:
            pool.submit(monitor.run, *[])
            pool.submit(manager.run, *[])
            node : TestSimulationNode.NonModularTestNode
            for node in nodes:                
                pool.submit(node.run, *[])
        print('\n')

    def test_init(self):
        node = TestSimulationNode.NonModularTestNode(1, 5555)
        self.assertEqual(type(node), TestSimulationNode.NonModularTestNode)

    def test__realtime_run(self):
        print('\nTESTING REAL-TIME CLOCK MANAGER')
        n_nodes = 1

        year = 2023
        month = 1
        day = 1
        hh = 12
        mm = 00
        ss = 00
        start_date = datetime(year, month, day, hh, mm, ss)
        end_date = datetime(year, month, day, hh, mm, ss+1)

        clock_config = RealTimeClockConfig(str(start_date), str(end_date))
        self.run_tester(clock_config, n_nodes, level=logging.WARNING)

    def test_accelerated_run(self):
        print('\nTESTING ACCELERATED REAL-TIME CLOCK MANAGER')
        n_nodes = 1

        year = 2023
        month = 1
        day = 1
        hh = 12
        mm = 00
        ss = 00
        start_date = datetime(year, month, day, hh, mm, ss)
        end_date = datetime(year, month, day, hh, mm, ss+1)

        clock_config = AcceleratedRealTimeClockConfig(str(start_date), str(end_date), 2.0)
        self.run_tester(clock_config, n_nodes, level=logging.WARNING)

    class DummyModule(InternalModule):
        def __init__(self, module_name: str, network_config: InternalModuleNetworkConfig, logger: logging.Logger = None) -> None:
            super().__init__(module_name, network_config, logger, [])

        
    def test_dummy_module(self):
        network_config = NetworkConfig('TEST_NETWORK',
                                            external_address_map = {
                                                                    zmq.REP: [f'tcp://*:{port}'],
                                                                    zmq.PUB: [f'tcp://*:{port+1}'],
                                                                    zmq.PUSH: [f'tcp://localhost:{port+2}']})
            
        module = TestSimulationNode.DummyModule('TEST_MODULE', network_config)