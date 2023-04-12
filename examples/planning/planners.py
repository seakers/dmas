from dmas.modules import *

class PlannerTypes(Enum):
    ACCBBA = 'ACCBBA' # Asynchronous Consensus Constraint-Based Bundle Algorithm

class PlannerModule(InternalModule):
    def __init__(self, 
                manager_port : int,
                agent_id : int,
                parent_network_config: NetworkConfig, 
                planner_type : PlannerTypes,
                level: int = logging.INFO, 
                logger: logging.Logger = None
                ) -> None:
        module_network_config =  NetworkConfig(f'AGENT_{agent_id}',
                                                manager_address_map = {
                                                zmq.REQ: [],
                                                zmq.PUB: [f'tcp://*:{manager_port+5 + 4*agent_id + 3}'],
                                                zmq.SUB: [f'tcp://localhost:{manager_port+5 + 4*agent_id + 2}']})
                
        super().__init__(f'PLANNING_MODULE_{agent_id}', 
                        module_network_config, 
                        parent_network_config, 
                        [], 
                        level, 
                        logger)
        
        if planner_type not in PlannerTypes:
            raise NotImplementedError(f'planner of type {planner_type} not yet supported.')
        self.planner_type = planner_type

class PlannerResults(ABC):
    @abstractmethod
    def __eq__(self, __o: object) -> bool:
        """
        Compares two results 
        """
        return super().__eq__(__o)

class ACCBBAPlannerModule(PlannerModule):
    def __init__(   self,  
                    manager_port: int, 
                    agent_id: int, 
                    parent_network_config: NetworkConfig, 
                    level: int = logging.INFO, logger: logging.Logger = None) -> None:
        super().__init__(   manager_port, 
                            agent_id, 
                            parent_network_config,
                            PlannerTypes.ACCBBA, 
                            level, 
                            logger)