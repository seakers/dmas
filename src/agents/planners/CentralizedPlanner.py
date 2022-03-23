from src.agents.planners.AbstractPlanner import AbstractPlanner
import json
import os

from src.agents.planners.Action import TransmitAction


def read_targets(plan):
    targets = []
    for action in plan:
        sat_id = action['sat_id']
        if not targets.__contains__(sat_id):
            targets.append(sat_id)

    return targets


class CentralizedPlannerGS(AbstractPlanner):
    def __init__(self, scenario, start_epoc=0, time_step=1):
        super().__init__(start_epoc=start_epoc, time_step=time_step)

        # Load in all pre-calculated plans from scenario
        directory = '../../scenarios/' + scenario + '/plans/'

        for filename in os.listdir(directory):
            with open(os.path.join(directory, filename), 'r') as f:
                # load each json plan
                plan_data = json.loads(f.read())
                horizon_start = float(plan_data['horizon_start'])
                horizon_end = float(plan_data['horizon_end'])
                plan = plan_data['plan']

                target_ids = read_targets(plan)

                # transform json into plans to submit by centralized planner
                for target in target_ids:
                    action = TransmitAction(1000, target, horizon_start, 1, 3, plan)
                    self.plan.append(action)

    def update_plan(self, component_list, received_messages, epoc):
        super().update_plan(component_list, received_messages, epoc)


class CentralizedPlannerSat(AbstractPlanner):
    def __init__(self, start_epoc=0, time_step=1):
        super().__init__(start_epoc=start_epoc, time_step=time_step)

    def update_plan(self, component_list, received_messages, epoc):
        super().update_plan(component_list, received_messages, epoc)
