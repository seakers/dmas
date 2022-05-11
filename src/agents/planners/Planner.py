from src.agents.components.Battery import Battery
from src.agents.components.Instrument import Instrument
from src.agents.components.SolarPanel import SolarPanel
from src.agents.planners.Action import TransmitAction, ActuateAction, AgentActuateAction, BatteryRechargeAction, \
    DropMessageAction, DataUpdateAction


class Planner:
    def __init__(self, unique_id, epoc):
        self.unique_id = unique_id
        self.epoc = epoc
        self.plan = []
        self.plan_out = []

    def update_planner(self, agent, state, epoc):
        # Update Epoc
        self.epoc = epoc

        # Delete Completed Actions
        actions_to_delete = []
        for action in self.plan:
            if action.is_complete(epoc):
                actions_to_delete.append(action)

        for action in actions_to_delete:
            self.plan.remove(action)

        return

    def get_plan(self):
        """
        Queries existing plan to return a list of actions that have to be performed at the current epoc
        :return: array of actions to be performed
        """
        plan = []
        for action in self.plan:
            if action.is_active(self.epoc):
                plan.append(action)

        return plan

class EngineeringModulePlanner(Planner):
    def update_planner(self, agent, state, epoc):
        super().update_planner(agent, state, epoc)

        # Power Regulation
        power_regulation_actions = self.update_power_regulation(agent, state, epoc)
        for new_action in power_regulation_actions:
            self.plan.append(new_action)

        # Data Storage Regulation
        data_storage_regulation_actions = self.update_data_storage_regulation(agent, state, epoc)
        for new_action in data_storage_regulation_actions:
            self.plan.append(new_action)

        return

    def update_data_storage_regulation(self, agent, state, epoc):
        new_plan = []

        # Data Storage Regulation
        data_volume = (state.data_stored + (state.data_in - state.data_out) * agent.dt)
        if data_volume > state.data_capacity:
            # if incoming data would exceed data storage capacity, then drop incoming messages
            for incoming_message in agent.get_incoming_messages():
                data_volume -= incoming_message.get_data_rate() * agent.dt
                new_plan.append(DropMessageAction(incoming_message, epoc))

                if data_volume <= state.data_capacity:
                    break

            if data_volume < state.data_capacity:
                # there is still not enough data storage for the incoming data. start to turn off instruments
                for component in agent.component_list:
                    if type(component) == Instrument and component.is_on():
                        new_plan.append(ActuateAction(component.get_name(), epoc, status=False))

                        data_volume -= component.data_generation * agent.dt
                        if data_volume <= state.data_capacity:
                            break

                if data_volume > state.data_capacity:
                    # there is still not enough data storage for the incoming data. turning off agent
                    return [AgentActuateAction(epoc, status=False)]

        # update storage
        new_plan.append(DataUpdateAction(state.data_in - state.data_out, epoc))

        return new_plan

    def update_power_regulation(self, agent, state, epoc):
        new_plan = []
        # Power Regulation
        power_deficit = state.power_in - state.power_out

        if state.power_in < state.power_out:
            # turn on power generators and batteries if possible
            components_to_turn_on = []
            for component in agent.component_list:
                # TODO ADD POWER GENERATORS TO LIST OF COMPONENTS TO TURN ON BASED ON ECLIPSE DATA
                if (not component.is_on() and component.power_generation > 0
                        and (type(component) == Battery)):
                    components_to_turn_on.append(component)
                    power_deficit += component.power_generation

                    if power_deficit >= 0:
                        break

            if power_deficit < 0:
                # power consumption would still exceed generation even if all power generators would be turned on.
                # turning off agent
                return [AgentActuateAction(epoc, status=False)]
            else:
                # power demand can be matched with agent's components. creating actuation actions for components
                for component in components_to_turn_on:
                    new_plan.append(ActuateAction(component.get_name(), epoc))

                if power_deficit > 0:
                    # power generation now exceeds power consumption, recharge batteries with excess energy
                    batteries = []
                    for component in agent.component_list:
                        if type(component) == Battery and not component.is_full():
                            batteries.append(component)

                    n_batteries = len(batteries)
                    if n_batteries == 0:
                        # no batteries available to be recharged. Turning off agent.
                        # TODO ALLOW AGENT TO DECIDE WHICH INSTRUMENTS TO TURN OFF IN CASE IT NEEDS IT
                        return [AgentActuateAction(epoc, status=False)]
                    else:
                        # batteries available to be recharged. creating charging action for said batteries
                        for battery in batteries:
                            battery_name = battery.get_name()
                            power_in = power_deficit / n_batteries
                            new_plan.append(BatteryRechargeAction(battery_name, power_in, epoc))

        if state.power_in > state.power_out:
            # charge batteries if possible, if not turn off power generation components
            batteries = []
            for component in agent.component_list:
                if type(component) == Battery and not component.is_full():
                    batteries.append(component)

            n_batteries = len(batteries)
            if n_batteries == 0:
                # no batteries available to be recharged. Turning off agent.
                # TODO ALLOW AGENT TO DECIDE WHICH INSTRUMENTS TO TURN OFF IN CASE IT NEEDS IT
                return [AgentActuateAction(epoc, status=False)]
            else:
                # batteries available to be recharged. creating charging action for said batteries
                for battery in batteries:
                    battery_name = battery.get_name()
                    power_in = power_deficit / n_batteries
                    new_plan.append(BatteryRechargeAction(battery_name, power_in, epoc))

        return new_plan

class TestPlanner(EngineeringModulePlanner):
    """
    Tests communications framework for two overlapping messages. Two agents will message the same agent with different
    start times. Both messages are each large enough to fill the receiver's memory. As the message from agent 0 starts
    to fill agent 1's memory, agent 1 is expected to drop the reception of the message from agent 2 as it cannot handle
    the incoming data volume.

    Agents will also perform maintenance tasks such as power and data handling.

    Agent organization:
    0 ---> 1 <--- 2
    """
    def __init__(self, unique_id, epoc):
        super().__init__(unique_id, epoc)
        if self.unique_id == 0:
            transmitAction = TransmitAction(self.unique_id, 1, 0, 1, 10,
                                            None)  # sender_id, target_id, start, data_rate, size, content
            batteryOn = ActuateAction('testBattery', 0)
            # antennaOn = ActuateAction('testComms', 0)
            batteryOff = ActuateAction('testBattery', 10, status=False)
            antennaOff = ActuateAction('testComms', 10, status=False)

            self.plan.append(transmitAction)
            self.plan.append(batteryOn)
            # self.plan.append(antennaOn)
            self.plan.append(batteryOff)
            self.plan.append(antennaOff)

        elif self.unique_id == 2:
            transmitAction = TransmitAction(self.unique_id, 1, 5, 1, 10,
                                            None)  # sender_id, target_id, start, data_rate, size, content

            batteryOn = ActuateAction('testBattery', 5)
            # antennaOn = ActuateAction('testComms', 5)
            batteryOff = ActuateAction('testBattery', 15, status=False)
            antennaOff = ActuateAction('testComms', 15, status=False)

            self.plan.append(transmitAction)
            self.plan.append(batteryOn)
            # self.plan.append(antennaOn)
            self.plan.append(batteryOff)
            self.plan.append(antennaOff)

