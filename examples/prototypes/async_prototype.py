import asyncio
import time
import concurrent.futures

class Tester:
    def f1(self, y):
        print('doing some rough work...')
        x = 0
        for i in range(y):
            x += i
        print('rough work done!')

    async def f2(self, t):
        print(f'sleeping for {t} [s]...')
        await asyncio.sleep(t)
        print('sleep completed!')

    async def f3(self, n, t):
        with concurrent.futures.ThreadPoolExecutor(n) as pool:
                for _ in range(n):
                    pool.submit(asyncio.run, *[self.f2(t)])
    
    async def f4(self, n, y):
        with concurrent.futures.ThreadPoolExecutor(n) as pool:
                for _ in range(n):
                    pool.submit(self.f1, *[y])

    def run(self):
        async def routine():
            n = 2
            y = 10000000
            t = 1

            t2 = asyncio.create_task(self.f2(t))
            t4 = asyncio.create_task(self.f4(n, y))

            # await t2
            await asyncio.wait([t2, t4], return_when=asyncio.ALL_COMPLETED)

            # with concurrent.futures.ThreadPoolExecutor(n) as pool:
            #     for _ in range(n):
            #         pool.submit(self.f1, *[y])
                    # pool.submit(asyncio.run, *[self.f3(n, t)])
           
            # await t2

        asyncio.run(routine())

if __name__ == '__main__':
    x = Tester()
    x.run()

