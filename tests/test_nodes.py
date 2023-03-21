import unittest
import concurrent.futures

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
        
        async def _internal_sync(self, _ : ClockConfig) -> dict:
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

    class DummyNode(Node):
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

    class NonModularTestNode(DummyNode):
        def __init__(self, id: int, port : int, level: int = logging.INFO, logger:logging.Logger=None) -> None:
            network_config = NetworkConfig('TEST_NETWORK',
                                            external_address_map = {
                                                                    zmq.REQ: [f'tcp://localhost:{port}'],
                                                                    zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                                    zmq.PUSH: [f'tcp://localhost:{port+2}']})


            super().__init__(f'NODE_{id}', network_config, [], level, logger)
        
    class ModularTestNode(DummyNode):
        def __init__(self, id: int, port : int, n_modules : int = 1, level: int = logging.INFO, logger:logging.Logger=None) -> None:
            
            module_ports = []
            for i in range(n_modules):
                module_port = port + 3 + id*(n_modules + 2) + i
                module_ports.append(module_port)
            
            node_pub_port = port + 3 + id*(n_modules + 2) + n_modules
            node_rep_port = port + 3 + id*(n_modules + 2) + n_modules + 1

            print(f'NODE {id} NETWORK CONFIG:')
            print(f'\tMANAGER REQ AND PUB PORT:\t{[port, port+1]}')
            print(f'\tMONITOR PORT:\t\t\t{[port+2]}')
            print(f'\tINTERNAL MODULE PORTS:\t\t{module_ports}')
            print(f'\tINTERNAL PUB AND REP PORTS:\t{[node_pub_port, node_rep_port]}\n')

            if n_modules > 0:
                internal_address_map = {
                                        zmq.REP: [f'tcp://*:{node_rep_port}'],
                                        zmq.PUB: [f'tcp://*:{node_pub_port}'],
                                        zmq.SUB: [f'tcp://localhost:{module_port}' for module_port in module_ports]
                                        }
            else:
                internal_address_map = dict()

            network_config = NetworkConfig('TEST_NETWORK',
                                            internal_address_map=internal_address_map,
                                            external_address_map={
                                                                    zmq.REQ: [f'tcp://localhost:{port}'],
                                                                    zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                                    zmq.PUSH: [f'tcp://localhost:{port+2}']})
            submodules = []
            for i in range(n_modules):
                module_port = module_ports[i]
                module_sub_ports = []
                for port in module_ports:
                    if module_port != port:
                        module_sub_ports.append(port)
                module_sub_ports.append(node_pub_port)

                submodule_network_config = NetworkConfig(f'NODE_{id}',
                                            internal_address_map = {
                                                                    zmq.REQ: [f'tcp://localhost:{node_rep_port}'],
                                                                    zmq.PUB: [f'tcp://*:{module_port}'],
                                                                    zmq.SUB: [f'tcp://localhost:{module_sub_port}' for module_sub_port in module_sub_ports]})
                
                submodules.append( TestSimulationNode.DummyModule(f'MODULE_{i}', submodule_network_config, logger) )

            super().__init__(f'NODE_{id}', network_config, submodules, level, logger)

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
                # do some 'work'
                self._log('doing some work...')
                while True:
                    await asyncio.sleep(2)
                   
            except asyncio.CancelledError:
                self._log(f'`_routine()` interrupted. {e}')
                return
            except Exception as e:
                self._log(f'`_routine()` failed. {e}')
                raise e

    def run_tester(self, clock_config : ClockConfig, n_nodes : int = 1, n_modules : int = 0, port : int = 5556, level : int = logging.WARNING):
        print(f'TESTING {n_nodes} NODES WITH {n_modules} MODULES')
        
        monitor = TestSimulationNode.DummyMonitor(clock_config, port, level)
        logger = monitor.get_logger()

        nodes = []
        simulation_element_name_list = []
        for i in range(n_nodes):            
            node = TestSimulationNode.ModularTestNode(i, port, n_modules, level, logger)
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

    def test_realtime_run(self):
        print('\nTESTING REAL-TIME CLOCK MANAGER')
        n_nodes = [2, 20]
        n_modules = [0, 4]
        port = 5555

        year = 2023
        month = 1
        day = 1
        hh = 12
        mm = 00
        ss = 00
        start_date = datetime(year, month, day, hh, mm, ss)
        end_date = datetime(year, month, day, hh, mm, ss+1)

        clock_config = RealTimeClockConfig(start_date, end_date)

        for n in n_nodes:
            for m in n_modules:
                self.run_tester(clock_config, n, m, port, level=logging.WARNING)
    
    def test_accelerated_realtime_run(self):
        print('\nTESTING ACCELERATED REAL-TIME CLOCK MANAGER')
        n_nodes = [2, 20]
        n_modules = [0, 4]
        port = 5555

        year = 2023
        month = 1
        day = 1
        hh = 12
        mm = 00
        ss = 00
        start_date = datetime(year, month, day, hh, mm, ss)
        end_date = datetime(year, month, day, hh, mm, ss+1)

        clock_config = AcceleratedRealTimeClockConfig(start_date, end_date, 2.0)

        for n in n_nodes:
            for m in n_modules:
                self.run_tester(clock_config, n, m, port, level=logging.WARNING)
