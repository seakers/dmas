from src.agents.components.components import *


class Platform:
    def __init__(self, env, component_list):
        # simulation environment
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
            elif type(component) == PowerGenerator:
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
        self.critical_state_event = simpy.Event(env)
        self.eclipse_start_event = simpy.Event(env)
        self.eclipse_end_event = simpy.Event(env)

    def update(self, prev_state, pos, vel, eclipse, t_curr):
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
        power_dif = power_in - power_out

        # calculate time-step
        dt = t_curr - prev_state.t

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
        if self.battery.is_charging() and power_dif >= 0:
            power_charging += power_dif
        if self.battery.is_on():
            power_charging -= self.battery.power

        if power_charging * dt > 0:
            self.battery.energy_stored.put(power_charging * dt)
        elif power_charging * dt < 0:
            self.battery.energy_stored.get(-power_charging * dt)

        # -orbital information
        for i in range(3):
            self.pos[i] = pos[i]
            self.vel[i] = vel[i]
        self.eclipse = eclipse

        return

    def background_system_check(self):
        yield self.critical_state_event | self.eclipse_start_event | self.eclipse_end_event

        return
