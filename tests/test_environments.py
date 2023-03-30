import logging
import unittest

import zmq
from dmas.environments import EnvironmentNode
from dmas.messages import SimulationElementRoles

from dmas.network import NetworkConfig


class TestEnvironmentNode(unittest.TestCase): 
    def test_init(self):
        port = 5555
        network_name = 'TEST_NETWORK'
        level = logging.DEBUG

        manager_network_config = NetworkConfig( network_name,
                                                manager_address_map = {
                                                        zmq.REP: [f'tcp://*:{port}'],
                                                        zmq.PUB: [f'tcp://*:{port+1}'],
                                                        zmq.PUSH: [f'tcp://localhost:{port+2}']
                                                })

        env_network_config = NetworkConfig( network_name,
                                            manager_address_map = {
                                                    zmq.REQ: [f'tcp://localhost:{port}'],
                                                    zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                    zmq.PUSH: [f'tcp://localhost:{port+2}']},
                                            external_address_map = {
                                                    zmq.REP: [f'tcp://*:{port+3}'],
                                                    zmq.PUB: [f'tcp://*:{port+4}']
                                            })
        

        env = EnvironmentNode(SimulationElementRoles.ENVIRONMENT.value,
                                env_network_config, 
                                manager_network_config,
                                level=level)