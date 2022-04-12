from src.agents.planners.AbstractPlanner import AbstractPlanner
from src.agents.planners.Action import TransmitAction, ActuateAction


class CommsTestPlanner(AbstractPlanner):
    """
    Tests communications framework for two overlapping messages. Two agents will message the same agent with different
    start times. Both messages are each large enough to fill the receiver's memory. As the message from agent 0 starts
    to fill agent 1's memory, agent 1 will then drop the reception of the message from agent 2 as it cannot handle the
    incoming data volume.

    Agent organization:
    0 ---> 1 <--- 2
    """

    def update_plan(self, component_list, received_messages, epoc):
        """
        Updates epoc and updates existing plan according to its current and newly received information
        :param component_list: list and state of each component contained in the agent
        :param received_messages: list of newly received messages
        :param epoc: current epoc in [s]
        :return:
        """
        super().update_plan(component_list, received_messages, epoc)
        if epoc == 0:
            if self.unique_id == 0:
                transmitAction = TransmitAction(self.unique_id, 1, 0, 1, 10, None) # sender_id, target_id, start, data_rate, size, content
                actuateActionOn = ActuateAction('testBattery', 0)
                actuateActionOff = ActuateAction('testBattery', 10, status=False)
                self.plan.append(transmitAction)
                self.plan.append(actuateActionOn)
                self.plan.append(actuateActionOff)

            elif self.unique_id == 2:
                transmitAction = TransmitAction(self.unique_id, 1, 5, 1, 10, None) # sender_id, target_id, start, data_rate, size, content
                actuateActionOn = ActuateAction('testBattery', 5)
                actuateActionOff = ActuateAction('testBattery', 15, status=False)
                self.plan.append(transmitAction)
                self.plan.append(actuateActionOn)
                self.plan.append(actuateActionOff)
        else:
            actions_to_remove = []
            for action in self.plan:
                if action.is_complete(epoc):
                    actions_to_remove.append(action)

            for action in actions_to_remove:
                self.plan.remove(action)
        return