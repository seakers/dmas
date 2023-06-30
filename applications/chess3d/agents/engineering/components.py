from abc import ABC, abstractmethod
from typing import Union
import uuid

from applications.chess3d.agents.engineering.actions import ComponentAction, ComponentProvidePower


class AbstractComponent(ABC):
    """
    # Abstract Component 

    Represents a generic component that is part of a subsystem onboard an agent's Engineering Module

    ### Attributes:
        - name (`str`) : name of the component
        - status (`str`) : current status of the component
        - t (`float` or `int`) : last updated time
        - id (`str`) : identifying number for this task in uuid format
    """
    ENABLED = 'ENABLED'
    DISABLED = 'DISABLED'
    FAILED = 'FAILED'

    def __init__(   self, 
                    name : str,
                    min_pwr : float,
                    status : str = DISABLED,
                    t : float = 0.0,
                    id : str = None
                    ) -> None:
        """
        Initiates an instance of an Abstract Component 

        ### Arguments:
            - name (`str`) : name of the component
            - status (`str`) : initial status of the component
            - t (`float` or `int`) : initial updated time  
            - id (`str`) : identifying number for this component in uuid format
        """
        super().__init__()
                
        self.name = name
        self.min_pwr = min_pwr
        self.status = status
        self.t = t
        self.id = str(uuid.UUID(id)) if id is not None else str(uuid.uuid1())

    @abstractmethod
    def update(self, **kwargs) -> None:
        """
        Propagates and updates the current state of the component.
        """
        pass

    @abstractmethod
    def perform_action(self, action : ComponentAction, t : Union[int, float]) -> bool:
        """
        Performs an action on this component

        ### Arguments:
            - action (:obj:`ComponentAction`) : action to be performed
            - t (`float` or `int`) : current simulation time in [s]

        ### Returns:
            - boolean value indicating if performing the action was successful or not
        """
        self.t = t

    @abstractmethod
    def is_critical(self, **kwargs) -> bool:
        """
        Returns true if the component is in a critical state
        """
        pass

    @abstractmethod
    def is_failure(self, **kwargs) -> bool:
        """
        Returns true if the component is in a failure state
        """
        pass

    @abstractmethod
    def predict_critical(self, **kwags) -> float:
        """
        Given the current state of the component, this method predicts when a critical state will be reached.

        Returns the time where this will ocurr in simulation seconds.
        """
        pass

    @abstractmethod
    def predict_failure(self, **kwags) -> float:
        """
        Given the current state of the component, this method predicts when a failure state will be reached.

        Returns the time where this will ocurr in simulation seconds.
        """
        pass

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this component object
        """
        return dict(self.__dict__)
    
class Battery(AbstractComponent):
    """
    # Battery Component 

    Represents a battery that is part of the EPS sybstem onboard an agent's Engineering Module

    ### Attributes:
        - max_pwr (`float`) : name of the component
        - current_pwr (`float`) : current power available
    """
    def __init__(   self, 
                    name : str,
                    max_energy : float,
                    status : str,
                    min_pwr : float = 0,
                    id : str = None
                    ) -> None:
        """
        Initiates an instance of an Abstract Component 

        ### Arguments:
            - name (`str`) : name of the component
            - status (`str`) : initial status of the component
            - t (`float` or `int`) : initial updated time  
            - id (`str`) : identifying number for this component in uuid format
        """
        super().__init__(self, name, min_pwr, status, 0.0, id)
                
        self.max_energy = max_energy
        self.current_energy = max_energy
        self.load = 0

    def perform_action(self, action : ComponentAction, t : Union[int, float]) -> bool:
        """
        Performs an action on this component

        ### Arguments:
            - action (:obj:`ComponentAction`) : action to be performed
            - t (`float` or `int`) : current simulation time in [s]

        ### Returns:
            - boolean value indicating if performing the action was successful or not
        """
        self.t = t

        if isinstance(action, ComponentProvidePower):
            receiver_pwr = action.receiver_pwr
            self.load += receiver_pwr

        elif isinstance(action, ):
            pass