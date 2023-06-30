from abc import ABC

class ComponentAction(ABC):
    """ 
    # Component Action
    
    Describes an action to be performed on or by an engineering module component
    """
    def __init__(   self, 
                    t : float = 0.0,
                    ) -> None:
        self.t = t

        super.__init__()

    pass

class SubsystemAction(ABC):
    """ 
    # Subsystem Action
    
    Describes an action to be performed on or by an engineering module subsystem
    """
    def __init__(   self, 
                    t : float = 0.0,
                    ) -> None:
        self.t = t

        super.__init__()
    pass

class SubsystemProvidePower(SubsystemAction):
    """ 
    # Subsystem Provide Power
    
    Describes an action to be performed on or by an engineering module subsystem
    """
    def __init__(   self,
                    receiver : str,
                    t : float = 0.0
                    ) -> None:

        super.__init__(self, t)

        self.receiver = receiver
        self.t = t

class ComponentProvidePower(ComponentAction):
    """ 
    # ComponentProvide Power
    
    Describes an action to be performed on or by an engineering module subsystem
    """
    def __init__(   self,
                    receiver_pwr : float,
                    t : float = 0.0
                    ) -> None:
        super.__init__(self, t)

        self.receiver_pwr = receiver_pwr