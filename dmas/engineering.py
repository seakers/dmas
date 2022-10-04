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
from messages import *
from tasks import *
from platform import *
from modules import Module
from utils import *

class EngineeringModule(Module):
    def __init__(self, parent_agent : Module) -> None:
        super().__init__(AgentModuleTypes.ENGINEERING_MODULE.value, parent_agent, [])
        self.submodules = [ 
                            PlatformSim(self) 
                          ]

class PlatformSim(Module):
    def __init__(self, parent_engineering_module) -> None:
        super().__init__(EngineeringModuleSubmoduleTypes.PLATFORM_SIM.value, parent_engineering_module, [])
        self.submodules = [
                            CommandAndDataHandlingSubsystem(self),
                            GuidanceAndNavigationSubsystem(self),
                            PayloadSubsystem(self),
                            AttitudeDeterminationAndControlSubsystem(self),
                            ElectricPowerSubsystem(self),
                            CommsSubsystem(self, 1e6)
        ]

        self.cndh = None
        for subsystem in self.submodules:
            subsystem : SubsystemModule
            if subsystem.name == SubsystemNames.CNDH.value:
                self.cndh = subsystem
                break
        
        if self.cndh is None:
            raise Exception('No command and data handling found in platform simulator')

    async def internal_message_handler(self, msg: InternalMessage):
        """
        Handles message intended for this module and performs actions accordingly. By default it only handles messages
        of the type 'PrintInstruction'.
        """
        try:
            dst_name = msg.dst_module
            if dst_name != self.name:
                # this module is NOT the intended receiver for this message. Forwarding to rightful destination
                await self.send_internal_message(msg)
            else:
                # this module is the intended receiver for this message. Handling message
                content = msg.content
                if isinstance(content, EnvironmentBroadcastMessage):
                    # forward environment messages to every submodule
                    for subsystem in self.submodules:
                        subsystem : SubsystemModule
                        msg = InternalMessage(self.name, subsystem.name, content)
                        await self.send_internal_message(msg)

                elif isinstance(content, PlatformTask):
                    # received platform instruction, forward to command and data handling subsystem
                    msg.dst_module = self.cndh.name
                    await self.send_internal_message(msg)
                
                else:
                    self.log(f'Internal messages with contents of type: {type(msg.content)} not yet supported. Discarting message.')

        except asyncio.CancelledError:
            return