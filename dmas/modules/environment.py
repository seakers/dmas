import asyncio
from enum import Enum

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
    # TIC_REQUEST_MODULE = 'TIC_REQUEST_MODULE'

class TicRequestModule(Module):
    def __init__(self, parent_environment) -> None:
        super().__init__(EnvironmentModuleTypes.TIC_REQUEST_MODULE.value, parent_environment, submodules=[], n_timed_coroutines=1)

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
                if RequestTypes[msg['@type']] is RequestTypes.TIC_REQUEST:
                    # if a tic request is received, add to tic_request_queue
                    t = msg['t']
                    await self.tic_request_queue.put(t)
                else:
                    # if not a tic request, dump message 
                    return
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        try:
            while True:
                if self.CLOCK_TYPE is SimClocks.SERVER_STEP:
                    # append tic request to request list
                    self.log(f'Waiting for next tic request ({len(self.tic_request_queue_sorted)} / {self.parent_module.NUMBER_OF_TIMED_COROUTINES_AGENTS})...')

                    tic_req = await self.tic_request_queue.get()
                    self.tic_request_queue_sorted.append(tic_req)

                    self.log(f'Tic request received! Queue status: ({len(self.tic_request_queue_sorted)} / {self.parent_module.NUMBER_OF_TIMED_COROUTINES_AGENTS})')
                        
                    # wait until all timed coroutines from all agents have entered a wait period and have submitted their respective tic requests
                    if len(self.tic_request_queue_sorted) == self.parent_module.NUMBER_OF_TIMED_COROUTINES_AGENTS:
                        # sort requests
                        self.log('Sorting tic requests...')
                        print(self.tic_request_queue_sorted)
                        self.tic_request_queue_sorted.sort(reverse=True)
                        self.log(f'Tic requests sorted: {self.tic_request_queue_sorted}')

                        # skip time to earliest requested time
                        t_next = self.tic_request_queue_sorted.pop()

                        # send a broadcast request to parent environmen                 
                        msg_dict = dict()
                        msg_dict['src'] = self.name
                        msg_dict['dst'] = self.parent_module.name
                        msg_dict['@type'] = BroadcastTypes.TIC.value
                        msg_dict['server_clock'] = t_next

                        t = msg_dict['server_clock']
                        self.log(f'Submitting broadcast request for tic with server clock at t={t}')

                        await self.parent_module.put_message(msg_dict)
                else:
                    await self.sim_wait(1e6)
        except asyncio.CancelledError:
            return