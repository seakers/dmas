class TimeInterval:
    """
    Represents a time interval in seconds
    """
    def __init__(self, start=0, end=1):
        """
        Constructor
        :param start: starting epoc in [s]
        :param end: end epoc in [s]
        """
        self.start = start
        self.end = end

    def in_interval(self, epoc) -> int:
        """
        Evaluates if an epoc is within this time interval
        :param epoc: epoc to be evaluated
        :return: -1 if epoc is before interval, 0 if contained within interval, 1 if epoc is after interval
        """
        if self.start < epoc:
            return -1
        elif self.start <= epoc <= self.end:
            return 0
        elif self.end < epoc:
            return 1

    def merge(self, other):
        """
        Merges two time intervals if an overlap exists
        :param other: other interval to be merged
        :return: merged time interval if overlap exists or None if no overlap exists
        """
        if self.start <= other.start:
            if self.end >= other.start:
                # overlap exists
                return TimeInterval(self.start, other.end)
        else:
            if other.end >= self.start:
                # overlap exists
                return TimeInterval(other.start, self.end)

        # no overlap exists
        return None


class Action:
    """
    Abstract action to be performed by an agent
    """
    def __init__(self, type=None, start=0, end=0):
        """
        Constructor
        :param type: action type
        :param start: start epoc in [s]
        :param end: end epoc in [s]
        """
        self.type = type
        self.time_interval = TimeInterval(start, end)

    def is_active(self, epoc) -> bool:
        """
        Indicates if this action is active during a given epoc
        :param epoc: epoc to the evaluated
        :return: True if action is active, False if not
        """
        return self.time_interval.in_interval(epoc) == 0

    def is_complete(self, epoc):
        """
        Indicates is this current action has been performed or epoc has passed its assigned time interval
        :param epoc: epoc to be evaluated
        :return: True if action has passed, False if not
        """
        return self.time_interval.in_interval(epoc) == 1


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
        return AbstractPlanner(start_epoc=self.epoc)

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