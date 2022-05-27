from src.agents.components.components import PowerGenerator
from src.agents.state import State
from src.planners.actions import *


class Planner:
    def __init__(self, env, knowledge_base=None):
        self.env = env
        self.plan = []
        self.active_plan = []
        self.completed_plan = []
        self.interrupted_plan = []
        self.knowledge_base = knowledge_base

    def update(self, state: State, t):
        # schedules next actions to be given to agent or reconsiders plan
        # must consider current state, time, knowledge, and previously done or interrupted actions
        pass

    def schedule_action(self, action: Action, state: State, t):
        duration = action.start - t
        if duration < 0:
            duration = 0

        yield self.env.timeout(duration)

        state.parent_agent.plan.put(action)

    def completed_action(self, action: Action, state: State, t):
        # self.active_plan.remove(action)
        self.completed_plan.append((action, t))

    def interrupted_action(self, action: Action, state: State, t):
        # self.active_plan.remove(action)
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

