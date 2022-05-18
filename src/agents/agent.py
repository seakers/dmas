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

            self.planner.completed_action(action)

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
        except simpy.Interrupt:
            # measurement interrupted
            instrument_list = action.instrument_list
            self.turn_off_components(instrument_list)
            self.planner.interrupted_action(action, self.env.now)

    def transmit(self, action):
        msg = action.msg

        msg_timeout = self.env.process(self.env.timeout(msg.timeout))
        msg_transmission = self.env.process(self.transmitter.send_message(self.env, msg))

        # TODO ADD CONTACT TIME RESTRICTIONS TO SEND MESSAGE

        yield msg_timeout | msg_transmission

        if msg_timeout.triggered and not msg_transmission.triggered:
            msg_transmission.interrupt("Message transmission timed out. Dropping packet")
            self.planner.interrupted_message(msg, self.env.now)
        elif msg_transmission.triggered:
            self.planner.message_received(msg, self.env.now)
            if not msg_timeout:
                msg_timeout.interrupt("Message successfully received!")
        return

    def charge(self, action):
        try:
            self.battery.charging = True
            self.env.timeout(action.end - action.start)
            self.battery.charging = False
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
        pass

    # def system_check(self):
    #     while True:
    #         # update components
    #         self.update_components()
    #
    #         # update state
    #         self.state.update(self.component_list, self.env.now)
    #
    #         # check for warnings, break if warning is found
    #         t, power_deficit, power_in, power_out, energy_stored, \
    #         energy_capacity, data_rate, data_stored, data_capacity = self.state.get_last_state()
    #
    #         # POWER CHECK
    #         if power_deficit > 0 and not self.power_storage.charging:
    #             break
    #         elif power_deficit < 0:
    #             break
    #
    #         # DATA CHECK
    #         if data_rate > 0 and data_stored >= data_capacity:
    #             break
    #
    #         # wait for one timestep
    #         yield self.env.timeout(1)

    def set_other_agents(self, others):
        for other in others:
            if other is not self:
                self.other_agents.append(other)

    def print_string(self, string):
        format_string = f"A{self.unique_id}-T{self.env.now}:\t"
        print(format_string + string)
