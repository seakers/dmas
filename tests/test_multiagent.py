import asyncio
from enum import Enum
import logging
import random
import time
import unittest
import concurrent.futures

import zmq
from dmas.agents import Agent, AgentState
from dmas.element import SimulationElement
from dmas.environments import EnvironmentNode
from dmas.managers import AbstractManager
from dmas.messages import *

from dmas.network import NetworkConfig

class TestMultiagentSim(unittest.TestCase): 
	class TestAgentState(AgentState):
		def __init__(self, 
	       				x0 : float = None, y0 : float = None, z0 : float = None,
						x_max : float = None, y_max : float = None, z_max : float = None) -> None:
			super().__init__()
			if x0 is not None and y0 is not None and z0 is not None:
				self.pos = [x0,
							y0,
							z0]
			elif x_max is not None and y_max is not None and z_max is not None:
				self.pos = [x_max * random.random(),
							y_max * random.random(),
							z_max * random.random()]
			else:
				self.pos = [random.random(),
							random.random(),
							random.random()]
				
		def update_state(self, pos, **_):
			self.pos = pos

		def get_pos(self):
			return self.pos

		def __str__(self) -> str:
			return f'pos: {self.pos}\n'
		
	class AgentPositionMessage(SimulationMessage):
		def __init__(self, src: str, dst : str, pos : list, id: str = None,  **_):
			super().__init__(src, dst, 'AGENT_POS_MESSAGE', id)
			self.pos = pos

	class AgentNames(Enum):
		AGENT_1 = 'AGENT_1'
		AGENT_2 = 'AGENT_2'

	class TestEnvironment(EnvironmentNode):
		async def setup(self) -> None:
			return

		def kinematic_model(self, pos : list, dt : float):
			"""
			Propagates an agent's position through time
			"""
			out = pos
			for i in range(len(out)):
				x_i = out[i]
				dx_i = random.random()
				if dx_i < 0.5:
					x_i -= dx_i*dt
				else:
					x_i += dx_i*dt
				out[i] = x_i
			return out	

		async def live(self) -> None:
			try:
				t_0 = time.time()
				while True:
					# listens for incoming requests
					_, src, msg_dict = await self.listen_peer_message()
					msg = TestMultiagentSim.AgentPositionMessage(**msg_dict)

					# does some work - calculate agent position
					pos = msg.pos
					dt = time.time() - t_0
					x = self.kinematic_model(pos, dt)
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

	class TestAgent(Agent):
		def __init__(self, 
	       				agent_name: str, 
						agent_network_config: NetworkConfig, 
						manager_network_config: NetworkConfig, 
						initial_state: AgentState, 
						level: int = logging.INFO, logger: logging.Logger = None) -> None:
			super().__init__(agent_name, agent_network_config, manager_network_config, initial_state, [], level, logger)

		async def setup(self):
			return

		async def live(self):
			try:
				self.state : TestMultiagentSim.TestAgentState
				t_0 = time.time()
				
				while True:
					dt = random.random()
					await self.sim_wait(dt)
					pos_msg = TestMultiagentSim.AgentPositionMessage(self.name,
																	SimulationElementRoles.ENVIRONMENT.value, 
																	self.state.pos)
					await self.send_peer_message(pos_msg)

					_, _, msg_dict = await self.listen_peer_message()
					response = TestMultiagentSim.AgentPositionMessage(**msg_dict)

					self.pos = response.pos
					self.log(f'position = {self.pos}', level=logging.WARNING)
			
			except asyncio.CancelledError:
				return
			
		async def teardown(self):
			pass

		async def sim_wait(self, delay: float) -> None:
			await asyncio.sleep(delay)

	def test_agent_init(self):
		port = 5555
		network_name = 'TEST_NETWORK'
		level = logging.DEBUG

		initial_state = TestMultiagentSim.TestAgentState()
		pos = [1.0, 1.0, 1.0]
		initial_state.update_state(pos)
		self.assertEqual(pos, initial_state.pos)
		
		agent_network_config = NetworkConfig( network_name,
											manager_address_map = {
													zmq.REQ: [f'tcp://localhost:{port}'],
													zmq.SUB: [f'tcp://localhost:{port+1}'],
													zmq.PUSH: [f'tcp://localhost:{port+2}']},
											external_address_map = {
													zmq.REQ: [f'tcp://*:{port+3}'],
													zmq.PUB: [f'tcp://*:{port+4}'],
													zmq.SUB: [f'tcp://*:{port+5}']
											})

		manager_network_config = NetworkConfig( network_name,
												manager_address_map = {
														zmq.REP: [f'tcp://*:{port}'],
														zmq.PUB: [f'tcp://*:{port+1}'],
														zmq.PUSH: [f'tcp://localhost:{port+2}']
												})
			
		TestMultiagentSim.TestAgent('TEST_AGENT', 
									agent_network_config, 
									manager_network_config, 
									initial_state, 
									level=level)
		
		with self.assertRaises(AttributeError):
			agent_network_config = NetworkConfig( network_name,
											manager_address_map = {
													zmq.REQ: [f'tcp://localhost:{port}'],
													zmq.SUB: [f'tcp://localhost:{port+1}'],
													zmq.PUSH: [f'tcp://localhost:{port+2}']},
											external_address_map = {
													zmq.PUB: [f'tcp://*:{port+4}'],
													zmq.SUB: [f'tcp://*:{port+5}']
											})	
			TestMultiagentSim.TestAgent('TEST_AGENT', 
										agent_network_config, 
										manager_network_config, 
										initial_state, 
										level=level)
		
		with self.assertRaises(AttributeError):
			agent_network_config = NetworkConfig( network_name,
											manager_address_map = {
													zmq.REQ: [f'tcp://localhost:{port}'],
													zmq.SUB: [f'tcp://localhost:{port+1}'],
													zmq.PUSH: [f'tcp://localhost:{port+2}']},
											external_address_map = {
													zmq.REQ: [f'tcp://*:{port+3}'],
													zmq.SUB: [f'tcp://*:{port+5}']
											})	
			TestMultiagentSim.TestAgent('TEST_AGENT', 
										agent_network_config, 
										manager_network_config, 
										initial_state, 
										level=level)
			
		with self.assertRaises(AttributeError):
			agent_network_config = NetworkConfig( network_name,
											manager_address_map = {
													zmq.REQ: [f'tcp://localhost:{port}'],
													zmq.SUB: [f'tcp://localhost:{port+1}'],
													zmq.PUSH: [f'tcp://localhost:{port+2}']},
											external_address_map = {
													zmq.REQ: [f'tcp://*:{port+3}'],
													zmq.PUB: [f'tcp://*:{port+4}']
											})	
			TestMultiagentSim.TestAgent('TEST_AGENT', 
										agent_network_config, 
										manager_network_config, 
										initial_state, 
										level=level)
	
	class DummyMonitor(SimulationElement):
		def __init__(self, clock_config : ClockConfig, port : int, level: int = logging.INFO, logger: logging.Logger = None) -> None:
			network_config = NetworkConfig('TEST_NETWORK',
                                            external_address_map = {zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                                    zmq.PULL: [f'tcp://*:{port+2}']})
		
			super().__init__('MONITOR', network_config, level, logger)
			self._clock_config = clock_config

		async def sim_wait(self, delay: float) -> None:
			return asyncio.sleep(delay)
        
		async def setup(self) -> None:
			return

		async def teardown(self) -> None:
			return
		
		async def _external_sync(self) -> dict:
			return self._clock_config, dict()
		
		async def _internal_sync(self, _ : ClockConfig) -> dict:
			return dict()
		
		async def _wait_sim_start(self) -> None:
			return

		async def _execute(self) -> None:
			try:
				self.log('executing...')
				while True:
					dst, src, content = await self._receive_external_msg(zmq.PULL)
					
					self.log(f'message received: {content}', level=logging.DEBUG)

					if (dst not in self.name 
						or SimulationElementRoles.MANAGER.value not in src 
						or content['msg_type'] != ManagerMessageTypes.SIM_END.value):
						self.log('wrong message received. ignoring message...')
					else:
						self.log('simulation end message received! ending simulation...')
						break
			except asyncio.CancelledError:
				return

			except Exception as e:
				raise e

		async def _publish_deactivate(self) -> None:
			return 

	class DummyManager(AbstractManager):
		def __init__(self, clock_config, simulation_element_name_list : list, port : int, level : int = logging.INFO, logger : logging.Logger = None) -> None:
			network_config = NetworkConfig('TEST_NETWORK',
											manager_address_map = {
																	zmq.REP: [f'tcp://*:{port}'],
																	zmq.PUB: [f'tcp://*:{port+1}'],
																	zmq.PUSH: [f'tcp://localhost:{port+2}']})
			
			super().__init__(simulation_element_name_list, clock_config, network_config, level, logger)

		def _check_element_list(self):
			return
		
		async def setup(self) -> None:
			return

		async def teardown(self) -> None:
			return
	
	def test_multiagent(self):
		print(f'AGENT-ENV TEST:')
		port = 5555
		level = logging.DEBUG
		
		year = 2023
		month = 1
		day = 1
		hh = 12
		mm = 00
		ss = 00
		start_date = datetime(year, month, day, hh, mm, ss)
		end_date = datetime(year, month, day, hh, mm, ss+1)
		clock_config = RealTimeClockConfig(start_date, end_date)

		# set up simulation monitor
		monitor = TestMultiagentSim.DummyMonitor(clock_config, port, level)
		logger = monitor.get_logger()
		print(logger)
		
		# set up simulation manager
		simulation_element_name_list = [
										SimulationElementRoles.ENVIRONMENT.value,
										# TestMultiagentSim.AgentNames.AGENT_1.value
										]
		manager = TestMultiagentSim.DummyManager(	clock_config, 
					   								simulation_element_name_list, 
													port, 
													logger=logger)

		# set up agent environment
		env_network_config = NetworkConfig( manager.get_network_config().network_name,
											manager_address_map = {
													zmq.REQ: [f'tcp://localhost:{port}'],
													zmq.SUB: [f'tcp://localhost:{port+1}'],
													zmq.PUSH: [f'tcp://localhost:{port+2}']},
											external_address_map = {
													zmq.REP: [f'tcp://*:{port+3}'],
													zmq.PUB: [f'tcp://*:{port+4}']
											})
		environment = TestMultiagentSim.TestEnvironment(env_network_config, 
						  								manager.get_network_config(), 
														[], 
														logger=logger)
		
		# # set up agent
		# agent_network_config = NetworkConfig( 	manager.get_network_config().network_name,
		# 										manager_address_map = {
		# 												zmq.REQ: [f'tcp://localhost:{port}'],
		# 												zmq.SUB: [f'tcp://localhost:{port+1}'],
		# 												zmq.PUSH: [f'tcp://localhost:{port+2}']},
		# 										external_address_map = {
		# 												zmq.REQ: [f'tcp://*:{port+5}'],
		# 												zmq.PUB: [f'tcp://*:{port+6}'],
		# 												zmq.SUB: [f'tcp://*:{port+7}']
		# 									})
		# initial_state = TestMultiagentSim.TestAgentState(x0 = 0, y0 = 0, z0 = 0)
		# agent = TestMultiagentSim.TestAgent(TestMultiagentSim.AgentNames.AGENT_1.value,
		# 									agent_network_config,
		# 									manager.get_network_config(),
		# 									initial_state,
		# 									logger=logger)
		
		# sim_elements = [monitor, manager, environment, agent]
		sim_elements = [monitor, manager]
		with concurrent.futures.ThreadPoolExecutor(len(sim_elements)) as pool:
			pool.submit(monitor.run, *[])
			pool.submit(manager.run, *[])
			# for sim_element in sim_elements:                
			# 	sim_element : SimulationElement
			# 	pool.submit(sim_element.run, *[])
		print('\n')