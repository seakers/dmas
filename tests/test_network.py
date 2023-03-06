import json
import random
import time
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
        def __init__(self, element_name: str, network_config: NetworkConfig, level: int = logging.INFO, logger: logging.Logger = None) -> None:
            super().__init__(element_name, network_config, level, logger)
            self.msgs = []

        async def _external_sync(self) -> dict:
            return dict()

        async def _internal_sync(self) -> dict:
            return dict()
        
        def activate(self) -> dict:
            self._network_context, self._external_socket_map, self._internal_socket_map = self.config_network()

        @abstractmethod
        async def routine():
            pass

        async def main(self):
                timeout_task = asyncio.create_task(asyncio.sleep(5))
                coroutine_task = asyncio.create_task(self.routine())

                _, pending = await asyncio.wait([timeout_task, coroutine_task], return_when=asyncio.FIRST_COMPLETED)

                if timeout_task in pending:
                    return
                else:
                    coroutine_task.cancel()
                    await coroutine_task

        def run(self):
            # try:
            asyncio.run(self.main())
            # finally:
            #     self._deactivate_network()

    class ReceiverKillMessage(SimulationMessage):
        """
        Dummy kill message
        """
        def __init__(self, src: str, dst: str, msg_type: str, id: str = None):
            super().__init__(src, dst, msg_type, id)

    class Sender(DummyNetworkElement):
        def __init__(self, t_type, socket_type : zmq.SocketType, port : int, n :int, level=logging.INFO) -> None:
            network_name = 'TEST_NETWORK'    
            if t_type is TestNetworkElement.TransmissionTypes.INT:   
                internal_address_map = {socket_type: [f'tcp://*:{port}']}
                external_address_map = dict()

                if socket_type is not zmq.PUB:
                    internal_address_map[zmq.PUB] = [f'tcp://*:{port+1}']

            elif t_type is TestNetworkElement.TransmissionTypes.EXT:
                internal_address_map = dict()
                external_address_map = {socket_type: [f'tcp://*:{port}']}

                if socket_type is not zmq.PUB:
                    external_address_map[zmq.PUB] = [f'tcp://*:{port+1}']

            network_config = NetworkConfig(network_name, internal_address_map, external_address_map)
            
            super().__init__('SENDER', network_config, level)
            self.socket_type = socket_type
            self.msgs = []
            self.n = n
            self.t_type = t_type

        async def routine(self):
            try:
                dt = 0.01
                await asyncio.sleep(dt*10)
                for _ in tqdm (range (self.n), desc="SENDER: Transmitting..."):
                    await asyncio.sleep(dt)

                    src = self.name
                    dst = self.get_network_name()

                    msg = SimulationMessage(src, dst, 'TEST')
                    self._log(f'sending message through port of type {self.socket_type}...')
                    if self.t_type is TestNetworkElement.TransmissionTypes.INT:   
                        status = 'successful!' if await self._send_internal_msg(msg, self.socket_type) else 'failed.'

                    elif self.t_type is TestNetworkElement.TransmissionTypes.EXT:
                        status = 'successful!' if await self._send_external_msg(msg, self.socket_type) else 'failed.'
                    self.msgs.append(msg)
                    self._log(f'finished sending message! Transmission status: {status}')

                src = self.name
                dst = self.get_network_name()
                kill_msg = TestNetworkElement.ReceiverKillMessage(src, dst, 'KILL')
                if self.t_type is TestNetworkElement.TransmissionTypes.INT:   
                    status = 'successful!' if await self._send_internal_msg(kill_msg, zmq.PUB) else 'failed.'

                elif self.t_type is TestNetworkElement.TransmissionTypes.EXT:
                    status = 'successful!' if await self._send_external_msg(kill_msg, zmq.PUB) else 'failed.'

                self._log(f'finished sending messages! Kill message transmission status: {status}')

            except asyncio.CancelledError:
                return

    class Receiver(DummyNetworkElement):
        def __init__(self, name, t_type, socket_type : zmq.SocketType, port : int, n :int, level=logging.INFO) -> None:
            network_name = 'TEST_NETWORK'     

            if t_type is TestNetworkElement.TransmissionTypes.INT:   
                internal_address_map = {socket_type: [f'tcp://localhost:{port}']}
                external_address_map = dict()

                if socket_type is not zmq.SUB:
                    internal_address_map[zmq.SUB] = [f'tcp://localhost:{port+1}']

            elif t_type is TestNetworkElement.TransmissionTypes.EXT:
                internal_address_map = dict()
                external_address_map = {socket_type: [f'tcp://localhost:{port}']}

                if socket_type is not zmq.SUB:
                    external_address_map[zmq.SUB] = [f'tcp://localhost:{port+1}']

            network_config = NetworkConfig(network_name, internal_address_map, external_address_map)
            
            super().__init__(name, network_config, level)
            self.socket_type = socket_type
            self.n = n
            self.t_type = t_type          

        def activate(self) -> dict:
            super().activate()

            self.poller = azmq.Poller()
            if self.t_type is TestNetworkElement.TransmissionTypes.INT:
                for socket_type in self._internal_socket_map:
                    socket, _ = self._internal_socket_map[socket_type]
                    self.poller.register(socket, zmq.POLLIN)

            elif self.t_type is TestNetworkElement.TransmissionTypes.EXT:
                for socket_type in self._external_socket_map:
                    socket, _ = self._external_socket_map[socket_type]
                    self.poller.register(socket, zmq.POLLIN)

        async def routine(self):
            try:
                for _ in tqdm (range (self.n), desc="RECEIVER:  Listening..."):
                    self._log(f'waiting for incoming messages...')

                    socks = dict(await self.poller.poll())

                    for polled_sock in socks:
                        src, dst, content = None, None, None

                        if self.t_type is TestNetworkElement.TransmissionTypes.INT:   
                            for socket_type in self._internal_socket_map:
                                sock, _ = self._internal_socket_map[socket_type]

                                if polled_sock is sock:
                                    dst, src, content = await self._receive_internal_msg(socket_type)
                                    
                                    if content['msg_type'] == 'KILL':
                                        self._log(f'received kill message from {src} intended for {dst}! Reception status: {len(self.msgs)}/{self.n}')
                                        return
                                    break

                        elif self.t_type is TestNetworkElement.TransmissionTypes.EXT:   # 
                            for socket_type in self._external_socket_map:
                                sock, _ = self._external_socket_map[socket_type]
                            
                                if polled_sock is sock:
                                    dst, src, content = await self._receive_external_msg(socket_type)

                                    if content['msg_type'] == 'KILL':
                                        self._log(f'received kill message from {src} intended for {dst}! Reception status: {len(self.msgs)}/{self.n}')
                                        return
                                    break
                        
                        if content is not None:
                            break
                            
                    self.msgs.append(SimulationMessage(**content))
                    self._log(f'received a message from {src} intended for {dst}! Reception status: {len(self.msgs)}/{self.n}')

            except asyncio.CancelledError:
                return      

    # def test_config_network(self):
    #     network_congif = NetworkConfig('TEST_NETWORK',
    #                                     {}, 
    #                                     {})

    def transmission_tester(self,
                            t_type : TransmissionTypes, 
                            sender_port_type : zmq.SocketType, 
                            receiver_port_type : zmq.SocketType, 
                            port : int,
                            n_receivers : int,
                            n_messages : int,
                            level : int = logging.INFO):

        if t_type is not TestNetworkElement.TransmissionTypes.INT and t_type is not TestNetworkElement.TransmissionTypes.EXT:
            raise TypeError('`t_type` must be of type `TransmissionTypes`')

        sender = TestNetworkElement.Sender(t_type, sender_port_type, port, n_messages, level)
        receivers = []
        for i in range(n_receivers):
            receiver = TestNetworkElement.Receiver(f'RECEVER_{i+1}', t_type, receiver_port_type, port, n_messages, level)
            receivers.append(receiver)
        
        sender.activate()
        for receiver in receivers:
            receiver : TestNetworkElement.DummyNetworkElement
            receiver.activate()
    
        with concurrent.futures.ThreadPoolExecutor(len(receivers) + 1) as pool:
            for receiver in receivers:
                pool.submit(receiver.run, *[])
            pool.submit(sender.run, *[])

        if receiver_port_type is zmq.SUB:
            received_messages = None
            for receiver in receivers:
                if received_messages is None:
                    received_messages = receiver.msgs.copy()
                
                if received_messages != receiver.msgs:
                    received_messages = []
                    return
        else:
            received_messages = []
            for receiver in receivers:
                for msg in receiver.msgs:
                    if msg not in received_messages:
                        received_messages.append(msg)

        self.assertEqual(len(sender.msgs), len(received_messages))
        for msg in sender.msgs:
            self.assertTrue(msg in received_messages)

    def test_message_broadcast(self):
        port = 5555
        listeners = [1, 20]
        n_messages = 20

        # INTERNAL MESSAGING
        print('\n\nTEST: Internal Message Broadcast (PUB-SUB)')
        for n_listeners in listeners:
            print(f'Number of listeners: {n_listeners}')
            self.transmission_tester(TestNetworkElement.TransmissionTypes.INT, zmq.PUB, zmq.SUB, port, n_listeners, n_messages)
            print('\n')

        # EXTERNAL MESSAGING
        print('TEST: External Message Broadcast (PUB-SUB)')
        for n_listeners in listeners:
            print(f'Number of listeners: {n_listeners}')
            self.transmission_tester(TestNetworkElement.TransmissionTypes.EXT, zmq.PUB, zmq.SUB, port, n_listeners, n_messages)
            print('\n')

    def test_message_distribution(self):
        port = 5556
        listeners = [1, 20]
        n_messages = 20

        # INTERNAL MESSAGING
        print('\n\nTEST: Internal Message Distribution (PUSH-PULL)')
        for n_listeners in listeners:
            print(f'Number of listeners: {n_listeners}')
            self.transmission_tester(TestNetworkElement.TransmissionTypes.INT, zmq.PUSH, zmq.PULL, port, n_listeners, n_messages)
            print('\n')

        # EXTERNAL MESSAGING
        print('TEST: Internal Message Distribution (PUSH-PULL)')
        for n_listeners in listeners:
            print(f'Number of listeners: {n_listeners}')
            self.transmission_tester(TestNetworkElement.TransmissionTypes.EXT, zmq.PUSH, zmq.PULL, port, n_listeners, n_messages)
            print('\n')
