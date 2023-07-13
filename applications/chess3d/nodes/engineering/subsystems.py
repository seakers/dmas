from abc import ABC, abstractmethod
from typing import Union
import uuid
from nodes.engineering.components import Component
from nodes.engineering.actions import SubsystemAction, ADCSAttitude,DisabledAction


class Subsystem(ABC):
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
                    components : list = [],
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
            if not isinstance(component, Component):
                raise ValueError(f'elements of list `components` must be of type `Component`. contains element of type {type(component)}.')
        
        # assign values
        self.name = name
        self.components = components
        self.status = status

        self.name = name
        self.status = status
        self.components = components
        self.t = t
        self.id = str(uuid.UUID(id)) if id is not None else str(uuid.uuid1())

    @abstractmethod
    def update_state(self, **kwargs) -> None:
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

class ACDS(Subsystem):
    """
    Attitude Control and Determination Subsystem of Agent's Engineeering Module
    
    ### Attributes:
        - name (`str`) : name of the subsystem
        - status (`str`) : current status of the subsystem
        - t (`float` or `int`) : last updated time
        - id (`str`) : identifying number for this subsystem in uuid format
    """
    ENABLED = 'ENABLED'
    DISABLED = 'DISABLED'
    FAILED = 'FAILED'
    def __init__(self, 
                 name: str,
                 mass: float,
                 altitude: float,
                 Inertia_sat: float,
                 Sat_rot: float,
                 #Inertia: list, 
                 components: list,
                 status: str = DISABLED, 
                 t: float = 0, 
                 id: str = None
                 )-> None:
        super().__init__(name, components, status, t, id)

        # check parameters
        if not isinstance(components, list):
            raise ValueError(f'`components` must be of type `list`. is of type {type(components)}.')
        for component in components:
            if not isinstance(component, Component):
                raise ValueError(f'elements of list `components` must be of type `Component`. contains element of type {type(component)}.')
        
        # assign values
        self.name = 'ADCS'
        self.components = components
        self.mass = mass
        self.altitude = altitude
        self.Inertia_sat = Inertia_sat
        self.Sat_rot = Sat_rot
        #self.Inertia = Inertia
        self.status = status

        self.name = name
        self.status = status
        self.components = components
        self.t = t

    def update_state(self,
                     t_f: float,
                     th_o: float,
                     dth: float,
                     status: str=None, 
                     **kwargs) -> None:
        """
        Propagates and updates the current state of the subsystem.
        """
        dt = t_f - self.t
        th = th_o + dth/dt
        self.th = th
    
    def perform_action(self, action : SubsystemAction, t : float) -> bool:
        """
        Performs an action of subsystem

        ### Arguments:
            - action (:obj:`SubsystemAction`) : action to be performed
            - t (`float` or `int`) : current simulation time in [s]

        ### Returns:
            - boolean value indicating if performing the action was successful or not
        """
        self.t = t

        if isinstance(action,DisabledAction):
            self.update_state(t,status=self.DISABLED)
        elif isinstance(action,ADCSAttitude):
            self.update_state(t,status=self.ENABLED)
            return self.perform_ADCSAttitude(action,t)

    def perform_ADCSAttitude(self, action : ADCSAttitude, t : float) -> bool:
        """
        Performs ADCS Attitude change

        ### Arguments:
            - action (:obj:`SubsystemAction`) : action to be performed
            - t (`float` or `int`) : current simulation time in [s]

        ### Returns:
            - boolean value indicating if performing the action was successful or not
        """
        self.t = t
    pass