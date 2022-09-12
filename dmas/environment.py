from abc import abstractmethod
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
import os
# os.environ['PYTHONASYNCIODEBUG'] = '0'
import asyncio
import json
import logging
import random
import time
from urllib import request
import zmq.asyncio
from orbitdata import OrbitData

from messages import BroadcastTypes, RequestTypes
from modules import  Module
from utils import Container, SimClocks
import pandas as pd

"""
--------------------------------------------------------
 ____                                                                         __      
/\  _`\                    __                                                /\ \__   
\ \ \L\_\    ___   __  __ /\_\  _ __   ___     ___     ___ ___      __    ___\ \ ,_\  
 \ \  _\L  /' _ `\/\ \/\ \\/\ \/\`'__\/ __`\ /' _ `\ /' __` __`\  /'__`\/' _ `\ \ \/  
  \ \ \L\ \/\ \/\ \ \ \_/ |\ \ \ \ \//\ \L\ \/\ \/\ \/\ \/\ \/\ \/\  __//\ \/\ \ \ \_ 
   \ \____/\ \_\ \_\ \___/  \ \_\ \_\\ \____/\ \_\ \_\ \_\ \_\ \_\ \____\ \_\ \_\ \__\
    \/___/  \/_/\/_/\/__/    \/_/\/_/ \/___/  \/_/\/_/\/_/\/_/\/_/\/____/\/_/\/_/\/__/
                                                                                      
 /'\_/`\            /\ \         /\_ \            
/\      \    ___    \_\ \  __  __\//\ \      __   
\ \ \__\ \  / __`\  /'_` \/\ \/\ \ \ \ \   /'__`\ 
 \ \ \_/\ \/\ \L\ \/\ \L\ \ \ \_\ \ \_\ \_/\  __/ 
  \ \_\\ \_\ \____/\ \___,_\ \____/ /\____\ \____\
   \/_/ \/_/\/___/  \/__,_ /\/___/  \/____/\/____/                                                                                                                                                    
--------------------------------------------------------
"""

class EnvironmentModuleTypes(Enum):
    TIC_REQUEST_MODULE = 'TIC_REQUEST_MODULE'
    ECLIPSE_EVENT_MODULE = 'ECLIPSE_EVENT_MODULE'
    GP_ACCESS_EVENT_MODULE = 'GP_ACCESS_EVENT_MODULE'
    GS_ACCESS_EVENT_MODULE = 'GS_ACCESS_EVENT_MODULE'
    AGENT_ACCESS_EVENT_MODULE = 'AGENT_ACCESS_EVENT_MODULE'
    AGENT_EXTERNAL_PROPAGATOR_MODULE = 'AGENT_EXTERNAL_PROPAGATOR_MODULE'

class TicRequestModule(Module):
    def __init__(self, parent_environment) -> None:
        super().__init__(EnvironmentModuleTypes.TIC_REQUEST_MODULE.value, parent_environment, submodules=[], n_timed_coroutines=0)

    async def activate(self):
        await super().activate()
        self.tic_request_queue = asyncio.Queue()
        self.tic_request_queue_sorted = []

    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            dst_name = msg['dst']
            if dst_name != self.name:
                await self.send_internal_message(msg)
            else:
                if 'REQUEST' in msg['@type'] and RequestTypes[msg['@type']] is RequestTypes.TIC_REQUEST:
                    # if a tic request is received, add to tic_request_queue
                    t = msg['t']
                    self.log(f'Received tic request for time {t}!')
                    await self.tic_request_queue.put(t)
                else:
                    # if not a tic request, dump message 
                    return
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        try:
            n_routines = self.parent_module.NUMBER_OF_TIMED_COROUTINES_AGENTS + self.parent_module.NUMBER_OF_TIMED_COROUTINES
            while True:
                if self.CLOCK_TYPE is SimClocks.SERVER_STEP:
                    # append tic request to request list
                    self.log(f'Waiting for next tic request ({len(self.tic_request_queue_sorted)} / {n_routines})...')

                    tic_req = await self.tic_request_queue.get()
                    self.tic_request_queue_sorted.append(tic_req)

                    self.log(f'Tic request received! Queue status: ({len(self.tic_request_queue_sorted)} / {n_routines})')
                        
                    # wait until all timed coroutines from all agents have entered a wait period and have submitted their respective tic requests
                    if len(self.tic_request_queue_sorted) == n_routines:
                        # sort requests
                        self.log('Sorting tic requests...')
                        print(self.tic_request_queue_sorted)
                        self.tic_request_queue_sorted.sort(reverse=True)
                        self.log(f'Tic requests sorted: {self.tic_request_queue_sorted}')

                        # skip time to earliest requested time
                        t_next = self.tic_request_queue_sorted.pop()

                        # send a broadcast request to parent environment              
                        msg_dict = dict()
                        msg_dict['src'] = self.name
                        msg_dict['dst'] = self.parent_module.name
                        msg_dict['@type'] = BroadcastTypes.TIC_EVENT.name
                        msg_dict['server_clock'] = t_next

                        t = msg_dict['server_clock']
                        self.log(f'Submitting broadcast request for tic with server clock at t={t}')

                        await self.send_internal_message(msg_dict)
                else:
                    await self.sim_wait(1e6, module_name=self.name)
        except asyncio.CancelledError:
            return


