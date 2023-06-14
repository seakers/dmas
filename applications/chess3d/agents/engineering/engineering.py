import logging
import uuid
from applications.chess3d.utils import ModuleTypes
from dmas.modules import InternalModule
from dmas.network import NetworkConfig

from agents.engineering.subsystems import AbstractSubsystem
       
class EngineeringModule(InternalModule):
    """
    
    """
    def __init__(   self, 
                    subsystems : list,
                    module_network_config: NetworkConfig, 
                    parent_node_network_config: NetworkConfig, 
                    level: int = logging.INFO, 
                    logger: logging.Logger = None
                ) -> None:
    
        super().__init__(ModuleTypes.ENGINEERING.value,
                         module_network_config, 
                         parent_node_network_config, 
                         level, 
                         logger
                         )
        
        # check parameters
        if not isinstance(subsystems, list):
            raise ValueError(f'`subsystems` must be of type `list`. is of type {type(subsystems)}.')
        for component in subsystems:
            if not isinstance(component, AbstractSubsystem):
                raise ValueError(f'elements of list `subsystems` must be of type `Subsystem`. contains element of type {type(component)}.')
            
        self.subsystems = subsystems