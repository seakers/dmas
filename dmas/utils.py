import asyncio
from enum import Enum
import random
import numpy

class EventPair:
    def __init__(self) -> None:
        self.start = asyncio.Event()
        self.end = asyncio.Event()

        self.end.set()

    def trigger_start(self):
        if not self.start.is_set():
            self.start.set()
        if self.end.is_set():
            self.end.clear()
    
    def trigger_end(self):
        if self.start.is_set():
            self.start.clear()
        if not self.end.is_set():
            self.end.set()

    async def wait_start(self):
        try:
            return await self.start.wait()
        except asyncio.CancelledError:
            return

    async def wait_end(self):
        try:
            return await self.end.wait()
        except asyncio.CancelledError:
            return

class ComponentStatus(Enum):
    ON = 'ON'
    OFF = 'OFF'    

class SubsystemStatus(Enum):
    ON = 'ON'
    OFF = 'OFF'  

class ComponentHealth(Enum):
    NOMINAL = 'NOMINAL'
    CRITIAL = 'CRITICAL'
    FAILURE = 'FAILURE'

class SubsystemHealth(Enum):
    NOMINAL = 'NOMINAL'
    CRITIAL = 'CRITICAL'
    FAILURE = 'FAILURE'

class ComponentNames(Enum):
    ONBOARD_COMPUTER = 'ONBOARD_COMPUTER'
    BATTERY = 'BATTERY'
    POWER_SUPPLY = 'POWER_SUPPLY'
    IMU = 'IMU'
    POS = 'POS'
    SUN_SENSOR = 'SUN_SENSOR'
    REACTION_WHEELS = 'REACTION_WHEELS'
    MAGNETORQUER = 'MAGNETORQUER'
    TRANSMITTER = 'TRANSMITTER'
    RECEIVER = 'RECEIVER'

class BatteryChargeStatus(Enum):
    DISCHARGING = 'DISCHARGING'
    CHARGING = 'CHARGING'

class TaskStatus(Enum):
    """
    Describes the state of a task being performed by a module
    """
    PENDING = 'PENDING'
    IN_PROCESS = 'IN_PROCESS'
    DONE = 'DONE'
    ABORTED = 'ABORTED'

class EnvironmentModuleTypes(Enum):    
    ENVIRONMENT_SERVER_NAME = 'ENV'
    TIC_REQUEST_MODULE = 'TIC_REQUEST_MODULE'
    ECLIPSE_EVENT_MODULE = 'ECLIPSE_EVENT_MODULE'
    GP_ACCESS_EVENT_MODULE = 'GP_ACCESS_EVENT_MODULE'
    GS_ACCESS_EVENT_MODULE = 'GS_ACCESS_EVENT_MODULE'
    AGENT_ACCESS_EVENT_MODULE = 'AGENT_ACCESS_EVENT_MODULE'
    AGENT_EXTERNAL_PROPAGATOR_MODULE = 'AGENT_EXTERNAL_PROPAGATOR_MODULE'

class AgentModuleTypes(Enum):
    ENGINEERING_MODULE = 'ENGINEERING_MODULE'
    SCIENCE_MODULE = 'SCIENCE_MODULE'
    PLANNING_MODULE = 'PLANNING_MODULE'

class EngineeringModuleSubmoduleTypes(Enum):
    PLATFORM_SIM = 'PLATFORM_SIM'
    NETWORK_TRANSMISSION_EMULATOR = 'NETWORK_TRANSMISSION_EMULATOR'

class ScienceModuleSubmoduleTypes(Enum):
    SCIENCE_VALUE = 'SCIENCE_VALUE'

class SubsystemNames(Enum):
    EPS = 'ELECTRIC_POWER_SUBSYSTEM'
    CNDH = 'COMMAND_AND_DATA_HANDLING'
    PAYLOAD = 'PAYLOAD'
    GNC = 'GUIDANCE_AND_NAVIGATION'
    ADCS = 'ATTITUDE_DETERMINATION_AND_CONTROL'
    COMMS = 'COMMS'

class SimClocks(Enum):
    # asynchronized clocks
    # -Each node in the network carries their own clocks to base their waits with
    REAL_TIME = 'REAL_TIME'             # runs simulations in real-time. 
    REAL_TIME_FAST = 'REAL_TIME_FAST'   # runs simulations in spead up real-time. Each real time second represents a user-given amount of simulation seconds

    # synchronized clocks
    # -Each node requests to be notified by the server when a particular time is reached, which they use to base their waits
    SERVER_TIME = 'SERVER_TIC'          # server sends tics at a fixed rate in real-time
    SERVER_TIME_FAST = 'SERVER_TIC'     # server sends tics at a fixed rate in spead up real-time
    SERVER_EVENTS = 'SERVER_EVENTS'     # server waits until all agents have submitted a tic request and fast-forwards to that time

class Container:
    def __init__(self, level: float =0, capacity: float =numpy.Infinity):
        if level > capacity:
            raise Exception('Initial level must be lower than maximum capacity.')

        self.level = level
        self.capacity = capacity
        self.updated = None

        self.updated = asyncio.Event()
        self.lock = asyncio.Lock()

    async def set_level(self, value):
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

def mwhr_to_joules(e):
    return e * 3600.0

"""
---------------------------
Container Class Testing 
---------------------------
"""

async def f1(container: Container):
    print('tast1 starting...')    
    await asyncio.sleep(1)
    await container.put(1)
    
async def f2(container: Container):
    print('tast2 starting...')
    # await asyncio.sleep(0.5)
    print(f'current container level: {container.level}')
    # await container.when_greater_than(0)
    
    await container.get(1)
    print(f'current container level: {container.level}')

async def f3(container: Container):
    for _ in range(100):
        await container.put(1)
        await asyncio.sleep(random.random()/10)
        await container.get(1)

async def main():
    container = Container(0, 100)

    # t1 = asyncio.create_task(f1(container))
    # t2 = asyncio.create_task(f2(container))
    t1 = asyncio.create_task(f3(container))
    t2 = asyncio.create_task(f3(container))
    
    print(f'Initial container level: {container.level}')
    await asyncio.wait([t1, t2], return_when=asyncio.ALL_COMPLETED)
    print(f'Final container level: {container.level}')

if __name__ == '__main__':
    asyncio.run(main())