class AbstractAgents:
    def __init__(self, env, unique_id, transceiver):
        self.env = env
        self.unique_id = unique_id
        self.other_agents = []
        self.transceiver = transceiver
