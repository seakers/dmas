
import asyncio
import time
import json
import zmq
import zmq.asyncio as azmq

async def server():
    try:
        print("SERVER: creating to hello world server socket...") 
        context = azmq.Context()
        socket = context.socket(zmq.ROUTER)
        socket.bind("tcp://*:5556")        
        print("SERVER: socket established!") 

        m = 0
        while m < 10:
            #  Wait for next request from client
            print('SERVER: waiting on message...')
            msg = await socket.recv_multipart()
            print(msg)
            for m in msg:
                print(m.decode('ascii'))
            # dst, content = await socket.recv_multipart()
            dst = dst.decode('ascii')
            content = json.loads(content.decode('ascii'))
            src : str = content['src']
            print(f"SERVER: Received request from {src}: {content}")

            #  Do some 'work'
            await asyncio.sleep(0.5)

            #  Send reply back to client
            # src : str = content['src']
            # resp : str = 'hello!'
            # socket.send_multipart([src.encode('ascii'), resp.encode('ascii')])

            m += 1
        
        print('SERVER: finished receving messages.')

    except asyncio.CancelledError:
        print ('SERVER: listnening INTERRUPTED')
        return
    
    finally:
        context.destroy()

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
            # src, content = await socket.recv_multipart()
            # src : bytes; content : bytes

            # t_f = time.perf_counter()
            # src = src.decode('ascii')
            # content = content.decode('ascii')
                            
            # print(f"CLIENT: Received reply from {dst} at {t_f - t_o} [s]: {content}")

        context.destroy()
        print(f"CLIENT: finished sending messages to the server.")

    except asyncio.CancelledError:
        print('Client service cancelled.')
        context.destroy()
        return

async def main():
    tasks = [asyncio.create_task(server()), asyncio.create_task(client())]
    await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)

if __name__ == '__main__':
    asyncio.run(main())