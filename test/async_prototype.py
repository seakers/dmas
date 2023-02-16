import asyncio
import time

def f(x : float):
    print(f'starting sleep of {x}[s]...')
    time.sleep(x)
    print(f'sleep of {x}[s] completed!')

async def af(x : float):
    try:
        print(f'starting async sleep of {x}[s]...')
        await asyncio.sleep(x)
        print(f'async sleep of {x}[s] completed!')
    
    except asyncio.CancelledError as e:
        print(f'interrupted async sleep of {x}[s]...')
        raise e

async def busy():
    try:
        await af(10)

        await af(5)

    except asyncio.CancelledError:
        return


async def main():
    t1 = asyncio.create_task(af(1))
    t2 = asyncio.create_task(busy())

    _, pending = await asyncio.wait([t1,t2], return_when=asyncio.FIRST_COMPLETED)

    for t in pending:
        t : asyncio.Task
        t.cancel()
        await t

if __name__ == '__main__':
    asyncio.run(main())

    asyncio.run(main())
