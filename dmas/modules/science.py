import asyncio
from modules.module import Module


class ScienceModule(Module):
    def __init__(self, name, parent_module, submodules=[], n_timed_coroutines=1) -> None:
        super().__init__(name, parent_module, submodules, n_timed_coroutines)

    async def activate(self):
        await super().activate()

    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            dst_name = msg['dst']
            if dst_name != self.name:
                await self.put_in_inbox(msg)
            else:
                if msg['@type'] == 'PRINT':
                    content = msg['content']
                    self.log(content)                
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        try:
            while True:
                t1 = asyncio.create_task(self.f1())
                t2 = asyncio.create_task(self.f2())
                t3 = asyncio.create_task(self.f3())

                await asyncio.wait([t1, t2, t3], return_when=asyncio.FIRST_COMPLETED)

                await self.sim_wait(1000)     
        except asyncio.CancelledError:
            return

    async def f1(self):
        pass
    async def f2(self):
        pass
    async def f3(self):
        pass