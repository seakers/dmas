from src.network.messages import Message


class Action:
    def __init__(self, action_type, start, end):
        self.action_type = action_type
        self.start = start
        self.end = end

    def is_active(self, t):
        return self.start <= t <= self.end

    def is_done(self, t):
        return self.end < t


class ChargeAction(Action):
    def __init__(self, power, start, end):
        super().__init__('charge', start, end)
        self.power = power


class TransmitAction(Action):
    def __init__(self, src, dst, start, size, rate, content=None):
        super().__init__('transmit', start, start+size/rate)
        self.src = src
        self.dst = dst
        message_id = "S{}D{}".format(src.unique_id, dst.unique_id)
        self.msg = Message(start, size, rate, message_id, content=None, src=src, dst=dst, flow_id=0)