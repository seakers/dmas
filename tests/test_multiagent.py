import asyncio
import enum
import logging
import time
import unittest

import zmq
from dmas.agents import AgentState
from dmas.environments import EnvironmentNode
from dmas.messages import SimulationMessage

from dmas.network import NetworkConfig


class TestMultiagentSim(unittest.TestCase): 
	class AgentPositionMessage(SimulationMessage):
		def __init__(self, src: str, dst: str, x : list, id: str = None,  **_):
			super().__init__(src, dst, 'AGENT_POS_MESSAGE', id)
			self.pos = x[0:3]
			self.vel = x[3:6]
			self.pos = x[6:9]

	# class AgentNames(enum):
	# 	AGENT_1 = 'AGENT_1'
	# 	AGENT_2 = 'AGENT_2'

	class TestEnvironment(EnvironmentNode):
		async def setup(self) -> None:
			return

		def kinematic_model(self, dt):
			"""
			Propagates an agent's position through time
			"""
			return [	dt**2,
						dt + 1,
						0 ]		

		async def live(self) -> None:
			try:
				t_0 = time.time()
				while True:
					# listens for incoming requests
					_, src, _ = await self.listen_peer_message()

					# does some work - calculate agent position
					dt = time.time() - t_0
					x = self.kinematic_model(dt)
					resp = TestMultiagentSim.AgentPositionMessage(self.name, src, x)

					# responds to request
					await self.respond_peer_message(resp)

			except asyncio.CancelledError as e:
				raise e

		async def teardown(self) -> None:
			return

		async def sim_wait(self, delay: float) -> None:
			return asyncio.sleep(delay)

	def test_env_init(self):
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


		env = TestMultiagentSim.TestEnvironment(
												env_network_config, 
												manager_network_config,
												level=level)
	
		with self.assertRaises(AttributeError):
			env_network_config = NetworkConfig( network_name,
												manager_address_map = {
														zmq.REQ: [f'tcp://localhost:{port}'],
														zmq.SUB: [f'tcp://localhost:{port+1}'],
														zmq.PUSH: [f'tcp://localhost:{port+2}']},
												external_address_map = {
														zmq.PUB: [f'tcp://*:{port+4}']
												})


			env = TestMultiagentSim.TestEnvironment(
													env_network_config, 
													manager_network_config,
													level=level)
		
		with self.assertRaises(AttributeError):
			env_network_config = NetworkConfig( network_name,
												manager_address_map = {
														zmq.REQ: [f'tcp://localhost:{port}'],
														zmq.SUB: [f'tcp://localhost:{port+1}'],
														zmq.PUSH: [f'tcp://localhost:{port+2}']},
												external_address_map = {
														zmq.REP: [f'tcp://*:{port+3}']
												})


			env = TestMultiagentSim.TestEnvironment(
													env_network_config, 
													manager_network_config,
													level=level)

	class TestAgentState(AgentState):
		def __init__(self) -> None:
			super().__init__()
			self.pos = [None, None, None]
			self.vel = [None, None, None]
			self.acc = [None, None, None]

		def update_state(self, pos, vel, acc, **kwargs):
			self.pos = pos
			self.vel = vel
			self.acc = acc

		def __str__(self) -> str:
			return f'pos: {self.pos}\nvel: {self.vel}\nacc: {self.acc}\n'

	
	def test_agent_state_init(self):
		pos = [1, 1, 1]
		vel = [2, 2, 2]
		acc = [3, 3, 3]

		state = TestMultiagentSim.TestAgentState()
		print(state)
		state.update_state(pos, vel, acc)
		print(state)