import asyncio
import logging

import zmq
from dmas.clocks import ClockConfig
from dmas.elements import SimulationElement
from dmas.messages import ManagerMessageTypes, SimulationElementRoles
from dmas.network import NetworkConfig

class SimulationMonitor(SimulationElement):
    def __init__(self, clock_config : ClockConfig, port : int, level: int = logging.INFO, logger: logging.Logger = None) -> None:
        network_config = NetworkConfig('TEST_NETWORK',
                                        external_address_map = {zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                                zmq.PULL: [f'tcp://*:{port+2}']})
    
        super().__init__('MONITOR', network_config, level, logger)
        self._clock_config = clock_config

    async def _external_sync(self) -> dict:
        return self._clock_config, dict()
    
    async def _internal_sync(self, _ : ClockConfig) -> dict:
        return dict()
    async def setup(self) -> None:
        # nothing to set-up
        return
    
    async def _wait_sim_start(self) -> None:
        # TODO: wait for simulation start message from the manager
        return

    async def _execute(self) -> None:
        try:
            self.log('executing...')
            while True:
                dst, src, content = await self._receive_external_msg(zmq.PULL)
                
                self.log(f'message received: {content}', level=logging.DEBUG)

                # TODO: classify and compile incoming states and results

                # Exit condition: All agents are deactivated and have reported it to the monitor
        except asyncio.CancelledError:
            return

        except Exception as e:
            raise e

    async def teardown(self) -> None:
        # TODO: print-out compiled information from all agents
        return

    async def _publish_deactivate(self) -> None:
        return 

    async def sim_wait(self, delay: float) -> None:
        return asyncio.sleep(delay)
    