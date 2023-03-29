
import unittest
import concurrent.futures

from tqdm import tqdm
from dmas.managers import *


class TestSimulationManager(unittest.TestCase): 
    class Client(SimulationElement):
        def __init__(self, id : int, port : int, level: int = logging.INFO, logger: logging.Logger = None) -> None:
            network_config = NetworkConfig('TEST_NETWORK',
                                            manager_address_map= {
                                                                    zmq.REQ: [f'tcp://localhost:{port}'],
                                                                    zmq.SUB: [f'tcp://localhost:{port+1}']})
            super().__init__(f'CLIENT_{id}', network_config, level, logger)

        async def _activate(self) -> None:
            # give manager time to set up
            self.log('waiting for simulation manager to configure its network...', level=logging.INFO) 
            await asyncio.sleep(1e-1 * random.random())

            # perform activation routine
            await super()._activate()

        async def _sim_wait(self, delay: float) -> None:
            return asyncio.sleep(delay)
        
        async def setup(self) -> None:
            return

        async def teardown(self) -> None:
            return

        async def _internal_sync(self, _) -> dict:
            return dict()

        async def _external_sync(self) -> dict:   
            try:         
                # inform manager client is online
                self.log('synchronizing to manager! connecting to manager\'s RES port...')
                sock, _ = self._manager_socket_map.get(zmq.REQ)
                sock : zmq.Socket; 

                sever_addresses = self._network_config.get_manager_addresses().get(zmq.REQ)
                sock.connect(sever_addresses[-1])
                self.log('connecting to manager\'s RES achieved!')
                
                while True:
                    self.log('sending sync request to manager...')
                    msg = NodeSyncRequestMessage(self.name, self._network_config.to_dict())
                    await self._send_manager_msg(msg, zmq.REQ)
                    
                    self.log('sync request sent! awaiting for response from manager...')
                    dst, src, content = await self._receive_manager_msg(zmq.REQ)
                    self.log(f'message received: {content}')
                    
                    if (dst not in self.name 
                        or SimulationElementRoles.MANAGER.value not in src 
                        or content['msg_type'] != ManagerMessageTypes.RECEPTION_ACK.value):
                        
                        print(dst not in self.name)
                        print(SimulationElementRoles.MANAGER.value not in src)
                        print(content['msg_type'] != ManagerMessageTypes.RECEPTION_ACK.value)

                        self.log('wrong message received. ignoring message...')
                        continue
                    else:
                        self.log('sync request accepted! disconnecting from manager\'s REQ port...')
                        break
                sock.disconnect(sever_addresses[-1])

                # wait for simulation info from manager
                self.log('disconnected from manager\'s REQ port! waiting for simulation info message from manager...')
                sock, _ = self._manager_socket_map.get(zmq.SUB)
                sock : zmq.Socket; 
                
                external_address_ledger = None
                clock_config = None

                while True:
                    dst, src, content = await self._receive_manager_msg(zmq.SUB)
                    
                    self.log(f'message received: {content}')

                    if (dst not in self.name 
                        or SimulationElementRoles.MANAGER.value not in src 
                        or content['msg_type'] != ManagerMessageTypes.SIM_INFO.value):
                        self.log('wrong message received. ignoring message...')
                        continue
                    else:
                        self.log('simulation information message received!')
                        msg = SimulationInfoMessage(**content)
                        external_address_ledger = msg.get_address_ledger()
                        clock_config = msg.get_clock_info()
                        break
                
                clock_type = clock_config['clock_type']
                if clock_type == ClockTypes.REAL_TIME.value:
                    return RealTimeClockConfig(**clock_config), external_address_ledger
                    
                elif clock_type == ClockTypes.ACCELERATED_REAL_TIME.value:
                    return AcceleratedRealTimeClockConfig(**clock_config), external_address_ledger

                else:
                    raise NotImplementedError(f'clock type {clock_type} not yet implemented.')


            except asyncio.CancelledError:
                return

            except Exception as e:
                raise e

        async def _wait_sim_start(self) -> None:
            # inform manager client is online
            self.log('waiting for simulation to start! connecting to manager\'s RES port...')
            sock, _ = self._manager_socket_map.get(zmq.REQ)
            sock : zmq.Socket; _ : asyncio.Lock

            sever_addresses = self._network_config.get_manager_addresses().get(zmq.REQ)
            sock.connect(sever_addresses[-1])
            self.log('connecting to manager\'s RES achieved!')
            
            while True:
                self.log('sending ready message to manager...')
                msg = NodeReadyMessage(self.name)
                await self._send_manager_msg(msg, zmq.REQ)
                
                self.log('ready message sent! awaiting for response from manager...')
                dst, src, content = await self._receive_manager_msg(zmq.REQ)

                self.log(f'message received: {content}')

                if (dst not in self.name 
                    or SimulationElementRoles.MANAGER.value not in src 
                    or content['msg_type'] != ManagerMessageTypes.RECEPTION_ACK.value):
                    self.log('wrong message received. ignoring message...')
                    continue
                else:
                    self.log('ready message accepted! disconnecting from manager\'s REQ port...')
                    break
            sock.disconnect(sever_addresses[-1])

            # wait for simulation start message from manager
            self.log(f'disconnected from manager\'s REP port. waiting for simulation start message...')
            while True:
                dst, src, content = await self._receive_manager_msg(zmq.SUB)

                self.log(f'message received: {content}', level=logging.DEBUG)

                if (dst not in self.name 
                    or SimulationElementRoles.MANAGER.value not in src 
                    or content['msg_type'] != ManagerMessageTypes.SIM_START.value):
                    self.log('wrong message received. ignoring message...')
                else:
                    self.log('simulation start message received! starting simulation...')
                    break

        async def _execute(self):
            self.log('executing...')
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

        async def _publish_deactivate(self) -> None:
            try:         
                # inform manager client is offline
                sock, _ = self._manager_socket_map.get(zmq.REQ)
                sock : zmq.Socket; _ : asyncio.Lock

                sever_addresses = self._network_config.get_manager_addresses().get(zmq.REQ)
                sock.connect(sever_addresses[-1])
                
                while True:
                    msg = NodeDeactivatedMessage(self.name)
                    await self._send_manager_msg(msg, zmq.REQ)

                    dst, src, content = await self._receive_manager_msg(zmq.REQ)
                    self.log(f'message received: {content}', level=logging.DEBUG)
                    
                    if (dst not in self.name 
                        or SimulationElementRoles.MANAGER.value not in src 
                        or content['msg_type'] != ManagerMessageTypes.RECEPTION_ACK.value):
                        continue
                    else:
                        break

                sock.disconnect(sever_addresses[-1])

            except asyncio.CancelledError:
                return

            except Exception as e:
                raise e

    class DummyMonitor(SimulationElement):
        def __init__(self, clock_config : ClockConfig, port : int, level: int = logging.INFO, logger: logging.Logger = None) -> None:
            network_config = NetworkConfig('TEST_NETWORK',
                                            manager_address_map= {zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                                  zmq.PULL: [f'tcp://*:{port+2}']})
            
            super().__init__('MONITOR', network_config, level, logger)
            self._clock_config = clock_config

        async def _sim_wait(self, delay: float) -> None:
            return asyncio.sleep(delay)
        
        async def setup(self) -> None:
            return

        async def teardown(self) -> None:
            return

        async def _external_sync(self) -> dict:
            return self._clock_config, dict()
        
        async def _internal_sync(self, _) -> dict:
            return dict()
        
        async def _wait_sim_start(self) -> None:
            return

        async def _execute(self) -> None:
            try:
                self.log('executing...')
                while True:
                    dst, src, content = await self._receive_manager_msg(zmq.PULL)
                    
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
        def _check_element_list(self):
                return
        
        async def setup(self) -> None:
            return

        async def teardown(self) -> None:
            return
        

    class TestManager(DummyManager):
        def __init__(self, clock_config, simulation_element_name_list: list,port : int, level: int = logging.INFO, logger = None) -> None:
            network_config = NetworkConfig('TEST_NETWORK',
                                            manager_address_map = {
                                                                    zmq.REP: [f'tcp://*:{port}'],
                                                                    zmq.PUB: [f'tcp://*:{port+1}'],
                                                                    zmq.PUSH: [f'tcp://localhost:{port+2}']})
            
            super().__init__(simulation_element_name_list, clock_config, network_config, level, logger)

    def test_init(self):
        n_clients = 1
        port = 5555

        year = 2023
        month = 1
        day = 1
        hh = 12
        mm = 00
        ss = 00
        start_date = datetime(year, month, day, hh, mm, ss)
        end_date = datetime(year, month, day, hh, mm, ss+1)

        clock_config = RealTimeClockConfig(str(start_date), str(end_date))

        simulation_element_name_list = []
        for i in range(n_clients):
            simulation_element_name_list.append(f'CLIENT_{i}')

        manager = TestSimulationManager.TestManager(clock_config, simulation_element_name_list, port)

        self.assertTrue(isinstance(manager, AbstractManager))

        with self.assertRaises(AttributeError):
            network_config = NetworkConfig('TEST', manager_address_map= {
                                                                    zmq.REP: [f'tcp://*:{port}'],
                                                                    zmq.PUB: [f'tcp://*:{port+1}'],
                                                                    zmq.PUSH: [f'tcp://localhost:{port+2}']})
            TestSimulationManager.DummyManager('[]', clock_config, network_config)
        with self.assertRaises(AttributeError):
            TestSimulationManager.DummyManager([], 'clock_config', network_config)
        with self.assertRaises(AttributeError):
            network_config = NetworkConfig('TEST', manager_address_map = {
                                                                    zmq.PUB: [f'tcp://*:{port+1}'],
                                                                    zmq.PUSH: [f'tcp://localhost:{port+2}']})
            TestSimulationManager.DummyManager([], clock_config, network_config)
        with self.assertRaises(AttributeError):
            network_config = NetworkConfig('TEST', manager_address_map = {
                                                                    zmq.REP: [f'tcp://*:{port}'],
                                                                    zmq.PUSH: [f'tcp://localhost:{port+2}']})
            TestSimulationManager.DummyManager([], clock_config, network_config)
        with self.assertRaises(AttributeError):
            network_config = NetworkConfig('TEST', manager_address_map = {
                                                                    zmq.REP: [f'tcp://*:{port}'],
                                                                    zmq.PUB: [f'tcp://*:{port+1}']})
            TestSimulationManager.DummyManager([], clock_config, network_config)
        with self.assertRaises(AttributeError):
            network_config = NetworkConfig('TEST', {})
            TestSimulationManager.DummyManager([], clock_config, network_config)


    def run_tester(self, clock_config : ClockConfig, n_clients : int = 1, port : int = 5556, level : int = logging.WARNING):
        monitor = TestSimulationManager.DummyMonitor(clock_config, port, level)
        logger = monitor.get_logger()

        clients = []
        simulation_element_name_list = []
        for i in range(n_clients):
            client = TestSimulationManager.Client(i, port, level, logger)
            clients.append(client)
            simulation_element_name_list.append(client.name)

        manager = TestSimulationManager.TestManager(clock_config, simulation_element_name_list, port, level, logger)
        
        with concurrent.futures.ThreadPoolExecutor(len(clients) + 2) as pool:
            pool.submit(manager.run, *[])
            client : TestSimulationManager.Client
            for client in clients:                
                pool.submit(client.run, *[])
            pool.submit(monitor.run, *[])
        print('\n')


    def test_realtime_clock_run(self):        
        print('\nTESTING REAL-TIME CLOCK MANAGER')
        n_clients = [1, 5, 20]
        # n_clients = [1]

        year = 2023
        month = 1
        day = 1
        hh = 12
        mm = 00
        ss = 00
        start_date = datetime(year, month, day, hh, mm, ss)
        end_date = datetime(year, month, day, hh, mm, ss+1)

        for n in n_clients:
            clock_config = RealTimeClockConfig(str(start_date), str(end_date))
            self.run_tester(clock_config, n, level=logging.WARNING)

    def test_accelerated_clock_run(self):
        print('\nTESTING ACCELERATED REAL-TIME CLOCK MANAGER')
        n_clients = [1, 5, 20]

        year = 2023
        month = 1
        day = 1
        hh = 12
        mm = 00
        ss = 00
        start_date = datetime(year, month, day, hh, mm, ss)
        end_date = datetime(year, month, day, hh, mm, ss+1)

        for n in n_clients:
            clock_config = AcceleratedRealTimeClockConfig(str(start_date), str(end_date), 2)
            self.run_tester(clock_config, n, level=logging.WARNING)