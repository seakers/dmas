import asyncio
from dmas.messages import PlatformTaskMessage
from dmas.modules import Module
from dmas.tasks import ObservationTask
from dmas.utils import AgentModuleTypes, InstrumentNames


class PlanningModule(Module):
    def __init__(self, parent_agent : Module, n_timed_coroutines=1) -> None:
        super().__init__(AgentModuleTypes.PLANNING_MODULE, parent_agent, [], n_timed_coroutines)

    async def coroutines(self):
        """
        Periodically sends a measurement plan to the platform every minute
        """
        try:
            while True:
                task = ObservationTask(-1, -1, [InstrumentNames.TEST.value], [1])
                msg = PlatformTaskMessage(self.name, AgentModuleTypes.ENGINEERING_MODULE.value, task)
                await self.send_internal_message(msg)
                
                await self.sim_wait(60)     
        except asyncio.CancelledError:
            return