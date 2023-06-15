from abc import ABC

from dmas.agents import AgentAction


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