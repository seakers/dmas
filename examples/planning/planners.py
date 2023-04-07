from dmas.modules import *

class ModuleNames(Enum):
    PLANNING_MODULE = 'PLANNING_MODULE'

class PlanningModule(InternalModule):
    def __init__(self, 
                module_network_config: NetworkConfig, 
                parent_network_config: NetworkConfig, 
                level: int = logging.INFO, 
                logger: logging.Logger = None
                ) -> None:

        super().__init__(ModuleNames.PLANNING_MODULE.value, 
                        module_network_config, 
                        parent_network_config, 
                        [], 
                        level, 
                        logger)

class PlannerResults(ABC):
    @abstractmethod
    def __eq__(self, __o: object) -> bool:
        """
        Compares two results 
        """
        return super().__eq__(__o)