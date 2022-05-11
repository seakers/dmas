import simpy


class Transceiver:
    def __init__(self, env, rate, buffer_size=None, limit_bytes=True,  debug=False):
        self.inbox = simpy.Store(env)
        self.mailbox = simpy.Store(env)
        self.outbox = simpy.Store(env)
        self.rate = rate
        self.env = env
        self.out = None
        self.packets_rec = 0
        self.packets_drop = 0
        self.packets_sent = 0
        self.buffer_size = buffer_size # Size of buffer in bytes
        self.buffer_in = 0  # Current size of the incoming buffer in bytes
        self.buffer_out = 0  # Current size of the outgoing buffer in bytes
        self.limit_bytes = limit_bytes
        self.debug = debug
        self.busy = 0  # Used to track if a packet is currently being sent