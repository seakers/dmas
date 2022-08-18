from abc import abstractmethod
import asyncio
from enum import Enum
import pandas as pd

from modules.module import Module
from messages import RequestTypes, BroadcastTypes
from utils import SimClocks

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
                await self.put_message(msg)
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

                        await self.put_message(msg_dict)
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
        
        # initialize scheduled events data and sort
        self.event_data = self.compile_event_data()
        self.event_data = self.event_data.sort_values(by=['time index'])

        # if data does not have proper format, reject
        if not self.check_data_format():
            raise Exception('Event data loaded in an incorrect format.')

        # get scheduled event time-step
        self.time_step = -1
        for agent_name in self.parent_module.orbit_data:
            orbit_data = self.parent_module.orbit_data[agent_name]
            self.time_step = orbit_data.time_step
            break
    
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
                await self.put_message(msg)
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
                await self.put_message(msg_dict)

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

        return BroadcastTypes.create_eclipse_event_broadcast(self.name, self.parent_module.name, agent_name, rise, t_next)
        
    def compile_event_data(self) -> pd.DataFrame:
        orbit_data = self.parent_module.orbit_data
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

        return BroadcastTypes.create_gs_access_event_broadcast(self.name, self.parent_module.name, agent_name, rise, t_next,
                                                                gndStat_name, gndStat_id, lat, lon)

    def compile_event_data(self) -> pd.DataFrame:
        orbit_data = self.parent_module.orbit_data
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
        pass

    def compile_event_data(self) -> pd.DataFrame:
        orbit_data = self.parent_module.orbit_data
        coverage_data = pd.DataFrame(columns=['time index', 'agent name', 'rise', 'instrument', 'mode', 'grid', 'GP index', 'pnt-opt index', 'lat [deg]', 'lon [deg]',])

        for agent in orbit_data:
            agent_gp_coverate_date =orbit_data[agent].gp_access_data

            for _, row in self.event_data.iterrows():
                coverage_events = pd.DataFrame(columns=['time index', 'agent name', 'rise', 'instrument', 'mode', 'grid', 'GP index', 'pnt-opt index', 'lat [deg]', 'lon [deg]',])

        # for agent in orbit_data:
        #     agent_eclipse_data = orbit_data[agent].eclipse_data
        #     nrows, _ = agent_eclipse_data.shape
        #     agent_name_column = [agent] * nrows

        #     eclipse_rise = agent_eclipse_data.get(['start index'])
        #     eclipse_rise = eclipse_rise.rename(columns={'start index': 'time index'})
        #     eclipse_rise['agent name'] = agent_name_column
        #     eclipse_rise['rise'] = [True] * nrows

        #     eclipse_set = agent_eclipse_data.get(['end index'])
        #     eclipse_set = eclipse_set.rename(columns={'end index': 'time index'})
        #     eclipse_set['agent name'] = agent_name_column
        #     eclipse_set['rise'] = [False] * nrows

        #     eclipse_merged = pd.concat([eclipse_rise, eclipse_set])
        #     if len(eclipse_data) == 0:
        #         eclipse_data = eclipse_merged
        #     else:
        #         eclipse_data = pd.concat([eclipse_data, eclipse_merged])

        return coverage_data