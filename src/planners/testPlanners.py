from src.agents.components.components import *
from src.agents.components.instruments import Instrument
from src.agents.state import State
from src.planners.planner import Planner
from src.planners.actions import *


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
            elif type(component) == PowerGenerator:
                self.power_generator = component
            elif type(component) == Battery:
                self.battery = component
            elif type(component) == Instrument:
                self.instrument = component

    def update(self, state, t):
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

            elif self.scenario == 3:
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

            elif self.scenario == 4:
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
                    message = TransmitAction(state.parent_agent, other_agent, t_start, 4,
                                             state.parent_agent.transmitter.max_data_rate, 10)

                    actuate_on_prc = self.env.process(self.schedule_action(actuate_on, state, t))
                    message_prc = self.env.process(self.schedule_action(message, state, t))

                    self.plan[actuate_on] = actuate_on_prc
                    self.plan[message] = message_prc

            else:
                raise ImportError(f'Testing scenario number {self.scenario} not yet supported.')

        if state.is_critical():
            if state.power_tot < 0:
                # power deficiency detected
                power_on = None
                if self.power_generator.power < self.power_generator.max_power_generation:
                    # if power generator is not up to its maximum power generation, turn on and provide power
                    power_on = ActuatePowerComponentAction(self.power_generator, t, -state.power_tot+self.power_generator.power)
                elif self.battery.power < self.battery.max_power_generation:
                    # else if battery is not up to its maximum power generation, turn on and provide power
                    power_on = ActuatePowerComponentAction(self.battery, t, -state.power_tot+self.battery.power)

                if power_on is not None:
                    power_on_prc = self.env.process(self.schedule_action(power_on, state, t))
                    self.plan[power_on] = power_on_prc

            elif state.power_tot > 0:
                # power surplus
                power_off = None
                if (self.battery.energy_stored.level/self.battery.energy_capacity < 0.70
                        and self.battery.power < state.power_tot and not self.battery.is_charging()):
                    # if battery not up to capacity, charge batteries
                    start = t
                    dt = (self.battery.energy_capacity - self.battery.energy_stored.level)/(state.power_tot - self.battery.power)
                    # dt = 3
                    end = start + dt

                    power_off = ChargeAction(start, end)

                elif self.battery.power > 0:
                    # else lower battery power output
                    power = self.battery.power - state.power_tot
                    power_off = ActuatePowerComponentAction(self.battery, t, power)

                elif self.power_generator.power > 0:
                    # else if batteries are off, lower power generator output
                    power = self.power_generator.power - state.power_tot
                    power_off = ActuatePowerComponentAction(self.power_generator, t, power)

                if power_off is not None:
                    power_off_prc = self.env.process(self.schedule_action(power_off, state, t))
                    self.plan[power_off] = power_off_prc

            # if len(self.plan) == 0:
            #     kill = ActuateAgentAction(t, status=False)
            #     kill_prc = self.env.process(self.schedule_action(kill, state, t))
            #     self.plan[kill] = kill_prc
        return

    def interrupted_action(self, action: Action, state: State, t):
        super().interrupted_action(action, state, t)
        if type(action) == MeasurementAction or type(action) == TransmitAction:
            action_prc = self.env.process(self.schedule_action(action, state, t))
            self.plan[action] = action_prc

    def completed_action(self, action: Action, state: State, t):
        super().completed_action(action, state, t)
        # if type(action) == TransmitAction:
        #     msg = action.msg
        #     delete_msg = DeleteMessageAction(msg, t)
        #     delete_msg_prc = self.env.process(self.schedule_action(delete_msg, state, t))
        #     self.plan[delete_msg] = delete_msg_prc

