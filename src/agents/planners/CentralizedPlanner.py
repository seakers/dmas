from src.agents.planners.AbstractPlanner import AbstractPlanner


class CentralizedPlanner(AbstractPlanner):
    def __init__(self, start_epoc=0, time_step=1):
        super().__init__(start_epoc=start_epoc, time_step=time_step)

    def update_plan(self, component_list, received_messages, epoc):
        super().update_plan(component_list, received_messages, epoc)