class ScheduledEventModule(Module): 
    """
    In charge of broadcasting scheduled events to all agents
    """
    def __init__(self, name: EnvironmentModuleTypes,parent_environment) -> None:   
        super().__init__(name, parent_environment, submodules=[], n_timed_coroutines=1)

        # initialize scheduled events data and sort
        self.event_data = self.compile_event_data()
        self.event_data = self.event_data.sort_values(by=['time index'])

        # if data does not have proper format, reject
        if not self.check_data_format():
            raise Exception('Event data loaded in an incorrect format.')

        # get scheduled event time-step
        self.time_step = -1
        for agent_name in self.parent_module.parent_module.orbit_data:
            orbit_data = self.parent_module.parent_module.orbit_data[agent_name]
            self.time_step = orbit_data.time_step
            break

    @abstractmethod
    def compile_event_data(self) -> pd.DataFrame:
        """
        Loads event data and returns a DataFrame containing information of all scheduled events to be broadcasted
        """
        pass

    @abstractmethod
    def row_to_msg_dict(self, row) -> dict:
        """converts a row of from 'event_data' into a message to be broadcast to other agents"""
        pass

    async def activate(self):
        """
        Initiates event scheduling by loading event information
        """
        await super().activate()
        self.log(self.event_data)
    
    def check_data_format(self) -> bool:
        """
        Verifyes if the 'compile_event_data()' method loaded data in the appropriate format.
        Event must at least specify:
            -'time index': when the event occurrs
            -'agent name': which agent is affected by said event
            -'rise': whether this broadcast would signal the start (True) or the end (False) of an event
        """
        required_columns = ['time index', 'agent name', 'rise']
        
        if len(required_columns) > len(self.event_data.columns):
            return False
        
        for required_column in required_columns:
            if required_column not in self.event_data.columns:
                return False

        return True

    async def internal_message_handler(self, msg):
        """
        Does not interact with other modules. Any message received will be ignored
        """
        try:
            dst_name = msg['dst']
            if dst_name != self.name:
                await self.send_internal_message(msg)
            else:
                # dumps all incoming messages
                return
        except asyncio.CancelledError:
            return    

    async def coroutines(self):
        """
        Parses through event data and sends broadcast requests to parent module
        """
        try:
            for _, row in self.event_data.iterrows():
                # get next scheduled event message
                msg_dict = self.row_to_msg_dict(row)

                # wait for said event to start
                t_next = msg_dict['server_clock']
                await self.sim_wait_to(t_next, module_name=self.name)

                broadcast_type = msg_dict['@type']
                agent_name = msg_dict['agent']

                if row['rise']:
                    self.log(f'Submitting broadcast request for {broadcast_type} start with server clock at t={t_next} for agent {agent_name}', module_name=self.name)
                else:
                    self.log(f'Submitting broadcast request for {broadcast_type} end with server clock at t={t_next} for agent {agent_name}', module_name=self.name)

                # send a broadcast request to parent environment      
                await self.send_internal_message(msg_dict)

            # once all events have occurred, go to sleep until the end of the simulation
            while True:
                await self.sim_wait(1e6, module_name=self.name)
        except asyncio.CancelledError:
            return

class EclipseEventModule(ScheduledEventModule):
    """
    In charge of broadcasting eclipse events to all agents
    """
    def __init__(self, parent_environment) -> None:
        super().__init__(EnvironmentModuleTypes.ECLIPSE_EVENT_MODULE.name, parent_environment)

    def row_to_msg_dict(self, row) -> dict:
        t_next = row['time index'] * self.time_step
        agent_name = row['agent name']
        rise = row['rise']

        return BroadcastTypes.create_eclipse_event_broadcast(self.name, self.parent_module.parent_module.name, agent_name, rise, t_next)
        
    def compile_event_data(self) -> pd.DataFrame:
        orbit_data = self.parent_module.parent_module.orbit_data
        eclipse_data = pd.DataFrame(columns=['time index', 'agent name', 'rise'])
        
        for agent in orbit_data:
            agent_eclipse_data = orbit_data[agent].eclipse_data
            nrows, _ = agent_eclipse_data.shape
            agent_name_column = [agent] * nrows

            eclipse_rise = agent_eclipse_data.get(['start index'])
            eclipse_rise = eclipse_rise.rename(columns={'start index': 'time index'})
            eclipse_rise['agent name'] = agent_name_column
            eclipse_rise['rise'] = [True] * nrows

            eclipse_set = agent_eclipse_data.get(['end index'])
            eclipse_set = eclipse_set.rename(columns={'end index': 'time index'})
            eclipse_set['agent name'] = agent_name_column
            eclipse_set['rise'] = [False] * nrows

            eclipse_merged = pd.concat([eclipse_rise, eclipse_set])
            if len(eclipse_data) == 0:
                eclipse_data = eclipse_merged
            else:
                eclipse_data = pd.concat([eclipse_data, eclipse_merged])

        return eclipse_data

class GndStatAccessEventModule(ScheduledEventModule):
    def __init__(self, parent_environment) -> None:
        super().__init__(EnvironmentModuleTypes.GS_ACCESS_EVENT_MODULE.name, parent_environment)

    def row_to_msg_dict(self, row) -> dict:
        t_next = row['time index'] * self.time_step
        agent_name = row['agent name']
        rise = row['rise']
        gndStat_id = row['gndStn id']
        gndStat_name = row['gndStn name']
        lat = row['lat [deg]']
        lon = row['lon [deg]']

        return BroadcastTypes.create_gs_access_event_broadcast(self.name, self.parent_module.parent_module.name, agent_name, rise, t_next,
                                                                gndStat_name, gndStat_id, lat, lon)

    def compile_event_data(self) -> pd.DataFrame:
        orbit_data = self.parent_module.parent_module.orbit_data
        gs_access_data = pd.DataFrame(columns=['time index', 'agent name', 'rise', 'gndStn id', 'gndStn name','lat [deg]','lon [deg]'])

        for agent in orbit_data:
            agent_gs_access_data = orbit_data[agent].gs_access_data
            nrows, _ = agent_gs_access_data.shape

            # rise events
            access_rise = agent_gs_access_data.copy()
            access_rise = access_rise.rename(columns={'start index': 'time index'})
            access_rise.pop('end index')
            access_rise['agent name'] = [agent] * nrows
            access_rise['rise'] = [True] * nrows

            # set events
            access_set = agent_gs_access_data.copy()
            access_set = access_set.rename(columns={'end index': 'time index'})
            access_set.pop('start index')
            access_set['agent name'] = [agent] * nrows
            access_set['rise'] = [False] * nrows

            access_merged = pd.concat([access_rise, access_set])
            if len(gs_access_data) == 0:
                gs_access_data = access_merged
            else:
                gs_access_data = pd.concat([gs_access_data, access_merged])

        return gs_access_data

