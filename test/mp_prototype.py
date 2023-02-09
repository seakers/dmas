
import asyncio
import json
import time
import zmq
import zmq.asyncio as azmq
import multiprocessing as mp
from multiprocessing import Pool, Process

async def server():
    try:
        print('SERVER START')

        context = azmq.Context()
        socket = context.socket(zmq.REP)
        socket.bind("tcp://*:5555")

        m = 0
        while m < 10:
            #  Wait for next request from client
            print('SERVER: waiting on message...')
            dst, content = await socket.recv_multipart()
            dst = dst.decode('ascii')
            content = json.loads(content.decode('ascii'))
            src : str = content['src']
            print(f"SERVER: Received request from {src}: {content}")

            #  Do some 'work'
            await asyncio.sleep(0.5)

            #  Send reply back to client
            src : str = content['src']
            resp : str = 'hello!'
            socket.send_multipart([src.encode('ascii'), resp.encode('ascii')])

            m += 1
        
        print('SERVER DONE')

    except asyncio.CancelledError:
        print ('SERVER INTERRUPTED')
        return

async def client():
    try:
        print("SERVER: Connecting to hello world server...") 
        context = azmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect("tcp://localhost:5555")
        print("SERVER: Connection established!") 

        #  Do 10 requests, waiting each time for a response
        for _ in range(10):
            dst : str = 'SERVER'
            content_dict = dict()
            content_dict['src'] = 'CLIENT'
            content_dict['dst'] = 'SERVER'
            content_dict['@type'] = 'HELLO WORLD'
            content : str = str(json.dumps(content_dict))

            print(f"CLIENT: sending message to {dst}...")
            await socket.send_multipart([dst.encode('ascii'), content.encode('ascii')])
            print(f"CLIENT: message sent! waiting for reply from {dst}...")

            #  Get the reply.
            src, content = await socket.recv_multipart()
            t = time.perf_counter()
            src = src.decode('ascii')
            content = content.decode('ascii')
                            
            print(f"CLIENT: Received reply from {dst} at {t} [s]: {content}")

    except asyncio.CancelledError:
        print('Client service cancelled.')
        return

def tough_process(n : int = 10000):
    try:
        print(f'CLIENT: starting tough process with n={n}...')
        nums = range(n)
        out = []
        for num in nums:
            out.append(num ** 2)

        print(f'CLIENT: tough process completed! {len(out)}')
        return out
    except:
        print(f'CLIENT: tough process interrupted')

def run_client():
    asyncio.run(client())

async def interrupter(n : float, src : str):
    try:
        await asyncio.sleep(n, src)
        print(f'{src}: INTERRUPTOR TRIGGERED!')
    except asyncio.CancelledError:
        print(f'{src}: interruptor interrupted.')
        return

def run_interruptor(n : float, src : str):
    asyncio.run(interrupter(n, src))

async def client_main():
    print('CLIENT START')

    # t1 = asyncio.create_task(client(), name='client')
    # t2 = asyncio.create_task(multitough(), name='multitough')
    # t3 = asyncio.create_task(interrupter(1), name='interrupter')

    # done, pending = await asyncio.wait([t3], return_when=asyncio.FIRST_COMPLETED)

    # for task in done:
    #     task : asyncio.Task
    #     print(f'{task.get_name()} completed!')

    # for task in pending:
    #     task : asyncio.Task
    #     print(f'cancelling {task.get_name()}...')
    #     task.cancel()
    #     await task
    #     print(f'{task.get_name()} cancelled!')

    # if not t2.done():
    #     print(f'cancelling {t2.get_name()}...')
    #     t2.cancel()
    #     await t2
    #     print(f'{t2.get_name()} cancelled!')
    
    # try:
    #     ctx = mp.get_context('spawn')

    #     p1 = ctx.Process(target=tough_process, args=(10000000,))
    #     p2 = ctx.Process(target=tough_process, args=(10000000,))
    #     p3 = ctx.Process(target=run_client, args=())
    #     p4 = ctx.Process(target=run_interruptor, args=(1,))

    #     # p1.daemon = True
    #     # p1.daemon = True

    #     p1.start()
    #     p2.start()
    #     p3.start()
    #     p4.start()

    #     p4.join()

    # except asyncio.CancelledError: 
    #     print('terminating tough processes!')
    
    # finally:
    #     p1.terminate()
    #     p2.terminate()
    #     p3.terminate()

    #     print('CLIENT DONE')

    pool = mp.Pool()
    
    pool.apply_async(tough_process, args = (10000000, ))
    pool.apply_async(tough_process, args = (10000000, ))
    pool.apply_async(run_client, args = ())
    pool.apply(run_interruptor, args = (2, 'CLIENT'))

    pool.terminate()
    pool.join()   

    print('CLIENT DONE')

async def server_main():
    t1 = asyncio.create_task(server(), name='server')
    t2 = asyncio.create_task(interrupter(10, 'SERVER'), name='interruptor')

    done, pending = await asyncio.wait([t1, t2], return_when=asyncio.FIRST_COMPLETED)

    for task in done:
        task : asyncio.Task
        print(f'SERVER: {task.get_name()} completed!')

    for task in pending:
        task : asyncio.Task
        print(f'SERVER: cancelling {task.get_name()}...')
        task.cancel()
        await task
        print(f'SERVER: {task.get_name()} cancelled!')

def server_run():
    asyncio.run(server_main())

def client_run():
    asyncio.run(client_main())

if __name__ == "__main__":
    # goal: show that listening and actions occur in parallel           
    p1 = Process(target=client_run)
    p2 = Process(target=server_run)  

    p1.start()
    p2.start()