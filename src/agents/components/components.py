from logging import Logger

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
        if energy_capacity > 0:
            self.energy_stored = simpy.Container(env, energy_capacity, energy_stored)
        self.energy_capacity = energy_capacity

        self.data_rate = data_rate
        if data_capacity > 0:
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

    def send_message(self, env: Environment, msg: Message, logger: Logger):
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
            logger.debug(f'T{env.now}:\tThe message being sent requests a data-rate higher than '
                         f'the maximum available for this transmitter. Dropping packet.')
            return

        try:
            # request transmitter to allocate outgoing message into its buffer
            logger.debug(f'T{env.now}:\tMoving message from internal memory to outgoing buffer...')
            yield self.data_stored.put(msg.size)
            logger.debug(f'T{env.now}:\tMessage successfully moved to outgoing buffer.')
        except simpy.Interrupt:
            logger.debug(f'T{env.now}:\tCould not move message to outgoing buffer.')
            return

        transmission_channel_established = False
        reception_channel_established = False
        channels_established = False
        transmission_started = False
        try:
            # request transmission and reception channels
            req_trs = self.channels.request()
            req_rcr = receiver.channels.request()

            logger.debug(f'T{env.now}:\tRequesting transmission channel...')
            yield req_trs
            transmission_channel_established = True
            logger.debug(f'T{env.now}:\tTransmission channel obtained! Requesting reception channel...')
            yield req_rcr
            reception_channel_established = True
            logger.debug(f'T{env.now}:\tReception channel obtained! Connection established.')

            channels_established = True

            # request receiver to allocate outgoing message into its buffer
            logger.debug(f'T{env.now}:\tRequesting receiver to allocate message size in buffer...')
            yield receiver.data_stored.put(msg.size)
            logger.debug(f'T{env.now}:\tBuffer memory allocated! Starting transmission...')

            # starting transmission
            transmission_started = True

            msg.start_time = env.now
            receiver.inbox.put(msg)
            self.turn_on()

            if self.is_on():
                self.data_rate += msg.data_rate
                yield env.timeout(msg.size / msg.data_rate - (env.now - msg.start_time))
                logger.debug(f'T{env.now}:\tTransmission complete!')
            else:
                # Transmitter is not on after being told to do so. Must be faulty. Dropping packet
                yield self.data_stored.get(msg.size)
                logger.debug(f'T{env.now}:\tTransmitter will not turn on. Must be faulty. Dropping packet.')

            # end transmission
            logger.debug(f'T{env.now}:\tReleasing transmission channel...')
            self.channels.release(req_trs)
            logger.debug(f'T{env.now}:\tReleasing reception channel...')
            receiver.channels.release(req_rcr)

            self.data_rate -= msg.data_rate
            if self.channels.count == 0:
                self.turn_off()
            logger.debug(f'T{env.now}:\tTransmission protocol done!')

        except simpy.Interrupt:
            logger.debug(f'T{env.now}:\tTransmission Interrupted. Dropping packet.')
            if not channels_established and not transmission_started:
                # transmission interrupted during channel request
                if transmission_channel_established:
                    logger.debug(f'T{env.now}:\tReleasing transmission channel.')
                    self.channels.release(req_trs)
                if reception_channel_established:
                    logger.debug(f'T{env.now}:\tReleasing reception channel...')
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
    def __init__(self, env, max_power_generation, energy_capacity, dod):
        super().__init__(env=env, name='battery', power=max_power_generation,
                         energy_stored=energy_capacity, energy_capacity=energy_capacity,
                         data_rate=0, data_stored=0, data_capacity=0, status=False)
        self.charging = False
        self.max_power_generation = max_power_generation
        self.dod = dod
        if not (0 <= dod <= 1):
            raise IOError("Depth-of-Discharge can only be a value between 0 and 1.")

    def is_charging(self):
        return self.charging
