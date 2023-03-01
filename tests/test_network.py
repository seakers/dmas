import json
import random
import unittest

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
    class DummyNetworkElement(NetworkElement):
        def _external_sync(self) -> dict:
            return dict()

        def _internal_sync(self) -> dict:
            return dict()
        
        def activate(self) -> dict:
            self._external_socket_map, self._internal_socket_map = self.config_network()

        @abstractmethod
        async def coroutine():
            pass

        def run(self):
            try:
                async def routine():
                    timeout_task = asyncio.create_task(asyncio.sleep(5))
                    coroutine_task = asyncio.create_task(self.coroutine())

                    _, pending = await asyncio.wait([timeout_task, coroutine_task], return_when=asyncio.FIRST_COMPLETED)

                    if timeout_task in pending:
                        return
                    else:
                        for task in pending:
                            task : asyncio.Task
                            task.cancel()
                            await task

                asyncio.run(routine())
            finally:
                self._deactivate_network()

    class ExternalSender(DummyNetworkElement):
        def __init__(self, socket_type : zmq.SocketType, n) -> None:
            network_name = 'TEST_NETWORK'        
            internal_address_map = dict()
            if socket_type == zmq.PUB:
                external_address_map = {socket_type: ['tcp://*:5556']}
            elif socket_type == zmq.PUSH:
                external_address_map = {socket_type: ['tcp://localhost:5556']}
            network_config = NetworkConfig(network_name, internal_address_map, external_address_map)
            
            super().__init__('SENDER', network_config, level=logging.INFO)
            self.socket_type = socket_type
            self.msgs = []
            self.n = n

        async def coroutine(self):
            try:
                for _ in range(self.n):
                    dt = 0.01
                    # print(f'SENDER: sleeping for {dt}[s]...')
                    await asyncio.sleep(dt)

                    src = self.name
                    dst = self.get_network_name()
                    msg_type = 'TEST'

                    msg = SimulationMessage(src, dst, msg_type)
                    print(f'SENDER: sending message through port of type {self.socket_type}...')
                    status = 'successful!' if await self._send_external_msg(msg, self.socket_type) else 'failed.'
                    self.msgs.append(msg)
                    print(f'SENDER: finished sending message! Transmission status: {status}')

            except asyncio.CancelledError:
                return

    class ExternalReceiver(DummyNetworkElement):
        def __init__(self, socket_type : zmq.SocketType, n) -> None:
            network_name = 'TEST_NETWORK'        
            internal_address_map = dict()

            if socket_type == zmq.SUB:
                external_address_map = {socket_type: ['tcp://localhost:5556']}
            elif socket_type == zmq.PULL:
                external_address_map = {socket_type: ['tcp://*:5556']}

            network_config = NetworkConfig(network_name, internal_address_map, external_address_map)
            
            super().__init__('RECEIVER', network_config, level=logging.INFO)
            self.socket_type = socket_type
            self.msgs = []
            self.n = n

        async def coroutine(self):
            try:
                while len(self.msgs) < self.n:
                    print(f'RECEIVER: waiting for incoming messages through port of type {self.socket_type}...')
                    dst, src, content = await self._receive_external_msg(self.socket_type)
                    self.msgs.append(SimulationMessage(**content))
                    print(f'RECEIVER: received a message from {src} intended for {dst}! Reception status: {len(self.msgs)}/{self.n}')

            except asyncio.CancelledError:
                return
        
    # def test_external_broadcast_msg(self):
    #     # PUB-SUB pattern
    #     n = 10

    #     sender_pub = TestNetworkElement.ExternalSender(zmq.PUB, n)
    #     receiver_sub = TestNetworkElement.ExternalReceiver(zmq.SUB, n)
        
    #     sender_pub.activate()
    #     receiver_sub.activate()

    #     with concurrent.futures.ThreadPoolExecutor(2) as pool:
    #         pool.submit(receiver_sub.run, *[])
    #         pool.submit(sender_pub.run, *[])

    #     self.assertEqual(sender_pub.msgs, receiver_sub.msgs)    

    def test_external_distributed_msg(self):
        # PUSH-PULL pattern
        n = 10

        sender = TestNetworkElement.ExternalSender(zmq.PUSH, n)
        receiver = TestNetworkElement.ExternalReceiver(zmq.PULL, n)
        
        sender.activate()
        receiver.activate()

        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            pool.submit(receiver.run, *[])
            pool.submit(sender.run, *[])

        self.assertEqual(sender.msgs, receiver.msgs)
            


    class InternalSender(DummyNetworkElement):
        def __init__(self, socket_type : zmq.SocketType, n) -> None:
            network_name = 'TEST_NETWORK'        
            external_address_map = dict()
            if socket_type is zmq.PUB:
                internal_address_map = {socket_type: ['tcp://*:5556']}
            elif socket_type is zmq.PUSH:
                internal_address_map = {socket_type: ['tcp://localhost:5556']}

            network_config = NetworkConfig(network_name, internal_address_map, external_address_map)
            
            super().__init__('SENDER', network_config)
            self.socket_type = socket_type
            self.msgs = []
            self.n = n

        async def coroutine(self):
            try:
                for _ in range(self.n):
                    dt = 0.01
                    print(f'SENDER: sleeping for {dt}[s]...')
                    await asyncio.sleep(dt)

                    src = self.name
                    dst = self.get_network_name()
                    msg_type = 'TEST'

                    msg = SimulationMessage(src, dst, msg_type)
                    print(f'SENDER: sending message through port of type {self.socket_type}...')
                    status = 'successful!' if await self._send_internal_msg(msg, self.socket_type) else 'failed.'
                    self.msgs.append(msg)
                    print(f'SENDER: finished sending message! Transmission status: {status}')
                
                print('SENDER: DONE!')
                return
            except asyncio.CancelledError:
                return

    class InternalReceiver(DummyNetworkElement):
        def __init__(self, socket_type : zmq.SocketType, n) -> None:
            network_name = 'TEST_NETWORK'        
            external_address_map = dict()

            if socket_type is zmq.SUB:
                internal_address_map = {socket_type: ['tcp://localhost:5556']}
            elif socket_type is zmq.PULL:
                internal_address_map = {socket_type: ['tcp://*:5556']}

            network_config = NetworkConfig(network_name, internal_address_map, external_address_map)
            
            super().__init__('RECEIVER', network_config)
            self.socket_type = socket_type
            self.msgs = []
            self.n = n

        async def coroutine(self):
            try:
                while len(self.msgs) < self.n:
                    print(f'RECEIVER: waiting for incoming messages through port of type {self.socket_type}...')
                    dst, src, content = await self._receive_internal_msg(self.socket_type)
                    self.msgs.append(SimulationMessage(**content))
                    print(f'RECEIVER: received a message from {src} intended for {dst}! Reception status: {len(self.msgs)}/{self.n}')

                print('RECEIVER: DONE!')
                return
            except asyncio.CancelledError:
                return
            
    # def test_internal_broadcast_msg(self):
    #     # PUB-SUB pattern
    #     n = 10

    #     sender = TestNetworkElement.InternalSender(zmq.PUB, n)
    #     receiver = TestNetworkElement.InternalReceiver(zmq.SUB, n)

    #     print(sender.get_socket_maps())
    #     print(receiver.get_socket_maps())
        
    #     sender.activate()
    #     receiver.activate()

    #     with concurrent.futures.ThreadPoolExecutor(2) as pool:
    #         pool.submit(receiver.run, *[])
    #         pool.submit(sender.run, *[])
        
    #     self.assertEqual(sender.msgs, receiver.msgs)

    # def test_internal_distributed_msg(self):
        # PUSH-PULL pattern
        # sender = TestNetworkElement.InternalSender(zmq.PUSH, n)
        # receiver = TestNetworkElement.InternalReceiver(zmq.PULL, n)
        
        # sender.activate()
        # receiver.activate()

        # with concurrent.futures.ThreadPoolExecutor(2) as pool:
        #     pool.submit(receiver.run, *[])
        #     pool.submit(sender.run, *[])

        # self.assertEqual(sender.msgs, receiver.msgs)