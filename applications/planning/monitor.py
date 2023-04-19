import asyncio
import logging
import random

import zmq
from dmas.clocks import ClockConfig
from dmas.elements import SimulationElement
from dmas.messages import ManagerMessageTypes, SimulationElementRoles
from dmas.network import NetworkConfig

class ResultsMonitor(SimulationElement):
    def __init__(self, clock_config : ClockConfig, monitor_network_config : int, level: int = logging.INFO, logger: logging.Logger = None) -> None:
        
        super().__init__(SimulationElementRoles.MONITOR.value, monitor_network_config, level, logger)
        self._clock_config = clock_config

    async def _external_sync(self) -> dict:
        return self._clock_config, dict()
    
    async def _internal_sync(self, _ : ClockConfig) -> dict:
        return dict()

    async def setup(self) -> None:
        # nothing to set-up
        return
    
    async def _wait_sim_start(self) -> None:
        """
        Waits for the manager to bradcast a `SIM_START` message
        """
        while True:
            # listen for any incoming broadcasts through SUB socket
            dst, src, content = await self._receive_external_msg(zmq.SUB)
            dst : str; src : str; content : dict
            msg_type = content['msg_type']

            if (
                # self.get_network_name() not in dst,
                # SimulationElementRoles.MANAGER.value not in src 
                msg_type != ManagerMessageTypes.SIM_START.value
                ):
                # undesired message received. Ignoring and trying again later
                self.log(f'received undesired message of type {msg_type}. Ignoring...')
                await asyncio.sleep(random.random())

            else:
                # manager announced the start of the simulation
                self.log(f'received simulation start message from simulation manager!', level=logging.INFO)
                return

    async def _execute(self) -> None:
        try:
            self.log('executing...')
            while True:
                dst, src, content = await self._receive_external_msg(zmq.PULL)
                
                # self.log(f'message received: {content}', level=logging.DEBUG)

                # TODO: classify and compile incoming states and results

                # TODO Exit condition: All agents are deactivated and have reported it to the monitor
                if content['msg_type'] == ManagerMessageTypes.SIM_END.value:
                    return
        except asyncio.CancelledError:
            return

        except Exception as e:
            raise e

    async def teardown(self) -> None:
        # TODO: print-out compiled information from all agents
        return

    async def _publish_deactivate(self) -> None:
        # no one to report deactivation to
        return 

    async def sim_wait(self, delay: float) -> None:
        return asyncio.sleep(delay)
    