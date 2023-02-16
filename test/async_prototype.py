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
        return 1
    
    except asyncio.CancelledError as e:
        print(f'interrupted async sleep of {x}[s]...')
        raise e

async def busy():
    try:
        await af(10)

        await af(5)

    except asyncio.CancelledError:
        return


def main():
    async def subroutine():
        t1 = asyncio.create_task(af(1))
        t2 = asyncio.create_task(busy())

        done, pending =await asyncio.wait([t1,t2], return_when=asyncio.FIRST_COMPLETED)

        for t in done:
            t : asyncio.Task
            print(f'{t.get_name()} task completed!')

        for t in pending:
            t : asyncio.Task
            await t

        return t1.result()
    
    return asyncio.run(subroutine())

if __name__ == '__main__':
    x = main()
    print(x)

    # asyncio.run(main())
