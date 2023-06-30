from abc import ABC, abstractmethod
from typing import Union
import uuid
import numpy as np
from engineering.actions import ComponentProvidePower, SubsystemAction, SubsystemProvidePower
from engineering.components import AbstractComponent


class AbstractSubsystem(ABC):
    """
    Represents a subsystem onboard an agent's Engineering Module
    
    ### Attributes:
        - name (`str`) : name of the subsystem
        - status (`str`) : current status of the subsystem
        - t (`float` or `int`) : last updated time
        - id (`str`) : identifying number for this subsystem in uuid format
    """
    ENABLED = 'ENABLED'
    DISABLED = 'DISABLED'
    FAILED = 'FAILED'

    def __init__(   self, 
                    name : str,
                    components : list,
                    status : str = DISABLED,
                    t : float = 0.0,
                    id : str = None
                    ) -> None:
        """
        Initiates an instance of an Abstract Subsystem 

        ### Arguments:
            - name (`str`) : name of the subsystem
            - components (`list`): list of components comprising this subsystem
            - status (`str`) : initial status of the subsystem
            - t (`float` or `int`) : initial updated time  
            - id (`str`) : identifying number for this task in uuid format
        """
        super().__init__()
                
        # check parameters
        if not isinstance(components, list):
            raise ValueError(f'`components` must be of type `list`. is of type {type(components)}.')
        for component in components:
            if not isinstance(component, AbstractComponent):
                raise ValueError(f'elements of list `components` must be of type `Component`. contains element of type {type(component)}.')
        
        # assign values
        self.name = name
        self.status = status
        self.t = t
        self.id = str(uuid.UUID(id)) if id is not None else str(uuid.uuid1())

        # converts the list of component objects into a dictionary with component names as the keys and component objects as values
        dictionary = {}
        for component in components:
            dictionary[component.name] = component
        self.components = dictionary

    @abstractmethod
    def update(self, **kwargs) -> None:
        """
        Propagates and updates the current state of the subsystem.
        """
        pass

    @abstractmethod
    def perform_action(self, action : SubsystemAction, t : Union[int, float]) -> bool:
        """
        Performs an action on this subsystem

        ### Arguments:
            - action (:obj:`SubsystemAction`) : action to be performed
            - t (`float` or `int`) : current simulation time in [s]

        ### Returns:
            - boolean value indicating if performing the action was successful or not
        """
        self.t = t

    @abstractmethod
    def is_critical(self, **kwargs) -> bool:
        """
        Returns true if the subsystem is in a critical state
        """
        pass

    @abstractmethod
    def is_failure(self, **kwargs) -> bool:
        """
        Returns true if the subsystem is in a failure state
        """
        pass

    @abstractmethod
    def predict_critical(self, **kwags) -> float:
        """
        Given the current state of the subsystem, this method predicts when a critical state will be reached.

        Returns the time where this will ocurr in simulation seconds.
        """
        pass

    @abstractmethod
    def predict_failure(self, **kwags) -> float:
        """
        Given the current state of the subsystem, this method predicts when a failure state will be reached.

        Returns the time where this will ocurr in simulation seconds.
        """
        pass

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this agent state object
        """
        return dict(self.__dict__)
    
    @abstractmethod
    def decompose_instructions(self, **kwags) -> float:
        ""

        ""
        pass

class EPSubsystem(AbstractSubsystem):
    """
    Represents the EPS subsystem onboard an agent's Engineering Module
    """

    ### Attributes:

    ENABLED = 'ENABLED'
    DISABLED = 'DISABLED'
    FAILED = 'FAILED'

    def __init__(   self, 
                    components : list,
                    connection : dict,
                    name : str = "EPS",
                    status : str = DISABLED,
                    t : float = 0.0,
                    id : str = None
                    ) -> None:
        """
        Initiates an instance of the EPS Subsystem 

        ### Arguments:
            - name (`str`) : name of the subsystem
            - components (`list`): list of components comprising this subsystem
            - status (`str`) : initial status of the subsystem
            - t (`float` or `int`) : initial updated time  
            - id (`str`) : identifying number for this task in uuid format
        """
        super().__init__(self, name, components, status, t, id)

        # check parameters
        if not isinstance(components, list):
            raise ValueError(f'`components` must be of type `list`. is of type {type(components)}.')
        for component in components:
            if not isinstance(component, AbstractComponent):
                raise ValueError(f'elements of list `components` must be of type `Component`. contains element of type {type(component)}.')
            
        
            
    def update(self):
        """
        Updates all components in the components list
        """
        for component in self.components:
            component.update()

    def perform_action(self, action : SubsystemAction, t : Union[int, float]) -> bool:
        self.t = t
        
        if isinstance(action, SubsystemProvidePower):
            receiver = self.components[action.receiver]

            ## Pick a source ##
            possible_sources = []

            values = list(self.connections.values())
            for i in range(len(values)):
                components = values[i]
                for component in components:
                    if component[0] == receiver:
                        possible_sources.append(list(self.connections.key())[i])
            
            receiver_pwr = receiver.min_pwr

            min_energy = 0
            chosen_source = None
            for source in possible_sources:
                if source.current_energy > min_energy:
                    chosen_source = source

            component_action = ComponentProvidePower(receiver_pwr, self.t)
            chosen_source.perform_action(component_action, self.t)

        elif isinstance():
            pass

    def is_failure(self):
        """
        Returns true if the subsystem is in a failure state
        Is defined by a source component such as a battery or solar array being in a falure state
        """
        for component in self.components:
            if component.is_failure():# and dict(component) == "source":
                return True
        return False

    def is_critical(self):
        """
        Returns true if the subsystem is in a critical state

        Is defined by a source component such as a battery or solar array being in a critical state
        """
        for component in self.components:
            if component.is_critical():# and dict(component) == "source":
                return True
        return False
    
    def predict_failure(self):
        """
        Given the current state of the subsystem, this method predicts when a failure state will be reached.

        Is defined by the source components with the shortest predicted failure state

        Returns the time where this will ocurr in simulation seconds.
        """
        time_to_fail = np.Inf
        for component in self.components:
            temp = component.predict_failure()
            if temp < time_to_fail:# and dict(component) == "source":
                time_to_fail = temp
        return time_to_fail

    def predict_critical(self):
        """
        Given the current state of the subsystem, this method predicts when a critical state will be reached.

        Is defined by the source components with the shortest predicted critical state

        Returns the time where this will ocurr in simulation seconds.
        """
        time_to_crit = np.Inf
        for component in self.components:
            temp = component.predict_critical()
            if temp < time_to_crit:# and dict(component) == "source":
                time_to_crit = temp
        return time_to_crit
