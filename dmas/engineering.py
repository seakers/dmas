from abc import abstractmethod
from ctypes import Union
import logging
from agent import AgentClient
from platform import PlatformSim
from messages import *
from utils import *
from modules import Module

"""
--------------------------------------------------------
 ____                                                                              
/\  _`\                   __                                __                     
\ \ \L\_\    ___      __ /\_\    ___      __     __   _ __ /\_\    ___      __     
 \ \  _\L  /' _ `\  /'_ `\/\ \ /' _ `\  /'__`\ /'__`\/\`'__\/\ \ /' _ `\  /'_ `\   
  \ \ \L\ \/\ \/\ \/\ \L\ \ \ \/\ \/\ \/\  __//\  __/\ \ \/ \ \ \/\ \/\ \/\ \L\ \  
   \ \____/\ \_\ \_\ \____ \ \_\ \_\ \_\ \____\ \____\\ \_\  \ \_\ \_\ \_\ \____ \ 
    \/___/  \/_/\/_/\/___L\ \/_/\/_/\/_/\/____/\/____/ \/_/   \/_/\/_/\/_/\/___L\ \
                      /\____/                                               /\____/
                      \_/__/                                                \_/__/    
 /'\_/`\            /\ \         /\_ \            
/\      \    ___    \_\ \  __  __\//\ \      __   
\ \ \__\ \  / __`\  /'_` \/\ \/\ \ \ \ \   /'__`\ 
 \ \ \_/\ \/\ \L\ \/\ \L\ \ \ \_\ \ \_\ \_/\  __/ 
  \ \_\\ \_\ \____/\ \___,_\ \____/ /\____\ \____\
   \/_/ \/_/\/___/  \/__,_ /\/___/  \/____/\/____/                                                                                                                                                    
--------------------------------------------------------
"""
class EngineeringModule(Module):
    def __init__(self, parent_agent : Module) -> None:
        super().__init__(AgentModuleTypes.ENGINEERING_MODULE.value, parent_agent, [], 1)
        self.submodules = [
            PlatformSim(self)
        ]

    async def internal_message_handler(self, msg: InternalMessage):
        """
        Forwards any task to the platform simulator
        """
        try:
            dst_name = msg.dst_module
            if dst_name != self.name:
                # this module is NOT the intended receiver for this message. Forwarding to rightful destination
                await self.send_internal_message(msg)
            else:
                if isinstance(msg, PlatformTaskMessage) or isinstance(msg, SubsystemTaskMessage) or isinstance(msg, ComponentTaskMessage):
                    msg.dst_module = EngineeringModuleParts.PLATFORM_SIMULATION.value
                    await self.send_internal_message(msg)
                else:
                    # this module is the intended receiver for this message. Handling message
                    self.log(f'Internal messages with contents of type: {type(msg.content)} not yet supported. Discarting message.')

        except asyncio.CancelledError:
            return

"""
--------------------
DEBUGGING MAIN
--------------------    
"""
if __name__ == '__main__':
    # print('Initializing agent...')
    class PlanningModule(Module):
        def __init__(self, name, parent_module : Module) -> None:
            super().__init__(name, parent_module)

        async def coroutines(self):
            """
            Routinely sends out a measurement task to the agent to perform every minute
            """
            try:
                while True:
                    task = ObservationTask(0, 0, [InstrumentNames.TEST.value], [1])
                    msg = PlatformTaskMessage(task)
                    await self.send_internal_message(msg)

                    await self.sim_wait(60)
            except asyncio.CancelledError:
                return

    class TestAgent(AgentClient):    
        def __init__(self, name, scenario_dir) -> None:
            super().__init__(name, scenario_dir)
            self.submodules = [
                EngineeringModule(self),
                PlanningModule(self)
                ]  

    print('Initializing agent...')
    
    agent = TestAgent('Mars1', './scenarios/sim_test')
    
    asyncio.run(agent.live())
    