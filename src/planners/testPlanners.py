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
        if self.scenario <= 2:
            if t == 0 and len(self.plan) == 0:
                measurement = MeasurementAction([self.instrument], None, 1, 8.5)
                measurement_prc = self.env.process(self.schedule_action(measurement, state, t))
                self.plan.append(measurement_prc)

                # kill = ActuateAgentAction(10.0)
                # kill_prc = self.env.process(self.schedule_action(measurement_prc, state, t))
                # self.plan.append(kill_prc)
        elif self.scenario <= 3:
            if t == 0 and len(self.plan) == 0:
                pass
        else:
            raise ImportError(f'Power Unit Testing scenario number {self.scenario} not yet supported.')

        if state.is_critical():
            data_rate_in, data_rate_out, data_rate_tot, \
            data_buffer_in, data_buffer_out, data_memory, data_capacity, \
            power_in, power_out, power_tot, energy_stored, energy_capacity, \
            t_0, critical, isOn = state.get_latest_state()

            if power_tot < 0:
                # power deficiency detected
                power_on = None
                if self.power_generator.power < self.power_generator.max_power_generation:
                    # if power generator is not up to its maximum power generation, turn on and provide power
                    power_on = ActuatePowerComponentAction(self.power_generator, t, -power_tot+self.power_generator.power)
                elif self.battery.power < self.battery.max_power_generation:
                    # else if battery is not up to its maximum power generation, turn on and provide power
                    power_on = ActuatePowerComponentAction(self.battery, t, -power_tot+self.battery.power)

                if power_on is not None:
                    power_on_prc = self.env.process(self.schedule_action(power_on, state, t))
                    self.plan.append(power_on_prc)

            elif power_tot > 0:
                # power surplus
                power_off = None
                if (self.battery.energy_stored.level < self.battery.energy_capacity
                        and self.battery.power < power_tot):
                    # if battery not up to capacity, charge batteries
                    start = t
                    dt = (self.battery.energy_capacity - self.battery.energy_stored.level)/(power_tot - self.battery.power)
                    end = start + dt

                    power_off = ChargeAction(start, end)

                elif self.battery.power > 0:
                    # else lower battery power output
                    power = self.battery.power - power_tot
                    power_off = ActuatePowerComponentAction(self.battery, t, power)

                elif self.power_generator.power > 0:
                    # else if batteries are off, lower power generator output
                    power = self.power_generator.power - power_tot
                    power_off = ActuatePowerComponentAction(self.power_generator, t, power)

                if power_off is not None:
                    power_off_prc = self.env.process(self.schedule_action(power_off, state, t))
                    self.plan.append(power_off_prc)
        return

    def interrupted_action(self, action: Action, state: State, t):
        action_prc = self.env.process(self.schedule_action(action, state, t))
        self.plan.append(action_prc)
