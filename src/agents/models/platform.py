import numpy as np

from src.agents.components.components import *


class Platform:
    def __init__(self, parent_agent, env, component_list):
        self.parent_agent = parent_agent
        self.env = env

        # component status
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
            elif type(component) == PowerGenerator or type(component) == SolarPanelArray:
                self.power_generator = component
            elif type(component) == Battery:
                self.battery = component

        if (self.transmitter is None or self.receiver is None or self.on_board_computer is None
                or self.power_generator is None or self.battery is None):
            raise Exception('Agent requires at least one of each of the following components:'
                            ' transmitter, receiver, on-board computer, power generator, and battery')

        # orbital information
        self.pos = [-1, -1, -1]
        self.vel = [-1, -1, -1]
        self.eclipse = False

        # events
        self.action_event = simpy.Event(env)
        self.t_prev = self.env.now

    def sim(self):
        critical_state_event = self.env.process(self.wait_for_critical_state())
        eclipse_event = self.env.process(self.wait_for_eclipse_event())
        periodic_update = self.env.process(self.periodic_update())

        while True:
            yield critical_state_event | eclipse_event | self.action_event | periodic_update
            # update component status
            t_curr = self.env.now
            self.update(t_curr)
            print(f'System updated at T{t_curr}')

            # update component capabilities
            if type(self.power_generator) == SolarPanelArray:
                if self.eclipse:
                    self.power_generator.in_eclipse = True

                    if self.power_generator.is_on():
                        self.power_generator.turn_off_generator()
                else:
                    self.power_generator.in_eclipse = False

            if (1 - self.battery.energy_stored.level/self.battery.energy_capacity) >= self.battery.dod:
                self.battery.can_hold_charge = False
                if self.battery.is_charging:
                    self.battery.turn_off_charge()

            # reset parallel processes as needed
            if not critical_state_event.triggered:
                critical_state_event.interrupt()
                yield critical_state_event
            # else:
                # self.parent_agent.critical_state.succeed()
            critical_state_event = self.env.process(self.wait_for_critical_state())

            if not eclipse_event.triggered:
                eclipse_event.interrupt()
                yield eclipse_event
            eclipse_event = self.env.process(self.wait_for_eclipse_event())

            if self.action_event.triggered:
                self.action_event = simpy.Event(self.env)

    def periodic_update(self):
        while True:
            yield self.env.timeout(1)
            # update component status
            t_curr = self.env.now
            self.update(t_curr)
            print(f'System updated at T{t_curr}')

    def update(self, t):
        dt = t - self.t_prev

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
                if type(component) == Battery or type(component) == PowerGenerator:
                    power_in += component.power
        power_tot = power_in - power_out

        # update values
        # -data
        if data_rate_in * dt > 0:
            dD = self.on_board_computer.data_capacity - self.on_board_computer.data_stored.level
            if dD > data_rate_in * dt:
                self.on_board_computer.data_stored.put(data_rate_in * dt)
            else:
                self.on_board_computer.data_stored.put(dD)

        if (self.transmitter.data_rate * dt > 0
                and self.transmitter.data_stored.level > 0
                and self.transmitter.is_transmitting()):
            if self.transmitter.data_stored.level >= self.transmitter.data_rate * dt:
                self.transmitter.data_stored.get(self.transmitter.data_rate * dt)
            else:
                self.transmitter.data_stored.get(self.transmitter.data_stored.level)

        # -power
        power_charging = 0
        if self.battery.is_charging() and power_tot >= 0:
            power_charging += power_tot
        if self.battery.is_on():
            power_charging -= self.battery.power

        if power_charging * dt > 0:
            self.battery.energy_stored.put(power_charging * dt)
        elif power_charging * dt < 0:
            self.battery.energy_stored.get(-power_charging * dt)

        # -orbital information
        self.eclipse = self.env.is_eclipse(self.parent_agent, t)
        self.pos = self.env.get_position(self.parent_agent, t)
        self.vel = self.env.get_velocity(self.parent_agent, t)

        self.t_prev = t
        return

    def wait_for_critical_state(self):
        """
        Predicts next critical state and waits for it to arrive.
        Critical states include charging while battery is full and not being used, battery charge dropping below the
        accepted depth of discharge, data coming in with a full memory that is not being depleted, and empty memory
        being depleted.
        """
        dt_min = np.Infinity

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
                if type(component) == Battery or type(component) == PowerGenerator:
                    power_in += component.power
        power_tot = power_in - power_out

        # check when battery will reach full charge
        if self.battery.is_charging():
            dx = self.battery.energy_capacity - self.battery.energy_stored.level
            dxdt = power_tot - self.battery.power
            if dxdt > 0:
                dt = dx / dxdt
                if dt < dt_min:
                    dt_min = dt

        # check when battery will go below DOD
        if self.battery.is_on():
            dx = self.battery.energy_capacity * (
                    1 - self.battery.dod) - self.battery.energy_stored.level
            dxdt = power_tot - self.battery.power
            dt = dx / dxdt
            if dt > 0:
                if dt < dt_min:
                    dt_min = dt

        # check when memory will fill up
        dx = self.on_board_computer.data_capacity - self.on_board_computer.data_stored.level
        dxdt = data_rate_in + self.receiver.data_rate - self.transmitter.data_rate
        if dxdt > 0:
            dt = dx / dxdt
            if dt < dt_min:
                dt_min = dt

        # check when memory will empty
        dx = -self.on_board_computer.data_stored.level
        dxdt = data_rate_in + self.receiver.data_rate - self.transmitter.data_rate
        if dxdt < 0:
            dt = dx / dxdt
            if dt < dt_min:
                dt_min = dt

        try:
            yield self.env.timeout(dt_min)
        except simpy.Interrupt as i:
            return


    def wait_for_eclipse_event(self):
        """
        Predicts next eclipse event and waits for it to arrive.
        :return:
        """
        t = self.env.now
        t_eclipse = self.env.orbit_data[self.parent_agent].get_next_eclipse(t)

        dt = t_eclipse - t

        try:
            yield self.env.timeout(dt)
        except simpy.Interrupt as i:
            return