import json
import random
import unittest
from tqdm import tqdm

import zmq
import concurrent.futures

from dmas.network import *

class TestNetworkConfig(unittest.TestCase): 
    def test_init(self):
        network_name = 'TEST_NETWORK'
        internal_address_map = {zmq.PUB: ['http://localhost.5555']}
        external_address_map = {zmq.SUB: ['http://localhost.5556']}
        
        network_config = NetworkConfig(network_name, internal_address_map, external_address_map)
        self.assertEqual(type(network_config), NetworkConfig)

        with self.assertRaises(TypeError):
            NetworkConfig(1, internal_address_map, external_address_map)
            NetworkConfig(network_name, {'x' : ['http://localhost.5555']}, external_address_map)
            NetworkConfig(network_name, internal_address_map, {'x' : ['http://localhost.5555']})
            NetworkConfig(network_name, {zmq.PUB : 'http://localhost.5555'}, external_address_map)
            NetworkConfig(network_name, internal_address_map, {zmq.SUB : 'http://localhost.5555'})
            NetworkConfig(network_name, {zmq.PUB : [1]}, external_address_map)
            NetworkConfig(network_name, internal_address_map, {zmq.SUB : [1]})
            
    def test_eq(self):
        network_name = 'TEST_NETWORK'
        internal_address_map = {zmq.PUB: ['http://localhost.5555']}
        external_address_map = {zmq.SUB: ['http://localhost.5556']}
        
        config_1 = NetworkConfig(network_name, internal_address_map, external_address_map)
        config_2 = NetworkConfig(network_name, internal_address_map, external_address_map)

        self.assertEqual(config_1, config_2)

        # network name
        config_1 = NetworkConfig(network_name, internal_address_map, external_address_map)
        config_2 = NetworkConfig('OTHER', internal_address_map, external_address_map)

        self.assertNotEqual(config_1, config_2)

        # internal addresses
        config_1 = NetworkConfig(network_name, internal_address_map, external_address_map)
        config_2 = NetworkConfig(network_name, dict(), external_address_map)

        self.assertNotEqual(config_1, config_2)

        # external addresses
        config_1 = NetworkConfig(network_name, internal_address_map, external_address_map)
        config_2 = NetworkConfig(network_name, internal_address_map, dict())

        self.assertNotEqual(config_1, config_2)

        # all
        config_1 = NetworkConfig(network_name, internal_address_map, external_address_map)
        config_2 = NetworkConfig('OTHER', dict(), dict())

        self.assertNotEqual(config_1, config_2)


    def test_dict(self):
        network_name = 'TEST_NETWORK'
        internal_address_map = {zmq.PUB: ['http://localhost.5555']}
        external_address_map = {zmq.SUB: ['http://localhost.5556']}

        network_config_1 = NetworkConfig(network_name, internal_address_map, external_address_map)
        network_config_2 = NetworkConfig(network_name, dict(), external_address_map)
        network_config_1_reconstructed = NetworkConfig(**network_config_1.to_dict())
        network_config_2_reconstructed = NetworkConfig(**json.loads(network_config_2.to_json()))

        self.assertEqual(network_config_1, network_config_1_reconstructed)
        self.assertNotEqual(network_config_1, network_config_2_reconstructed)

    def test_json(self):
        network_name = 'TEST_NETWORK'
        internal_address_map = {zmq.PUB: ['http://localhost.5555']}
        external_address_map = {zmq.SUB: ['http://localhost.5556']}

        network_config_1 = NetworkConfig(network_name, internal_address_map, external_address_map)
        network_config_2 = NetworkConfig(network_name, dict(), external_address_map)

        network_config_1_reconstructed = NetworkConfig(**json.loads(network_config_1.to_json()))
        network_config_2_reconstructed = NetworkConfig(**json.loads(network_config_2.to_json()))

        self.assertEqual(network_config_1, network_config_1_reconstructed)
        self.assertNotEqual(network_config_1, network_config_2_reconstructed)

    # TODO Test Port in Use and Port/Address generators   

