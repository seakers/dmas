import simpy
from simpy import Environment
from src.network.messages import Message


class Component:
    def __init__(self, env, name, power, energy_stored, energy_capacity,
                 data_rate, data_stored, data_capacity, status=False):
        self.name = name
        self.status = status
        self.health = True

        self.power = power
        if data_capacity > 0:
            self.energy_stored = simpy.Container(env, energy_capacity, energy_stored)
        self.energy_capacity = energy_capacity

        self.data_rate = data_rate
        if energy_capacity > 0:
            self.data_stored = simpy.Container(env, data_capacity, data_stored)
        self.data_capacity = data_capacity

    def is_on(self):
        return self.status

    def turn_on(self):
        if self.health:
            self.status = True
        else:
            self.status = False

    def turn_off(self):
        self.status = False


class OnBoardComputer(Component):
    def __init__(self, env, power, memory_size):
        super().__init__(env=env, name='memory', power=-power, energy_stored=0,
                         energy_capacity=0, data_rate=0, data_stored=0,
                         data_capacity=memory_size, status=True)


class Transmitter(Component):
    def __init__(self, env, power, max_data_rate, buffer_size, num_channels=1):
        super().__init__(env=env, name='transmitter', power=-power, energy_stored=0, energy_capacity=0,
                         data_rate=0, data_stored=0, data_capacity=buffer_size,
                         status=False)
        self.max_data_rate = max_data_rate
        self.num_channels = num_channels
        self.channels = simpy.Resource(env, num_channels)

    def send_message(self, env: Environment, msg: Message):
        '''
        This function attempts to send a message to the destination specified in the message.
        It waits for the transmitter to have enough room in its buffer to move message from
        the agent's on-board computer to the transmitter. It then requests a transmission and
        reception channel and waits until they are granted. The function then finally waits for
        the receiver's buffer to become available to start the transmission.
        :param env: Environment being used
        :param msg: Message being sent
        :return:
        '''
        dst = msg.dst
        receiver = dst.receiver

        if msg.data_rate > self.max_data_rate:
            # The message being sent requests a data-rate higher than the maximum available
            # for this transmitter. Dropping packet.
            return

        try:
            # request transmitter to allocate outgoing message into its buffer
            yield self.data_stored.put(msg.size)
        except simpy.Interrupt:
            return

        transmission_channel_established = False
        reception_channel_established = False
        channels_established = False
        transmission_started = False
        try:
            # request transmission and reception channels
            req_trs = self.channels.request()
            req_rcr = receiver.channels.request()

            yield req_trs
            transmission_channel_established = True
            yield req_rcr
            reception_channel_established = True

            channels_established = True

            # request receiver to allocate outgoing message into its buffer
            yield receiver.data_stored.put(msg.size)

            # starting transmission
            transmission_started = True

            msg.start_time = env.now
            receiver.inbox.put(msg)
            self.turn_on()

            if self.is_on():
                self.data_rate += msg.data_rate
                yield env.timeout(msg.size / msg.data_rate - (env.now - msg.start_time))
            else:
                # Transmitter is not on after being told to do so. Must be faulty. Dropping packet
                yield self.data_stored.get(msg.size)

            # end transmission
            self.channels.release(req_trs)
            receiver.channels.release(req_rcr)
            self.data_rate -= msg.data_rate
            if self.channels.count == 0:
                self.turn_off()

        except simpy.Interrupt:
            if not channels_established and not transmission_started:
                # transmission interrupted during channel request
                if transmission_channel_established:
                    self.channels.release(req_trs)
                if reception_channel_established:
                    receiver.channels.release(req_rcr)
                self.data_stored.get(msg.size)
                return
            elif channels_established and not transmission_started:
                # transmission interrupted while waiting for receiver buffer allocation
                self.channels.release(req_trs)
                receiver.channels.release(req_rcr)
                self.data_stored.get(msg.size)
                return
            else:
                # transmission interrupted while broadcasting

                # release channels used
                self.channels.release(req_trs)
                receiver.channels.release(req_rcr)

                # drop packet and turn off transmitter
                self.data_stored.get(msg.size - (env.now - msg.start_time) * msg.data_rate)
                self.data_rate -= msg.data_rate
                if self.channels.count == 0:
                    self.turn_off()
                return
        return


