import asyncio
import numpy

"""
------------------
ASYNCHRONOUS CONTAINER
------------------
"""
class Container:
    """
    ## Container Object

    Holds a numerical value ('float' or 'int') 
    """
    def __init__(self, level: float = 0, capacity: float = numpy.Infinity):
        if level > capacity:
            raise Exception('Initial level must be lower than maximum capacity.')

        self.level = level
        self.capacity = capacity

        self.updated = asyncio.Event()
        self.lock = asyncio.Lock()

    async def set_level(self, value : float):
        self.level = 0
        await self.put(value)

    async def empty(self):
        self.set_level(0)

    async def put(self, value):
        if self.updated is None:
            raise Exception('Container not activated in event loop')

        def accept():
            return self.level + value <= self.capacity
        
        await self.lock.acquire()
        while not accept():
            self.lock.release()
            self.updated.clear()
            await self.updated.wait()
            await self.lock.acquire()        
        self.level += value
        self.updated.set()
        self.lock.release()

    async def get(self, value):
        if self.updated is None:
            raise Exception('Container not activated in event loop')

        def accept():
            return self.level - value >= 0
        
        await self.lock.acquire()
        while not accept():
            self.lock.release()
            self.updated.clear()
            await self.updated.wait()
            await self.lock.acquire()        
        self.level -= value
        self.updated.set()
        self.lock.release()

    async def when_cond(self, cond):
        if self.updated is None:
            raise Exception('Container not activated in event loop')
             
        while not cond():
            self.updated.clear()
            await self.updated.wait()
        return True

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