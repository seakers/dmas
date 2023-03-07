from abc import ABC, abstractmethod
from enum import Enum
import json
import uuid
import zmq
from dmas.messages import SimulationMessage

from dmas.network import NetworkConfig

class ExampleMessageTypes(Enum):
    TEST = 'TEST'

if __name__ == '__main__':
    network_name = 'TEST_NETWORK'
    internal_address_map = {zmq.PUB: ['http://localhost.5555']}
    external_address_map = {zmq.SUB: ['http://localhost.5556']}
    
    # Test Network Config
    print('NETWORK CONFIG TEST')
    network_config = NetworkConfig(network_name, internal_address_map, external_address_map)

    print(network_config.to_dict())

    network_config_reconstructed = NetworkConfig(**network_config.to_dict())
    # network_config_reconstructed = NetworkConfig(**json.loads(network_config.to_json()))
    print(network_config_reconstructed.to_dict())

    assert network_config == network_config
