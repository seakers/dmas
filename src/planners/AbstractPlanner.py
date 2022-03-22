class TimeInterval:
    def __init__(self, start=0, end=1):
        self.start = start
        self.end = end

    def in_interval(self, epoc):
        return self.start <= epoc and epoc <= self.end

    def merge(self, other):
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
    def __init__(self, type=None, start=0, end=0):
        self.type = type
        self.time = TimeInterval(start, end)


class AbstractPlanner:
    def __init__(self, epoc=0):
        self.epoc = epoc
        self.plan = []
