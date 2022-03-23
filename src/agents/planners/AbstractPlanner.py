class AbstractPlanner:
    """
    Abstract Class representing an agent's planner
    """
    def __init__(self, start_epoc=0, time_step=1):
        """
        Constructor
        :param start_epoc: starting epoc for the planner
        :param time_step: time step of the simulation
        """
        self.epoc = start_epoc
        self.dt = time_step
        self.plan = []

    def __copy__(self):
        """
        Copy constructor
        :return: deep copy of the current planner
        """
        new_plan = AbstractPlanner(start_epoc=self.epoc)
        for action in self.plan:
            new_plan.plan.append(action.copy())
        return

    def copy(self):
        return self.__copy__()

    def update_plan(self, component_list, received_messages, epoc):
        """
        Updates epoc and updates existing plan according to its current and newly received information
        :param component_list: list and state of each component contained in the agent
        :param received_messages: list of newly received messages
        :param epoc: current epoc in [s]
        :return:
        """
        self.epoc = epoc
        return

    def get_plan(self):
        """
        Queries existing plan to return a list of actions that have to be performed at the current epoc
        :return: array of actions to be performed
        """
        plan = []
        for action in self.plan:
            if action.is_active(self.epoc):
                plan.append(action)

        return plan