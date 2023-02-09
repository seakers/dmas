
import asyncio
import json
import time
import zmq
import zmq.asyncio as azmq
import multiprocessing as mp
from multiprocessing import Pool, Process

"""
ASYNC
"""
async def server():
    try:
        print("SERVER: creating to hello world server socket...") 
        context = azmq.Context()
        socket = context.socket(zmq.REP)
        socket.bind("tcp://*:5556")        
        print("SERVER: socket established!") 

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
        
        context.destroy()
        print('SERVER: finished receving messages.')

    except asyncio.CancelledError:
        print ('SERVER: listnening INTERRUPTED')
        context.destroy()
        return

async def client():
    try:
        print("CLIENT: Connecting to hello world server...") 
        context = azmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect("tcp://localhost:5556")
        print("CLIENT: Connection established!") 

        #  Do 10 requests, waiting each time for a response
        t_o = time.perf_counter()
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
            t_f = time.perf_counter()
            src = src.decode('ascii')
            content = content.decode('ascii')
                            
            print(f"CLIENT: Received reply from {dst} at {t_f - t_o} [s]: {content}")

        context.destroy()
        print(f"CLIENT: finished sending messages to the server.")

    except asyncio.CancelledError:
        print('Client service cancelled.')
        context.destroy()
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

def run_server():
    asyncio.run(server())

async def interruptor(n : float, src : str):
    try:
        print(f'{src}: interruptor waiting for {n} [s]...')
        await asyncio.sleep(n, src)
        print(f'{src}: INTERRUPTOR TRIGGERED!')
    except asyncio.CancelledError:
        print(f'{src}: interruptor interrupted.')
        return

def run_interruptor(n : float, src : str):
    asyncio.run(interruptor(n, src))

async def server_main():
    print('SERVER: START')

    t1 = asyncio.create_task(server(), name='server')
    # t2 = asyncio.create_task(interruptor(10, 'SERVER'), name='interruptor')

    done, pending = await asyncio.wait([t1], return_when=asyncio.FIRST_COMPLETED)

    for task in done:
        task : asyncio.Task
        print(f'SERVER: {task.get_name()} completed!')

    for task in pending:
        task : asyncio.Task
        print(f'SERVER: cancelling {task.get_name()}...')
        task.cancel()
        await task
        print(f'SERVER: {task.get_name()} cancelled!')

    # pool = mp.Pool()
    
    # pool.apply_async(run_server, args = ())
    # pool.apply(run_interruptor, args = (10, 'SERVER'))

    # pool.terminate()
    # pool.join()   

    print('SERVER: DONE')

def server_run():
    asyncio.run(server_main())

def client_run():
    print('CLIENT: START')

    pool = mp.Pool(processes=4)
    
    pool.apply_async(tough_process, args = (10000000, ))
    pool.apply_async(tough_process, args = (10000000, ))
    pool.apply_async(run_client, args = ())
    pool.apply(run_interruptor, args = (10, 'CLIENT'))

    pool.terminate()
    pool.join()   

    print('CLIENT: DONE')

if __name__ == "__main__":
    # goal: show that listening and actions occur in parallel           
    p1 = Process(target=client_run)
    p2 = Process(target=server_run)  

    p1.start()
    p2.start()


# def server():
#     print('SERVER START')

#     context = zmq.Context()
#     socket = context.socket(zmq.REP)
#     socket.bind("tcp://*:5555")

#     m = 0
#     while m < 10:
#         #  Wait for next request from client
#         print('SERVER: waiting on message...')
#         dst, content = socket.recv_multipart()
#         dst = dst.decode('ascii')
#         content = json.loads(content.decode('ascii'))
#         src : str = content['src']
#         print(f"SERVER: Received request from {src}: {content}")

#         #  Do some 'work'
#         await asyncio.sleep(0.5)

#         #  Send reply back to client
#         src : str = content['src']
#         resp : str = 'hello!'
#         socket.send_multipart([src.encode('ascii'), resp.encode('ascii')])

#         m += 1
    
#     print('SERVER DONE')


# if __name__ == "__main__":
#     # goal: show that listening and actions occur in parallel           
#     p1 = Process(target=client_run)
#     p2 = Process(target=server_run)  

#     p1.start()
#     p2.start()