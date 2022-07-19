from dmas.agents.components.components import *
from dmas.agents.components.instruments import Instrument
from dmas.agents.state import State
from dmas.planners.planner import Planner
from dmas.planners.actions import *


class PowerTracking(Planner):
    def __init__(self, env, unique_id, component_list, scenario=1):
        super().__init__(env)
        self.unique_id = unique_id
        self.component_list = []
        self.scenario = scenario

        for component in component_list:
            self.component_list.append(component)
            if type(component) == Transmitter:
                self.transmitter = component
            if type(component) == Receiver:
                self.receiver = component
            elif type(component) == OnBoardComputer:
                self.on_board_computer = component
            elif type(component) == PowerGenerator or type(component) == SolarPanelArray:
                self.power_generator = component
            elif type(component) == Battery:
                self.battery = component
            elif type(component) == Instrument:
                self.instrument = component

    def update(self, state, t):
        super().update(state, t)

        if t == 0 and len(self.plan) == 0:
            if 1 <= self.scenario <= 2:
                t_start = 1
                t_end = 8.5
                actuate_on = ActuateComponentAction(self.instrument, t_start, status=True)
                actuate_off = ActuateComponentAction(self.instrument, t_end, status=False)
                measurement = MeasurementAction([self.instrument], None, t_start, t_end)

                actuate_on_prc = self.env.process(self.schedule_action(actuate_on, state, t))
                actuate_off_prc = self.env.process(self.schedule_action(actuate_off, state, t))
                measurement_prc = self.env.process(self.schedule_action(measurement, state, t))

                self.plan[actuate_on] = actuate_on_prc
                self.plan[actuate_off] = actuate_off_prc
                self.plan[measurement] = measurement_prc

            elif self.scenario <= 3:
                power_on = ActuatePowerComponentAction(self.power_generator, 1, self.power_generator.max_power_generation)
                power_on_prc = self.env.process(self.schedule_action(power_on, state, t))
                self.plan[power_on] = power_on_prc

                t_start = 8.5
                t_end = t_start + 5
                actuate_on = ActuateComponentAction(self.instrument, t_start, status=True)
                actuate_off = ActuateComponentAction(self.instrument, t_end, status=False)
                measurement = MeasurementAction([self.instrument], None, t_start, t_end)

                actuate_on_prc = self.env.process(self.schedule_action(actuate_on, state, t))
                actuate_off_prc = self.env.process(self.schedule_action(actuate_off, state, t))
                measurement_prc = self.env.process(self.schedule_action(measurement, state, t))

                self.plan[actuate_on] = actuate_on_prc
                self.plan[actuate_off] = actuate_off_prc
                self.plan[measurement] = measurement_prc

            elif self.scenario <= 4:
                if state.parent_agent.unique_id == 0:
                    t_start = 1
                    t_end = 5
                    actuate_on = ActuateComponentAction(self.instrument, t_start, status=True)
                    actuate_off = ActuateComponentAction(self.instrument, t_end, status=False)
                    measurement = MeasurementAction([self.instrument], None, t_start, t_end)

                    actuate_on_prc = self.env.process(self.schedule_action(actuate_on, state, t))
                    actuate_off_prc = self.env.process(self.schedule_action(actuate_off, state, t))
                    measurement_prc = self.env.process(self.schedule_action(measurement, state, t))

                    self.plan[actuate_on] = actuate_on_prc
                    self.plan[actuate_off] = actuate_off_prc
                    self.plan[measurement] = measurement_prc

                    t_start = 6
                    other_agent = state.parent_agent.other_agents[0]

                    actuate_on = ActuateComponentAction(self.transmitter, t_start, status=True)
                    transmit = TransmitAction(state.parent_agent, other_agent, t_start, 4, 1, 10)

                    actuate_on_prc = self.env.process(self.schedule_action(actuate_on, state, t))
                    transmit_prc = self.env.process(self.schedule_action(transmit, state, t))

                    self.plan[actuate_on] = actuate_on_prc
                    self.plan[transmit] = transmit_prc
            elif self.scenario <= 7.5:
                if state.parent_agent.unique_id == 0 or state.parent_agent.unique_id == 1:
                    t_start = 1
                    t_end = 5
                    actuate_on = ActuateComponentAction(self.instrument, t_start, status=True)
                    actuate_off = ActuateComponentAction(self.instrument, t_end, status=False)
                    measurement = MeasurementAction([self.instrument], None, t_start, t_end)

                    actuate_on_prc = self.env.process(self.schedule_action(actuate_on, state, t))
                    actuate_off_prc = self.env.process(self.schedule_action(actuate_off, state, t))
                    measurement_prc = self.env.process(self.schedule_action(measurement, state, t))

                    self.plan[actuate_on] = actuate_on_prc
                    self.plan[actuate_off] = actuate_off_prc
                    self.plan[measurement] = measurement_prc

                    t_start = 6

                    other_agent = None
                    for agent in state.parent_agent.other_agents:
                        if agent.unique_id == 2:
                            other_agent = agent
                            break

                    transmit = None
                    actuate_on = ActuateComponentAction(self.transmitter, t_start, status=True)
                    if self.scenario <= 5:
                        transmit = TransmitAction(state.parent_agent, other_agent, t_start, 4, 1, 10)
                    elif self.scenario <= 5.5:
                        transmit = TransmitAction(state.parent_agent, other_agent, t_start, 4, 1, 4)
                    elif self.scenario <= 6:
                        transmit = TransmitAction(state.parent_agent, other_agent, t_start, 4, 1, 10)
                    elif self.scenario <= 6.5:
                        transmit = TransmitAction(state.parent_agent, other_agent, t_start, 4, 1, 4)
                    elif self.scenario <= 7:
                        transmit = TransmitAction(state.parent_agent, other_agent, t_start, 4, 1, 10)

                    actuate_on_prc = self.env.process(self.schedule_action(actuate_on, state, t))
                    transmit_prc = self.env.process(self.schedule_action(transmit, state, t))

                    self.plan[actuate_on] = actuate_on_prc
                    self.plan[transmit] = transmit_prc
            elif self.scenario <= 8:
            #     turn_on = ActuatePowerComponentAction(self.power_generator, 10.5, 10)
            #     turn_on_prc = self.env.process(self.schedule_action(turn_on, state, t))
            #     self.plan[turn_on] = turn_on_prc
                return
            else:
                raise ImportError(f'Testing scenario number {self.scenario} not yet supported.')
        return

    def interrupted_action(self, action: Action, state: State, t):
        super().interrupted_action(action, state, t)

        if self.safe_mode:
            return

        if type(action) == MeasurementAction:
            action_prc = self.env.process(self.schedule_action(action, state, t))
            self.plan[action] = action_prc
        elif type(action) == TransmitAction:
            msg = action.msg
            if t - msg.timeout_start >= msg.timeout and msg.timeout_start > -1:
                actuate_off = ActuateComponentAction(self.transmitter, t, status=False)
                delete = DeleteMessageAction(action.msg, t)

                actuate_off_prc = self.env.process(self.schedule_action(actuate_off, state, t))
                delete_prc = self.env.process(self.schedule_action(delete, state, t))

                self.plan[actuate_off] = actuate_off_prc
                self.plan[delete] = delete_prc
            else:
                action_prc = self.env.process(self.schedule_action(action, state, t))
                self.plan[action] = action_prc
