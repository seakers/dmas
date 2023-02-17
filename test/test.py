from abc import ABC, abstractmethod
import json
import uuid
import zmq



if __name__ == '__main__':
    d = dict()
    d['list'] = [1, 2, 3]

    print(json.dumps(d))