import asyncio
from typing import Union
import zmq
from zmq import asyncio as azmq

async def server(port : int, n_clients : int, t : Union[float, int]):
    try:
        context = azmq.Context()
        socket = context.socket(zmq.ROUTER)
        socket.bind(f'tcp://*:{port}')
        print(f't={0} | SERVER: sockets initiated!')

        for i in range(t+1):
            reqs = {}
            while len(reqs) < n_clients:
                print(f't={i} | SERVER: listening for messages...')
                msg = await socket.recv_multipart()
                print(f't={i} | SERVER: received a message {msg}')
                address, gap, dst, src, content = msg
                address : bytes; gap : bytes; src : bytes; dst : bytes; content : bytes

                print(f't={i} | SERVER: unpacking contents [{address}, {gap}, {dst}, {src}, {content}]')
                
                if src not in reqs :
                    reqs[src] = address

            print(f't={i} | SERVER: received request from all clients! responding to every client...')

            for dst in reqs:
                dst : bytes
                src : bytes = b'SERVER'
                address : bytes = reqs[dst]

                content : bytes = b'Hello!'
                print(f't={i} | SERVER: responding to {dst} with message `{content}`...')

                msg = [     address,
                            gap,
                            dst,
                            src,
                            content
                            ]
                print(msg)
                await socket.send_multipart(msg) 

    finally:
        socket.close()
        context.term()

async def client(id : int, port : int, t : Union[float, int]):
    try:
        name = f'CLIENT_{id}'
        context = azmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect(f'tcp://localhost:{port}')
        print(f't={0} | {name}: sockets initiated!')

        for i in range(t+1):
            dst : str = 'SERVER'
            src : str = name

            content : str = f'Hello {dst}!'
            print(f't={i} | {name}: sending message `{content}`')

            await socket.send_multipart([   dst.encode('ascii'), 
                                            src.encode('ascii'), 
                                            content.encode('ascii')])
            print(f't={i} | {name}: message sent! waiting on response...')
            
            resp = await socket.recv_multipart()
            print(f't={i} | {name}: received response `{resp}`!')
    finally:
        socket.close()
        context.term()

async def main():
    try:
        port = 5556
        n_clients = 1
        t = 3

        tasks = [asyncio.create_task(server(port, n_clients, t))]
        for id in range(n_clients):
            tasks.append(asyncio.create_task(client(id, port, t)))

        print('')
        await asyncio.wait(tasks)

    finally:
        for task in tasks:
            task : asyncio.Task
            if not task.done():
                task.cancel()
                await task

if __name__ == '__main__':
    asyncio.run(main())