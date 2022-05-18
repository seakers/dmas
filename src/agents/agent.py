from simpy import AllOf, AnyOf

from src.agents.components.components import *
from src.agents.state import State
from src.planners.actions import *
from src.planners.planner import Planner


class AbstractAgent:
    def __init__(self, env, unique_id, component_list=None, planner: Planner = None):
        self.alive = True

        self.env = env
        self.unique_id = unique_id
        self.other_agents = []
        self.component_list = component_list

        self.transmitter = None
        self.receiver = None
        self.on_board_computer = None
        self.power_generator = None
        self.battery = None
        for component in component_list:
            if type(component) == Transmitter:
                self.transmitter = component
            if type(component) == Receiver:
                self.receiver = component
            elif type(component) == OnBoardComputer:
                self.on_board_computer = component
            elif type(component) == PowerGenerator:
                self.power_generator = component
            elif type(component) == Battery:
                self.battery = component

        self.planner = planner

        self.state = State(self, component_list, env.now)

    def live(self, env):
        while self.alive:
            # update planner
            self.planner.update(self.state, env.now)
            plan = self.planner.update(self.state, self)

            # perform actions from planner
            tasks, maintenance_actions = self.plan_to_events(plan)
            listening = self.env.process(self.listening())
            system_check = self.env.process(self.system_check())

            # -perform maintenance actions first
            self.perform_maintenance_actions(maintenance_actions)

            # -check if agent is still alive after maintenance actions
            if not self.alive:
                break

            # -performs other actions while listening for incoming
            #  messages and performing system checks
            if len(tasks) > 0:
                yield AllOf(self.env, tasks) | listening | system_check
            else:
                yield listening | system_check

            # -interrupt all actions being performed in case a message
            #  is received or a critical system state is detected
            if listening.triggered or system_check.triggered:
                for task in tasks:
                    if not task.triggered:
                        if listening.triggered:
                            task.interrupt("New message received! Reevaluating plan...")
                        elif system_check.triggered:
                            task.interrupt("WARING - Critical system state reached! Reevaluating plan...")
            if listening.triggered and not system_check.triggered:
                system_check.interrupt("New message received! Reevaluating plan...")
            elif not listening.triggered and system_check.triggered:
                listening.interrupt("WARING - Critical system state reached! Reevaluating plan...")
            elif not listening.triggered and not system_check.triggered:
                system_check.interrupt("Completed all planner tasks! Updating plan...")
                listening.interrupt("Completed all planner tasks! Updating plan...")

    def plan_to_events(self, actions):
        events = []
        maintenance = []
        for action in actions:
            action_event = None
            mnt_event = None
            if type(action) == ActuateAgentAction:
                mnt_event = action
            elif type(action) == ActuateComponentAction:
                mnt_event = action
            elif type(action) == DeleteMessageAction:
                mnt_event = action

            elif type(action) == MeasurementAction:
                action_event = self.env.process(self.measure(action))
            elif type(action) == TransmitAction:
                action_event = self.env.process(self.transmit(action))
            elif type(action) == ChargeAction:
                action_event = self.env.process(self.charge(action))

            if action_event is not None:
                events.append(action_event)
            if mnt_event is not None:
                maintenance.append(mnt_event)

        return events, maintenance

    '''
    ==========MAINTENANCE ACTIONS==========
    '''

    def perform_maintenance_actions(self, actions):
        for action in actions:
            if type(action) == ActuateAgentAction:
                self.actuate_agent(action)
            elif type(action) == ActuateComponentAction:
                self.actuate_component(action)
            elif type(action) == DeleteMessageAction:
                self.delete_msg(action)
            else:
                raise Exception(f"Maintenance task of type {type(action)} not yet supported.")

            self.planner.completed_action(action, self.env.now)

    def actuate_agent(self, action):
        # turn agent on or off
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

    def delete_msg(self, action):
        # remove message from on-board memory and inform planner
        msg = action.msg
        self.on_board_computer.data_stored.get(msg.size)
        self.planner.message_deleted(msg)

    def turn_on_components(self, component_list):
        for component_i in component_list:
            for component_j in self.component_list:
                if component_i == component_j:
                    component_j.turn_on()
                    break

    def turn_off_components(self, component_list):
        for component_i in component_list:
            for component_j in self.component_list:
                if component_i == component_j:
                    component_j.turn_off()
                    break

    '''
    ==========TASK ACTIONS==========
    '''

    def measure(self, action: MeasurementAction):
        try:
            # un package measurement information
            instrument_list = action.instrument_list
            target = action.target

            # turn on components, collect information, and turn off components
            self.turn_on_components(instrument_list)
            yield self.env.timeout(action.end - action.start)
            self.turn_off_components(instrument_list)

            # process captured data
            # TODO ADD MEASUREMENT RESULTS TO PLANNER KNOWLEDGE BASE:
            #   results = measurementSimulator(target, instrument_list)
            #   planner.update_knowledge_base(measurement_results=results)

            # inform planner of task completion
            self.planner.completed_action(action, self.env.now)

            # update system status
            return self.update_system()
        except simpy.Interrupt:
            # measurement interrupted
            instrument_list = action.instrument_list
            self.turn_off_components(instrument_list)
            self.planner.interrupted_action(action, self.env.now)

    def transmit(self, action):
        msg = action.msg

        msg_timeout = self.env.process(self.env.timeout(msg.timeout))
        msg_transmission = self.env.process(self.transmitter.send_message(self.env, msg))

        # TODO ADD CONTACT-TIME RESTRICTIONS TO SEND MESSAGE
        #   wait_for_access = env.timeout(self.orbit_data.next_access(msg.dst) - self.env.now)
        #   yield wait_for_access | timeout
        #   only continue if wait is done but not timeout

        yield msg_timeout | msg_transmission

        if msg_timeout.triggered and not msg_transmission.triggered:
            msg_transmission.interrupt("Message transmission timed out. Dropping packet")
            self.planner.interrupted_message(msg, self.env.now)
        elif msg_transmission.triggered:
            self.planner.message_received(msg, self.env.now)
            if not msg_timeout:
                msg_timeout.interrupt("Message successfully received!")

        # integrate current state
        return self.update_system()

    def charge(self, action):
        try:
            self.battery.charging = True
            self.env.timeout(action.end - action.start)
            self.battery.charging = False

            # integrate current state
            return self.update_system()
        except simpy.Interrupt:
            self.battery.charging = False
            self.planner.interrupted_action(action, self.env.now)

    '''
    ==========BACKGROUND ACTIONS==========
    '''

    def listening(self):
        if len(self.transmitter.received_messages) > 0:
            msg = self.transmitter.received_messages.pop()
        else:
            msg = (yield self.receiver.inbox.get())

        msg_timeout = self.env.process(self.env.timeout(msg.timeout))
        msg_reception = self.env.process(self.receiver.receive(self.env, msg, self.on_board_computer))

        yield msg_timeout | msg_reception

        if msg_timeout.triggered and not msg_reception.triggered:
            msg_reception.interrupt("Message reception timed out. Dropping packet")
        if msg_reception.triggered:
            self.planner.measurement_received(msg)
            if not msg_timeout.triggered:
                msg_timeout.interrupt("Message successfully received!")

        return

    def system_check(self):
        while True:
            # check if system state is critical
            if self.is_in_critical_state():
                if self.state.is_critical():
                    # if state is still critical after planner changes, kill agent
                    kill = ActuateAgentAction(self.env.now, status=False)
                    self.actuate_agent(kill)
                else:
                    self.state.critical = True
                break
            else:
                self.state.critical = False

            # wait 1 second and continue
            yield self.env.timeout(1)

            # integrate current state at new time
            self.update_system()

    def update_system(self):
        # count power and data usage
        data_rate_in = 0
        power_out = 0
        power_in = 0
        for component in self.component_list:
            if component.is_on():
                if component.power <= 0:
                    power_out -= component.power
                if type(component) != Receiver and type(component) != Transmitter:
                    data_rate_in += component.data_rate
                if type(component) == Receiver and type(component) == Transmitter:
                    power_in += component.power
        power_dif = power_in - power_out

        # calculate time-step
        dt = self.env.now - self.state.get_last_update_time()

        # update values
        # -data
        yield self.on_board_computer.data_stored.put(data_rate_in * dt)
        yield self.transmitter.data_stored.get(self.transmitter.data_rate * dt)

        # -power
        power_charging = 0
        if self.battery.is_charging() and power_dif >= 0:
            power_charging += power_dif
        if self.battery.is_on():
            power_charging -= self.battery.power
        self.battery.energy_stored.put(power_charging * dt)

        # update in state tracking
        self.state.update(self, self.component_list, self.env.now)

    def is_in_critical_state(self):
        data_rate_in, data_rate_out, data_rate_tot, \
        data_buffer_in, data_buffer_out, data_memory, data_capacity, \
        power_in, power_out, power_tot, energy_stored, energy_capacity, \
        t, critical = self.state.get_latest_state()

        if (1 - self.battery.energy_stored.level / self.battery.energy_capacity) > self.battery.dod:
            # battery has reached its maximum depth-of-discharge level
            return True
        elif self.battery.energy_stored.level == self.battery.energy_capacity and self.battery.is_on():
            # battery is full and is still charging
            return True
        elif power_tot < 0:
            # insufficient power being generated
            return True
        elif power_tot > 0 and not self.battery.is_on():
            # excess power being generated and not being used for charging
            return True
        elif self.on_board_computer.data_stored.level == self.on_board_computer.data_capacity and data_rate_in > 0:
            # on-board memory full and data is coming in faster than it is leaving
            return True

        return False

    def set_other_agents(self, others):
        for other in others:
            if other is not self:
                self.other_agents.append(other)

    def print_string(self, string):
        format_string = f"A{self.unique_id}-T{self.env.now}:\t"
        print(format_string + string)
