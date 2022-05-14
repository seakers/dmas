from simpy import AllOf

from src.agents.components.components import *
from src.agents.state import State
from src.planners.actions import *


class AbstractAgent:
    def __init__(self, env, unique_id, component_list=None, planner=None):
        self.alive = True

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

        self.state = State(self, component_list, env.now)

    def live(self):
        while self.alive:
            # update planner
            self.planner.update(self.state, self.env.now)

            # perform actions from planner
            actions = self.planner.get_plan(self.env.now)
            events, maintenance = self.actions_to_events(actions)
            listening = self.env.process(self.listening())
            system_check = self.env.process(self.system_check())

            # -perform maintenance tasks first
            if len(maintenance) > 0:
                yield AllOf(self.env, maintenance)

            # -performs other actions while listening for incoming
            #  messages and performing system checks
            if len(events) > 0:
                yield AllOf(self.env, events) | listening | system_check
            else:
                yield listening | system_check

            # -interrupt all actions being performed in case a message
            #  is received or a critical system state is detected
            if listening.triggered or system_check.triggered:
                for event in events:
                    if not event.triggered:
                        if listening.triggered:
                            event.interrupt("New message received! Reevaluating plan...")
                        elif system_check.triggered:
                            event.interrupt("WARING - Critical system state reached! Reevaluating plan...")

    def actions_to_events(self, actions):
        events = []
        maintenance = []
        for action in actions:
            action_event = None
            mnt_event = None
            if type(action) == TransmitAction:
                action_event = self.env.process(self.transmit(action))
            elif type(action) == ActuateComponentAction:
                mnt_event = self.env.process(self.actuate_component(action))
            elif type(action) == ActuateAgentAction:
                mnt_event = self.env.process(self.actuate_agent(action))
            elif type(action) == ChargeAction:
                action_event = self.env.process(self.charge(action))

            if action_event is not None:
                events.append(action_event)
            if mnt_event is not None:
                maintenance.append(mnt_event)

        return events, maintenance

    def charge(self, action):
        try:
            self.power_storage.charging = True
            start = action.start
            end = action.end
            self.env.timeout(end - start)
            self.power_storage.charging = False
        except simpy.Interrupt as inter:
            self.power_storage.charging = False

    def actuate_agent(self, action):
        status = action.status
        self.alive = status

    def actuate_component(self, action):
        # actuate component described in action
        component_actuate = action.component
        status = action.status

        for component in self.component_list:
            if component == component_actuate:
                component.status = status
                break

        # update component status
        self.update_components()

        # update state
        self.state.update(self.component_list, self.env.now)

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

    def transmit(self, action):
        other = action.dst
        msg = action.msg

        self.print_string("Starting transmission of msg {} towards A{}..."
                          .format(msg.message_id, msg.dst.unique_id))
        other.put_message_in_inbox(msg)
        self.transceiver.sending_message = True
        yield self.env.timeout(msg.size / -self.transceiver.data_rate)
        # self.data_storage.remove_message(msg)

        self.transceiver.sending_message = False
        self.print_string("Finished transmission of msgID towards A{}!"
                          .format(msg.message_id, msg.dst.unique_id))

        self.update_components()

    def listening(self):
        self.print_string("Listening for messages...")
        msg = (yield self.transceiver.inbox.get())
        self.transceiver.receiving_message = True

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
        self.transceiver.receiving_message = False

    def system_check(self):
        while True:
            # update components
            self.update_components()

            # update state
            self.state.update(self.component_list, self.env.now)

            # check for warnings, break if warning is found
            t, power_deficit, power_in, power_out, energy_stored, \
            energy_capacity, data_rate, data_stored, data_capacity = self.state.get_last_state()

            # POWER CHECK
            if power_deficit > 0 and not self.power_storage.charging:
                break
            elif power_deficit < 0:
                break

            # DATA CHECK
            if data_rate > 0 and data_stored >= data_capacity:
                break

            # wait for one timestep
            yield self.env.timeout(1)

    def update_components(self):
        t, power_deficit, power_in, power_out, energy_stored, \
        energy_capacity, data_rate, data_stored, data_capacity = self.state.get_last_state()

        dt = self.env.now - t

        if self.power_storage.is_on(): # battery is on, it is consuming power
            if self.power_storage.charging:
                pass
            else:

        else:
            if self.power_storage.charging:
                pass
            else:
                pass

        self.data_storage.update_data_storate(data_rate, dt)

    def set_other_agents(self, others):
        for other in others:
            if other is not self:
                self.other_agents.append(other)

    def print_string(self, string):
        format_string = "A{}-T{}:\t".format(self.unique_id, self.env.now)
        print(format_string + string)
