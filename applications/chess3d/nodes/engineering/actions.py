from abc import ABC
from enum import Enum
from typing import Union

from dmas.agents import AgentAction

class ComponentAction(AgentAction):
    """ 
    # Component Action
    
    Describes an action to be performed on or by an engineering module component
    """
    def __init__(self, 
                action_type: str, 
                target : str, 
                t_start: Union[float, int], 
                status: str = 'PENDING', 
                id: str = None, 
                **_) -> None:
        super().__init__(action_type, t_start, status=status, id=id)
        self.target = target


class SubsystemAction(AgentAction):
    """ 
    # Subsystem Action
    
    Describes an action to be performed on or by an engineering module subsystem

    ### Attributes:
        - action_type (`str`): type of action to be performed
        - t_start (`float`): start time of this action in [s] from the beginning of the simulation
        - t_end (`float`): end time of this this action in [s] from the beginning of the simulation
        - status (`str`): completion status of the action
        - id (`str`) : identifying number for this action in uuid format
    """
    def __init__(self, 
                action_type: str, 
                target : str, 
                t_start: Union[float, int], 
                status: str = 'PENDING', 
                id: str = None, 
                **_) -> None:
        super().__init__(action_type, t_start, status=status, id=id)
        self.target = target

class ComponentActuateAction(ComponentAction):
    pass

class ADCSAttitude(AgentAction):
    """ 
    #  ADCS Subsystem Action
    
    Adjusts Attitude of craft based on rate of spin
    """
    def __init__(self, 
                action_type: str,
                des_att: float,
                cur_spd: float, 
                target : str, 
                t_start: Union[float, int], 
                status: str = 'PENDING', 
                id: str = None, 
                **_) -> None:
        super().__init__(action_type, t_start, status=status, id=id)
        self.target = target
    def Reactionwheel(self,**kwargs) -> None:
        I_s = self.Inertia_sat
        I_w = self.Inertia_wheel
        w_wo = self.rot_spd
        w_so = self.Sat_rot
        w_sf = self.cur_spd 
        wheel_spd = (I_s*(w_so - w_sf))/I_w  + w_wo
        self.wheel_spd = wheel_spd