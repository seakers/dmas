import simpy

class Planner:
    def __init__(self, parent_agent):
        self.agent = parent_agent
        self.plan = []

    def update_plan(self, parent_agent):
        pass

class Action:
    def __init__(self, type, start, end):
        self.type = type
        self.start = start
        self.end = end

class Message:
    def __init__(self, time, size, rate, message_id, content=None, src="a", dst="z", flow_id=0):
        self.time = time
        self.size = size
        self.rate = rate
        self.message_id = message_id
        self.content = content
        self.src = src
        self.dst = dst
        self.flow_id = flow_id

    def __repr__(self):
        return "id: {}, src: {}, time: {}, size: {}".\
            format(self.id, self.src, self.time, self.size)


class Transceiver:
    def __init__(self, rate, buffer_size=None, limit_bytes=True,  debug=False):
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


class Agent:
    def __init__(self, env, unique_id, transceiver):
        self.env = env
        self.unique_id = unique_id
        self.other_agents = []
        self.transceiver = transceiver

    def set_other_agents(self, others):
        for other in others:
            if other is not self:
                self.other_agents.append(other)

    def live(self):
        self.print_string('Hello World!')

        self.print_string("I know of the following agents:")
        for other in self.other_agents:
            print('\t\t Agent %d' % other.unique_id)

        if self.unique_id == 0:
            other = self.other_agents[0]
            self.print_string("Sending message to Agent {}...".format(other.unique_id))

            msg = Message(self.env.now, 10, 1, 'TESTMSG1', src='A0', dst='A1')
            transmit = self.env.process(self.transmit_message(msg, other))

            yield transmit

            self.print_string("Turning off")
        else:
            self.print_string("Not much to do right now. Idling...")
            idle = Action("Idle", 0, 90)

            perf_action = self.env.process(self.perform_action(idle))
            receive = self.env.process(self.receive_message())

            yield receive | perf_action

            if receive.triggered and not perf_action.triggered:
                perf_action.interrupt("New message received! Reevaluating plan...")

                if self.env.now < idle.end:
                    idle.start = self.env.now
                    perf_action = self.env.process(self.perform_action(idle))

                    self.print_string("No modification to current plan. Continuing last action of type {}"
                                      .format(idle.type))
                    yield perf_action

                    self.print_string("Turning off")

    def perform_action(self, action):
        self.print_string("Performing action of type {}...".format(action.type))
        try:
            start = action.start
            end = action.end
            yield self.env.timeout(end - start)
            self.print_string("Finished action of type {}!".format(action.type))
        except simpy.Interrupt as inter:
            self.print_string("Interrupted action of type {} at {}s. {}"
                              .format(action.type, env.now, inter.cause))

    def receive_message(self):
        msg = (yield self.transceiver.inbox.get())
        self.transceiver.busy = 1
        self.transceiver.buffer_in -= msg.size

        self.print_string("Starting reception of msgID:{} from {}...".format(msg.message_id, msg.src))
        yield self.env.timeout(msg.size / self.transceiver.rate)
        self.transceiver.mailbox.put(msg)
        self.print_string("Finished reception of msgID:{} from {}!".format(msg.message_id, msg.src))

        self.transceiver.busy = 0

    def transmit_message(self, msg, other):
        other.put(msg)
        self.print_string("Starting transmission of msgID:{} towards {}...".format(msg.message_id, msg.dst))
        yield self.env.timeout(msg.size / self.transceiver.rate)
        self.print_string("Finished transmission of msgID:{} towards {}!".format(msg.message_id, msg.dst))

    def put(self, msg):
        self.transceiver.packets_rec += 1
        tmp_byte_count = self.transceiver.buffer_in + msg.size

        if self.transceiver.buffer_size is None:
            self.transceiver.buffer_in = tmp_byte_count
            return self.transceiver.inbox.put(msg)
        if self.transceiver.limit_bytes and tmp_byte_count >= self.transceiver.buffer_size:
            self.transceiver.packets_drop += 1
            return
        elif not self.transceiver.limit_bytes and len(self.transceiver.inbox.items) >= self.transceiver.buffer_size - 1:
            self.transceiver.packets_drop += 1
        else:
            self.transceiver.buffer_in = tmp_byte_count
            return self.transceiver.inbox.put(msg)

    def print_string(self, string):
        format_string = "A{}-T{}:\t".format(self.unique_id, env.now)
        print(format_string + string)


n = 2
env = simpy.Environment()
agents = []
for i in range(n):
    receiver = Transceiver(1, debug=True)
    agents.append(Agent(env, i, receiver))
for agent in agents:
    agent.set_other_agents(agents)
    env.process(agent.live())

env.run()

x = 1
