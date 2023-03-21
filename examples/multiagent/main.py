import logging
import zmq
from dmas.clocks import ClockConfig
from dmas.element import SimulationElement
from dmas.messages import *
from dmas.network import NetworkConfig, NetworkElement
from examples.multiagent.agent import Agent
from examples.multiagent.environment import EnvironmentNode
from examples.multiagent.manager import SimulationManager
import concurrent.futures


class DummyMonitor(SimulationElement):
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
    
    async def _wait_sim_start(self) -> None:
        return

    async def _execute(self) -> None:
        try:
            self._log('executing...')
            while True:
                dst, src, content = await self._receive_external_msg(zmq.PULL)
                
                self._log(f'message received: {content}', level=logging.DEBUG)

                if (dst not in self.name 
                    or SimulationElementRoles.MANAGER.value not in src 
                    or content['msg_type'] != ManagerMessageTypes.SIM_END.value):
                    self._log('wrong message received. ignoring message...')
                else:
                    self._log('simulation end message received! ending simulation...')
                    break
        except asyncio.CancelledError:
            return

        except Exception as e:
            raise e

    async def _publish_deactivate(self) -> None:
        return 

if __name__ == '__main__':
    # dst_address = 'tcp://*:5555'
    # print('DST ADDRESS: ', dst_address)
    # if '*' in dst_address:
    #     dst_address : str
    #     dst_address = dst_address.replace('*', 'localhost')
    #     print('MODIFIED DST ADDRESS: ', dst_address.replace('*', 'localhost'))
            

    level = logging.DEBUG
    dt = 3
    f = 2.0
    
    port = 5555

    year = 2023
    month = 1
    day = 1
    hh = 12
    mm = 00
    ss = 00
    start_date = datetime(year, month, day, hh, mm, ss)
    end_date = datetime(year, month, day, hh, mm, ss+dt)

    clock_config = AcceleratedRealTimeClockConfig(start_date, end_date, f)
    
    monitor = DummyMonitor( clock_config, 
                            port, 
                            level
                           )
    manager = SimulationManager(    clock_config, 
                                    [
                                        SimulationElementRoles.ENVIRONMENT.value,
                                        'AGENT_i'
                                    ], 
                                    port, 
                                    logger=monitor.get_logger()
                                )
    environment = EnvironmentNode(  port, 
                                    logger=monitor.get_logger()
                                )
    
    network_config = NetworkConfig( 'TEST_NETWORK',
                                    internal_address_map = {},
                                    external_address_map = {
                                                            zmq.REQ: [f'tcp://localhost:{port}'],
                                                            zmq.SUB: [f'tcp://localhost:{port+1}'],
                                                            zmq.PUSH: [f'tcp://localhost:{port+2}']}
                                    )
    agent = Agent('AGENT_i', network_config, logger=monitor.get_logger())

    sim_elements = [monitor, manager, environment, agent]
    with concurrent.futures.ThreadPoolExecutor(len(sim_elements)) as pool:
        for sim_element in sim_elements:
            sim_element : NetworkElement
            pool.submit(sim_element.run, *[])