class GPAccessEventModule(ScheduledEventModule):
    def __init__(self, parent_environment) -> None:
        super().__init__(EnvironmentModuleTypes.GP_ACCESS_EVENT_MODULE.name, parent_environment)

    def row_to_msg_dict(self, row) -> dict:
        t_next = row['time index'] * self.time_step
        agent_name = row['agent name']
        rise = row['rise']
        grid_index = row['grid index']
        gp_index = row['GP index']
        lat = row['lat [deg]']
        lon = row['lon [deg]']

        return BroadcastTypes.create_gp_access_event_broadcast(self.name, self.parent_module.parent_module.name, agent_name, rise, t_next,
                                                                grid_index, gp_index, lat, lon)

    def compile_event_data(self) -> pd.DataFrame:
        orbit_data = self.parent_module.parent_module.orbit_data
        coverage_data = pd.DataFrame(columns=['time index', 'agent name', 'rise', 'instrument', 'mode', 'grid index', 'GP index', 'pnt-opt index', 'lat [deg]', 'lon [deg]',])

        for agent in orbit_data:
            agent_gp_coverate_data =orbit_data[agent].gp_access_data
            grid_data = orbit_data[agent].grid_data

            for grid_index in range(len(grid_data)):
                grid = grid_data[grid_index]

                for _, grid_point in grid.iterrows():
                    gp_index = grid_point['GP index']

                    gp_data = agent_gp_coverate_data.query('`GP index` == @gp_index & `grid index` == @grid_index')
                    gp_data = gp_data.sort_values(by=['time index'])

                    intervals = []
                    for _, row in gp_data.iterrows():
                        t_index = row['time index']

                        interval_found = False
                        for interval in intervals:
                            i_interval = intervals.index(interval)
                            t_start, t_end = interval

                            if t_index == t_start - 1:
                                t_start = t_index
                                interval_found = True
                            elif t_index == t_end + 1:
                                t_end = t_index
                                interval_found = True

                            if interval_found:
                                intervals[i_interval] = [t_start, t_end]
                                break                                                        

                        if not interval_found:
                            interval = [t_index, t_index]
                            intervals.append(interval)

                    for interval in intervals:
                        t_rise, t_set = interval
                        
                        access_rise = gp_data.query('`time index` == @t_rise').copy()
                        access_rise['rise'] = [True]

                        access_set = gp_data.query('`time index` == @t_set').copy()
                        access_set['rise'] = [False]

                        access_merged = pd.concat([access_rise, access_set])

                        if len(coverage_data) == 0:
                            coverage_data = access_merged
                        else:
                            coverage_data = pd.concat([coverage_data, access_merged])
            
        return coverage_data

class AgentAccessEventModule(ScheduledEventModule):
    def __init__(self, parent_environment) -> None:
        super().__init__(EnvironmentModuleTypes.AGENT_ACCESS_EVENT_MODULE.name, parent_environment)

    def row_to_msg_dict(self, row) -> dict:
        t_next = row['time index'] * self.time_step
        agent_name = row['agent name']
        rise = row['rise']
        target = row['target']

        return BroadcastTypes.create_agent_access_event_broadcast(self.name, self.parent_module.parent_module.name, rise, t_next, agent_name, target)

    def compile_event_data(self) -> pd.DataFrame:
        orbit_data = self.parent_module.parent_module.orbit_data  
        agent_access_data = pd.DataFrame(columns=['time index', 'agent name', 'rise', 'target'])
        
        for src in orbit_data:
            isl_data = orbit_data[src].isl_data
            for dst in isl_data:
                nrows, _ = isl_data[dst].shape
                
                # rise data
                access_rise = isl_data[dst].copy()
                access_rise = access_rise.rename(columns={'start index': 'time index'})
                access_rise.pop('end index')
                access_rise['agent name'] = [src] * nrows
                access_rise['rise'] = [True] * nrows
                access_rise['target'] = [dst] * nrows

                # set data
                access_set = isl_data[dst].copy()
                access_set = access_set.rename(columns={'end index': 'time index'})
                access_set.pop('start index')
                access_set['agent name'] = [src] * nrows
                access_set['rise'] = [False] * nrows
                access_set['target'] = [dst] * nrows

                access_merged = pd.concat([access_rise, access_set])
                if len(agent_access_data) == 0:
                    agent_access_data = access_merged
                else:
                    agent_access_data = pd.concat([agent_access_data, access_merged])
        
        return agent_access_data

class AgentExternalStatePropagator(Module):
    """
    Module in charge of propagating the external state of the agents present in this simulated scenario
    """
    def __init__(self, parent_module) -> None:
        super().__init__(EnvironmentModuleTypes.AGENT_EXTERNAL_PROPAGATOR_MODULE, 
                            parent_module, 
                            submodules=[], 
                            n_timed_coroutines=1)
        self.submodules = [EclipseEventModule(self), 
                            GPAccessEventModule(self),
                            GndStatAccessEventModule(self),
                            AgentAccessEventModule(self)]

