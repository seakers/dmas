from abc import ABC, abstractmethod
from typing import Union
import uuid

from nodes.engineering.actions import ComponentAction


class Component(ABC):
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
    def is_critial(self, **kwargs) -> bool:
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

class Instrument(Component):
    def __init__(   self, 
                    name: str, 
                    id: str = None) -> None:
        super().__init__(name, id=id)

class ReactionWheel(ABC):
    """
    # ADCS Component 

    Reaction Wheel component of the ADCS subsystem

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
                    max_rot_spd: float,
                    rot_spd: float,
                    pwr_req: float,
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
        self.max_rot_spd = max_rot_spd
        self.rot_spd = rot_spd
        self.pwr_req = pwr_req
        self.status = status
        self.t = t
        self.id = str(uuid.UUID(id)) if id is not None else str(uuid.uuid1())

    def update(self,
               t_f: float,
               th_o: float,
               dth: float, 
               **kwargs) -> None:
        """
        Propagates and updates the current state of the the Reaction Wheels
        """
        dt = t_f - self.t
        th = th_o + dth/dt
        self.th = th
    def Reactionwheel(self,**kwargs) -> None:
        I_s = self.Inertia_sat
        I_w = self.Inertia_wheel
        w_wo = self.rot_spd
        w_so = self.Sat_rot
        w_sf = self.cur_spd 
        wheel_spd = (I_s*(w_so - w_sf))/I_w  + w_wo
        self.wheel_spd = wheel_spd