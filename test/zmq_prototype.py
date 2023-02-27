
import asyncio
import time
import json
import zmq
import zmq.asyncio as azmq

class Subscriber(object):
    def __init__(self, name, id) -> None:
        self.scenario = name
        self.name = name + f'/subscriber_{id}'
        self.sub_id = id

    async def routine(self):
        try:
            print(f"SUB_{self.sub_id}: creating to hello world server socket...") 
            context = azmq.Context()
            socket = context.socket(zmq.SUB)
            socket.connect("tcp://localhost:5556")      
            socket.setsockopt(zmq.SUBSCRIBE, self.scenario.encode('ascii'))  
            # socket.setsockopt(zmq.SUBSCRIBE, self.name.encode('ascii'))  
            print(f"SUB_{self.sub_id}: socket established! subscribed to topic {self.name.encode('ascii')}") 

            for _ in range(9):
                #  Wait for next request from client
                print(f'SUB_{self.sub_id}: waiting on message...')

                dst, content = await socket.recv_multipart()

                # dst, content = await socket.recv_multipart()
                dst = dst.decode('ascii')
                content = json.loads(content.decode('ascii'))
                src : str = content['src']
                print(f"SUB_{self.sub_id}: Received message from {src}: {content}")

                #  Do some 'work'
                await asyncio.sleep(0.5)
            
            print(f'SUB_{self.sub_id}: finished receving messages.')

        except asyncio.CancelledError:
            print (f'SUB_{self.sub_id}: listnening INTERRUPTED')
            return
        
        finally:
            context.destroy()

    def run(self):
        asyncio.run(self.routine())    

class Publisher(object):
    def __init__(self, name) -> None:
        self.name = name

    async def routine(self):
        try:
            print("PUB: Connecting to hello world server...") 
            context = azmq.Context()
            socket = context.socket(zmq.PUB)
            socket.bind("tcp://*:5556")
            print("PUB: Connection established!") 

            for _ in range(3):
                dst : str = self.name
                content_dict = dict()
                content_dict['src'] = self.name
                content_dict['dst'] = dst
                content_dict['@type'] = 'HELLO WORLD'
                content : str = str(json.dumps(content_dict))

                print(f"PUB: sending message to {dst}...")
                await socket.send_multipart([dst.encode('ascii'), content.encode('ascii')])
                print(f"PUB: message sent! waiting to send the next message...")

                await asyncio.sleep(0.5)

                dst : str = self.name + '/subscriber_0' 
                content_dict['dst'] =  dst 
                content : str = str(json.dumps(content_dict))

                print(f"PUB: sending message to {dst}...")
                await socket.send_multipart([dst.encode('ascii'), content.encode('ascii')])
                print(f"PUB: message sent! waiting to send the next message...")

                await asyncio.sleep(0.5)

                dst : str = self.name + '/subscriber_1' 
                content_dict['dst'] =  dst 
                content : str = str(json.dumps(content_dict))

                print(f"PUB: sending message to {dst}...")
                await socket.send_multipart([dst.encode('ascii'), content.encode('ascii')])
                print(f"PUB: message sent! waiting to send the next message...")

                await asyncio.sleep(0.5)

            print(f'PUB: finished sending messages.')

        except asyncio.CancelledError:
            print (f'PUB: broadcasts INTERRUPTED')
            return
        
        finally:
            context.destroy()

    def run(self):
        asyncio.run(self.routine())   

# async def server():
#     try:
#         print("SERVER: creating to hello world server socket...") 
#         context = azmq.Context()
#         socket = context.socket(zmq.ROUTER)
#         socket.bind("tcp://*:5556")        
#         print("SERVER: socket established!") 

#         m = 0
#         while m < 10:
#             #  Wait for next request from client
#             print('SERVER: waiting on message...')
#             msg = await socket.recv_multipart()
#             print(msg)
#             for m in msg:
#                 print(m.decode('ascii'))
#             # dst, content = await socket.recv_multipart()
#             dst = dst.decode('ascii')
#             content = json.loads(content.decode('ascii'))
#             src : str = content['src']
#             print(f"SERVER: Received request from {src}: {content}")

#             #  Do some 'work'
#             await asyncio.sleep(0.5)

#             #  Send reply back to client
#             # src : str = content['src']
#             # resp : str = 'hello!'
#             # socket.send_multipart([src.encode('ascii'), resp.encode('ascii')])

#             m += 1
        
#         print('SERVER: finished receving messages.')

#     except asyncio.CancelledError:
#         print ('SERVER: listnening INTERRUPTED')
#         return
    
#     finally:
#         context.destroy()

# async def client():
#     try:
        # print("CLIENT: Connecting to hello world server...") 
        # context = azmq.Context()
        # socket = context.socket(zmq.REQ)
        # socket.connect("tcp://localhost:5556")
        # print("CLIENT: Connection established!") 

        #  Do 10 requests, waiting each time for a response
        # t_o = time.perf_counter()
        # for _ in range(10):
        #     dst : str = 'SERVER'
        #     content_dict = dict()
        #     content_dict['src'] = 'CLIENT'
        #     content_dict['dst'] = 'SERVER'
        #     content_dict['@type'] = 'HELLO WORLD'
        #     content : str = str(json.dumps(content_dict))

        #     print(f"CLIENT: sending message to {dst}...")
        #     await socket.send_multipart([dst.encode('ascii'), content.encode('ascii')])
        #     print(f"CLIENT: message sent! waiting for reply from {dst}...")

            #  Get the reply.
            # src, content = await socket.recv_multipart()
            # src : bytes; content : bytes

            # t_f = time.perf_counter()
            # src = src.decode('ascii')
            # content = content.decode('ascii')
                            
            # print(f"CLIENT: Received reply from {dst} at {t_f - t_o} [s]: {content}")

#         context.destroy()
#         print(f"CLIENT: finished sending messages to the server.")

#     except asyncio.CancelledError:
#         print('Client service cancelled.')
#         context.destroy()
#         return

async def main():
    # tasks = [asyncio.create_task(server()), asyncio.create_task(client())]

    name = 'TEST'
    publisher = Publisher(name)
    subscribers = []
    for i in range(1):
        subscribers.append(Subscriber(name, i+1))
    
    tasks = []
    for subscriber in subscribers:
        subscriber : Subscriber
        tasks.append(asyncio.create_task(subscriber.routine()))
    tasks.append(asyncio.create_task(publisher.routine()))

    await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)

if __name__ == '__main__':
    asyncio.run(main())