"""
--------------------------------------------------------
 ____                                                                         __      
/\  _`\                    __                                                /\ \__   
\ \ \L\_\    ___   __  __ /\_\  _ __   ___     ___     ___ ___      __    ___\ \ ,_\  
 \ \  _\L  /' _ `\/\ \/\ \\/\ \/\`'__\/ __`\ /' _ `\ /' __` __`\  /'__`\/' _ `\ \ \/  
  \ \ \L\ \/\ \/\ \ \ \_/ |\ \ \ \ \//\ \L\ \/\ \/\ \/\ \/\ \/\ \/\  __//\ \/\ \ \ \_ 
   \ \____/\ \_\ \_\ \___/  \ \_\ \_\\ \____/\ \_\ \_\ \_\ \_\ \_\ \____\ \_\ \_\ \__\
    \/___/  \/_/\/_/\/__/    \/_/\/_/ \/___/  \/_/\/_/\/_/\/_/\/_/\/____/\/_/\/_/\/__/                                                         
 ____                                           
/\  _`\                                         
\ \,\L\_\     __   _ __   __  __     __   _ __  
 \/_\__ \   /'__`\/\`'__\/\ \/\ \  /'__`\/\`'__\
   /\ \L\ \/\  __/\ \ \/ \ \ \_/ |/\  __/\ \ \/ 
   \ `\____\ \____\\ \_\  \ \___/ \ \____\\ \_\ 
    \/_____/\/____/ \/_/   \/__/   \/____/ \/_/                                                                                                                                                   
--------------------------------------------------------
"""

def count_number_of_subroutines(module: Module):
    count = module.NUMBER_OF_TIMED_COROUTINES
    for submodule in module.submodules:
        count += count_number_of_subroutines(submodule)
    return count

def is_port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