class TestNetworkElement(unittest.TestCase): 

    class TransmissionTypes:
        INT = 'INTERNAL'
        EXT = 'EXTERNAL'

    class DummyNetworkElement(NetworkElement):
        def _external_sync(self) -> dict:
            return dict()

        def _internal_sync(self) -> dict:
            return dict()
        
        def activate(self) -> dict:
            self._external_socket_map, self._internal_socket_map = self.config_network()

        @abstractmethod
        async def routine():
            pass

        async def main(self):
                # try:
                timeout_task = asyncio.create_task(asyncio.sleep(15))
                coroutine_task = asyncio.create_task(self.routine())

                _, pending = await asyncio.wait([timeout_task, coroutine_task], return_when=asyncio.FIRST_COMPLETED)

                if timeout_task in pending:
                    return
                else:
                    coroutine_task.cancel()
                    await coroutine_task

                # finally:
                #     self._deactivate_network()

        def run(self):
            try:
                asyncio.run(self.main())
            finally:
                self._deactivate_network()

    class Sender(DummyNetworkElement):
        def __init__(self, t_type, socket_type : zmq.SocketType, port : int, n :int, level=logging.INFO) -> None:
            network_name = 'TEST_NETWORK'    
            if t_type is TestNetworkElement.TransmissionTypes.INT:   
                internal_address_map = {socket_type: [f'tcp://*:{port}']}
                external_address_map = dict()

            elif t_type is TestNetworkElement.TransmissionTypes.EXT:
                internal_address_map = dict()
                external_address_map = {socket_type: [f'tcp://*:{port}']}

            network_config = NetworkConfig(network_name, internal_address_map, external_address_map)
            
            super().__init__('SENDER', network_config, level)
            self.socket_type = socket_type
            self.msgs = []
            self.n = n
            self.t_type = t_type

        async def routine(self):
            try:
                for _ in tqdm (range (self.n), desc="SENDER: Transmitting..."):
                    dt = 0.01
                    await asyncio.sleep(dt)

                    src = self.name
                    dst = self.get_network_name()
                    msg_type = 'TEST'

                    msg = SimulationMessage(src, dst, msg_type)
                    self._log(f'sending message through port of type {self.socket_type}...')
                    if self.t_type is TestNetworkElement.TransmissionTypes.INT:   
                        status = 'successful!' if await self._send_internal_msg(msg, self.socket_type) else 'failed.'

                    elif self.t_type is TestNetworkElement.TransmissionTypes.EXT:
                        status = 'successful!' if await self._send_external_msg(msg, self.socket_type) else 'failed.'
                    self.msgs.append(msg)
                    self._log(f'finished sending message! Transmission status: {status}')

            except asyncio.CancelledError:
                return

    class Receiver(DummyNetworkElement):
        def __init__(self, t_type, socket_type : zmq.SocketType, port : int, n :int, level=logging.INFO) -> None:
            network_name = 'TEST_NETWORK'     

            if t_type is TestNetworkElement.TransmissionTypes.INT:   
                internal_address_map = {socket_type: [f'tcp://localhost:{port}']}
                external_address_map = dict()

            elif t_type is TestNetworkElement.TransmissionTypes.EXT:
                internal_address_map = dict()
                external_address_map = {socket_type: [f'tcp://localhost:{port}']}

            network_config = NetworkConfig(network_name, internal_address_map, external_address_map)
            
            super().__init__('RECEIVER', network_config, level)
            self.socket_type = socket_type
            self.msgs = []
            self.n = n
            self.t_type = t_type

        async def routine(self):
            try:
                for _ in tqdm (range (self.n), desc="RECEIVER:  Listening..."):
                    self._log(f'waiting for incoming messages through port of type {self.socket_type}...')
                    if self.t_type is TestNetworkElement.TransmissionTypes.INT:   
                        dst, src, content = await self._receive_internal_msg(self.socket_type)

                    elif self.t_type is TestNetworkElement.TransmissionTypes.EXT:
                        dst, src, content = await self._receive_external_msg(self.socket_type)

                    self.msgs.append(SimulationMessage(**content))
                    self._log(f'received a message from {src} intended for {dst}! Reception status: {len(self.msgs)}/{self.n}')

            except asyncio.CancelledError:
                return

    def transmission_tester(self,
                            t_type : TransmissionTypes, 
                            sender_port_type : zmq.SocketType, 
                            receiver_port_type : zmq.SocketType, 
                            port : int,
                            n : int):
        if t_type is not TestNetworkElement.TransmissionTypes.INT and t_type is not TestNetworkElement.TransmissionTypes.EXT:
            raise TypeError('`t_type` must be of type `TransmissionTypes`')

        sender = TestNetworkElement.Sender(t_type, sender_port_type, port, n)
        receiver = TestNetworkElement.Receiver(t_type, receiver_port_type, port, n)

        sender.activate()
        receiver.activate()
    
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            pool.submit(receiver.run, *[])
            pool.submit(sender.run, *[])

        self.assertEqual(sender.msgs, receiver.msgs)  
         
    def test_external_messaging(self):
        port = 5556
        n = 10

        # PUB-SUB pattern
        print('\nTEST: External Message Broadcast (PUB-SUB)')
        self.transmission_tester(TestNetworkElement.TransmissionTypes.EXT, zmq.PUB, zmq.SUB, port, n) 
        print('\n')

        # PUSH-PULL pattern
        print('\nTEST: External Message Distribution (PUSH-PULL)')
        self.transmission_tester(TestNetworkElement.TransmissionTypes.EXT, zmq.PUSH, zmq.PULL, port, n) 
        print('\n')

    def test_internal_messaging(self):
        port = 5556
        n = 10

        # PUB-SUB pattern
        print('\nTEST: Internal Message Broadcast (PUB-SUB)')
        self.transmission_tester(TestNetworkElement.TransmissionTypes.INT, zmq.PUB, zmq.SUB, port, n) 

        # # PUSH-PULL pattern
        # print('\nTEST: Internal Message Distribution (PUSH-PULL)')
        # self.transmission_tester(TestNetworkElement.TransmissionTypes.INT, zmq.PUSH, zmq.PULL, port, n) 
        print('\n')