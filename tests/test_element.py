
import unittest
import concurrent.futures

from tqdm import tqdm
from dmas.element import *


class TestSimulationElement(unittest.TestCase): 
    class DummyNetworkElement(SimulationElement):
        def __init__(self, element_name: str, network_config: NetworkConfig, level: int = logging.INFO, logger: logging.Logger = None) -> None:
            super().__init__(element_name, network_config, level, logger)
            self.msgs = []        

        async def _internal_sync(self, _) -> dict:
            return dict()

        async def _sim_wait(self, delay: float) -> None:
            return asyncio.sleep(delay)
        
        async def setup(self) -> None:
            return

        async def teardown(self) -> None:
            return

    class Server(DummyNetworkElement):        
        def __init__(self, port : int, n_clients: int = 1, dt : float = 1.0, level: int = logging.INFO, logger: logging.Logger = None) -> None:
            network_config = NetworkConfig('TEST_NETWORK',
                                            manager_address_map = {
                                                                    zmq.REP: [f'tcp://*:{port}'],
                                                                    zmq.PUB: [f'tcp://*:{port+1}']})
            super().__init__(f'SERVER', network_config, level, logger)
            self.n_clients = n_clients
            self.dt = dt

        async def _external_sync(self) -> dict:
            try:
                synced = []
                desc = f'{self.name}: Synchronizing'

                with tqdm(total=self.n_clients, desc=desc) as pbar:
                    while len(synced) < self.n_clients:
                        dst, src, content = await self._receive_manager_msg(zmq.REP)
                        msg = SimulationMessage(**content)

                        self.log(f'message recived: {msg}')

                        if dst not in self.name:
                            self.log(f'NOT INTENDED FOR ME {dst} != {self.name}')
                            resp = SimulationMessage(self.name, src, 'NO')
                        elif src in synced:
                            self.log('ALREADY SYNCED')
                            resp = SimulationMessage(self.name, src, 'NO')
                        elif msg.msg_type != 'SYNC':
                            self.log('NOT A SYNC MESSAGE')
                            resp = SimulationMessage(self.name, src, 'NO')
                        else:
                            synced.append(src)
                            pbar.update(1)
                            resp = SimulationMessage(self.name, src, 'OK')
                            
                        await self._send_manager_msg(resp, zmq.REP)

                year = 2023
                month = 1
                day = 1
                hh = 12
                mm = 00
                ss = 00
                start_date = datetime(year, month, day, hh, mm, ss)
                end_date = datetime(year, month, day+1, hh, mm, ss)
                return RealTimeClockConfig(str(start_date), str(end_date)), dict()

            except asyncio.CancelledError:
                return

            except Exception as e:
                raise e
        
        async def _wait_sim_start(self) -> None:
            await asyncio.sleep(0.1)
            msg = SimulationMessage(self.name, self._network_name, 'START')
            await self._send_manager_msg(msg, zmq.PUB)

        async def _execute(self):
            # wait for dt seconds
            desc = f'{self.name}: Working      '
            for _ in tqdm (range (10), desc=desc):
                await asyncio.sleep(self.dt/10)

            # publish sim is over
            msg = SimulationMessage(self.name, self._network_name, 'END')
            await self._send_manager_msg(msg, zmq.PUB)

            # wait for response
            deactivated = []
            desc = f'{self.name}: Deactivating '

            with tqdm(total=self.n_clients, desc=desc) as pbar:
                while len(deactivated) < self.n_clients:
                    dst, src, content = await self._receive_manager_msg(zmq.REP)
                    msg = SimulationMessage(**content)

                    self.log(f'message recived: {msg}')

                    if dst not in self.name:
                        self.log(f'NOT INTENDED FOR ME {dst} != {self.name}')
                        resp = SimulationMessage(self.name, src, 'NO')
                    elif src in deactivated:
                        self.log('ALREADY TERMINATED')
                        resp = SimulationMessage(self.name, src, 'NO')
                    elif msg.msg_type != 'TERMINATED':
                        self.log('NOT A TERMINATED MESSAGE')
                        resp = SimulationMessage(self.name, src, 'NO')
                    else:
                        deactivated.append(src)
                        pbar.update(1)
                        resp = SimulationMessage(self.name, src, 'OK')
                        
                    await self._send_manager_msg(resp, zmq.REP)
           
        async def _publish_deactivate(self) -> None:
            return

    class Client(DummyNetworkElement):
        def __init__(self, id : int, port : int, level: int = logging.INFO, logger: logging.Logger = None) -> None:
            network_config = NetworkConfig('TEST_NETWORK',
                                            manager_address_map= {
                                                                    zmq.REQ: [f'tcp://localhost:{port}'],
                                                                    zmq.SUB: [f'tcp://localhost:{port+1}']})
            super().__init__(f'CLIENT_{id}', network_config, level, logger)

        async def _external_sync(self) -> dict:   
            try:         
                sock, _ = self._manager_socket_map.get(zmq.REQ)
                sock : zmq.Socket; _ : asyncio.Lock

                server_addresses = self._network_config.get_manager_addresses().get(zmq.REQ)
                sock.connect(server_addresses[-1])
                
                while True:
                    msg = SimulationMessage(self.name, self._network_name + '/SERVER', 'SYNC')
                    await self._send_manager_msg(msg, zmq.REQ)

                    dst, src, content = await self._receive_manager_msg(zmq.REQ)
                    msg = SimulationMessage(**content)

                    if (dst not in self.name 
                        or 'SERVER' not in src 
                        or msg.msg_type != 'OK'):
                        print(msg)
                        continue
                    else:
                        break
                
                sock.disconnect(server_addresses[-1])

                year = 2023
                month = 1
                day = 1
                hh = 12
                mm = 00
                ss = 00
                start_date = datetime(year, month, day, hh, mm, ss)
                end_date = datetime(year, month, day+1, hh, mm, ss)
                return RealTimeClockConfig(str(start_date), str(end_date)), dict()

            except asyncio.CancelledError:
                return

            except Exception as e:
                raise e

        async def _wait_sim_start(self) -> None:
            while True:
                dst, src, content = await self._receive_manager_msg(zmq.SUB)
                msg = SimulationMessage(**content)

                self.log(content, level=logging.DEBUG)

                if (dst not in self.name 
                    or 'SERVER' not in src 
                    or msg.msg_type != 'START'):
                    continue
                else:
                    break

        async def _execute(self):
            while True:
                dst, src, content = await self._receive_manager_msg(zmq.SUB)
                msg = SimulationMessage(**content)

                self.log(content, level=logging.DEBUG)

                if (dst not in self.name 
                    or 'SERVER' not in src 
                    or msg.msg_type != 'END'):
                    continue
                else:
                    break

        async def _publish_deactivate(self) -> None:
            try:         
                sock, _ = self._manager_socket_map.get(zmq.REQ)
                sock : zmq.Socket; _ : asyncio.Lock

                sever_addresses = self._network_config.get_manager_addresses().get(zmq.REQ)
                sock.connect(sever_addresses[-1])
                
                while True:
                    msg = SimulationMessage(self.name, self._network_name + '/SERVER', 'TERMINATED')
                    await self._send_manager_msg(msg, zmq.REQ)

                    dst, src, content = await self._receive_manager_msg(zmq.REQ)
                    msg = SimulationMessage(**content)

                    if (dst not in self.name 
                        or 'SERVER' not in src 
                        or msg.msg_type != 'OK'):
                        print(msg)
                        continue
                    else:
                        break
                
                sock.disconnect(sever_addresses[-1])

            except asyncio.CancelledError:
                return

            except Exception as e:
                raise e

    def test_run(self):
        print('TEST: Simulation Element Sync Routine')
        port = 5556
        n_clients = 10

        server = TestSimulationElement.Server(port, n_clients, level=logging.WARNING)
        logger = server.get_logger()
        clients = []
        for id in range(n_clients):
            clients.append(TestSimulationElement.Client(id, port,logger=logger))

        print('\n')
        with concurrent.futures.ThreadPoolExecutor(len(clients) + 1) as pool:
            client : TestSimulationElement.Client
            for client in clients:                
                pool.submit(client.run, *[])
            pool.submit(server.run, *[])
    