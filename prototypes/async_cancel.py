import asyncio


async def c_1():
    try:
        await asyncio.sleep(1)

    except asyncio.CancelledError as e:
        print(f'c_1() cancelled by {e}')
        return

async def c_2():
    try:
        t_1 = asyncio.create_task(c_3())
        t_2 = asyncio.create_task(asyncio.sleep(0.1))

        _, pending = await asyncio.wait([t_1, t_2], return_when=asyncio.FIRST_COMPLETED)
        
        print('c_2: completed one task! cancelling the other...')
        for task in pending:
            task : asyncio.Task
            task.cancel()
            await task
    except:
        return

async def c_3():
    await c_1()

if __name__ == '__main__':
    asyncio.run(c_2())