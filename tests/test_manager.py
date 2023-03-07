
import unittest
import concurrent.futures

from tqdm import tqdm
from dmas.manager import *


class TestSimulationManager(unittest.TestCase): 
    class Client(SimulationElement):
        def __init__(self, id : int, port : int, level: int = logging.INFO, logger: logging.Logger = None) -> None:
            network_config = NetworkConfig('TEST_NETWORK',
                                            external_address_map = {
                                                                    zmq.REQ: [f'tcp://localhost:{port}'],
                                                                    zmq.SUB: [f'tcp://localhost:{port+1}']})
            super().__init__(f'CLIENT_{id}', network_config, level, logger)

        async def _internal_sync(self) -> dict:
            return dict()

        async def _external_sync(self) -> dict:   
            try:         
                # inform manager client is online
                self._log('synchronizing to manager! connecting to manager\'s RES port...')
                sock, _ = self._external_socket_map.get(zmq.REQ)
                sock : zmq.Socket; 

                sever_addresses = self._network_config.get_external_addresses().get(zmq.REQ)
                sock.connect(sever_addresses[-1])
                self._log('connecting to manager\'s RES achieved!')
                
                while True:
                    self._log('sending sync request to manager...')
                    msg = NodeSyncRequestMessage(self.name, self._network_config.to_dict())
                    await self._send_external_msg(msg, zmq.REQ)
                    
                    self._log('sync request sent! awaiting for response from manager...')
                    dst, src, content = await self._receive_external_msg(zmq.REQ)
                    self._log(f'message received: {content}')
                    
                    if (dst not in self.name 
                        or SimulationElementRoles.MANAGER.value not in src 
                        or content['msg_type'] != ManagerMessageTypes.RECEPTION_ACK.value):
                        
                        print(dst not in self.name)
                        print(SimulationElementRoles.MANAGER.value not in src)
                        print(content['msg_type'] != ManagerMessageTypes.RECEPTION_ACK.value)

                        self._log('wrong message received. ignoring message...')
                        continue
                    else:
                        self._log('sync request accepted! disconnecting from manager\'s REQ port...')
                        break
                sock.disconnect(sever_addresses[-1])

                # wait for simulation info from manager
                self._log('disconnected from manager\'s REQ port! waiting for simulation info message from manager...')
                sock, _ = self._external_socket_map.get(zmq.SUB)
                sock : zmq.Socket; 

                # print(sock.)

                external_address_ledger = None
                clock_config = None

                while True:
                    dst, src, content = await self._receive_external_msg(zmq.SUB)
                    
                    self._log(f'message received: {content}')

                    if (dst not in self.name 
                        or SimulationElementRoles.MANAGER.value not in src 
                        or content['msg_type'] != ManagerMessageTypes.SIM_INFO.value):
                        self._log('wrong message received. ignoring message...')
                        continue
                    else:
                        self._log('simulation information message received!')
                        msg = SimulationInfoMessage(**content)
                        external_address_ledger = msg.get_address_ledger()
                        clock_config = msg.get_clock_info()
                        break
                
                return ClockConfig(**clock_config), external_address_ledger

            except asyncio.CancelledError:
                return

            except Exception as e:
                raise e

        async def _wait_sim_start(self) -> None:
            # inform manager client is online
            self._log('waiting for simulation to start! connecting to manager\'s RES port...')
            sock, _ = self._external_socket_map.get(zmq.REQ)
            sock : zmq.Socket; _ : asyncio.Lock

            sever_addresses = self._network_config.get_external_addresses().get(zmq.REQ)
            sock.connect(sever_addresses[-1])
            self._log('connecting to manager\'s RES achieved!')
            
            while True:
                self._log('sending ready message to manager...')
                msg = NodeReadyMessage(self.name)
                await self._send_external_msg(msg, zmq.REQ)
                
                self._log('ready message sent! awaiting for response from manager...')
                dst, src, content = await self._receive_external_msg(zmq.REQ)

                self._log(f'message received: {content}')

                if (dst not in self.name 
                    or SimulationElementRoles.MANAGER.value not in src 
                    or content['msg_type'] != ManagerMessageTypes.RECEPTION_ACK.value):
                    self._log('wrong message received. ignoring message...')
                    continue
                else:
                    self._log('ready message accepted! disconnecting from manager\'s REQ port...')
                    break
            sock.disconnect(sever_addresses[-1])

            self._log(f'disconnected from manager\'s REP port. waiting for simulation start message...')
            while True:
                dst, src, content = await self._receive_external_msg(zmq.SUB)

                self._log(f'message received: {content}', level=logging.DEBUG)

                if (dst not in self.name 
                    or SimulationElementRoles.MANAGER.value not in src 
                    or content['msg_type'] != ManagerMessageTypes.SIM_START.value):
                    self._log('wrong message received. ignoring message...')
                else:
                    self._log('simulation start message received! starting simulation...')
                    break

        async def _execute(self):
            self._log('executing...')
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

        async def _publish_deactivate(self) -> None:
            try:         
                # inform manager client is offline
                sock, _ = self._external_socket_map.get(zmq.REQ)
                sock : zmq.Socket; _ : asyncio.Lock

                sever_addresses = self._network_config.get_external_addresses().get(zmq.REQ)
                sock.connect(sever_addresses[-1])
                
                while True:
                    msg = NodeDeactivatedMessage(self.name)
                    await self._send_external_msg(msg, zmq.REQ)

                    dst, src, content = await self._receive_external_msg(zmq.REQ)
                    
                    if (dst not in self.name 
                        or SimulationElementRoles.MANAGER.value not in src 
                        or content['msg_type'] != ManagerMessageTypes.RECEPTION_ACK.value):
                        print(msg)
                        continue
                    else:
                        break

                sock.disconnect(sever_addresses[-1])

            except asyncio.CancelledError:
                return

            except Exception as e:
                raise e

    class TestManager(Manager):
        def __init__(self, simulation_element_name_list: list,port : int, level: int = logging.INFO) -> None:
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

    def test_init(self):
        n_clients = 1
        port = 5555

        simulation_element_name_list = []
        for i in range(n_clients):
            simulation_element_name_list.append(f'CLIENT_{i}')

        manager = TestSimulationManager.TestManager(simulation_element_name_list, port)

        self.assertTrue(isinstance(manager, Manager))

    def test_run(self):
        n_clients = 1
        port = 5555

        clients = []
        simulation_element_name_list = []
        for i in range(n_clients):
            client = TestSimulationManager.Client(i, port, level=logging.DEBUG)
            clients.append(client)
            simulation_element_name_list.append(client.name)

        manager = TestSimulationManager.TestManager(simulation_element_name_list, port, level=logging.DEBUG)
        
        print('\n')
        with concurrent.futures.ThreadPoolExecutor(len(clients) + 1) as pool:
            client : TestSimulationManager.Client
            for client in clients:                
                pool.submit(client.run, *[])
            pool.submit(manager.run, *[])

