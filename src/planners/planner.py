from src.agents.components.components import PowerGenerator
from src.planners.actions import *


class Planner:
    def __init__(self, knowledge_base=None):
        self.plan = []
        self.knowledge_base = knowledge_base

    def update(self, state, t):
        pass

    def get_plan(self, t):
        active_plan = []
        for action in self.plan:
            if action.is_active(t):
                active_plan.append(action)

        if len(active_plan) > 0:
            for action in active_plan:
                self.plan.remove(action)

        return active_plan


class PingPlanner(Planner):
    def __init__(self):
        super().__init__()

    def update(self, state, t):
        parent_agent = state.agent

        if t == 0 and parent_agent.unique_id == 0:
            dst = parent_agent.other_agents[0]
            start = 0
            size = 10
            rate = 1
            transmit = TransmitAction(parent_agent, dst, start, size, rate)
            self.plan.append(transmit)

        elif len(parent_agent.data_storage.mailbox.items) > 0 and parent_agent.unique_id == 1:
            msg = parent_agent.data_storage.mailbox.get().value
            dst = msg.src
            start = t
            size = 10
            rate = 1
            transmit = TransmitAction(parent_agent, dst, start, size, rate)
            self.plan.append(transmit)

            parent_agent.data_storage.data_stored -= msg.size


class StationKeepingPlanner(Planner):
    def __init__(self):
        super().__init__()

    def update(self, state, t):
        _, power_generation, energy_stored, energy_capacity, \
        data_rate, data_stored, data_capacity = state.get_last_state()

        if power_generation > 0:
            if energy_stored >= energy_capacity:
                power_generator = None
                for component in self.parent_agent.component_list:
                    if type(component) == PowerGenerator:
                        # turn off generator
                        action = ActuateComponentAction

