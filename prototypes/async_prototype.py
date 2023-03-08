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

    def run(self):
        async def routine():
            n = 2
            y = 10000000
            dt = 1

            with concurrent.futures.ThreadPoolExecutor(n + 2) as pool:
                for _ in range(n):
                    pool.submit(self.f1, *[y])
                pool.submit(asyncio.run, *[self.f2(dt)])
           
            # await self.f2(dt)

        asyncio.run(routine())

if __name__ == '__main__':
    x = Tester()
    x.run()

