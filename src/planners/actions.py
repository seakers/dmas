from src.network.messages import Message


class Action:
    def __init__(self, action_type, start, end):
        self.action_type = action_type
        self.start = start
        self.end = end

    def is_active(self, t):
        return self.start <= t < self.end

    def is_done(self, t):
        return self.end <= t


class ActuateAgentAction(Action):
    def __init__(self, start, status=True):
        super().__init__('actuate_agent', start, start + 1)
        self.status = status


class ActuateComponentAction(Action):
    def __init__(self, component, start, status=True):
        super().__init__('actuate_component', start, start+1)
        self.component = component
        self.status = status


class DeleteMessageAction(Action):
    def __init__(self, msg, start):
        super().__init__('delete_message', start, start + 1)
        self.msg = msg


class MeasurementAction(Action):
    def __init__(self, instrument_list, target, start, end):
        super().__init__('measurement', start, end)
        self.instrument_list = []
        for instrument in instrument_list:
            self.instrument_list.append(instrument)
        self.target = target


class TransmitAction(Action):
    def __init__(self, src, dst, start, size, rate, timeout, content=None):
        super().__init__('transmit', start, start+size/rate)
        self.src = src
        self.dst = dst
        message_id = f"S{src.unique_id}D{dst.unique_id}"
        self.msg = Message(self, size, rate, message_id, timeout=timeout, content=content, src=src, dst=dst)


class ChargeAction(Action):
    def __init__(self, start, end):
        super().__init__('charge', start, end)
