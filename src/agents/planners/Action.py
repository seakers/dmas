from src.agents.planners.TimeInterval import TimeInterval
from src.messages.Message import CentralPlannerMessage, AbstractMessage


class AbstractAction:
    """
    Abstract action to be performed by an agent
    """
    def __init__(self, type=None, start=0, end=1):
        """
        Constructor
        :param type: action type
        :param start: start epoc in [s]
        :param end: end epoc in [s]
        """
        self.type = type
        self.time_interval = TimeInterval(start, end)
        self.status = False

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
        return self.time_interval.in_interval(epoc) == 1 or self.status

    def set_complete(self):
        self.status = True

    def copy(self):
        return self.__copy__()

    def __copy__(self):
        pass


class TransmitAction(AbstractAction):
    def __init__(self, sender_id, target_id, start, data_rate, size, content):
        super().__init__(type='transmit', start=start, end=(size / data_rate + start))
        self.sender_id = sender_id
        self.target_id = target_id
        self.data_rate = data_rate
        self.size = size
        self.content = content
        self.message = AbstractMessage(self.sender_id, self.target_id, self.time_interval.start,
                                       self.data_rate, self.size, self.content)

    def get_message_size(self):
        return self.size

    def get_target_id(self):
        return self.target_id

    def get_message(self):
        return self.message


class ActuateAction(AbstractAction):
    def __init__(self, component_name, start, status=True):
        super().__init__(type='actuate', start=start, end=start+1)
        self.component_name = component_name
        self.actuationStatus = status

    def get_component_name(self):
        return self.component_name

    def get_actuation_status(self):
        return self.actuationStatus
