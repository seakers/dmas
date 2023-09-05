
import asyncio
import time
import json
import zmq
import zmq.asyncio as azmq

class Subscriber(object):
    def __init__(self, name : str, id : int) -> None:
        self.scenario: str = name
        self.name : str = name + f'/subscriber_{id}'
        self.sub_id : int = id
        self.inbox = asyncio.Queue()

    async def listener(self):
        try:
            while True:
                #  Wait for next request from client
                print(f'SUB_{self.sub_id}_LISTENER: waiting on message...')

                dst, content = await self.socket.recv_multipart()

                # dst, content = await socket.recv_multipart()
                dst = dst.decode('ascii')
                content = json.loads(content.decode('ascii'))
                src : str = content['src']
                print(f"SUB_{self.sub_id}_LISTENER: Received message from {src}: {content}")

                #  send to handler
                await self.inbox.put(content)
            
        except asyncio.CancelledError:
            print (f'SUB_{self.sub_id}_LISTENER: listnening INTERRUPTED')
            return
        
        finally:
            print(f'SUB_{self.sub_id}_LISTENER: finished receving messages.')

    async def handler(self):
        try:
            for _ in range(5):
                # wait for message to be read
                print (f'SUB_{self.sub_id}_HANDLER: waiting to handle message...')
                content = await self.inbox.get()
                print (f'SUB_{self.sub_id}_HANDLER: handling message {content}')

                # do some work
                await asyncio.sleep(0.5)
                print (f'SUB_{self.sub_id}_HANDLER: message handled!')
            
            # disconnect socket
            print (f'SUB_{self.sub_id}_HANDLER: disconnecting from subscriber...')
            self.socket.disconnect("tcp://localhost:5556")      
            print (f'SUB_{self.sub_id}_HANDLER: disconnected!')

        except asyncio.CancelledError:
            print (f'SUB_{self.sub_id}: handler INTERRUPTED')
            return

    async def routine(self):
        try:
            print(f"SUB_{self.sub_id}: creating to hello world server socket...") 
            self.context = azmq.Context()
            self.socket = self.context.socket(zmq.SUB)
            self.socket.connect("tcp://localhost:5556")      
            self.socket.setsockopt(zmq.SUBSCRIBE, self.scenario.encode('ascii')) 
            print(f"SUB_{self.sub_id}: socket established! subscribed to topic {self.name.encode('ascii')}") 

            t_1 = asyncio.create_task(self.listener())
            t_2 = asyncio.create_task(self.handler())

            _, pending = await asyncio.wait([t_1, t_2], return_when=asyncio.FIRST_COMPLETED)

            for task in pending:
                task : asyncio.Task
                task.cancel()
                await task

            # for _ in range(9):
            #     #  Wait for next request from client
            #     print(f'SUB_{self.sub_id}: waiting on message...')

            #     dst, content = await socket.recv_multipart()

            #     # dst, content = await socket.recv_multipart()
            #     dst = dst.decode('ascii')
            #     content = json.loads(content.decode('ascii'))
            #     src : str = content['src']
            #     print(f"SUB_{self.sub_id}: Received message from {src}: {content}")

            #     #  Do some 'work'
            #     await asyncio.sleep(0.5)
            
            # print(f'SUB_{self.sub_id}: finished receving messages.')

        except asyncio.CancelledError:
            print (f'SUB_{self.sub_id}: routine INTERRUPTED')
            return
        
        finally:
            self.context.destroy()

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

async def main():
    name = 'TEST'
    n_sub = 1

    publisher = Publisher(name)
    subscribers = []
    for i in range(n_sub):
        subscribers.append(Subscriber(name, i+1))
    
    tasks = []
    for subscriber in subscribers:
        subscriber : Subscriber
        tasks.append(asyncio.create_task(subscriber.routine()))
    tasks.append(asyncio.create_task(publisher.routine()))

    await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)

if __name__ == '__main__':
    asyncio.run(main())