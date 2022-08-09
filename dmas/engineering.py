import json

class EngineeringModule:
    def __init__(self) -> None:
        pass

class NetworkSimulator:
    def __init__(self) -> None:
        pass

    async def message_handler(self):
        while True:
            socks = dict(self.poller.poll())                

            if self.environment_broadcast_socket in socks:
                msg_string = self.environment_broadcast_socket.recv_json()
                msg_dict = json.loads(msg_string)

                src = msg_dict['src']
                dst = msg_dict['dst']
                msg_type = msg_dict['@type']
                t_server = msg_dict['server_clock']

                self.message_logger.info(f'Received message of type {msg_type} from {src} intended for {dst} with server time of t={t_server}!')
                self.state_logger.info(f'Received message of type {msg_type} from {src} intended for {dst} with server time of t={t_server}!')

                if msg_type == 'END':
                    self.state_logger.info(f'Sim has ended.')
                    
                    # send a reception confirmation
                    self.request_logger.info('Connection to environment established!')
                    self.environment_request_socket.send_string(self.name)
                    self.request_logger.info('Agent termination aknowledgement sent. Awaiting environment response...')

                    # wait for server reply
                    self.environment_request_socket.recv() 
                    self.request_logger.info('Response received! terminating agent.')
                    return

                elif msg_type == 'tic':
                    self.message_logger.info(f'Updating internal clock.')

class PlatformSimulator:
    def __init__(self) -> None:
        pass

class OperationsPlanner:
    def __init__(self) -> None:
        pass

class 
