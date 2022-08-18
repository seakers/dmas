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
                        msg_dict['@type'] = BroadcastTypes.TIC.name
                        msg_dict['server_clock'] = t_next

                        t = msg_dict['server_clock']
                        self.log(f'Submitting broadcast request for tic with server clock at t={t}')

                        await self.put_message(msg_dict)
                else:
                    await self.sim_wait(1e6, module_name=self.name)
        except asyncio.CancelledError:
            return

class EclipseEventModule(Module):
    def __init__(self, parent_environment) -> None:
        """
        In charge of scheduling eclise event broadcasts to all agents
        """
        super().__init__(EnvironmentModuleTypes.ECLIPSE_EVENT_MODULE.value, parent_environment, submodules=[], n_timed_coroutines=1)

    async def activate(self):
        await super().activate()
        self.eclipse_data = self.compile_eclipse_events()
        for agent_name in self.parent_module.orbit_data:
            orbit_data = self.parent_module.orbit_data[agent_name]
            self.time_step = orbit_data.time_step
            break
        
    def compile_eclipse_events(self):
        orbit_data = self.parent_module.orbit_data
        eclipse_data = pd.DataFrame(columns=['time index','agent name', 'rise'])
        
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

        return eclipse_data.sort_values(by=['time index'])

    async def internal_message_handler(self, msg):
        """
        Does not interact with other modules. Any message received 
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
        try:
            for _, row in self.eclipse_data.iterrows():
                # get next scheduled eclipse event
                t_next = row['time index'] * self.time_step
                agent_name = row['agent name']
                
                # wait for said event to start
                await self.sim_wait_to(t_next, module_name=self.name)

                # send a broadcast request to parent environment               
                msg_dict = dict()
                msg_dict['src'] = self.name
                msg_dict['dst'] = self.parent_module.name
                msg_dict['@type'] = BroadcastTypes.ECLIPSE_EVENT.name
                msg_dict['server_clock'] = t_next
                msg_dict['agent'] = agent_name
                msg_dict['rise'] = row['rise']

                if row['rise']:
                    self.log(f'Submitting broadcast request for eclipse event start with server clock at t={t_next} for agent {agent_name}')
                else:
                    self.log(f'Submitting broadcast request for eclipse event end with server clock at t={t_next} for agent {agent_name}')

                await self.put_message(msg_dict)

            # once all eclipse events have occurred, go to sleep
            while True:
                await self.sim_wait(1e6, module_name=self.name)
        except asyncio.CancelledError:
            return