class Receiver(Component):
    def __init__(self, env, power, max_data_rate, buffer_size, num_channels=1):
        super().__init__(env=env, name='receiver', power=-power, energy_stored=0, energy_capacity=0,
                         data_rate=0, data_stored=0, data_capacity=buffer_size,
                         status=False)
        self.max_data_rate = max_data_rate
        self.num_channels = num_channels
        self.channels = simpy.Resource(env, num_channels)
        self.inbox = simpy.Store(env)
        self.received_messages = []

    def receive(self, env, msg, on_board_computer: OnBoardComputer):
        try:
            if self.data_rate + msg.data_rate > self.max_data_rate:
                # The message being received requests a data-rate higher than the maximum
                # available for this transmitter. Dropping packet.
                return

            self.data_rate += msg.data_rate

            yield env.timeout(msg.size / msg.data_rate)

            msg.reception_time = env.now
            self.received_messages.append(msg)

            yield on_board_computer.data_stored.put(msg.size)

            self.received_messages.remove(msg)
            self.data_stored.get(msg.size)

        except simpy.Interrupt:
            self.data_stored.get(msg.size)
            return


class PowerGenerator(Component):
    def __init__(self, env, power_generation):
        super().__init__(env, name='generator', power=power_generation, energy_stored=0,
                         energy_capacity=0, data_rate=0, data_stored=0, data_capacity=0,
                         status=True)


class Battery(Component):
    def __init__(self, env, max_power_generation, energy_capacity):
        super().__init__(env=env, name='battery', power=max_power_generation,
                         energy_stored=energy_capacity, energy_capacity=energy_capacity,
                         data_rate=0, data_stored=0, data_capacity=0, status=False)
        self.charging = False
        self.max_power_generation = max_power_generation

'''
class Transceiver(Component):
    def __init__(self, env, power, data_rate, buffer_size):
        super().__init__(name='transceiver', power=-power, energy_stored=0, energy_capacity=0,
                         data_rate=-data_rate, data_stored=0, data_capacity=0,
                         status=False)
        self.inbox = simpy.Store(env)
        self.mailbox = simpy.Store(env)
        self.packets_rec = 0
        self.packets_drop = 0
        self.packets_sent = 0
        self.buffer = 0
        self.buffer_size = buffer_size
        self.receiving_message = False
        self.sending_message = False
        self.max_data_rate = data_rate


class DataStorage(Component):
    def __init__(self, env, power, data_capacity):
        super().__init__(name='memory', power_generation=-power, energy_stored=0,
                         energy_capacity=0, data_rate=0, data_stored=0,
                         data_capacity=data_capacity, status=True)
        self.mailbox = simpy.Store(env)

    def add_to_data_storage(self, data):
        self.data_stored += data

    def update_data_storage(self, data_rate, dt):
        self.data_stored += data_rate * dt

    def check_data_state(self):
        return self.data_stored <= self.data_capacity
    # def remove_message(self, msg):
    #     self.data_stored -= msg.size


class PowerGenerator(Component):
    def __init__(self, power_generation):
        super().__init__(name='generator', power_generation=power_generation, energy_stored=0, energy_capacity=0,
                         data_rate=0, data_stored=0, data_capacity=0, status=True)


class PowerStorage(Component):
    def __init__(self, power_generation, energy_capacity):
        super().__init__(name='battery', power_generation=power_generation, energy_stored=energy_capacity,
                         energy_capacity=energy_capacity, data_rate=0, data_stored=0,
                         data_capacity=0, status=False)
        self.max_power = power_generation
        self.charging = False

    def update_power_storage(self, power, dt):
        if power > 0 and self.energy_stored < self.energy_capacity:
            self.charging = True
            self.energy_stored += power * dt
        elif power > 0 and self.energy_stored >= self.energy_capacity:
            self.charging = False
            self.energy_stored = self.energy_capacity
        elif power <= 0:
            self.charging = False
            self.energy_stored += power * dt

    def add_to_power_storage(self, energy):
        self.energy_stored += energy

    def check_power_state(self):
        return self.energy_stored <= self.energy_capacity

class AttitudeController(Component):
    def __init__(self, power, omega):
        super().__init__(name='adcs', power_generation=-power, energy_stored=0, energy_capacity=0,
                         data_rate=0, data_stored=0, data_capacity=0, status=False)
        self.omega = omega
'''
