import asyncio
import numpy


class Container:
    def __init__(self, level=0, capacity=numpy.Infinity):
        if level > capacity:
            raise Exception('Initial level must be lower than maximum capacity.')

        self.level = level
        self.capacity = capacity
        self.updated = None

    def activate(self):
        self.updated = asyncio.Event()

    async def put(self, value):
        if self.updated is None:
            raise Exception('Container not activated in event loop')

        def accept():
            return self.level + value <= self.capacity

        if accept():
            self.level += value
            self.updated.set()
            print(f'Container state: {self.level}/{self.capacity}')
        else:
            self.updated.clear()
            await self.updated.wait()
            await self.put(value)

    async def get(self, value):
        if self.updated is None:
            raise Exception('Container not activated in event loop')

        def accept():
            return self.level - value >= 0
        
        if accept():
            self.level -= value
            self.updated.set()
            print(f'Container state: {self.level}/{self.capacity}')
        else:
            self.updated.clear()
            await self.updated.wait()         
            await self.get(value)

    async def when_cond(self, cond):
        if self.updated is None:
            raise Exception('Container not activated in event loop')
             
        if cond():
            return True
        else:
            self.updated.clear()
            await self.updated.wait()  
            await self.when_cond(cond)

    async def when_not_empty(self):
        def accept():
            return self.level > 0
        
        await self.when_cond(accept)
    
    async def when_empty(self):
        def accept():
            return self.level == 0
        
        await self.when_cond(accept)

    async def when_less_than(self, val):
        def accept():
            return self.level < val
        
        await self.when_cond(accept)
    
    async def when_leq_than(self, val):
        def accept():
            return self.level <= val
        
        await self.when_cond(accept)

    async def when_greater_than(self, val):
        def accept():
            return self.level > val
        
        await self.when_cond(accept)
    
    async def when_geq_than(self, val):
        def accept():
            return self.level >= val
        
        await self.when_cond(accept)