from abc import ABC
from typing import Union

from dmas.agents import AgentAction
# from agents.engineering.subsystems import pwr_src,pwr_recieve,pwr
# from agents.engineering.components import pwr_src,pwr_recieve,pwr


class ComponentAction(AgentAction):
    """ 
    # Component Action
    
    Describes an action to be performed on or by an engineering module component
    """
    pass

class SubsystemAction(AgentAction):
    """ 
    # Subsystem Action
    
    Describes an action to be performed on or by an engineering module subsystem
    """
    pass

class ComponentActuateAction(ComponentAction):
    pass


class ProvidePower(AgentAction):
    def __init__(self,  
                 power_source: str,
                 power_reciever: str,
                 power: int,
                 action_type: str, 
                 t_start: float | int, t_end: float | int, status: str = 'PENDING', id: str = None, **_) -> None:
        super().__init__(action_type, t_start, t_end, status, id, **_)
        self.power_source = power_source
        self.power_reciever = power_reciever
        self.power = power 
    """ 
    # Subsystem Action
    
    Initiates the provision of power from source to reciever
    """
    pass

class StopProvidePower(AgentAction):
    """ 
    # Subsystem Action
    
    Stops the provision of power to a reciever
    """
    def __init__(self,  
                 power_source: str,
                 power_reciever: str,
                 power: int,
                 action_type: str, 
                 t_start: float | int, t_end: float | int, status: str = 'PENDING', id: str = None, **_) -> None:
        super().__init__(action_type, t_start, t_end, status, id, **_)
        self.power_source = power_source
        self.power_reciever = power_reciever
        self.power = power 
    pass

class ChargeBattery(AgentAction):
    """ 
    # Subsystem Action
    
    Charges battery given input power
    """
    def __init__(self,
                 power_reciever: str,
                 power: int,
                 action_type: str, 
                 t_start: float | int, t_end: float | int, status: str = 'PENDING', id: str = None, **_) -> None:
        super().__init__(action_type, t_start, t_end, status, id, **_)
        self.power_reciever = power_reciever
        self.power = power 
    pass