import asyncio
import logging
from typing import Any, Callable
from nodes.science.reqs import *
from dmas.network import NetworkConfig
from nodes.planning.groundstat import GroundStationPlanner
from nodes.science.science import ScienceModule
from nodes.agent import SimulationAgentState, SimulationAgent
import pandas as pd
import zmq

class GroundStationAgent(SimulationAgent):
    def __init__(self, 
                    agent_name: str, 
                    results_path: str,
                    scenario_name: str, 
                    port : int,
                    manager_network_config: NetworkConfig, 
                    initial_state: SimulationAgentState, 
                    utility_func: Callable[[], Any],  
                    measurement_reqs : list = [],
                    science_module : ScienceModule = None,
                    level: int = logging.INFO, 
                    logger: logging.Logger = None
                ) -> None:


        manager_addresses : dict = manager_network_config.get_manager_addresses()
        req_address : str = manager_addresses.get(zmq.REP)[0]
        req_address = req_address.replace('*', 'localhost')

        sub_address : str = manager_addresses.get(zmq.PUB)[0]
        sub_address = sub_address.replace('*', 'localhost')

        pub_address : str = manager_addresses.get(zmq.SUB)[0]
        pub_address = pub_address.replace('*', 'localhost')

        push_address : str = manager_addresses.get(zmq.PUSH)[0]

        agent_network_config = NetworkConfig( 	scenario_name,
												manager_address_map = {
														zmq.REQ: [req_address],
														zmq.SUB: [sub_address],
														zmq.PUB: [pub_address],
                                                        zmq.PUSH: [push_address]},
												external_address_map = {
														zmq.REQ: [],
														zmq.SUB: [f'tcp://localhost:{port+1}'],
														zmq.PUB: [f'tcp://*:{port+2}']},
                                                internal_address_map = {
														zmq.REP: [f'tcp://*:{port+3}'],
														zmq.PUB: [f'tcp://*:{port+4}'],
														zmq.SUB: [f'tcp://localhost:{port+5}']
											})

        planning_module = GroundStationPlanner( results_path, 
                                                agent_name, 
                                                measurement_reqs, 
                                                agent_network_config, 
                                                utility_func,
                                                level,
                                                logger)

        super().__init__(   agent_name, 
                            results_path,
                            manager_network_config, 
                            agent_network_config, 
                            initial_state, 
                            [], 
                            planning_module, 
                            science_module, 
                            level, 
                            logger)

        self.measurement_reqs = measurement_reqs

    async def setup(self) -> None:
        # nothing to setup
        return
    
    async def live(self):
        await asyncio.sleep(5e-2) # wait for others to connect 
        
        await super().live()

    async def teardown(self) -> None:
        await super().teardown()

        # print measurement requests from the ground
        headers = ['id', 'type', 'x_pos','y_pos','z_pos','s_max','measurements','t_start','t_end','t_corr']
        data = []
        for req in self.measurement_reqs:
            req : GroundPointMeasurementRequest
            line = [    
                        req.id.split('-')[0],
                        req.request_type,
                        req.pos[0],
                        req.pos[1],
                        req.pos[2],
                        req.s_max,
                        f"{req.measurements}",
                        req.t_start,
                        req.t_end,
                        req.t_corr
                    ]
            data.append(line)

        # log and save results
        summary_df = pd.DataFrame(data, columns=headers)
        self.log(f"\nMEASUREMENT REQUESTS:\n{str(summary_df)}\n\n", level=logging.WARNING)
        summary_df.to_csv(f"{self.results_path}/../gpRequests.csv", index=False)