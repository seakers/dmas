from abc import abstractmethod
from ctypes import Union
import logging
import uuid
import numpy as np
from nodes.engineering.actions import *
from applications.chess3d.utils import ModuleTypes

from nodes.engineering.subsystems import Subsystem
       
class EngineeringModule(object):
    """
    
    """
    def __init__(   self, 
                    subsystems : list,
                    t : Union[int, float] = 0.0,
                    level: int = logging.INFO, 
                    logger: logging.Logger = None,
                    id : str = None
                ) -> None:
        """
        ### Arguments
            - subsystems (`list`) : List of susbsystems that comprise this engineering module
            - t (`int` or `float`) : latest update time [s]
            - level (`int`) : logger level
            - logger 
        """

        # check parameters
        if not isinstance(subsystems, list):
            raise ValueError(f'`subsystems` must be of type `list`. is of type {type(subsystems)}.')
        for component in subsystems:
            if not isinstance(component, Subsystem):
                raise ValueError(f'elements of list `subsystems` must be of type `Subsystem`. contains element of type {type(component)}.')
            
        self.name = ModuleTypes.ENGINEERING.value
        self.subsystems = subsystems
        self.level = level
        self.logger = logger
        self.id = str(uuid.UUID(id)) if id is not None else str(uuid.uuid1())

    def update_state(self, t : Union[int, float]) -> None:
        """
        Updates the current state of the engineering module.
        """
        for subsystem in self.subsystems:
            subsystem : Subsystem
            subsystem.update_state(t)

    def propagate(self, t : Union[int, float]) -> object:
        """
        Propagates and the current state of the engineering module.
        """
        # TODO
        pass

    def is_critial(self) -> bool:
        """
        Returns true if the Engineering Module is in a critical state.

        This is reached if any subsystem reaches a critical state
        """
        for subsystem in self.subsystems:
            subsystem : Subsystem
            if subsystem.is_critical():
                return True
        
        return False

    def is_failure(self) -> bool:
        """
        Returns true if the Engineering Module is in a failure state.

        This is reached if any subsystem reaches a failure state
        """
        for subsystem in self.subsystems:
            subsystem : Subsystem
            if subsystem.is_failure():
                return True
        
        return False

    def predict_critical(self) -> float:
        """
        Given the current state of the engineering module subsystems, this method predicts when a critical state will be reached.

        Returns the time where this will ocurr in simulation seconds.
        """
        t_min = np.Inf
        for subsystem in self.subsystems:
            subsystem : Subsystem
            t_crit = subsystem.predict_critical()
            if t_crit < t_min:
                t_min = t_crit
        
        return t_min

    def predict_failure(self) -> float:
        """
        Given the current state of the engineering module subsystems, this method predicts when a failure state will be reached.

        Returns the time where this will ocurr in simulation seconds.
        """
        t_min = np.Inf
        for subsystem in self.subsystems:
            subsystem : Subsystem
            t_crit = subsystem.predict_failure()
            if t_crit < t_min:
                t_min = t_crit
        
        return t_min

    @abstractmethod
    def perform_action(self, action : Union[AgentAction, SubsystemAction, ComponentAction], t : Union[int, float]) -> bool:
        """
        Performs an action on this subsystem

        ### Arguments:
            - action (:obj:`SubsystemAction`) : action to be performed
            - t (`float` or `int`) : current simulation time in [s]

        ### Returns:
            - status (`str`): action completion status
            - dt (`float`): time to be waited by the agent
        """
        pass