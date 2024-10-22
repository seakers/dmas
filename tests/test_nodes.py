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

        async def sim_wait(self, delay: float) -> None:
            return asyncio.sleep(delay)
        
        async def setup(self) -> None:
            return

        async def teardown(self) -> None:
            return
        
        async def _external_sync(self) -> dict:
            return self._clock_config, dict()
        
        async def _internal_sync(self, _ : ClockConfig) -> dict:
            return dict()
        
        async def _wait_sim_start(self) -> None:
            return

        async def _execute(self) -> None:
            try:
                self.log('executing...')
                while True:
                    dst, src, content = await self._receive_external_msg(zmq.PULL)
                    
                    self.log(f'message received: {content}', level=logging.DEBUG)

                    if (dst not in self.name 
                        or SimulationElementRoles.MANAGER.value not in src 
                        or content['msg_type'] != ManagerMessageTypes.SIM_END.value):
                        self.log('wrong message received. ignoring message...')
                    else:
                        self.log('simulation end message received! ending simulation...')
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
                                            manager_address_map = {
                                                                    zmq.REP: [f'tcp://*:{port}'],
                                                                    zmq.PUB: [f'tcp://*:{port+1}'],
                                                                    zmq.PUSH: [f'tcp://localhost:{port+2}']})
            
            super().__init__(simulation_element_name_list, clock_config, network_config, level, logger)

        def _check_element_list(self):
            return
        
        async def setup(self) -> None:
            return

        async def teardown(self) -> None:
            return

        async def sim_wait(self, delay: float) -> None:
            try:
                if isinstance(self._clock_config, AcceleratedRealTimeClockConfig):
                    desc = f'{self.name}: Simulating for {delay}[s]'
                    for _ in tqdm (range (10), desc=desc):
                        await asyncio.sleep(delay/10)

                else:
                    raise NotImplemented(f'clock configuration of type {type(self._clock_config)} not yet supported.')

            except asyncio.CancelledError:
                return

    class DummyNode(Node):        
        async def setup(self) -> None:
            return

        async def live(self) -> None:
            try:
                work_task = asyncio.create_task(self.work_routine())
                listen_task = asyncio.create_task(self.listen_to_manager())
                tasks = [work_task, listen_task]

                _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

                for task in pending:
                    task : asyncio.Task
                    task.cancel()
                    await task
            
            except asyncio.CancelledError:
                self.log(f'`live()` interrupted.')
                return
            except Exception as e:
                self.log(f'`live()` failed. {e}')
                raise e

        async def work_routine(self) -> None:
            try:
                self.log(f'doing some work...')
                while True:
                    await asyncio.sleep(1.6*random.random())
            
            except asyncio.CancelledError:
                self.log('work being done was cancelled!')
                return

        async def listen_to_manager(self) -> None:
            try:
                self.log(f'waiting for manager to end simulation...')
                while True:
                    dst, src, content = await self._receive_manager_msg(zmq.SUB)
                    self.log(f'message received: {content}', level=logging.DEBUG)

                    if (dst not in self.name 
                        or SimulationElementRoles.MANAGER.value not in src 
                        or content['msg_type'] != ManagerMessageTypes.SIM_END.value):
                        self.log('wrong message received. ignoring message...')
                    else:
                        self.log('simulation end message received! ending simulation...')
                        break

            except asyncio.CancelledError:
                self.log(f'`live()` interrupted.')
                return
            except Exception as e:
                self.log(f'`live()` failed. {e}')
                raise e

        async def teardown(self) -> None:
            return
        
        async def sim_wait(self, delay: float) -> None:
            return asyncio.sleep(delay)

    class ModularTestNode(DummyNode):
        def __init__(   self, 
                        id: int, 
                        port : int, 
                        manager_network_config : NetworkConfig,
                        n_modules : int = 1, 
                        level: int = logging.INFO, 
                        logger:logging.Logger=None
                    ) -> None:
            
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

            node_network_config = NetworkConfig('TEST_NETWORK',
                                            internal_address_map=internal_address_map,
                                            manager_address_map={
                                                                    zmq.REQ: [f'tcp://localhost:{port}'],
                                                                    zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                                    zmq.PUSH: [f'tcp://localhost:{port+2}']})
            modules = []
            for i in range(n_modules):
                module_port = module_ports[i]
                module_sub_ports = []
                for port in module_ports:
                    if module_port != port:
                        module_sub_ports.append(port)
                module_sub_ports.append(node_pub_port)

                submodule_network_config = NetworkConfig(f'NODE_{id}',
                                                            manager_address_map = {
                                                                    zmq.REQ: [f'tcp://localhost:{node_rep_port}'],
                                                                    zmq.PUB: [f'tcp://*:{module_port}'],
                                                                    zmq.SUB: [f'tcp://localhost:{module_sub_port}' for module_sub_port in module_sub_ports],
                                                                    zmq.PUSH: [f'tcp://localhost:{port+2}']
                                                                                }
                                                        )
                
                modules.append( TestSimulationNode.DummyModule(f'MODULE_{i}', submodule_network_config, node_network_config, logger=logger) )

            super().__init__(   f'NODE_{id}', 
                                node_network_config, 
                                manager_network_config, 
                                modules, 
                                level=level, 
                                logger=logger)

    class DummyModule(InternalModule):
        def __init__(   self, 
                        module_name: str, 
                        module_network_config: NetworkConfig, 
                        parent_node_network_config: NetworkConfig, 
                        level: int = logging.INFO, 
                        logger: logging.Logger = None) -> None:
            super().__init__(module_name, module_network_config, parent_node_network_config, level, logger)
        
        # def __init__(self, module_name: str, network_config: NetworkConfig, parent_network_config : NetworkConfig, logger: logging.Logger = None) -> None:
        #     super().__init__(module_name, network_config, parent_network_config, [], logger=logger)

        async def setup(self) -> None:
            return

        async def teardown(self) -> None:
            return

        async def sim_wait(self, delay: float) -> None:
            await asyncio.sleep(delay)

        async def live(self) -> None:
            t_1 = asyncio.create_task(self.listen(),name='listen()')
            t_2 = asyncio.create_task(self.work(),name='work()')
            _, pending = await asyncio.wait([t_1, t_2], return_when=asyncio.FIRST_COMPLETED)

            for task in pending:
                task : asyncio.Task
                task.cancel()
                await task

        async def listen(self):
            try:
                # do some 'listening'
                self.log('listening...')
                
                await self._receive_manager_msg(zmq.SUB)
                   
            except asyncio.CancelledError:
                self.log(f'`listen()` interrupted.')
                return
            except Exception as e:
                self.log(f'`listen()` failed. {e}')
                raise e
            
        async def work(self):
            try:
                # do some 'work'
                self.log('doing some work...')
                while True:
                    await asyncio.sleep(2)
                   
            except asyncio.CancelledError:
                self.log(f'`work()` interrupted.')
                return
            except Exception as e:
                self.log(f'`work()` failed. {e}')
                raise e

    def test_init(self):
        port = 5555
        network_config = NetworkConfig('TEST', manager_address_map={
                                                                zmq.REQ: [f'tcp://localhost:{port}'],
                                                                zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                                zmq.PUSH: [f'tcp://localhost:{port+2}']})
        node = TestSimulationNode.DummyNode('NAME', network_config, [])

        with self.assertRaises(AttributeError):
            network_config = NetworkConfig('TEST', {})
            TestSimulationNode.DummyNode('NAME', network_config, [], logger=node.get_logger())

        with self.assertRaises(AttributeError):
            network_config = NetworkConfig('TEST', manager_address_map={
                                                                    zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                                    zmq.PUSH: [f'tcp://localhost:{port+2}']})
            TestSimulationNode.DummyNode('NAME', network_config, [], logger=node.get_logger())
        with self.assertRaises(AttributeError):
            network_config = NetworkConfig('TEST', manager_address_map={
                                                                    zmq.REQ: [f'tcp://localhost:{port}'],
                                                                    zmq.PUSH: [f'tcp://localhost:{port+2}']})
            TestSimulationNode.DummyNode('NAME', network_config, [], logger=node.get_logger())
        with self.assertRaises(AttributeError):
            network_config = NetworkConfig('TEST', manager_address_map={
                                                                    zmq.REQ: [f'tcp://localhost:{port}'],
                                                                    zmq.SUB: [f'tcp://localhost:{port+1}']})
            TestSimulationNode.DummyNode('NAME', network_config, [], logger=node.get_logger())
           
    def run_tester(self, clock_config : ClockConfig, n_nodes : int = 1, n_modules : int = 0, port : int = 5556, level : int = logging.WARNING, logger : logging.Logger = None):
        print(f'TESTING {n_nodes} NODES WITH {n_modules} MODULES')
        
        monitor = TestSimulationNode.DummyMonitor(clock_config, port, level, logger)
        
        logger = monitor.get_logger() if logger is None else logger

        simulation_element_name_list = []
        for i in range(n_nodes):            
            simulation_element_name_list.append(f'NODE_{i}')

        manager = TestSimulationNode.DummyManager(clock_config, simulation_element_name_list, port, level, logger)

        nodes = []
        for i in range(n_nodes):            
            node = TestSimulationNode.ModularTestNode(i, port, manager.get_network_config(), n_modules, level=level, logger=logger)
            nodes.append(node)

        with concurrent.futures.ThreadPoolExecutor(len(nodes) + 2) as pool:
            pool.submit(monitor.run, *[])
            pool.submit(manager.run, *[])
            node : TestSimulationNode.ModularTestNode
            for node in nodes:                
                pool.submit(node.run, *[])
        print('\n')

        return logger

    def test_sync_routine_realtime(self):
        print('\nTESTING SYNC ROUTINE')

        n_nodes = [10]
        n_modules = [3]
        level=logging.WARNING

        year = 2023
        month = 1
        day = 1
        hh = 12
        mm = 00
        ss = 00
        start_date = datetime(year, month, day, hh, mm, ss)
        end_date = datetime(year, month, day, hh, mm, ss+1)

        print('Real-time Clock Config:')
        port = random.randint(5555, 9999)
        clock_config = RealTimeClockConfig(start_date, end_date)

        logger = None
        for n in n_nodes:
            for m in n_modules:
                logger = self.run_tester(clock_config, n, m, port, level=level, logger=logger)

        print('\nAccelerated Real-time Clock Config:')
        port = random.randint(5555, 9999)
        clock_config = AcceleratedRealTimeClockConfig(start_date, end_date, 2.0)

        logger = None
        for n in n_nodes:
            for m in n_modules:
                logger = self.run_tester(clock_config, n, m, port, level=level, logger=logger)

        
    class TransmissionTypes(Enum):
        DIRECT = 'DIRECT'
        BROADCAST = 'BROADCAST'

    class PeerNode(Node):
        def __init__(   self, 
                        node_name : str, 
                        t_type,
                        node_network_config: NetworkConfig, 
                        manager_network_config: NetworkConfig, 
                        level: int = logging.INFO, 
                        logger: logging.Logger = None
                    ) -> None:
            super().__init__(node_name, 
                            node_network_config, 
                            manager_network_config, 
                            [],
                            level=level, 
                            logger=logger)
            self.t_type : TestSimulationNode.TransmissionTypes = t_type
            self.msgs = []

        async def sim_wait(self, delay: float) -> None:
            return asyncio.sleep(delay)
        
        async def setup(self) -> None:
            return

        async def teardown(self) -> None:
            return

    class PingNode(PeerNode):
        def __init__(   self, 
                        t_type, 
                        node_network_config: NetworkConfig,
                        manager_network_config: NetworkConfig, 
                        level: int = logging.INFO, 
                        logger: logging.Logger = None
                    ) -> None:
            super().__init__('PING', 
                            t_type, 
                            node_network_config,
                            manager_network_config, 
                            level, 
                            logger)

        async def listen_to_manager(self):
            poller = azmq.Poller()
            socket_manager, _ = self._manager_socket_map.get(zmq.SUB)
            poller.register(socket_manager, zmq.POLLIN)

            await poller.poll()

        async def send_ping(self):
            while True:
                # send ping
                msg = SimulationMessage(self.get_element_name(), f'PONG', 'PING')
                self.msgs.append(msg.to_dict())
                if self.t_type is TestSimulationNode.TransmissionTypes.BROADCAST:
                    # broadcast ping message 
                    await self.send_peer_broadcast(msg)

                elif self.t_type is TestSimulationNode.TransmissionTypes.DIRECT:
                    # send ping message
                    await self.send_peer_message(msg)

                # register sent message
                # print('PING: ', msg)

                # do some 'work'
                await asyncio.sleep(0.1*random.random())

        async def live(self) -> None:
            try:
                poller = azmq.Poller()
                socket_manager, _ = self._manager_socket_map.get(zmq.SUB)
                poller.register(socket_manager, zmq.POLLIN)

                if self.t_type is TestSimulationNode.TransmissionTypes.BROADCAST:
                    # wait for pong to be ready for boradcasts
                    await self.listen_peer_message()
                    resp = SimulationMessage(self.get_element_name(), f'PONG', 'OK')
                    await self.respond_peer_message(resp)
                
                _, pending = await asyncio.wait([asyncio.create_task(self.listen_to_manager()),
                                    asyncio.create_task(self.send_ping())],
                                    return_when=asyncio.FIRST_COMPLETED)
                
                for task in pending:
                    task : asyncio.Task
                    task.cancel()
                    await task

            except asyncio.CancelledError:
                self.log(f'`live()` interrupted.', level=logging.INFO)
                return

            except Exception as e:
                self.log(f'`live()` failed. {e}', level=logging.ERROR)
                raise e

    class PongNode(PeerNode):
        def __init__(   self, 
                        t_type, 
                        node_network_config: NetworkConfig,
                        manager_network_config: NetworkConfig, 
                        level: int = logging.INFO, 
                        logger: logging.Logger = None
                    ) -> None:
            super().__init__('PONG', t_type, node_network_config, manager_network_config, level, logger)

        async def live(self) -> None:
            try:
                poller = azmq.Poller()
                socket_manager, _ = self._manager_socket_map.get(zmq.SUB)
                poller.register(socket_manager, zmq.POLLIN)

                if self.t_type is TestSimulationNode.TransmissionTypes.BROADCAST:
                    # tell ping im ready for broadcasts
                    ready_msg = SimulationMessage(self.get_element_name(), f'PING', 'READY')
                    await self.send_peer_message(ready_msg)
                    socket_agents, _ = self._external_socket_map.get(zmq.SUB)
                else:
                    socket_agents, _ = self._external_socket_map.get(zmq.REP)

                poller.register(socket_agents, zmq.POLLIN)  

                while True:
                    socks = dict(await poller.poll())
                    
                    if socket_manager in socks:
                        # check for incoming manager messages
                        dst, src, content = await self._receive_manager_msg(zmq.SUB)
                        self.log(f'message received: {content}', level=logging.DEBUG)

                        if (dst not in self.name 
                            or SimulationElementRoles.MANAGER.value not in src 
                            or content['msg_type'] != ManagerMessageTypes.SIM_END.value):
                            self.log('wrong message received. ignoring message...')
                        else:
                            self.log('simulation end message received! ending simulation...')
                            break
                    
                    if socket_agents in socks:
                        # listen for ping messages
                        if self.t_type is TestSimulationNode.TransmissionTypes.BROADCAST:
                            # wait for ping message 
                            _, _, msg = await self.listen_peer_broadcast()
                            
                            # register received message
                            self.msgs.append(msg)

                        elif self.t_type is TestSimulationNode.TransmissionTypes.DIRECT:
                            # wait for ping message 
                            _, _, msg = await self.listen_peer_message()
                            
                            # register received message
                            self.msgs.append(msg)
                            
                            # respond to message
                            resp = SimulationMessage(self.get_element_name(), f'PING', 'PONG')
                            await self.respond_peer_message(resp)

            except asyncio.CancelledError:
                self.log(f'`live()` interrupted.', level=logging.INFO)
                return

            except Exception as e:
                self.log(f'`live()` failed. {e}', level=logging.ERROR)
                raise e

    def test_ping_pong_broadcast(self):
        print(f'PING-PONG TEST')
        port = random.randint(5555, 9999)
        level = logging.WARNING
        
        year = 2023
        month = 1
        day = 1
        hh = 12
        mm = 00
        ss = 00
        start_date = datetime(year, month, day, hh, mm, ss)
        end_date = datetime(year, month, day, hh, mm, ss+1)
        clock_config = RealTimeClockConfig(start_date, end_date)

        logger = None
        # for t_type in TestSimulationNode.TransmissionTypes:
        for t_type in [TestSimulationNode.TransmissionTypes.BROADCAST]:
            print(f'\nTransmission Type: {t_type.value}')
            monitor = TestSimulationNode.DummyMonitor(clock_config, port, level, logger)
            
            logger = monitor.get_logger() if logger is None else logger

            # simulation_element_name_list = [f'{monitor.get_network_name()}/PING', f'{monitor.get_network_name()}/PONG']
            simulation_element_name_list = ['PONG', 'PING']
            manager = TestSimulationNode.DummyManager(clock_config, simulation_element_name_list, port, level, logger)

            ping_network_config = NetworkConfig(manager.get_network_name(),
                                                manager_address_map = {
                                                                    zmq.REQ: [f'tcp://localhost:{port}'],
                                                                    zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                                    zmq.PUSH: [f'tcp://localhost:{port+2}']
                                                                    },
                                                external_address_map={
                                                                    zmq.REQ: [],
                                                                    zmq.PUB: [f'tcp://*:{port+3}'],
                                                                    zmq.REP: [f'tcp://*:{port+5}']
                                                                    })
            pong_network_config = NetworkConfig(manager.get_network_name(),
                                                manager_address_map = {
                                                                    zmq.REQ: [f'tcp://localhost:{port}'],
                                                                    zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                                    zmq.PUSH: [f'tcp://localhost:{port+2}']
                                                                    },
                                                external_address_map={
                                                                    zmq.REQ: [f'tcp://localhost:{port+5}'],
                                                                    zmq.REP: [f'tcp://*:{port+4}'],
                                                                    zmq.SUB: [f'tcp://localhost:{port+3}']
                                                                    })

            ping = TestSimulationNode.PingNode(t_type, ping_network_config, manager.get_network_config(), level, logger)
            pong = TestSimulationNode.PongNode(t_type, pong_network_config, manager.get_network_config(), level, logger)
            nodes = [ping, pong]

            with concurrent.futures.ThreadPoolExecutor(len(nodes) + 2) as pool:
                pool.submit(monitor.run, *[])
                pool.submit(manager.run, *[])
                node : TestSimulationNode.ModularTestNode
                for node in nodes:                
                    pool.submit(node.run, *[])
                    
            self.assertGreater(len(ping.msgs), 0)
            self.assertEqual(ping.msgs, pong.msgs)

    def test_ping_pong_direct(self):
        print(f'PING-PONG TEST')
        port = random.randint(5555, 9999)
        level = logging.WARNING
        
        year = 2023
        month = 1
        day = 1
        hh = 12
        mm = 00
        ss = 00
        start_date = datetime(year, month, day, hh, mm, ss)
        end_date = datetime(year, month, day, hh, mm, ss+1)
        clock_config = RealTimeClockConfig(start_date, end_date)

        logger = None
        for t_type in [TestSimulationNode.TransmissionTypes.DIRECT]:
            print(f'\nTransmission Type: {t_type.value}')
            monitor = TestSimulationNode.DummyMonitor(clock_config, port, level, logger)
            
            logger = monitor.get_logger() if logger is None else logger

            simulation_element_name_list = [f'PING', f'PONG']
            manager = TestSimulationNode.DummyManager(clock_config, simulation_element_name_list, port, level, logger)

            ping_network_config = NetworkConfig(manager.get_network_name(),
                                                manager_address_map = {
                                                                    zmq.REQ: [f'tcp://localhost:{port}'],
                                                                    zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                                    zmq.PUSH: [f'tcp://localhost:{port+2}']
                                                                    },
                                                external_address_map={
                                                                    zmq.REQ: [],
                                                                    zmq.PUB: [f'tcp://*:{port+3}'],
                                                                    zmq.REP: [f'tcp://*:{port+5}']
                                                                    })
            pong_network_config = NetworkConfig(manager.get_network_name(),
                                                manager_address_map = {
                                                                    zmq.REQ: [f'tcp://localhost:{port}'],
                                                                    zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                                    zmq.PUSH: [f'tcp://localhost:{port+2}']
                                                                    },
                                                external_address_map={
                                                                    zmq.REQ: [f'tcp://localhost:{port+5}'],
                                                                    zmq.REP: [f'tcp://*:{port+4}'],
                                                                    zmq.SUB: [f'tcp://localhost:{port+3}']
                                                                    })

            ping = TestSimulationNode.PingNode(t_type, ping_network_config, manager.get_network_config(), level, logger)
            pong = TestSimulationNode.PongNode(t_type, pong_network_config, manager.get_network_config(), level, logger)
            nodes = [ping, pong]

            with concurrent.futures.ThreadPoolExecutor(len(nodes) + 2) as pool:
                pool.submit(monitor.run, *[])
                pool.submit(manager.run, *[])
                node : TestSimulationNode.ModularTestNode
                for node in nodes:                
                    pool.submit(node.run, *[])
                    
            self.assertGreater(len(ping.msgs), 0)
            self.assertEqual(ping.msgs, pong.msgs)