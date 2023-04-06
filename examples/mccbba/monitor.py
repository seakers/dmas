import asyncio
import logging

import zmq
from dmas.clocks import ClockConfig
from dmas.element import SimulationElement
from dmas.messages import ManagerMessageTypes, SimulationElementRoles
from dmas.network import NetworkConfig


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