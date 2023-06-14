from abc import ABC


class ComponentAction(ABC):
    """ 
    # Component Action
    
    Describes an action to be performed on or by an engineering module component
    """
    pass

class SubsystemAction(ABC):
    """ 
    # Subsystem Action
    
    Describes an action to be performed on or by an engineering module subsystem
    """
    pass

class ComponentActuateAction(ComponentAction):
    pass