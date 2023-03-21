import logging
import zmq
from dmas.managers import AbstractManager
from dmas.messages import SimulationElementRoles
from dmas.network import NetworkConfig


class SimulationManager(AbstractManager):
    def __init__(self, clock_config, simulation_element_name_list : list, port : int, level : int = logging.INFO, logger : logging.Logger = None) -> None:
        network_config = NetworkConfig('TEST_NETWORK',
                                        external_address_map = {
                                                                zmq.REP: [f'tcp://*:{port}'],
                                                                zmq.PUB: [f'tcp://*:{port+1}'],
                                                                zmq.PUSH: [f'tcp://localhost:{port+2}']})
        
        super().__init__(simulation_element_name_list, clock_config, network_config, level, logger)

    def _check_element_list(self):
        # check if an environment is contained in the simulation
        if SimulationElementRoles.ENVIRONMENT.name not in self._simulation_element_name_list:
            raise AttributeError('List of simulation elements must include one simulation environment.')
               
        if self._simulation_element_name_list.count(SimulationElementRoles.ENVIRONMENT.name) > 1:
            raise AttributeError('List of simulation elements includes more than one simulation environment.')
        