import asyncio
import enum
import logging
import unittest

import zmq
from dmas.environments import EnvironmentNode
from dmas.messages import SimulationElementRoles

from dmas.network import NetworkConfig


class TestMultiagentSim(unittest.TestCase): 
	class AgentNames(enum):
		AGENT_1 = 'AGENT_1'
		AGENT_2 = 'AGENT_2'

	class TestEnvironment(EnvironmentNode):
		async def setup(self) -> None:
			return

		def pos(self, t):
			return [	t**2,
						t + 1,
						0 ]		

		async def live(self) -> None:
			try:
				while True:
					# listens for incoming requests
					dst, src, content = await self.listen_peer_message()

					# does some work

					# responds to request

					return
			except asyncio.CancelledError as e:
				raise e

		async def teardown(self) -> None:
			return

		async def sim_wait(self, delay: float) -> None:
			return asyncio.sleep(delay)

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


		env = TestMultiagentSim.TestEnvironment(SimulationElementRoles.ENVIRONMENT.value,
								env_network_config, 
								manager_network_config,
								level=level)
	