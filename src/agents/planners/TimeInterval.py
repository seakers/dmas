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
        if epoc < self.start:
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