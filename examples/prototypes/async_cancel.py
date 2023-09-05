import asyncio


async def c_1():
    try:
        await asyncio.sleep(1)

    except asyncio.CancelledError as e:
        print(f'c_1() cancelled by parent function.')
        raise e
        # return

async def c_2():
    try:
        t_1 = asyncio.create_task(c_3(), name='c_3()')
        t_2 = asyncio.create_task(asyncio.sleep(0.1), name='c_2()')

        done, pending = await asyncio.wait([t_1, t_2], return_when=asyncio.FIRST_COMPLETED)
        
        for task in done:
            task : asyncio.Task
            print(f'{task.get_name()} completed! cancelling all other tasks...')

        for task in pending:
            task : asyncio.Task
            print(f'cancelling {task.get_name()}...')
            task.cancel()
            await task
            print(f'{task.get_name()} cancelled!')
    
    except asyncio.CancelledError as e:
        print(f'c_2() cancelled by parent function.')
        return

async def c_3():
    try:
        await c_1()

        print('c_3(): doing some work...')
        await asyncio.sleep(0.2)
        print('c_3(): done!')

    except asyncio.CancelledError as e:
        print(f'c_3() cancelled by parent function.')
        raise e

if __name__ == '__main__':
    asyncio.run(c_2())