import asyncio
import logging
from nodes.states import GroundStationAgentState, SatelliteAgentState, SimulationAgentTypes, UAVAgentState
from nodes.agent import *
from messages import *
from dmas.messages import ManagerMessageTypes
from dmas.network import NetworkConfig
from nodes.planning.planners import PlanningModule


class FixedPlanner(PlanningModule):
    def __init__(self, 
                results_path: str, 
                parent_name: str, 
                plan : list,
                parent_network_config: NetworkConfig, 
                utility_func: Callable[[], Any],
                level: int = logging.INFO, 
                logger: logging.Logger = None
                ) -> None:
        super().__init__(   results_path, 
                            parent_name, 
                            parent_network_config, 
                            utility_func, 
                            level, 
                            logger
                        )
        self.plan = plan        

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
                                                        
                            # send to bundle builder 
                            await self.states_inbox.put(state_msg) 

                        elif sense['msg_type'] == SimulationMessageTypes.MEASUREMENT_REQ.value:
                            x = 1
                            
                        # TODO support down-linked information processing

        except asyncio.CancelledError:
            return
        
        finally:
            self.listener_results = results

    async def planner(self) -> None:
        try:
            t_curr = 0
            while True:
                plan_out = []
                msg : AgentStateMessage = await self.states_inbox.get()

                # update current time:
                if msg.state['state_type'] == SimulationAgentTypes.SATELLITE.value:
                    state = SatelliteAgentState(**msg.state)
                elif msg.state['state_type'] == SimulationAgentTypes.UAV.value:
                    state = UAVAgentState(**msg.state)
                elif msg.state['state_type'] == SimulationAgentTypes.GROUND_STATION.value:
                    state = GroundStationAgentState(**msg.state)
                else:
                    raise NotImplementedError(f"`state_type` {msg.state['state_type']} not supported.")

                if t_curr < state.t:
                    t_curr = state.t

                while not self.action_status_inbox.empty():
                    msg : AgentActionMessage = await self.action_status_inbox.get()

                    if msg.status != AgentAction.COMPLETED and msg.status != AgentAction.ABORTED:
                        # if action wasn't completed, re-try
                        action_dict : dict = msg.action
                        self.log(f'action {action_dict} not completed yet! trying again...')
                        plan_out.append(action_dict)

                    elif msg.status == AgentAction.COMPLETED:
                        # if action was completed, remove from plan
                        action_dict : dict = msg.action
                        completed_action = AgentAction(**action_dict)
                        removed = None
                        for action in self.plan:
                            action : AgentAction
                            if action.id == completed_action.id:
                                removed = action
                                break

                        if removed is not None:
                            self.plan.remove(removed)
                
                for action in self.plan:
                    action : AgentAction
                    if action.t_start <= t_curr <= action.t_end:
                        plan_out.append(action.to_dict())
                        break

                if len(plan_out) == 0:
                    # if no plan left, just idle for a time-step
                    self.log('no more actions to perform. instruct agent to idle for the remainder of the simulation.')
                    t_idle = t_curr + 1e6 # TODO find end of simulation time        
                    action = WaitForMessages(t_curr, t_idle)
                    plan_out.append(action.to_dict())
                    
                self.log(f'sending {len(plan_out)} actions to agent...')
                plan_msg = PlanMessage(self.get_element_name(), self.get_network_name(), plan_out)
                await self._send_manager_msg(plan_msg, zmq.PUB)

                self.log(f'actions sent!')

        except asyncio.CancelledError:
            return

        except Exception as e:
            self.log(f'routine failed. {e}')
            raise e

    async def teardown(self) -> None:
        # nothing to tear-down
        return