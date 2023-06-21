import asyncio
import logging
from nodes.groundstat import GroundStationAgentState
from nodes.satellite import SatelliteAgentState
from nodes.uav import UAVAgentState
from nodes.agent import *
from messages import *
from dmas.messages import ManagerMessageTypes
from dmas.network import NetworkConfig
from nodes.planning.planners import PlanningModule


class GroundStationPlanner(PlanningModule):
    def __init__(self, 
                results_path: str, 
                parent_name: str, 
                measurement_reqs : list,
                module_network_config: NetworkConfig, 
                parent_network_config: NetworkConfig, 
                utility_func: function, 
                level: int = logging.INFO, 
                logger: logging.Logger = None
                ) -> None:
        super().__init__(   results_path, 
                            parent_name, 
                            module_network_config, 
                            parent_network_config, 
                            utility_func, 
                            level, 
                            logger
                        )
        self.measurement_reqs = measurement_reqs

    async def setup(self) -> None:
        # initialize internal messaging queues
        self.states_inbox = asyncio.Queue()
        self.relevant_changes_inbox = asyncio.Queue()
        self.action_status_inbox = asyncio.Queue()

    async def live(self) -> None:
        """
        Performs three concurrent tasks:
        - Listener: receives messages from the parent agent and checks results
        - Bundle-builder: plans and bids according to local information
        - Rebroadcaster: forwards plan to agent
        """
        try:
            listener_task = asyncio.create_task(self.listener(), name='listener()')
            bundle_builder_task = asyncio.create_task(self.planner(), name='planner()')
            
            tasks = [listener_task, bundle_builder_task]

            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        finally:
            for task in done:
                self.log(f'`{task.get_name()}` task finalized! Terminating all other tasks...')

            for task in pending:
                task : asyncio.Task
                if not task.done():
                    task.cancel()
                    await task


    async def listener(self) -> None:
        try:
            # initiate results tracker
            results = {}
            t_curr = 0.0

            # listen for broadcasts and place in the appropriate inboxes
            while True:
                self.log('listening to manager broadcast!')
                _, _, content = await self.listen_manager_broadcast()

                # if sim-end message, end agent `live()`
                if content['msg_type'] == ManagerMessageTypes.SIM_END.value:
                    self.log(f"received manager broadcast or type {content['msg_type']}! terminating `live()`...")
                    return

                elif content['msg_type'] == SimulationMessageTypes.SENSES.value:
                    self.log(f"received senses from parent agent!", level=logging.DEBUG)

                    # unpack message 
                    senses_msg : SensesMessage = SensesMessage(**content)

                    senses = []
                    senses.append(senses_msg.state)
                    senses.extend(senses_msg.senses)     

                    for sense in senses:
                        if sense['msg_type'] == SimulationMessageTypes.AGENT_ACTION.value:
                            # unpack message 
                            action_msg = AgentActionMessage(**sense)
                            self.log(f"received agent action of status {action_msg.status}! sending to bundle-builder...")
                            
                            # send to bundle builder 
                            await self.action_status_inbox.put(action_msg)

                        elif sense['msg_type'] == SimulationMessageTypes.AGENT_STATE.value:
                            # unpack message 
                            state_msg : AgentStateMessage = AgentStateMessage(**sense)
                            self.log(f"received agent state message! sending to bundle-builder...")
                            
                            # update current time:
                            if state_msg.state['state_type'] == SimulationAgentTypes.SATELLITE.value:
                                state = SatelliteAgentState(**state_msg.state)
                            elif state_msg.state['state_type'] == SimulationAgentTypes.UAV.value:
                                state = UAVAgentState(**state_msg.state)
                            elif state_msg.state['state_type'] == SimulationAgentTypes.GROUND_STATION.value:
                                state = GroundStationAgentState(**state_msg.state)
                            else:
                                raise NotImplementedError(f"`state_type` {state_msg.state['state_type']} not supported.")

                            
                            if t_curr < state.t:
                                t_curr = state.t

                            # send to bundle builder 
                            await self.states_inbox.put(state_msg) 

        except asyncio.CancelledError:
            return
        
        finally:
            self.listener_results = results

    async def planner(self) -> None:
        pass