class EnvironmentServer(Module):
    """
    Server encompasing all environment processes. Main module regulates simulation start and end as well as managing network ledgers for all agents to communicate with eachother.
    Submodules manage the environment clock and the scenario simulation. The latter concerns propagating the state of the environment as a function of time as well as propagating
    the external states of the agents. 
    """
    ENVIRONMENT_SERVER_NAME = 'ENV'

    def __init__(self, scenario_dir, agent_name_list: list, duration, clock_type: SimClocks = SimClocks.REAL_TIME, simulation_frequency: float = -1) -> None:
        super().__init__(EnvironmentServer.ENVIRONMENT_SERVER_NAME, n_timed_coroutines=1)
        # Constants
        self.AGENT_NAME_LIST = []                                       # List of names of agent present in the simulation
        self.NUMBER_AGENTS = len(agent_name_list)                       # Number of agents present in the simulation
        self.NUMBER_OF_TIMED_COROUTINES_AGENTS = 0                      # Number of timed co-routines to be performed by other agents

        for agent_name in agent_name_list:
            self.AGENT_NAME_LIST.append(agent_name)

        # simulation start and end tracking lists
        self.alive_subscribers = []
        self.offline_subscribers = []

        # simulation clock constants
        self.CLOCK_TYPE = clock_type                                    # Clock type being used in this simulation
        self.DURATION = duration                                        # Duration of simulation in simulation-time

        self.SIMULATION_FREQUENCY = None
        if self.CLOCK_TYPE == SimClocks.REAL_TIME:
            self.SIMULATION_FREQUENCY = 1
        elif self.CLOCK_TYPE == SimClocks.REAL_TIME_FAST:
            self.SIMULATION_FREQUENCY = simulation_frequency            # Ratio of simulation-time seconds to real-time seconds
        elif self.CLOCK_TYPE != SimClocks.SERVER_STEP:
            raise Exception(f'Simulation clock of type {clock_type.value} not yet supported')
        
        if simulation_frequency < 0 and self.CLOCK_TYPE == SimClocks.REAL_TIME_FAST:
            raise Exception('Simulation frequency needed to initiate simulation with a REAL_TIME_FAST clock.')

        # propagate orbit and coverage information
        self.orbit_data = OrbitData.from_directory(scenario_dir)

        # set up submodules
        self.submodules = [ TicRequestModule(self), 
                            AgentExternalStatePropagator(self)
                          ]
        
        # set up results dir
        self.SCENARIO_RESULTS_DIR, self.ENVIRONMENT_RESULTS_DIR = self.set_up_results_directory(scenario_dir)

        # set up loggers
        [self.message_logger, self.request_logger, self.state_logger, self.actions_logger] = self.set_up_loggers()

        print('Environment Initialized!')

    async def live(self):
        """
        MAIN FUNCTION 
        executes event loop for ayncronous processes within the environment
        """
        # Activate 
        await self.activate()

        # Run simulation
        await self.run()

    async def activate(self):
        """
        Initiates and executes commands that are thread-sensitive but that must be performed before the simulation starts.
        """
        self.log('Starting activation routine...', level=logging.INFO)
        
        # activate network ports
        self.log('Configuring network ports...', level=logging.INFO)
        await self.network_config()
        self.log('Network configuration completed!', level=logging.INFO)

        # Wait for agents to initialize their own network ports
        self.log(f"Waiting for {self.NUMBER_AGENTS} to initiate...", level=logging.INFO)
        subscriber_to_port_map =await self.sync_agents()
        self.log(f"All subscribers initalized! Starting simulation...", level=logging.INFO)
        
        # broadcasting simulation start
        await self.broadcast_sim_start(subscriber_to_port_map)

        self.log(f'Activating environment submodules...')
        await super().activate()
        self.log('Environment Activated!', level=logging.INFO)
    
    async def run(self):        
        """
        Performs simulation actions.

        Runs every module owned by the agent. Stops when one of the modules goes off-line, completes its run() routines, 
        or the environment sends a simulation end broadcast.
        """  
        # begin simulation
        self.log(f"Starting simulation...", level=logging.INFO)
        await super().run()

    async def _shut_down(self):
        """
        Terminate processes 
        """
        self.log(f"Shutting down...", level=logging.INFO)

        # broadcast simulation end
        # await asyncio.sleep(random.random())
        await self.broadcast_sim_end()

        # close network ports  
        self.log(f"Closing all network sockets...") 
        self.publisher.close()
        self.reqservice.close()
        self.context.term()
        self.log(f"Network sockets closed.", level=logging.INFO)
        
        self.log(f"Simulation done, good night!", level=logging.INFO)

    """
    --------------------
    CO-ROUTINES AND TASKS
    --------------------
    """
    async def coroutines(self):
        """
        Executes list of coroutine tasks to be excuted by the environment. These coroutine task incluide:
            1- 'sim_end_timer': counts down to the end of the simulation
            2- 'request_handler': listens to 'reqservice' port and handles agent requests being sent
            3- 'broadcast_handler': receives broadcast requests and publishes them to all agents
        """
        sim_end_timer = asyncio.create_task(self.sim_wait(self.DURATION))
        sim_end_timer.set_name('sim_timer')
        request_handler = asyncio.create_task(self.request_handler())
        request_handler.set_name('req_handler')
        broadcast_handler = asyncio.create_task(self.broadcast_handler())
        broadcast_handler.set_name('broadast_handler')
        routines = [sim_end_timer, request_handler, broadcast_handler]

        _, pending = await asyncio.wait(routines, return_when=asyncio.FIRST_COMPLETED)
        print('DONE')

        done_name = None
        for coroutine in routines:
            if coroutine not in pending:
                done_name = coroutine.get_name()
        self.log(f"{done_name} completed!", level=logging.INFO)

        for p in pending:
            self.log(f"Terminating {p.get_name()}...")
            p.cancel()
            await p

        self.log(f"Simulation time completed!", level=logging.INFO)

    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            dst_name = msg['dst']
            if dst_name != self.name:
                self.log(f'Message not intended for this module. Rerouting.')
                await self.send_internal_message(msg)
            else:
                # if the message is of type broadcast, send to broadcast handler
                msg_type = msg['@type']
                self.log(f'Handling message of type {msg_type}...')

                if ('REQUEST' not in msg_type and 
                    (BroadcastTypes[msg_type] is BroadcastTypes.TIC_EVENT
                    or BroadcastTypes[msg_type] is BroadcastTypes.ECLIPSE_EVENT
                    or BroadcastTypes[msg_type] is BroadcastTypes.GP_ACCESS_EVENT
                    or BroadcastTypes[msg_type] is BroadcastTypes.GS_ACCESS_EVENT
                    or BroadcastTypes[msg_type] is BroadcastTypes.AGENT_ACCESS_EVENT)):
                        self.log(f'Submitting message of type {msg_type} for publishing...')
                        await self.publisher_queue.put(msg)
                        
                elif RequestTypes[msg_type] is RequestTypes.TIC_REQUEST:
                    # if an submodule sends a tic request, forward to tic request submodule
                    msg['dst'] = EnvironmentModuleTypes.TIC_REQUEST_MODULE
                    
                    self.log(f'Forwarding Tic request to relevant submodule...')
                    await self.send_internal_message(msg)
                else:
                    self.log(f'Dumping internal message of type {msg_type}.')

                self.log(f'Done handling message.')
                return
        except asyncio.CancelledError:
            return

    async def request_handler(self):
        """
        Listens to 'reqservice' socket and handles agent requests accordingly. List of supported requests:
            1- tic_request: agents ask to be notified when a certain time has passed in the environment's clock    
            2- agent_access_request: agent asks the enviroment if the agent is capable of accessing another agent at the current simulation time
            3- gp_access_request: agent asks the enviroment if the agent is capable of accessing a ground point at the current simulation time
            4- gs_access_request: agent asks the enviroment if the agent is capable of accessing a ground station at the current simulation time
            5- agent_information_request: agent asks for information regarding its current position, velocity, and eclipse at the current simulation time
            6- observation_request: agent requests environment information regarding a the state of a ground point at the current simulation time
            7- agent_end_confirmation: agent notifies the environment that it has successfully terminated its operations

        Only tic request create future broadcast tasks. The rest require an immediate response from the environment.
        """
        async def request_worker(request):
            try:
                # check request message format
                if not RequestTypes.format_check(request):
                    # if request does not match any of the standard request format, dump and continue
                    self.log(f'Request does not match the standard format for a request message. Dumping request...')
                    await self.reqservice.send_string('')
                    return
        
                # unpackage message type and handle accordingly 
                req_type = request.get('@type')
                req_type = RequestTypes[req_type]

                if req_type is RequestTypes.TIC_REQUEST:
                    # send reception confirmation to agent
                    await self.reqservice.send_string('')

                    # schedule tic request
                    t_req = request.get('t')
                    self.log(f'Received tic request for t_req={t_req}!')

                    # change source and destination to internal modules
                    request['src'] = self.name
                    request['dst'] = EnvironmentModuleTypes.TIC_REQUEST_MODULE.name

                    # send to internal message router for forwarding
                    await self.send_internal_message(request)

                elif req_type is RequestTypes.AGENT_ACCESS_REQUEST:
                    # unpackage message
                    src = request['src']
                    target = request['target']
                    
                    t_curr = self.get_current_time()
                    self.log(f'Received agent access request from {src} to {target} at simulation time t={t_curr}!')

                    # query agent access database
                    request['result'] = self.orbit_data[src].is_accessing_agent(target, t_curr) 
                    
                    # change source and destination for response message
                    request['dst'] = request['src']
                    request['src'] = self.name
                    req_json = json.dumps(request)
                    
                    # send response to agent
                    await self.reqservice.send_json(req_json)
                
                elif req_type is RequestTypes.GP_ACCESS_REQUEST:
                    # unpackage message
                    src = request['src']
                    lat = request['lat']
                    lon = request['lon']

                    t_curr = self.get_current_time()
                    self.log(f'Received ground point access request from {src} to ({lat}°, {lon}°) at simulation time t={t_curr}!')

                    # query ground point access database
                    _, _, gp_lat, gp_lon = self.orbit_data[src].find_gp_index(lat, lon)

                    request['result'] = self.orbit_data[src].is_accessing_ground_point(gp_lat, gp_lon, t_curr)
                    request['gp_lat'] = gp_lat
                    request['gp_lon'] = gp_lon
                    
                    # change source and destination for response message
                    request['dst'] = request['src']
                    request['src'] = self.name
                    req_json = json.dumps(request)

                    # send response to agent
                    await self.reqservice.send_json(req_json)

                elif req_type is RequestTypes.GS_ACCESS_REQUEST:
                    # unpackage message
                    src = request['src']
                    target = request['target']

                    t_curr = self.get_current_time()
                    self.log(f'Received ground station access request from {src} to {target} at simulation time t={t_curr}!')

                    # query ground point access database
                    request['result'] = self.orbit_data[src].is_accessing_ground_station(target, t_curr) 
                    
                    # change source and destination for response message
                    request['dst'] = request['src']
                    request['src'] = self.name
                    req_json = json.dumps(request)
                    
                    # send response to agent
                    await self.reqservice.send_json(req_json)

                elif req_type is RequestTypes.AGENT_INFO_REQUEST:
                    # unpackage message
                    src = request['src']

                    t_curr = self.get_current_time()
                    self.log(f'Received agent information request from {src} at simulation time t={t_curr}!')

                    # query agent state database
                    pos, vel, is_eclipse = self.orbit_data[src].get_orbit_state( t_curr) 
                    results = dict()
                    results['pos'] = pos
                    results['vel'] = vel
                    results['eclipse'] = is_eclipse

                    request['result'] = results
                    
                    # change source and destination for response message
                    request['dst'] = request['src']
                    request['src'] = self.name                    
                    req_json = json.dumps(request)
                    
                    # send response to agent
                    await self.reqservice.send_json(req_json)

                # elif req_type is RequestTypes.OBSERVATION_REQUEST:
                #     await self.reqservice.send_string('')
                #     pass

                elif req_type is RequestTypes.AGENT_END_CONFIRMATION:
                    # register that agent node has gone offline mid-simulation
                    # (this agent node won't be considered when broadcasting simulation end)
                    src = request['src']

                    if src not in self.offline_subscribers:
                        self.offline_subscribers.append(src)

                else:
                    # if request type is not supported, dump and ignore message
                    self.log(f'Request of type {req_type.value} not yet supported. Dumping request.')
                    self.reqservice.send_string('')
                    return
            except asyncio.CancelledError:
                self.log('Request handling cancelled. Sending blank response...')
                await self.reqservice.send_string('')

        
        try:            
            self.log('Acquiring access to request service port...')
            await self.reqservice_lock.acquire()
            while True:
                req_str = None
                worker_task = None

                # listen for requests
                self.log('Waiting for agent requests.')
                req_str = await self.reqservice.recv_json()
                self.log(f'Request received!')
                
                # convert request to json
                req = json.loads(req_str)

                # handle request
                self.log(f'Handling request...')
                worker_task = asyncio.create_task(request_worker(req))
                await worker_task

        except asyncio.CancelledError:
            if req_str is not None:
                self.log('Sending blank response...')
                await self.reqservice.send_string('')
            elif worker_task is not None:
                self.log('Cancelling response...')
                worker_task.cancel()
                await worker_task
            else:
                poller = zmq.asyncio.Poller()
                poller.register(self.reqservice, zmq.POLLIN)
                poller.register(self.reqservice, zmq.POLLOUT)

                evnt = await poller.poll(1000)
                if len(evnt) > 0:
                    self.log('Request received during shutdown process. Sending blank response..')
                    await self.reqservice.send_string('')

            self.log('Releasing request service port...')
            self.reqservice_lock.release()
            return

    async def broadcast_handler(self):
        """
        Listens to internal message inbox to see if any submodule wishes to broadcast information to all agents.
        Broadcast types supported:
            1- tic: informs all agents of environment server's current time
            2- eclipse_event: informs agents that an agent has entered eclipse. agents must ignore transmission if they are not the agent affected by the event
            3- gp_access_event: informs an agent that it can access or can no longer access a ground point. agents must ignore transmission if they are not the agent affected by the event
            4- gs_access_event: informs an agent that it can access or can no longer access a ground station. agents must ignore transmission if they are not the agent affected by the event
            5- agent_access_event: informs an agent that it can access or can no longer access another agent. agents must ignore transmission if they are not the agent affected by the event
        """
        try:
            while True:
                msg = await self.publisher_queue.get()

                if not BroadcastTypes.format_check(msg):
                    # if broadcast task does not meet the desired format, reject and dump
                    self.log('Broadcast task did not meet format specifications. Task dumped.')
                    print(msg)
                    # raise Exception(msg)
                    continue

                # change from internal message to external message
                msg['src'] = self.name
                msg_type = msg['@type']

                self.log(f'Broadcast task of type {msg_type} received! Publishing to all agents...')

                if BroadcastTypes[msg_type] is BroadcastTypes.TIC_EVENT:
                    msg['dst'] = 'all'
                    t_next = msg['server_clock']
                    self.log(f'Updating internal clock to t={t_next}')
                    await self.sim_time.set_level(t_next)

                elif (BroadcastTypes[msg_type] is BroadcastTypes.ECLIPSE_EVENT
                     or BroadcastTypes[msg_type] is BroadcastTypes.GS_ACCESS_EVENT
                     or BroadcastTypes[msg_type] is BroadcastTypes.GP_ACCESS_EVENT
                     or BroadcastTypes[msg_type] is BroadcastTypes.AGENT_ACCESS_EVENT):
                    msg['dst'] = msg['agent']
                    msg.pop('agent')
                
                else:
                    self.log(f'Broadcast task of type {msg_type} not yet supported. Dumping task...')
                    continue

                # broadcast message
                self.log('Awaiting access to publisher socket...')
                await self.publisher_lock.acquire()
                self.log('Access to publisher socket acquired.')
                msg_json = json.dumps(msg)
                await self.publisher.send_json(msg_json)
                self.log('Broadcast sent')
                self.publisher_lock.release()

        except asyncio.CancelledError:
            return
        finally:
            if self.publisher_lock.locked():
                self.publisher_lock.release()

    """
    --------------------
    HELPING FUNCTIONS
    --------------------    
    """

    async def network_config(self):
        """
        Creates communication sockets and binds this environment to them.

        'publisher': socket in charge of broadcasting messages to all agents in the simulation
        'reqservice': socket in charge of receiving and answering requests from agents. These request can range from:
            1- sync_requests: agents confirm their activation and await a synchronized simulation start message
            2- tic_requests: agents ask to be notified when a certain time has passed in the environment's clock
            3- agent_information_request: agent asks for information regarding its current position, velocity, and eclipse
            4- observation_request: agent requests environment information regarding a the state of a ground point
        """
        # Activate network ports
        self.context = zmq.asyncio.Context()
    
        # Assign ports to sockets
        ## Set up socket to broadcast information to agents
        self.environment_port_number = '5561'
        if is_port_in_use(int(self.environment_port_number)):
            raise Exception(f"{self.environment_port_number} port already in use")
        self.publisher = self.context.socket(zmq.PUB)                   
        self.publisher.sndhwm = 1100000                                 ## set SNDHWM, so we don't drop messages for slow subscribers
        self.publisher.bind(f"tcp://*:{self.environment_port_number}")
        self.publisher_lock = asyncio.Lock()
        self.publisher_queue = asyncio.Queue()

        ## Set up socket to receive synchronization and measurement requests from agents
        self.request_port_number = '5562'
        if is_port_in_use(int(self.request_port_number)):
            raise Exception(f"{self.request_port_number} port already in use")
        self.reqservice = self.context.socket(zmq.REP)
        self.reqservice.bind(f"tcp://*:{self.request_port_number}")
        self.reqservice_lock = asyncio.Lock()

    async def sync_agents(self):
        """
        Awaits for all other agents to undergo their initialization and activation routines and to become online. Once they do, 
        they will reach out to the environment through its 'reqservice' socket and subscribe to future broadcasts from the 
        environment's 'publisher' socket.

        The environment will then create a ledger mapping which agents are assigned to which ports. This ledger will later be 
        broadcasted to all agents.
        """

        # wait for agents to synchronize
        subscriber_to_port_map = dict()
        while len(self.alive_subscribers) < self.NUMBER_AGENTS:
            # wait for synchronization request
            msg_str = await self.reqservice.recv_json() 
            msg = json.loads(msg_str)
            msg_type = msg['@type']
            if RequestTypes[msg_type] != RequestTypes.SYNC_REQUEST or msg.get('port') is None:
                continue
            
            msg_src = msg.get('src', None)
            src_port = msg.get('port')
            self.NUMBER_OF_TIMED_COROUTINES_AGENTS += msg.get('n_coroutines')

            self.log(f'Received sync request from {msg_src}! Checking if already synchronized...', level=logging.INFO) 

            # log subscriber confirmation
            for agent_name in self.AGENT_NAME_LIST:
                if (agent_name in msg_src) and (agent_name not in self.alive_subscribers):
                    self.alive_subscribers.append(agent_name)
                    self.log(f"{agent_name} is now synchronized to environment ({len(self.alive_subscribers)}/{self.NUMBER_AGENTS}).")
                    
                    subscriber_to_port_map[msg_src] = src_port
                    break
                elif (agent_name in self.alive_subscribers):
                    self.log(f"{agent_name} is already synchronized to environment ({len(self.alive_subscribers)}/{self.NUMBER_AGENTS}).")
                elif (msg_src not in self.AGENT_NAME_LIST):
                    self.log(f"{agent_name} agent node not in list of agents for this environment ({len(self.alive_subscribers)}/{self.NUMBER_AGENTS}).")
                    
            # send synchronization reply
            await self.reqservice.send_string('')

        # self.NUMBER_OF_TIMED_COROUTINES = count_number_of_subroutines(self)

        return subscriber_to_port_map
                    
    async def broadcast_sim_start(self, subscriber_to_port_map):
        """
        Broadcasts simulation start to all agents subscribed to this environment.
        Simulation start message also contains a ledger that maps agent names to ports to be connected to for inter-agent
        communications. This message also contains information about the clock-type being used in this simulation.
        """
        # create message
        msg_dict = dict()
        msg_dict['src'] = self.name
        msg_dict['dst'] = 'ALL'
        msg_dict['@type'] = BroadcastTypes.SIM_START_EVENT.name
        
        # include subscriber-to-port map to message
        msg_dict['port_map'] = subscriber_to_port_map
        
        # include clock information to message
        clock_info = dict()
        clock_info['@type'] = self.CLOCK_TYPE.name
        if self.CLOCK_TYPE == SimClocks.REAL_TIME or self.CLOCK_TYPE == SimClocks.REAL_TIME_FAST:
            clock_info['freq'] = self.SIMULATION_FREQUENCY
            self.sim_time = 0
        else:
            self.sim_time = Container()
        msg_dict['clock_info'] = clock_info

        # package message and broadcast
        msg_json = json.dumps(msg_dict)
        await self.publisher.send_json(msg_json)

        # log simulation start time
        self.START_TIME = time.perf_counter()

        # initiate tic request queue if simulation uses a synchronized server clock
        if self.CLOCK_TYPE == SimClocks.SERVER_STEP:
            self.tic_request_queue = asyncio.Queue()
            self.tic_request_queue_sorted = []
            
    async def broadcast_sim_end(self):
        """
        Broadcasts a message announcing the end of the simulation to all agents subscribed to this environment. 
        All agents must aknowledge that they have received and processed this message for the simulation to end.
        """
        # wait for other processes to submit their final responses to other agents.
        self.log(f'Awating access to request service socket...')
        await self.reqservice_lock.acquire()
        
        # broadcast simulation end to all subscribers
        msg_dict = dict()
        msg_dict['src'] = self.name
        msg_dict['dst'] = 'all'
        msg_dict['@type'] =  BroadcastTypes.SIM_END_EVENT.name
        msg_dict['server_clock'] = time.perf_counter() - self.START_TIME
        kill_msg = json.dumps(msg_dict)
        
        t = msg_dict['server_clock']
        self.message_logger.debug(f'Broadcasting simulation end at t={t}[s]')
        self.log(f'Broadcasting simulation end at t={t}[s]')
        
        await self.publisher.send_json(kill_msg)
        
        # wait for all agents to send their confirmation
        self.request_logger.info(f'Waiting for simulation end confirmation from {len(self.AGENT_NAME_LIST)} agents...')
        self.log(f'Waiting for simulation end confirmation from {len(self.AGENT_NAME_LIST)} agents...', level=logging.INFO)
        while len(self.offline_subscribers) < self.NUMBER_AGENTS:
            # wait for synchronization request
            msg_str = await self.reqservice.recv_json() 
            msg_dict = json.loads(msg_str)
            msg_src = msg_dict['src']
            msg_type = msg_dict['@type']

            if RequestTypes[msg_type] is not RequestTypes.AGENT_END_CONFIRMATION:
                # if request is not of the type end-of-simulation, then discard and wait for the next
                self.log(f'Request of type {msg_type} received at the end of simulation. Discarting request and sending a blank response...', level=logging.INFO)
                await self.reqservice.send_string('')
                continue
            
            self.request_logger.info(f'Received simulation end confirmation from {msg_src}!')
            self.log(f'Received simulation end confirmation from {msg_src}!', level=logging.INFO)
            
            # log subscriber confirmation
            for agent_name in self.AGENT_NAME_LIST:
                if agent_name in msg_src and not agent_name in self.offline_subscribers:
                    self.offline_subscribers.append(agent_name)
                    self.log(f"{agent_name} has ended its processes ({len(self.offline_subscribers)}/{self.NUMBER_AGENTS}).", level=logging.INFO)
                    break
            
            # send blank response
            await self.reqservice.send_string('')
        
        self.reqservice_lock.release()

    def set_up_results_directory(self, scenario_dir):
        scenario_results_path = scenario_dir + '/results'
        if not os.path.exists(scenario_results_path):
            # if directory does not exists, create it
            os.mkdir(scenario_results_path)

        enviroment_results_path = scenario_results_path + f'/{self.name}'
        if os.path.exists(enviroment_results_path):
            # if directory already exists, cleare contents
            for f in os.listdir(enviroment_results_path):
                os.remove(os.path.join(enviroment_results_path, f)) 
        else:
            # if directory does not exist, create a new onw
            os.mkdir(enviroment_results_path)

        return scenario_results_path, enviroment_results_path


    def set_up_loggers(self):
        # set root logger to default settings
        logging.root.setLevel(logging.NOTSET)
        logging.basicConfig(level=logging.NOTSET)

        logger_names = ['messages', 'requests', 'state', 'actions']

        loggers = []
        for logger_name in logger_names:
            path = self.ENVIRONMENT_RESULTS_DIR + f'/{logger_name}.log'

            if os.path.isdir(path):
                # if file already exists, delete
                os.remove(path)

            # create logger
            logger = logging.getLogger(f'{self.name}_{logger_name}')
            logger.propagate = False

            # create handlers
            c_handler = logging.StreamHandler()
            if logger_name == 'actions':
                c_handler.setLevel(logging.DEBUG)
            else:
                c_handler.setLevel(logging.WARNING)

            f_handler = logging.FileHandler(path)
            f_handler.setLevel(logging.DEBUG)

            # add handlers to logger
            logger.addHandler(c_handler)
            logger.addHandler(f_handler)

            loggers.append(logger)
        return loggers

    async def request_submitter(self, req):
        """
        Submits requests to itself whenever a submodule requires information that can only be obtained from request messages
        """
        req['src'] = self.name
        req_type = req['@type']

        if RequestTypes[req_type] is RequestTypes.TIC_REQUEST:
            req['dst'] = EnvironmentModuleTypes.TIC_REQUEST_MODULE.name
        else:
            raise Exception(f'Internal handling of request type {req_type} not yet supported')
        await self.send_internal_message(req)
        
"""
--------------------
MAIN
--------------------    
"""
if __name__ == '__main__':
    print('Initializing environment...')
    scenario_dir = './scenarios/sim_test/'
    dt = 4.6656879355937875
    # duration = 6048
    # duration = 10
    # duration = 70
    duration = 537 * dt 
    print(f'Simulation duration: {duration}[s]')

    # environment = EnvironmentServer('ENV', scenario_dir, ['AGENT0'], 5, clock_type=SimClocks.REAL_TIME)
    # environment = EnvironmentServer(scenario_dir, ['Mars1'], duration, clock_type=SimClocks.SERVER_STEP)
    environment = EnvironmentServer(scenario_dir, ['Mars1', 'Mars2'], duration, clock_type=SimClocks.SERVER_STEP)
    
    asyncio.run(environment.live())