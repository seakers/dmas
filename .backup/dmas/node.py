
from agent import AgentClient

from modules.engineering import EngineeringModule

class SimulationNode(AgentClient):
    def __init__(self, name, scenario_dir, component_list) -> None:
        super().__init__(name, scenario_dir)
        self.modules = [
                        # SchedulingModule(self),
                        # PlatformSimulatorModule(self),
                        EngineeringModule(self, component_list)
                       ]
    
