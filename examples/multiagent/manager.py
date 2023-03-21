from dmas.managers import AbstractManager
from dmas.messages import SimulationElementRoles


class SimulationManager(AbstractManager):
    def _check_element_list(self):
        # check if an environment is contained in the simulation
        if SimulationElementRoles.ENVIRONMENT.name not in self._simulation_element_name_list:
            raise AttributeError('List of simulation elements must include one simulation environment.')
               
        if self._simulation_element_name_list.count(SimulationElementRoles.ENVIRONMENT.name) > 1:
            raise AttributeError('List of simulation elements includes more than one simulation environment.')