import logging
from dmas.agents import *
from dmas.network import NetworkConfig

from messages import *
from states import *
from planners import *

class SimulationAgent(Agent):
    def __init__(   self, 
                    network_name : str,
                    manager_port : int,
                    id : int,
                    manager_network_config: NetworkConfig, 
                    planner_type: PlannerTypes,
                    initial_state: SimulationAgentState, 
                    level: int = logging.INFO, 
                    logger: logging.Logger = None) -> None:
        
        # generate network config 
        agent_network_config = NetworkConfig( 	network_name,
												manager_address_map = {
														zmq.REQ: [f'tcp://localhost:{manager_port}'],
														zmq.SUB: [f'tcp://localhost:{manager_port+1}'],
														zmq.PUSH: [f'tcp://localhost:{manager_port+2}']},
												external_address_map = {
														zmq.REQ: [],
														zmq.PUB: [f'tcp://*:{manager_port+5 + 4*id}'],
														zmq.SUB: [f'tcp://localhost:{manager_port+4}']},
                                                internal_address_map = {
														zmq.REP: [f'tcp://*:{manager_port+5 + 4*id + 1}'],
														zmq.PUB: [f'tcp://*:{manager_port+5 + 4*id + 2}'],
														zmq.SUB: [f'tcp://localhost:{manager_port+5 + 4*id + 3}']
											})
        
        if planner_type is PlannerTypes.ACCBBA:
            planning_module = ACCBBAPlannerModule(manager_port,
                                                    id,
                                                    agent_network_config,
                                                    level,
                                                    logger)
        else:
            raise NotImplementedError(f'planner of type {planner_type} not yet supported.')

        super().__init__(f'AGENT_{id}', 
                        agent_network_config, 
                        manager_network_config, 
                        initial_state, 
                        [planning_module], 
                        level, 
                        logger)

    async def setup(self) -> None:
        # nothing to set-up
        return

    async def sense(self, statuses: dict) -> list:
        # initiate senses array
        senses = []

        # check status of previously performed tasks
        completed = []
        for action in statuses:
            # sense and compile updated task status for planner 
            action : AgentAction
            status = statuses[action]
            msg = AgentActionMessage(   self.get_element_name(), 
                                        self.get_element_name(), 
                                        action.to_dict(),
                                        status)
            senses.append(msg)      

            # compile completed tasks for state tracking
            if status == AgentAction.COMPLETED:
                self.state : SimulationAgentState
                completed.append(action)

        # update state
        t = self.get_current_time()
        self.state.update_state(t, completed)

        # inform environment of new state
        state_msg = AgentStateMessage(  self.get_element_name(), 
                                        SimulationElementRoles.ENVIRONMENT.value,
                                        self.state.to_dict())
        await self.send_peer_message(state_msg)

        # handle manager broadcasts
        while not self.manager_inbox.empty():
            # do nothing; empty maanger inbox
            _, _, _ = await self.manager_inbox.get()
        
        # handle peer broadcasts
        while not self.external_inbox.empty():
            _, _, content = await self.external_inbox.get()

            if content['msg_type'] == SimulationMessageTypes.CONNECTIVITY_UPDATE.value:
                # update connectivity
                msg = AgentConnectivityUpdate(**msg)
                if msg.connected:
                    self.subscribe_to_broadcasts(msg.target)
                else:
                    self.unsubscribe_to_broadcasts(msg.target)

                # udpate state

            elif content['msg_type'] == SimulationMessageTypes.AGENT_STATE.value:
                # forward to planner
                senses.append(AgentStateMessage(**content))

            elif content['msg_type'] == SimulationMessageTypes.TASK_REQ.value:
                # forward to planner
                senses.append(TaskRequest(**content))

            elif content['msg_type'] == SimulationMessageTypes.PLANNER_UPDATE.value:
                # forward to planner
                senses.append(PlannerUpdate(**content))

        return senses

    async def think(self, senses: list) -> list:
        # send all sensed messages to planner
        for sense in senses:
            sense : SimulationMessage
            await self.send_internal_message(sense)

        # wait for planner to send list of tasks to perform
        return await self.internal_inbox.get()

    async def do(self, actions: list) -> dict:
        # update state

        # for every state action
        #   do action
        #   update state
        #   inform environment

        # for every measurement action
        #   do action
        #   update state
        #   inform environment 
        pass

    async def teardown(self) -> None:
        pass

    async def sim_wait(self, delay: float) -> None:
        try:
            if isinstance(self._clock_config, FixedTimesStepClockConfig):
                if delay > 0:
                    # desired time not yet reached
                    t0 = self.get_current_time()
                    tf = t0 + delay
                    
                    # send tic request
                    tic_req = TicRequest(self.get_element_name(), t0, tf)
                    await self.send_manager_message(tic_req)

                    # wait for time update
                    self.t_curr : Container
                    await self.t_curr.when_geq_than(tf)

            elif isinstance(self._clock_config, AcceleratedRealTimeClockConfig):
                await asyncio.sleep(delay / self._clock_config.sim_clock_freq)

            else:
                raise NotImplementedError(f'`sim_wait()` for clock of type {type(self._clock_config)} not yet supported.')
                
        except asyncio.CancelledError:
            return