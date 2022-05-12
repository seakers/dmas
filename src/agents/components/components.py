import simpy


class Component:
    def __init__(self, power_generation, energy_stored, energy_capacity,
                 data_rate, data_stored, data_capacity, status=False):
        self.status = status
        self.health = True

        self.power_generation = power_generation
        self.energy_stored = energy_stored
        self.energy_capacity = energy_capacity

        self.data_rate = data_rate
        self.data_stored = data_stored
        self.data_capacity = data_capacity

    def turn_on(self):
        if self.health:
            self.status = True
        else:
            self.status = False

    def turn_off(self):
        self.status = False

    def add_to_power_storage(self, energy):
        self.energy_stored += energy

    def add_to_data_storage(self, data):
        self.data_stored += data

    def update_power_storage(self, power, dt):
        self.energy_stored += power * dt

    def update_data_storage(self, data_rate, dt):
        self.data_stored += data_rate * dt

    def check_power_state(self):
        return self.energy_stored <= self.energy_capacity

    def check_data_state(self):
        return self.data_stored <= self.data_capacity


class Transceiver(Component):
    def __init__(self, env, power, data_rate, buffer_size):
        super().__init__(power_generation=-power, energy_stored=0, energy_capacity=0,
                         data_rate=-data_rate, data_stored=0, data_capacity=0,
                         status=False)
        self.inbox = simpy.Store(env)
        self.mailbox = simpy.Store(env)
        self.packets_rec = 0
        self.packets_drop = 0
        self.packets_sent = 0
        self.buffer = 0
        self.buffer_size = buffer_size
        self.receiving_message = 0


class DataStorage(Component):
    def __init__(self, env, power, data_capacity):
        super().__init__(power_generation=-power, energy_stored=0, energy_capacity=0,
                         data_rate=0, data_stored=0, data_capacity=data_capacity,
                         status=True)
        self.mailbox = simpy.Store(env)

    def remove_message(self, msg):
        self.data_stored -= msg.size


class PowerGenerator(Component):
    def __init__(self, power_generation):
        super().__init__(power_generation=power_generation, energy_stored=0, energy_capacity=0,
                         data_rate=0, data_stored=0, data_capacity=0, status=True)


class PowerStorage(Component):
    def __init__(self, power_generation, energy_capacity):
        super().__init__(power_generation=power_generation, energy_stored=energy_capacity,
                         energy_capacity=energy_capacity, data_rate=0, data_stored=0,
                         data_capacity=0, status=False)

class AttitudeController(Component):
    def __init__(self, power, omega):
        super().__init__(power_generation=-power, energy_stored=0, energy_capacity=0,
                         data_rate=0, data_stored=0, data_capacity=0, status=False)
        self.omega = omega
