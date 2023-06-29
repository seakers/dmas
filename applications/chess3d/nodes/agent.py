import logging
from typing import Any, Callable
import numpy as np
from pandas import DataFrame

from instrupy.base import Instrument
from nodes.states import SimulationAgentState
from nodes.science.reqs import MeasurementRequest
from nodes.engineering.engineering import EngineeringModule
from nodes.engineering.actions import SubsystemAction, ComponentAction
from nodes.planning.planners import PlanningModule
from nodes.science.science import ScienceModule
from utils import setup_results_directory
from nodes.actions import *
from dmas.agents import *
from dmas.network import NetworkConfig

from messages import *

class SimulationAgent(Agent):
    """
    # Abstract Simulation Agent

    #### Attributes:
        - agent_name (`str`): name of the agent
        - scenario_name (`str`): name of the scenario being simulated
        - manager_network_config (:obj:`NetworkConfig`): network configuration of the simulation manager
        - agent_network_config (:obj:`NetworkConfig`): network configuration for this agent
        - initial_state (:obj:`SimulationAgentState`): initial state for this agent
        - payload (`list): list of instruments on-board the spacecraft
        - utility_func (`function`): utility function used to evaluate the value of observations
        - planning_module (`PlanningModule`): planning module assigned to this agent
        - science_module (`ScienceModule): science module assigned to this agent
        - level (int): logging level
        - logger (logging.Logger): simulation logger 
    """
    def __init__(   self, 
                    agent_name: str, 
                    scenario_name: str,
                    manager_network_config: NetworkConfig, 
                    agent_network_config: NetworkConfig,
                    initial_state : SimulationAgentState,
                    payload : list,
                    utility_func : Callable[[], Any],
                    planning_module : PlanningModule = None,
                    science_module : ScienceModule = None,
                    level: int = logging.INFO, 
                    logger: logging.Logger = None
                    ) -> None:
        """
        Initializes an instance of a Simulation Agent Object

        #### Arguments:
            - agent_name (`str`): name of the agent
            - scenario_name (`str`): name of the scenario being simulated
            - manager_network_config (:obj:`NetworkConfig`): network configuration of the simulation manager
            - agent_network_config (:obj:`NetworkConfig`): network configuration for this agent
            - initial_state (:obj:`SimulationAgentState`): initial state for this agent
            - payload (`list): list of instruments on-board the spacecraft
            - utility_func (`function`): utility function used to evaluate the value of observations
            - planning_module (`PlanningModule`): planning module assigned to this agent
            - science_module (`ScienceModule): science module assigned to this agent
            - level (int): logging level
            - logger (logging.Logger): simulation logger 
        """
        # load agent modules
        modules = []
        if planning_module is not None:
            if not isinstance(planning_module, PlanningModule):
                raise AttributeError(f'`planning_module` must be of type `PlanningModule`; is of type {type(planning_module)}')
            modules.append(planning_module)
        if science_module is not None:
            if not isinstance(science_module, ScienceModule):
                raise AttributeError(f'`science_module` must be of type `ScienceModule`; is of type {type(science_module)}')
            modules.append(science_module)

        # initialize agent
        super().__init__(agent_name, 
                        agent_network_config, 
                        manager_network_config, 
                        initial_state, 
                        modules, 
                        level, 
                        logger)

        if not isinstance(payload, list):
            raise AttributeError(f'`payload` must be of type `list`; is of type {type(payload)}')
        for instrument in payload:
            if not isinstance(instrument, Instrument):
                raise AttributeError(f'`payload` must be a `list` containing elements of type `Instrument`; contains elements of type {type(instrument)}')
        
        self.payload : list = payload
        self.utility_func : function = utility_func
        self.state_history : list = []
        
        # setup results folder:
        self.results_path = setup_results_directory(f'./results/' + scenario_name + '/' + self.get_element_name())
          

    async def sense(self, statuses: list) -> list:
        # initiate senses array
        senses = []

        # check status of previously performed tasks
        completed = []
        for action, status in statuses:
            # sense and compile updated task status for planner 
            action : AgentAction
            status : str
            msg = AgentActionMessage(   self.get_element_name(), 
                                        self.get_element_name(), 
                                        action.to_dict(),
                                        status)
            senses.append(msg)      

            # compile completed tasks for state tracking
            if status == AgentAction.COMPLETED:
                completed.append(action.id)

        # update state
        self.state.update_state(self.get_current_time(), 
                                status=SimulationAgentState.SENSING)
        self.state_history.append(self.state.to_dict())

        # sense environment for updated state
        state_msg = AgentStateMessage(  self.get_element_name(), 
                                        SimulationElementRoles.ENVIRONMENT.value,
                                        self.state.to_dict()
                                    )
        _, _, content = await self.send_peer_message(state_msg)

        env_resp = BusMessage(**content)
        for resp in env_resp.msgs:
            # unpackage message
            resp : dict
            resp_msg : SimulationMessage = message_from_dict(**resp)

            if isinstance(resp_msg, AgentStateMessage):
                # update state
                self.state.update_state(self.get_current_time(), state=resp_msg.state)
                senses.append(resp_msg)

            elif isinstance(resp_msg, AgentConnectivityUpdate):
                if resp_msg.connected == 1:
                    self.subscribe_to_broadcasts(resp_msg.target)
                else:
                    self.unsubscribe_to_broadcasts(resp_msg.target)
                # senses.append(rep_msg)

        # handle environment broadcasts
        while not self.environment_inbox.empty():
            # save as senses to forward to planner
            _, _, msg_dict = await self.environment_inbox.get()
            msg = message_from_dict(**msg_dict)
            senses.append(msg)

        # handle peer broadcasts
        while not self.external_inbox.empty():
            # save as senses to forward to planner
            _, _, msg_dict = await self.external_inbox.get()
            msg = message_from_dict(**msg_dict)
            senses.append(msg)

        return senses

    async def think(self, senses: list) -> list:
        # send all sensed messages to planner
        self.log(f'sending {len(senses)} senses to planning module...', level=logging.DEBUG)
        senses_dict = []
        state_dict = None
        for sense in senses:
            sense : SimulationMessage
            if isinstance(sense, AgentStateMessage):
                state_dict = sense.to_dict()
            else:
                senses_dict.append(sense.to_dict())

        senses_msg = SensesMessage(self.get_element_name(), self.get_element_name(), state_dict, senses_dict)
        await self.send_internal_message(senses_msg)

        # wait for planner to send list of tasks to perform
        self.log(f'senses sent! waiting on response from planner module...')
        actions = []
        
        while True:
            _, _, content = await self.internal_inbox.get()
            
            if content['msg_type'] == SimulationMessageTypes.PLAN.value:
                msg = PlanMessage(**content)
                for action_dict in msg.plan:
                    self.log(f"received an action of type {action_dict['action_type']}", level=logging.DEBUG)
                    actions.append(action_dict)  
                break
        
        self.log(f"plan of {len(actions)} actions received from planner module!")
        return actions

    async def do(self, actions: list) -> dict:
        statuses = []
        self.log(f'performing {len(actions)} actions', level=logging.DEBUG)
        
        for action_dict in actions:
            action_dict : dict
            action = AgentAction(**action_dict)
            t_0 = time.perf_counter()

            if self.get_current_time() < action.t_start:
                self.log(f"action of type {action_dict['action_type']} has NOT started yet. waiting for start time...", level=logging.INFO)
                action.status = AgentAction.PENDING
                statuses.append((action, action.status))
                continue
            
            if action.t_end < self.get_current_time():
                self.log(f"action of type {action_dict['action_type']} has already occureed. could not perform task before...", level=logging.INFO)
                action.status = AgentAction.ABORTED
                statuses.append((action, action.status))
                continue

            self.log(f"performing action of type {action_dict['action_type']}...", level=logging.INFO)    
            if (action_dict['action_type'] == ActionTypes.IDLE.value 
                or action_dict['action_type'] == ActionTypes.TRAVEL.value
                or action_dict['action_type'] == ActionTypes.MANEUVER.value):
                
                # this action affects the agent's state

                # unpackage action
                action = action_from_dict(**action_dict)
                t = self.get_current_time()

                # modify the agent's state
                status, dt = self.state.perform_action(action, t)

                if dt > 0:
                    try:
                        # perfrom time wait if needed
                        await self.sim_wait(dt)

                        # modify the agent's state
                        t = self.get_current_time()
                        status, dt = self.state.perform_action(action, t)

                    except asyncio.CancelledError:
                        return

                # update action completion status
                action.status = status

            elif action_dict['action_type'] == ActionTypes.BROADCAST_MSG.value:
                # unpack action
                action = BroadcastMessageAction(**action_dict)
                msg_out = message_from_dict(**action.msg)

                # update state
                self.state.update_state(self.get_current_time(), status=SimulationAgentState.MESSAGING)
                self.state_history.append(self.state.to_dict())
                
                # perform action
                msg_out.dst = self.get_network_name()
                await self.send_peer_broadcast(msg_out)

                # set task complation
                action.status = AgentAction.COMPLETED
            
            
            elif action_dict['action_type'] == ActionTypes.WAIT_FOR_MSG.value:
                # unpack action 
                task = WaitForMessages(**action_dict)
                t_curr = self.get_current_time()
                self.state.update_state(t_curr, status=SimulationAgentState.LISTENING)
                self.state_history.append(self.state.to_dict())

                if not self.external_inbox.empty():
                    action.status = AgentAction.COMPLETED
                else:
                    if isinstance(self._clock_config, FixedTimesStepClockConfig):
                        # give the agent time to finish sending/processing messages before submitting a tic-request
                        await asyncio.sleep(1e-2)

                    receive_broadcast = asyncio.create_task(self.external_inbox.get())
                    timeout = asyncio.create_task(self.sim_wait(task.t_end - t_curr))

                    done, _ = await asyncio.wait([timeout, receive_broadcast], return_when=asyncio.FIRST_COMPLETED)

                    if receive_broadcast in done:
                        # a mesasge was received before the timer ran out; cancel timer
                        try:
                            timeout.cancel()
                            await timeout

                        except asyncio.CancelledError:
                            # restore message to inbox so it can be processed during `sense()`
                            await self.external_inbox.put(receive_broadcast.result())    

                            # update action completion status
                            action.status = AgentAction.COMPLETED                
                    else:
                        # timer ran out or time advanced
                        try:
                            # cancel listen to broadcast
                            receive_broadcast.cancel()
                            await receive_broadcast

                        except asyncio.CancelledError:
                            # update action completion status
                            if self.external_inbox.empty():
                                action.status = AgentAction.PENDING
                            else:
                                action.status = AgentAction.COMPLETED
            
            elif action_dict['action_type'] == ActionTypes.MEASURE.value:
                # unpack action 
                action = MeasurementAction(**action_dict)

                # perform action
                self.state : SimulationAgentState
                measurement_req = MeasurementRequest(**action.measurement_req)
                
                self.state.update_state(self.get_current_time(), 
                                        status=SimulationAgentState.MEASURING)
                try:
                    # send a measurement data request to the environment
                    measurement = MeasurementResultsRequest(self.get_element_name(),
                                                            SimulationElementRoles.ENVIRONMENT.value, 
                                                            self.state.to_dict(), 
                                                            action_dict
                                                            )

                    dst, src, measurement_dict = await self.send_peer_message(measurement)

                    # add measurement to environment inbox to be processed during `sensing()`
                    await self.environment_inbox.put((dst, src, measurement_dict))

                    # wait for the designated duration of the measurmeent 
                    await self.sim_wait(measurement_req.duration)  # TODO only compensate for the time lost between queries
                    
                except asyncio.CancelledError:
                    return
            else:
                # ignore action
                self.log(f"action of type {action_dict['action_type']} not yet supported. ignoring...", level=logging.INFO)
                action.status = AgentAction.ABORTED  
                
            self.log(f"finished performing action of type {action_dict['action_type']}! action completion status: {action.status}", level=logging.INFO)
            statuses.append((action, action.status))

            if (action.status in [
                                    AgentAction.COMPLETED, 
                                    AgentAction.PENDING,
                                    AgentAction.ABORTED
                                ]):
                dt = time.perf_counter() - t_0
                if action_dict['action_type'] not in self.stats:
                    self.stats[action_dict['action_type']] = []    
                self.stats[action_dict['action_type']].append(dt)

        self.log(f'returning {len(statuses)} statuses', level=logging.DEBUG)
        return statuses

    async def teardown(self) -> None:
        # log agent capabilities
        # log state 
        n_decimals = 3
        headers = ['t', 'x_pos', 'y_pos', 'z_pos', 'x_vel', 'y_vel', 'z_vel', 'status']
        data = []

        # out += '\nt, pos, vel, status\n'
        for state_dict in self.state_history:
            line_data = [
                            np.round(state_dict['t'],3),

                            np.round(state_dict['pos'][0],n_decimals),
                            np.round(state_dict['pos'][1],n_decimals),
                            np.round(state_dict['pos'][2],n_decimals),

                            np.round(state_dict['vel'][0],n_decimals),
                            np.round(state_dict['vel'][1],n_decimals),
                            np.round(state_dict['vel'][2],n_decimals),
                            
                            state_dict['status']
                        ]
            data.append(line_data)
        
        state_df = DataFrame(data,columns=headers)
        self.log(f'\nPayload: {self.payload}\nSTATE HISTORY\n{str(state_df)}\n', level=logging.WARNING)
        state_df.to_csv(f"{self.results_path}/states.csv", index=False)

        # log performance stats
        headers = ['routine','t_avg','t_std','t_med','n']
        data = []

        for routine in self.stats:
            t_avg = np.mean(self.stats[routine])
            t_std = np.std(self.stats[routine])
            t_median = np.median(self.stats[routine])
            n = len(self.stats[routine])

            line_data = [ 
                            routine,
                            np.round(t_avg,n_decimals),
                            np.round(t_std,n_decimals),
                            np.round(t_median,n_decimals),
                            n
                            ]
            data.append(line_data)

        stats_df = DataFrame(data, columns=headers)
        self.log(f'\nAGENT RUN-TIME STATS\n{str(stats_df)}\n', level=logging.WARNING)
        stats_df.to_csv(f"{self.results_path}/agent_runtime_stats.csv", index=False)

    async def sim_wait(self, delay: float) -> None:
        try:  
            if (
                isinstance(self._clock_config, FixedTimesStepClockConfig) 
                or isinstance(self._clock_config, EventDrivenClockConfig)
                ):
                if delay < 1e-6: 
                    ignored = None
                    return

                # desired time not yet reached
                t0 = self.get_current_time()
                tf = t0 + delay

                # check if failure or critical state will be reached first
                self.state : SimulationAgentState
                if self.state.engineering_module is not None:
                    t_failure = self.state.engineering_module.predict_failure() 
                    t_crit = self.state.engineering_module.predict_critical()
                    t_min = min(t_failure, t_crit)
                    tf = t_min if t_min < tf else tf
                
                # wait for time update        
                ignored = []   
                while self.get_current_time() <= t0:
                    # send tic request
                    tic_req = TicRequest(self.get_element_name(), t0, tf)
                    toc_msg = None
                    confirmation = None
                    confirmation = await self._send_manager_msg(tic_req, zmq.PUB)

                    self.log(f'tic request for {tf}[s] sent! waiting on toc broadcast...')
                    dst, src, content = await self.manager_inbox.get()
                    
                    if content['msg_type'] == ManagerMessageTypes.TOC.value:
                        # update clock
                        toc_msg = TocMessage(**content)
                        await self.update_current_time(toc_msg.t)
                        self.log(f'toc received! time updated to: {self.get_current_time()}[s]')
                    else:
                        # ignore message
                        self.log(f'some other manager message was received. ignoring...')
                        ignored.append((dst, src, content))

            elif isinstance(self._clock_config, AcceleratedRealTimeClockConfig):
                await asyncio.sleep(delay / self._clock_config.sim_clock_freq)

            else:
                raise NotImplementedError(f'`sim_wait()` for clock of type {type(self._clock_config)} not yet supported.')
        
        except asyncio.CancelledError as e:
            # if still waiting on  cancel request
            if confirmation is not None and toc_msg is None:
                tic_cancel = CancelTicRequest(self.get_element_name(), t0, tf)
                await self._send_manager_msg(tic_cancel, zmq.PUB)

            raise e

        finally:
            if (
                isinstance(self._clock_config, FixedTimesStepClockConfig) 
                or isinstance(self._clock_config, EventDrivenClockConfig)
                ) and ignored is not None:

                # forward all ignored messages as manager messages
                for dst, src, content in ignored:
                    await self.manager_inbox.put((dst,src,content))
