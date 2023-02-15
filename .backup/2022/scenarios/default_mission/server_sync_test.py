#
#  Synchronized subscriber
#
from multiprocessing import Process
import time
import zmq

def is_port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

class Server:
    def main(self):
        SUBSCRIBERS_EXPECTED = 1

        context = zmq.Context()

        # Socket to talk to clients
        publisher = context.socket(zmq.PUB)
        # set SNDHWM, so we don't drop messages for slow subscribers
        publisher.sndhwm = 1100000
        publisher.bind("tcp://*:5561")

        # Socket to receive signals
        syncservice = context.socket(zmq.REP)
        syncservice.bind("tcp://*:5562")

        # Get synchronization from subscribers
        subscribers = 0
        while subscribers < SUBSCRIBERS_EXPECTED:
            # wait for synchronization request
            msg = syncservice.recv()
            # send synchronization reply
            syncservice.send(b'')
            subscribers += 1
            print(f"+1 subscriber ({subscribers}/{SUBSCRIBERS_EXPECTED})")

        # Now broadcast exactly 1M updates followed by END
        for i in range(1000000):
            publisher.send(b"Rhubarb")

        publisher.send(b"END")

        publisher.close()
        syncservice.close()
        context.term()

class Client:
    def main(self):
        context = zmq.Context()

        # First, connect our subscriber socket
        subscriber = context.socket(zmq.SUB)
        subscriber.connect("tcp://localhost:5561")
        subscriber.setsockopt(zmq.SUBSCRIBE, b'')

        time.sleep(1)

        # Second, synchronize with publisher
        syncclient = context.socket(zmq.REQ)
        syncclient.connect("tcp://localhost:5562")

        # send a synchronization request
        syncclient.send(b'')

        # wait for synchronization reply
        syncclient.recv()

        # Third, get our updates and report how many we got
        nbr = 0
        while True:
            msg = subscriber.recv()
            if msg == b"END":
                break
            nbr += 1

        print(f"Received {nbr} updates")

        subscriber.close()
        syncclient.close()
        context.term()



if __name__ == "__main__":
    clients = [Client() for _ in range(1)]
    server = Server()

    server_prcs = Process(target=server.main)
    client_prcs = [Process(target=client.main) for client in clients]
    
    server_prcs.start()
    for prcs in client_prcs:
        prcs.start()

    server_prcs.join()
    for prcs in client_prcs:
        prcs.join()