import json
import unittest

import zmq

from dmas.network import NetworkConfig


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

        #all
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
        