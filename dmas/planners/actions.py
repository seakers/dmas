from dmas.network.messages import Message


class Action:
    def __init__(self, action_type, start, end):
        self.action_type = action_type
        self.start = start
        self.end = end
        self.started = False
        self.completed = False

    def begin(self):
        self.started = True

    def has_started(self):
        return self.started

    def is_active(self, t):
        return self.start <= t < self.end and self.has_started()

    def complete(self):
        self.completed = True

    def is_done(self, t):
        return self.completed

    def __str__(self):
        return f'{self.action_type},{self.start},{self.end},{self.started},{self.completed}'

    def __repr__(self) -> str:
        return f'{self.action_type}'


class ActuateAgentAction(Action):
    def __init__(self, start, status=True):
        super().__init__('actuate_agent', start, start + 1)
        self.status = status

    def __str__(self):
        out = super().__str__()
        return out + f',{self.status}'

    def __repr__(self) -> str:
        if self.status:
            return f'Actuate Agent ON'
        else:
            return f'Actuate Agent OFF'


class ActuateComponentAction(Action):
    def __init__(self, component, start, status=True):
        super().__init__('actuate_component', start, start+1)
        self.component = component
        self.status = status

    def __str__(self):
        out = super().__str__()
        return out + f',{self.component.name},{self.status}'

    def __repr__(self) -> str:
        if self.status:
            return f'Actuate {self.component.name} ON'
        else:
            return f'Actuate {self.component.name} OFF'


class ActuatePowerComponentAction(ActuateComponentAction):
    def __init__(self, component, start, power):
        super().__init__(component, start)
        self.power = power

    def __str__(self):
        out = super().__str__()
        return out + f',{self.power}'

    def __repr__(self) -> str:
        return f'Regulate {self.component.name} to {self.power}W'


class DeleteMessageAction(Action):
    def __init__(self, msg, start):
        super().__init__('delete_message', start, start + 1)
        self.msg = msg

    def __str__(self):
        out = super().__str__()
        return out + f',{self.msg.size}'

    def __repr__(self) -> str:
        return f'Delete Message'

class MeasurementAction(Action):
    def __init__(self, instrument_list, target, start, end):
        super().__init__('measurement', start, end)
        self.instrument_list = []
        for instrument in instrument_list:
            self.instrument_list.append(instrument)
        self.target = target

    def __str__(self):
        out = super().__str__()
        for instrument in self.instrument_list:
            out += f',{instrument.name}'

        return out + f',{self.target}'

    def __repr__(self) -> str:
        return f'Measure Target {self.target} with Instrument {self.instrument_list}'


class TransmitAction(Action):
    def __init__(self, src, dst, start, size, rate, timeout, content=None):
        super().__init__('transmit', start, start+size/rate)
        self.src = src
        self.dst = dst
        message_id = f"S{src.unique_id}D{dst.unique_id}"
        self.msg = Message(size, rate, message_id, timeout, src, dst, content=content)

    def __str__(self):
        out = super().__str__()
        return out + f',{self.src},{self.dst}'

    def __repr__(self) -> str:
        return f'Transmit Message to {self.dst.name}'


class ChargeAction(Action):
    def __init__(self, start, end):
        super().__init__('charge', start, end)

    def __repr__(self) -> str:
        return f'Charge Batteries'
