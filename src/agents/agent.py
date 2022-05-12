from simpy import AllOf

from src.agents.components.components import *
from src.agents.state import State
from src.planners.actions import *


class AbstractAgent:
    def __init__(self, env, unique_id, component_list=None, planner=None):
        self.env = env
        self.unique_id = unique_id
        self.other_agents = []
        self.component_list = component_list

        self.transceiver = None
        self.data_storage = None
        self.power_generator = None
        self.power_storage = None
        for component in component_list:
            if type(component) == Transceiver:
                self.transceiver = component
            elif type(component) == DataStorage:
                self.data_storage = component
            elif type(component) == PowerGenerator:
                self.power_generator = component
            elif type(component) == PowerStorage:
                self.power_storage = component

        self.planner = planner

        self.state = State(self, component_list)

        self.t_prev = env.now

    def live(self):
        while True:
            # update state
            self.state.update(self.component_list)

            # update planner
            self.planner.update(self.state, self.env.now)

            # perform actions from planner
            actions = self.planner.get_plan(self.env.now)
            events = self.actions_to_events(actions)
            listening = self.env.process(self.listening())

            if len(events) > 0:
                yield AllOf(self.env, events) | listening
            else:
                yield listening

            if listening.triggered:
                for event in events:
                    if not event.triggered:
                        event.interrupt("New message received! Reevaluating plan...")

            # update time
            self.t_prev = self.env.now

    def actions_to_events(self, actions):
        events = []
        for action in actions:
            event = None
            if type(action) == TransmitAction:
                event = self.env.process(self.transmit(action))
            # elif type(action) == IdleAction:
            #     event = self.env.process(self.idle(action))

            if event is not None:
                events.append(event)

        return events

    def put_message_in_inbox(self, msg):
        self.print_string("Starting reception of msg {} from A{}..."
                          .format(msg.message_id, msg.src.unique_id))

        self.transceiver.packets_rec += 1
        tmp_byte_count = self.transceiver.buffer + msg.size

        if tmp_byte_count >= self.transceiver.buffer_size:
            self.transceiver.packets_drop += 1
            self.print_string("Not enough room in the buffer. Dropping message...".format(msg.message_id, msg.dst))
            return
        else:
            self.transceiver.buffer_in = tmp_byte_count
            return self.transceiver.inbox.put(msg)

    def listening(self):
        self.print_string("Listening for messages...")
        msg = (yield self.transceiver.inbox.get())
        self.transceiver.busy = 1

        yield self.env.timeout(msg.size / msg.rate)
        self.transceiver.buffer -= msg.size

        tmp_byte_count = self.data_storage.data_stored + msg.size
        if tmp_byte_count > self.data_storage.data_capacity:
            self.print_string("Not enough memory in the data storage unit. Dropping message...")
        else:
            self.data_storage.mailbox.put(msg)
            self.data_storage.data_stored += msg.size
            self.print_string("Finished reception of msg {} from A{}!"
                              .format(msg.message_id, msg.src.unique_id))
        self.transceiver.busy = 0

    def transmit(self, action):
        other = action.dst
        msg = action.msg

        self.print_string("Starting transmission of msg {} towards A{}..."
                          .format(msg.message_id, msg.dst.unique_id))
        other.put_message_in_inbox(msg)
        yield self.env.timeout(msg.size / -self.transceiver.data_rate)
        self.data_storage.remove_message(msg)
        self.print_string("Finished transmission of msgID towards A{}!"
                          .format(msg.message_id, msg.dst.unique_id))

        self.update_components()

    def update_components(self):
        dt = self.env.now - self.t_prev


        pass

    def set_other_agents(self, others):
        for other in others:
            if other is not self:
                self.other_agents.append(other)

    def print_string(self, string):
        format_string = "A{}-T{}:\t".format(self.unique_id, self.env.now)
        print(format_string + string)
