import math
from messages import PlanMessage, AgentActionMessage, AgentStateMessage, SimulationMessageTypes
from states import SimulationAgentState
from tasks import IdleAction, MoveAction, MeasurementTask
from dmas.agents import AgentAction
from dmas.modules import *

class PlannerTypes(Enum):
    ACCBBA = 'ACCBBA'   # Asynchronous Consensus Constraint-Based Bundle Algorithm
    FIXED = 'FIXED'     # Fixed pre-determined plan

class PlannerResults(ABC):
    @abstractmethod
    def __eq__(self, __o: object) -> bool:
        """
        Compares two results 
        """
        return super().__eq__(__o)

class PlannerModule(InternalModule):
    def __init__(self, 
                results_path : str, 
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
        self.results_path = results_path
        self.parent_id = agent_id

    async def listen(self) -> None:
        try:
            # listen for incoming broadcasts from other modules
            while True:
                await asyncio.sleep(1e6)

        except asyncio.CancelledError:
            return

class FixedPlannerModule(PlannerModule):
    def __init__(self, 
                results_path : str, 
                manager_port: int, 
                agent_id: int, 
                parent_network_config: NetworkConfig, 
                level: int = logging.INFO, 
                logger: logging.Logger = None
                ) -> None:
        super().__init__(results_path,
                         manager_port, 
                         agent_id, 
                         parent_network_config, 
                         PlannerTypes.FIXED, 
                         level, 
                         logger)
        
    async def setup(self) -> None:
        # create an initial plan
        dt = 1
        steps = 1 * (self.parent_id + 1)
        pos = [steps, steps]
        t_start = math.sqrt( pos[0]**2 + pos[1]**2 ) + dt
        
        travel_to_target = MoveAction(pos, dt)
        measure = MeasurementTask(pos, 1, ['VNIR'], t_start, t_end=1e6)
        return_to_origin = MoveAction([0,0], t_start)

        self.plan = [
                    travel_to_target,
                    measure,
                    return_to_origin
                    ]
        
    async def routine(self) -> None:
        try:
            self.log('initial plan sent!')
            t_curr = 0
            while True:
                # listen for agent to send new senses
                self.log('waiting for incoming senses from parent agent...')
                senses = await self.empty_manager_inbox()

                self.log(f'received {len(senses)} senses from agent! processing senses...')
                new_plan = []
                for sense in senses:
                    sense : dict
                    if sense['msg_type'] == SimulationMessageTypes.AGENT_ACTION.value:
                        # unpack message 
                        msg : AgentActionMessage = AgentActionMessage(**sense)
                        
                        if msg.status != AgentAction.COMPLETED and msg.status != AgentAction.ABORTED:
                            # if action wasn't completed, re-try
                            action_dict : dict = msg.action
                            self.log(f'action {action_dict} not completed yet! trying again...')
                            msg.dst = self.get_parent_name()
                            new_plan.append(action_dict)

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

                    elif sense['msg_type'] == SimulationMessageTypes.AGENT_STATE.value:
                        # unpack message 
                        msg : AgentStateMessage = AgentStateMessage(**sense)
                        state = SimulationAgentState(**msg.state)

                        # update current simulation time
                        if t_curr < state.t:
                            t_curr = state.t               

                if len(new_plan) == 0:
                    # no previously submitted actions will be re-attempted
                    for action in self.plan:
                        action : AgentAction
                        if action.t_start <= t_curr <= action.t_end:
                            new_plan.append(action.to_dict())
                            break

                    if len(new_plan) == 0:
                        # if no plan left, just idle for a time-step
                        self.log('no more actions to perform. instruct agent to idle for one time-step.')
                        t_idle = 1e6
                        for action in self.plan:
                            action : AgentAction
                            t_idle = action.t_start if action.t_start < t_idle else t_idle
                        
                        action = IdleAction(t_curr, t_idle)
                        new_plan.append(action.to_dict())

                self.log(f'sending {len(new_plan)} actions to agent...')
                plan_msg = PlanMessage(self.get_element_name(), self.get_network_name(), new_plan)
                await self._send_manager_msg(plan_msg, zmq.PUB)

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
                results_path,
                manager_port: int, 
                agent_id: int, 
                parent_network_config: NetworkConfig, 
                level: int = logging.INFO, 
                logger: logging.Logger = None
                ) -> None:
        super().__init__(   results_path,
                            manager_port, 
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