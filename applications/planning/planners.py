from messages import AgentActionMessage, AgentStateMessage, SimulationMessageTypes
from states import SimulationAgentState
from tasks import ActionTypes, IdleAction, MoveAction
from dmas.agents import AgentAction
from dmas.modules import *

class PlannerTypes(Enum):
    ACCBBA = 'ACCBBA'   # Asynchronous Consensus Constraint-Based Bundle Algorithm
    FIXED = 'FIXED'     # Fixed pre-determined plan

class PlannerModule(InternalModule):
    def __init__(self, 
                manager_port : int,
                agent_id : int,
                parent_network_config: NetworkConfig, 
                planner_type : PlannerTypes,
                level: int = logging.INFO, 
                logger: logging.Logger = None
                ) -> None:
        module_network_config =  NetworkConfig(f'AGENT_{agent_id}',
                                                manager_address_map = {
                                                zmq.REQ: [],
                                                zmq.PUB: [f'tcp://*:{manager_port+5 + 4*agent_id + 3}'],
                                                zmq.SUB: [f'tcp://localhost:{manager_port+5 + 4*agent_id + 2}']})
                
        super().__init__(f'PLANNING_MODULE_{agent_id}', 
                        module_network_config, 
                        parent_network_config, 
                        [], 
                        level, 
                        logger)
        
        if planner_type not in PlannerTypes:
            raise NotImplementedError(f'planner of type {planner_type} not yet supported.')
        self.planner_type = planner_type

    
class PlannerResults(ABC):
    @abstractmethod
    def __eq__(self, __o: object) -> bool:
        """
        Compares two results 
        """
        return super().__eq__(__o)
    
class FixedPlannerModule(PlannerModule):
    def __init__(self, 
                manager_port: int, 
                agent_id: int, 
                parent_network_config: NetworkConfig, 
                level: int = logging.INFO, 
                logger: logging.Logger = None
                ) -> None:
        super().__init__(manager_port, 
                         agent_id, 
                         parent_network_config, 
                         PlannerTypes.FIXED, 
                         level, 
                         logger)
        
    async def setup(self) -> None:
        # create an initial plan
        move_right = MoveAction([10,0], 0)
        move_left = MoveAction([0,0], 0)

        self.plan = [
                    # move_right
                    # ,
                    move_left
                    ]
        
        # self.plan = [move_right]

        # self.plan = []
    
    async def listen(self) -> None:
        try:
            # listen for incoming messages from other modules
            while True:
                await asyncio.sleep(1e6)

        except asyncio.CancelledError:
            return
        
    async def routine(self) -> None:
        try:
            # self.log('sending initial plan...')
            # for action in self.plan:
            #     action : AgentAction
            #     msg = AgentActionMessage(self.get_element_name(), self.get_parent_name(), action.to_dict())
            #     await self._send_manager_msg(msg, zmq.PUB)

            self.log('initial plan sent!')
            t_curr = 0
            while True:
                # listen for agent to send new senses
                self.log('waiting for incoming agent senses...')
                senses = await self.empty_manager_inbox()

                self.log(f'received {len(senses)} senses from agent! processing senses...')
                new_plan = []
                # for sense in senses:
                #     sense : dict
                #     if sense['msg_type'] == SimulationMessageTypes.AGENT_ACTION.value:
                #         # unpack message 
                #         msg = AgentActionMessage(**sense)
                        
                #         # if action wasn't completed, re-try
                #         if msg.status != AgentAction.COMPLETED and msg.status != AgentAction.ABORTED:
                #             self.log(f'action {msg.action} not completed yet! trying again...')
                #             msg.dst = self.get_parent_name()
                #             new_plan.append(msg)

                #     elif sense['msg_type'] == SimulationMessageTypes.AGENT_STATE.value:
                #         # unpack message 
                #         msg : AgentStateMessage = AgentStateMessage(**sense)
                #         state = SimulationAgentState(**msg.state)

                #         # update current simulation time
                #         if t_curr < state.t:
                #             t_curr = state.t               

                if len(new_plan) < 1:
                    if len(self.plan) > 0:
                        action : AgentAction = self.plan.pop(0)
                        msg = AgentActionMessage(self.get_element_name(),
                                                self.get_parent_name(),
                                                action.to_dict())
                        new_plan.append(msg)
                    else:
                        # if no plan left, just idle for a time-step
                        self.log('no more actions to perform. instruct agent to idle for one time-step.')
                        idle = IdleAction(t_curr, t_curr+1000000)
                        msg = AgentActionMessage(self.get_element_name(),
                                                self.get_parent_name(),
                                                idle.to_dict())
                        # await self.send_manager_message(msg)
                        new_plan.append(msg)

                self.log(f'sending {len(new_plan)} actions to agent...')
                for msg in new_plan:
                    msg : AgentActionMessage
                    await self._send_manager_msg(msg, zmq.PUB)

                self.log(f'actions sent!')

        except asyncio.CancelledError:
            return
        
        except Exception as e:
            self.log(f'routine failed. {e}')
            raise e

    async def empty_manager_inbox(self) -> list:
        msgs = []
        while True:
            # wait for manager messages
            self.log('waiting for parent agent message...')
            _, _, content = await self.manager_inbox.get()
            msgs.append(content)

            # wait for any current transmissions to finish being received
            self.log('waiting for any possible transmissions to finish...')
            await asyncio.sleep(0.01)

            if self.manager_inbox.empty():
                self.log('manager queue empty.')
                break
            self.log('manager queue still contains elements.')
        
        return msgs

    async def teardown(self) -> None:
        # nothing to tear-down
        return

class ACCBBAPlannerModule(PlannerModule):
    def __init__(self,  
                manager_port: int, 
                agent_id: int, 
                parent_network_config: NetworkConfig, 
                level: int = logging.INFO, 
                logger: logging.Logger = None
                ) -> None:
        super().__init__(   manager_port, 
                            agent_id, 
                            parent_network_config,
                            PlannerTypes.ACCBBA, 
                            level, 
                            logger)
    
    async def listen(self):
        # listen for any messages from the agent and adjust results ledger

        # if changes are made that affect the bundle, inform `routine()`
        pass

    async def routine(self) -> None:
        # waits for changes in the ledger that may affect the current bundle
        pass