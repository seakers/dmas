from src.agents.components.components import PowerGenerator
from src.planners.actions import *


class Planner:
    def __init__(self, knowledge_base=None):
        self.plan = []
        self.active_plan = []
        self.completed_plan = []
        self.interrupted_plan = []
        self.knowledge_base = knowledge_base

    def update(self, state, t):
        # must consider current state, time, knowledge, and previously done or interrupted actions
        pass

    def get_plan(self, t):
        active_plan = []
        for action in self.plan:
            if action.is_active(t):
                active_plan.append(action)

        if len(active_plan) > 0:
            for action in active_plan:
                self.active_plan.append(action)
                self.plan.remove(action)

        return active_plan

    def completed_action(self, action, t):
        self.active_plan.remove(action)
        self.completed_plan.append((action, t))

    def interrupted_action(self, action, t):
        self.active_plan.remove(action)
        self.interrupted_plan.append((action, t))

    def interrupted_message(self, msg, t):
        pass

    def timed_out_message(self, msg, t):
        pass

    def message_received(self, msg, t):
        pass

    def message_deleted(self, msg, t):
        pass

    def update_knowledge_base(self, measurement_results):
        pass

